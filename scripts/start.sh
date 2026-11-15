#!/bin/bash
# Starts Shahrazad: the local model processes it needs, then the tutor. Each stops by itself after TUTOR_MAX_HOURS (default 8; 0 means never).
# Settings come from .env. A part set to cloud (SHAHRAZAD_BRAIN, SHAHRAZAD_HEARING, SHAHRAZAD_VOICE) starts nothing locally.
# Usage: scripts/start.sh
cd "$(dirname "$0")/.." || exit 1
. scripts/ui.sh
[ -f .env ] || die "there is no .env file. Run ./install.sh, or copy .env.example to .env and fill it in."
set -a; . ./.env; set +a
: "${SHAHRAZAD_MODELS:=./models}" "${LLAMA_SERVER:=llama-server}" "${VENV_TUTOR:=.venv-tutor}" "${VENV_SPARK:=.venv-spark}" "${VENV_VOXTRAL:=.venv-voxtral}"
: "${GPU_LLM:=0}" "${GPU_ASR:=1}" "${GPU_VOICE:=$GPU_LLM}" "${GEMMA_CPU_MOE:=16}" "${VOXTRAL_GPU_FRACTION:=0.91}" "${TUTOR_HOST:=127.0.0.1}"
: "${VOXTRAL_PORT:=18098}" "${GEMMA_PORT:=18099}" "${SPARK_LM_PORT:=18097}" "${SPARK_PORT:=18096}" "${TUTOR_PORT:=8791}"
: "${SHAHRAZAD_BRAIN:=local}" "${SHAHRAZAD_HEARING:=local}" "${SHAHRAZAD_VOICE:=local}" "${TUTOR_MAX_HOURS:=8}"
export SHAHRAZAD_MODELS VOXTRAL_PORT GEMMA_PORT SPARK_LM_PORT SPARK_PORT TUTOR_PORT SHAHRAZAD_BRAIN SHAHRAZAD_HEARING SHAHRAZAD_VOICE
case "$SHAHRAZAD_BRAIN$SHAHRAZAD_HEARING$SHAHRAZAD_VOICE" in *cloud*) [ -n "$OPENROUTER_API_KEY" ] || die "a part is set to cloud, so OPENROUTER_API_KEY must be set in .env.";; esac
if [ "$SHAHRAZAD_VOICE" = local ] && ! [ -f "${SHAHRAZAD_REF_AUDIO:-}" ]; then
  die "SHAHRAZAD_REF_AUDIO in .env must point to a voice clip. The default is assets/default_voice.wav."
fi
LIFE=$(( TUTOR_MAX_HOURS * 3600 )); R=run; mkdir -p "$R" data; M=$SHAHRAZAD_MODELS; T0=$SECONDS
SCHEME=http; [ -n "${TUTOR_SSL_CERT:-}" ] && SCHEME=https
URL="$SCHEME://$TUTOR_HOST:$TUTOR_PORT"

