#!/bin/bash
# Starts Shahrazad's five local processes. Each stops by itself after TUTOR_MAX_HOURS (default 8). Settings come from .env.
# Usage: scripts/start.sh
cd "$(dirname "$0")/.." || exit 1
[ -f .env ] || { echo "Missing .env: copy .env.example and fill it in."; exit 1; }
set -a; . ./.env; set +a
: "${SHAHRAZAD_MODELS:=./models}" "${LLAMA_SERVER:=llama-server}" "${VENV_TUTOR:=.venv-tutor}" "${VENV_SPARK:=.venv-spark}" "${VENV_VOXTRAL:=.venv-voxtral}"
: "${GPU_LLM:=0}" "${GPU_ASR:=1}" "${GPU_VOICE:=$GPU_LLM}" "${GEMMA_CPU_MOE:=16}" "${VOXTRAL_GPU_FRACTION:=0.91}" "${TUTOR_HOST:=127.0.0.1}"
: "${VOXTRAL_PORT:=18098}" "${GEMMA_PORT:=18099}" "${SPARK_LM_PORT:=18097}" "${SPARK_PORT:=18096}" "${TUTOR_PORT:=8791}"
export SHAHRAZAD_MODELS VOXTRAL_PORT GEMMA_PORT SPARK_LM_PORT SPARK_PORT TUTOR_PORT
[ -n "$SHAHRAZAD_REF_AUDIO" ] && [ -f "$SHAHRAZAD_REF_AUDIO" ] || { echo "SHAHRAZAD_REF_AUDIO must point to a voice clip. The default is assets/default_voice.wav."; exit 1; }
LIFE=$(( ${TUTOR_MAX_HOURS:-8} * 3600 )); R=run; mkdir -p "$R" data; M=$SHAHRAZAD_MODELS

is_up(){ [ "$(timeout 3 curl -k -s -o /dev/null "$1" -w '%{http_code}')" = 200 ]; }
wait_up(){ for _ in $(seq 1 100); do is_up "$1" && return 0; python3 -c "import time;time.sleep(3)"; done; echo "timed out waiting for $1"; exit 1; }
# Fresh PyTorch processes occasionally die with "Illegal instruction" on CPUs without AVX2, so this retries.
start_retry(){ local name=$1 url=$2; shift 2
  for attempt in 1 2 3 4; do
    setsid nohup "$@" > "$R/$name.log" 2>&1 &
    local pid=$!; echo "$pid" > "$R/$name.pid"
    for _ in $(seq 1 90); do
      is_up "$url" && return 0
      kill -0 "$pid" 2>/dev/null || { echo "$name attempt $attempt failed, retrying"; break; }
      python3 -c "import time;time.sleep(2)"
    done
  done
  echo "$name failed to start; see $R/$name.log"; exit 1
}

# Hearing: Voxtral on vLLM. Session length 1024 tokens = 82 s, which is what lets it fit in 12 GB.
if ! is_up "http://127.0.0.1:$VOXTRAL_PORT/health"; then
  PATH="$VENV_VOXTRAL/bin:$PATH" CUDA_VISIBLE_DEVICES=$GPU_ASR VLLM_DISABLE_COMPILE_CACHE=1 VLLM_USE_FLASHINFER_SAMPLER=0 \
    setsid nohup timeout $LIFE "$VENV_VOXTRAL/bin/vllm" serve "$M/voxtral-ar" --host 127.0.0.1 --port "$VOXTRAL_PORT" --served-model-name voxtral-ar \
    --tokenizer-mode mistral --config-format mistral --load-format mistral --max-model-len 1024 --max-num-seqs 1 \
    --gpu-memory-utilization "$VOXTRAL_GPU_FRACTION" --compilation_config '{"cudagraph_mode":"PIECEWISE"}' > "$R/voxtral.log" 2>&1 &
  echo $! > "$R/voxtral.pid"
fi
wait_up "http://127.0.0.1:$VOXTRAL_PORT/health"

# Tutor and vowelling: Gemma 4 26B-A4B. Part of its experts run on the CPU so everything fits.
CUDA_VISIBLE_DEVICES=$GPU_LLM setsid nohup timeout $LIFE "$LLAMA_SERVER" --port "$GEMMA_PORT" --host 127.0.0.1 \
  -m "$M/gemma4-26b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf" --model-draft "$M/gemma4-26b/MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf" \
  --spec-type draft-mtp --spec-draft-n-max 4 -ngl all -fa on --jinja -c 16384 -ctk q8_0 -ctv q8_0 --n-cpu-moe "$GEMMA_CPU_MOE" --reasoning off --parallel 2 -kvu --no-cache-idle-slots > "$R/gemma.log" 2>&1 &
echo $! > "$R/gemma.pid"
wait_up "http://127.0.0.1:$GEMMA_PORT/health"

# Voice: Spark's language model (BF16 GGUF only; F16 returns NaN), then its decoder service.
CUDA_VISIBLE_DEVICES=$GPU_VOICE setsid nohup timeout $LIFE "$LLAMA_SERVER" -m "$M/spark-gguf/spark-llm-BF16.gguf" --port "$SPARK_LM_PORT" --host 127.0.0.1 -ngl all -fa on -c 2048 --parallel 1 > "$R/sparklm.log" 2>&1 &
echo $! > "$R/sparklm.pid"
wait_up "http://127.0.0.1:$SPARK_LM_PORT/health"
HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=$GPU_VOICE start_retry spark "http://127.0.0.1:$SPARK_PORT/health" timeout $LIFE "$VENV_SPARK/bin/python" -I spark_service.py

SCHEME=http; [ -n "$TUTOR_SSL_CERT" ] && SCHEME=https
if [ "$SCHEME" = http ] && [ "$TUTOR_HOST" != 127.0.0.1 ] && [ "$TUTOR_HOST" != localhost ]; then
  echo "Warning: browsers block the microphone on plain HTTP outside localhost. Run ./install.sh --lan to set up HTTPS."
fi
start_retry app "$SCHEME://$TUTOR_HOST:$TUTOR_PORT/" timeout $LIFE "$VENV_TUTOR/bin/python" app.py
nvidia-smi --query-gpu=index,memory.free --format=csv,noheader
echo "Shahrazad is running at $SCHEME://$TUTOR_HOST:$TUTOR_PORT"