# ---------------------------------------------------------------- helpers
is_up(){ [ "$(timeout 3 curl -k -s -o /dev/null "$1" -w '%{http_code}')" = 200 ]; }
port_of(){ local p=${1##*:}; echo "${p%%/*}"; }
port_owner(){ ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*",pid=[0-9]*' | head -1 | sed 's/users:(("\(.*\)",pid=\(.*\)/\1 (PID \2)/'; }
# The part of Shahrazad a process belongs to (by the process group start() gave it), or nothing for another program.
part_of(){ local g f; g=$(ps -o pgid= -p "$1" 2>/dev/null | tr -d ' '); [ -n "$g" ] || return
  for f in "$R"/*.pid; do [ -f "$f" ] && [ "$(cat "$f")" = "$g" ] && { label "$(basename "$f" .pid)"; return; }; done; }
gb(){ awk -v m="$1" 'BEGIN{printf "%.1f", m/1024}'; }   # MiB -> GB
gpu_name(){ nvidia-smi -i "$1" --query-gpu=name --format=csv,noheader 2>/dev/null | sed 's/NVIDIA //;s/GeForce //'; }

# Each GPU's free memory, and every program holding some of it.
gpu_users(){ local gpu=$1 uuid
  uuid=$(nvidia-smi -i "$gpu" --query-gpu=uuid --format=csv,noheader 2>/dev/null)
  nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader,nounits 2>/dev/null | while IFS=', ' read -r u pid mib; do
    [ "$u" = "$uuid" ] || continue
    local part; part=$(part_of "$pid")
    if [ -n "$part" ]; then info "$(gb "$mib") GB  $part"
    else info "$(gb "$mib") GB  another program: $(ps -o args= -p "$pid" 2>/dev/null | cut -c1-90) (PID $pid)"; fi
  done; }
gpu_report(){ local idx used total
  command -v nvidia-smi >/dev/null || { warn "nvidia-smi not found, so GPU memory can't be shown"; return; }
  while IFS=', ' read -r idx used total; do
    printf '   GPU %s  %-14s %s of %s GB free\n' "$idx" "$(gpu_name "$idx")" "$(gb $((total - used)))" "$(gb "$total")"
    gpu_users "$idx"
  done < <(nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits)
}

# Why a process failed, in plain words, from the end of its log. Then stop.
fail(){ local name=$1 gpus=$2 port=$3 log="$R/$1.log" what; what=$(label "$1")
  progress_end
  if grep -q -i -E 'Free memory on device|out of memory|cudaMalloc failed|failed to allocate|CUDA_ERROR_OUT_OF_MEMORY' "$log"; then
    printf '   %s✗%s %s: not enough free GPU memory.\n' "$RED" "$RESET" "$what"
    for g in ${gpus//,/ }; do gpu_report_one "$g"; done
    die "free some GPU memory (close or unload the other program shown above), then run scripts/start.sh again."
  elif grep -q 'Address already in use' "$log"; then
    printf '   %s✗%s %s: port %s is taken by %s.\n' "$RED" "$RESET" "$what" "$port" "$(port_owner "$port")"
    die "stop that program, or choose another port in .env, then run scripts/start.sh again."
  elif grep -q -E 'No such file or directory|does not exist|failed to load model' "$log"; then
    printf '   %s✗%s %s: a file it needs is missing.\n' "$RED" "$RESET" "$what"
    grep -h -m2 -E 'No such file or directory|does not exist|failed to load model' "$log" | cut -c1-200 | while read -r l; do info "$l"; done
    die "run ./install.sh to download what's missing."
  fi
  printf '   %s✗%s %s stopped while starting. The end of its log (%s):\n' "$RED" "$RESET" "$what" "$log"
  grep -v '^\s*$' "$log" | grep -i -E 'error|exception|failed|abort' | tail -3 | cut -c1-200 | while read -r l; do info "$l"; done
  die "see $log for the details."
}
gpu_report_one(){ local used total
  IFS=', ' read -r used total < <(nvidia-smi -i "$1" --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null)
  [ -n "$total" ] && printf '     GPU %s has %s of %s GB free. Using it:\n' "$1" "$(gb $((total - used)))" "$(gb "$total")"
  gpu_users "$1"; }

# start NAME HEALTH_URL GPUS COMMAND...: runs one process on the given GPUs, stopped after TUTOR_MAX_HOURS, and waits
# until it answers, up to 5 minutes. One already answering is kept.
start(){ local name=$1 url=$2 gpus=$3 what where; shift 3
  what=$(label "$name"); where=${gpus:+ on GPU $gpus}
  if is_up "$url"; then ok "$what: already running"; return 0; fi
  local port; port=$(port_of "$url")
  if ss -ltnH "sport = :$port" 2>/dev/null | grep -q .; then
    printf '   %s✗%s %s: port %s is already taken by %s.\n' "$RED" "$RESET" "$what" "$port" "$(port_owner "$port")"
    die "stop that program, or choose another port in .env, then run scripts/start.sh again."
  fi
  # Fresh PyTorch processes occasionally die with "Illegal instruction" on CPUs without AVX2; only that is worth a retry.
  for attempt in 1 2 3; do
    CUDA_VISIBLE_DEVICES=$gpus HF_HUB_OFFLINE=1 setsid nohup timeout "$LIFE" "$@" > "$R/$name.log" 2>&1 &
    local pid=$! t=$SECONDS; echo "$pid" > "$R/$name.pid"
    while [ $((SECONDS - t)) -lt 300 ]; do
      progress "$what: loading$where, $(duration $((SECONDS - t)))"
      if is_up "$url"; then progress_end; ok "$what: ready$where ($(duration $((SECONDS - t))))"; return 0; fi
      kill -0 "$pid" 2>/dev/null || break
      sleep 2
    done
    if kill -0 "$pid" 2>/dev/null; then
      progress_end; die "$what is still loading after 5 minutes but doesn't answer. See $R/$name.log."
    fi
    if grep -q 'Illegal instruction' "$R/$name.log" && [ "$attempt" -lt 3 ]; then
      progress_end; warn "$what crashed while starting (an occasional PyTorch crash on this CPU). Trying again."
      continue
    fi
    rm -f "$R/$name.pid"; fail "$name" "$gpus" "$port"
  done
  rm -f "$R/$name.pid"; fail "$name" "$gpus" "$port"
}
health(){ echo "http://127.0.0.1:$1/health"; }
where(){ [ "$1" = cloud ] && echo "in the cloud (OpenRouter)" || echo "on this computer, GPU $2"; }

# ---------------------------------------------------------------- start
step "Starting Shahrazad"
printf '   Brain    Gemma 4, %s\n' "$(where "$SHAHRAZAD_BRAIN" "$GPU_LLM")"
printf '   Hearing  Voxtral, %s\n' "$(where "$SHAHRAZAD_HEARING" "$GPU_ASR")"
printf '   Voice    Spark, %s\n' "$(where "$SHAHRAZAD_VOICE" "$GPU_VOICE")"
if [ "$TUTOR_MAX_HOURS" -gt 0 ] 2>/dev/null; then
  info "Everything stops by itself at $(date -d "+$TUTOR_MAX_HOURS hours" +%H:%M) (after $TUTOR_MAX_HOURS hours; TUTOR_MAX_HOURS in .env, 0 = never)."
fi

if [ "$SHAHRAZAD_BRAIN$SHAHRAZAD_HEARING$SHAHRAZAD_VOICE" != cloudcloudcloud ]; then
  step "GPU memory before starting"
  gpu_report
fi

step "Loading the models"
# Hearing: Voxtral on vLLM. Session length 1024 tokens = 82 s, which is what lets it fit in 12 GB.
if [ "$SHAHRAZAD_HEARING" = local ]; then
  PATH="$VENV_VOXTRAL/bin:$PATH" VLLM_DISABLE_COMPILE_CACHE=1 VLLM_USE_FLASHINFER_SAMPLER=0 \
    start voxtral "$(health "$VOXTRAL_PORT")" "$GPU_ASR" "$VENV_VOXTRAL/bin/vllm" serve "$M/voxtral-ar" --host 127.0.0.1 --port "$VOXTRAL_PORT" --served-model-name voxtral-ar \
    --tokenizer-mode mistral --config-format mistral --load-format mistral --max-model-len 1024 --max-num-seqs 1 \
    --gpu-memory-utilization "$VOXTRAL_GPU_FRACTION" --compilation_config '{"cudagraph_mode":"PIECEWISE"}'
else ok "Hearing: in the cloud, nothing to load"; fi

# Voice: Spark's language model (BF16 GGUF only; F16 returns NaN), then its decoder service.
if [ "$SHAHRAZAD_VOICE" = local ]; then
  start sparklm "$(health "$SPARK_LM_PORT")" "$GPU_VOICE" "$LLAMA_SERVER" -m "$M/spark-gguf/spark-llm-BF16.gguf" --port "$SPARK_LM_PORT" --host 127.0.0.1 -ngl all -fa on -c 2048 --parallel 1
  start spark "$(health "$SPARK_PORT")" "$GPU_VOICE" "$VENV_SPARK/bin/python" -I spark_service.py
else ok "Voice: in the cloud, nothing to load"; fi

# Tutor and vowelling: Gemma 4 26B-A4B, started last, around the others. GEMMA_CPU_MOE of its expert layers run on the CPU.
if [ "$SHAHRAZAD_BRAIN" = local ]; then
  start gemma "$(health "$GEMMA_PORT")" "$GPU_LLM" "$LLAMA_SERVER" --port "$GEMMA_PORT" --host 127.0.0.1 \
    -m "$M/gemma4-26b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf" --model-draft "$M/gemma4-26b/MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf" \
    --spec-type draft-mtp --spec-draft-n-max 4 -ngl all -fa on --jinja -c 16384 -ctk q8_0 -ctv q8_0 --n-cpu-moe "$GEMMA_CPU_MOE" --reasoning off --parallel 2 -kvu --no-cache-idle-slots
else ok "Brain: in the cloud, nothing to load"; fi

step "Starting the tutor"
if [ "$SCHEME" = http ] && [ "$TUTOR_HOST" != 127.0.0.1 ] && [ "$TUTOR_HOST" != localhost ]; then
  warn "Browsers block the microphone on plain HTTP except on localhost. Run ./install.sh --lan to set up HTTPS."
fi
start app "$URL/" "" "$VENV_TUTOR/bin/python" app.py

# ---------------------------------------------------------------- summary
step "Shahrazad is ready ($(duration $((SECONDS - T0))))"
if h=$(timeout 5 curl -k -s "$URL/health"); then
  python3 -c '
import json, sys
names = {"brain": "Brain", "hearing": "Hearing", "voice": "Voice"}
for part, p in json.loads(sys.argv[1]).items():
    mark = "\033[32m✓\033[0m" if p["ok"] else "\033[31m✗\033[0m"
    if not sys.stdout.isatty(): mark = "ok" if p["ok"] else "NOT OK"
    where = " (cloud)" if p["mode"] == "cloud" else ""
    print("   " + mark + " " + names.get(part, part).ljust(8) + " " + p["name"] + where)' "$h"
fi
[ "$SHAHRAZAD_BRAIN$SHAHRAZAD_HEARING$SHAHRAZAD_VOICE" != cloudcloudcloud ] && { step "GPU memory now"; gpu_report; }
echo
printf '   Open %s%s%s in your browser.\n' "$BOLD" "$URL" "$RESET"
info "To stop: scripts/stop.sh     Logs: $R/*.log"
