#!/usr/bin/env bash
# Shahrazad's installer. It checks what this machine already has and does only what's missing, so it's safe to re-run.
#
#   ./install.sh                         # install for use on this computer
#   ./install.sh --lan                   # also serve over HTTPS on this computer's network address
#   ./install.sh --cloud all --key KEY   # no suitable GPU: run every part in the cloud through OpenRouter
#
# Options:
#   --cloud PARTS        run these parts in the cloud: all, or a list of brain, hearing, voice (e.g. --cloud hearing)
#   --local              run every part on this computer again
#   --key KEY            your OpenRouter API key, needed for any part in the cloud (https://openrouter.ai/keys)
#   --ref-audio FILE     use a different voice: a clear recording you have the right to use (WAV, 6-10 s)
#   --lan [IP]           serve on the network, with a self-signed certificate. Without an IP, it is detected.
#   --models DIR         where models live or should be downloaded (default ./models)
#   --llama-server FILE  use this llama-server build
#   --llama-cpp DIR      use this llama.cpp source folder for model conversion
#   --check              report what is present and missing, and change nothing
# If the hardware can't run a part, the installer stops and names the parts to move to the cloud.
set -u
cd "$(dirname "$0")" || exit 1

LLAMA_COMMIT=3f03b17724ad8b69040825f45c43c59b092a0244   # the llama.cpp version this project was tested with
REF="" LAN="" MODELS="" SERVER="" CPP="" CHECK=0 CLOUD="" KEY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --ref-audio) REF=${2:-}; shift 2 ;;
    --lan) if [[ ${2:-} =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then LAN=$2; shift 2; else LAN=auto; shift; fi ;;
    --models) MODELS=${2:-}; shift 2 ;;
    --llama-server) SERVER=${2:-}; shift 2 ;;
    --llama-cpp) CPP=${2:-}; shift 2 ;;
    --check) CHECK=1; shift ;;
    --cloud) CLOUD=${2:-}; shift 2 ;;
    --local) CLOUD=none; shift ;;
    --key) KEY=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see ./install.sh --help)"; exit 1 ;;
  esac
done

step(){ printf '\n== %s\n' "$*"; }
ok(){ printf '   ok: %s\n' "$*"; }
todo(){ printf '   needed: %s\n' "$*"; MISSING=$((MISSING + 1)); }
die(){ printf '\nStopped: %s\n' "$*"; exit 1; }
MISSING=0

env_get(){ [ -f .env ] && sed -n "s/^$1=//p" .env | tail -1; }
env_set(){ python3 - "$1" "$2" <<'PY'
import re, sys
from pathlib import Path
k, v = sys.argv[1:3]
p = Path(".env")
t = p.read_text()
t, n = re.subn(rf"^{re.escape(k)}=.*$", lambda _: f"{k}={v}", t, flags=re.M)
p.write_text(t if n else t.rstrip("\n") + f"\n{k}={v}\n")
PY
}
abs_path(){ python3 -c 'import os,sys;print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$1"; }

# ---------------------------------------------------------------- system
step "System"
[ "$(uname -s)" = Linux ] || die "Only Linux is supported for now."
packages=()
for tool in python3 curl git openssl; do command -v "$tool" >/dev/null || packages+=("$tool"); done
if command -v uv >/dev/null; then PY_TOOL=uv; ok "uv"
elif command -v python3.12 >/dev/null && python3.12 -c 'import venv, ensurepip' 2>/dev/null; then PY_TOOL=venv; ok "python3.12"
else PY_TOOL=""; packages+=(python3.12 python3.12-venv); fi
if command -v nvidia-smi >/dev/null; then
  ok "NVIDIA driver, CUDA $(nvidia-smi | grep -o 'CUDA Version: [0-9.]*' | grep -o '[0-9.]*$')"
else
  echo "   no NVIDIA driver found: only parts set to cloud can run on this computer"
fi
if [ ${#packages[@]} -gt 0 ]; then
  [ "$CHECK" = 1 ] && todo "system packages: ${packages[*]}" || die "Install these first: sudo apt install ${packages[*]}"
fi
free_gb=$(df -BG . | awk 'NR==2 {print $4+0}')

# ---------------------------------------------------------------- settings
step "Settings"
if [ ! -f .env ]; then
  if [ "$CHECK" = 1 ]; then todo ".env (will be created)"; else cp .env.example .env && ok "created .env"; fi
else ok ".env"; fi
if [ "$CHECK" = 0 ]; then
  [ -n "$MODELS" ] && env_set SHAHRAZAD_MODELS "$(abs_path "$MODELS")"
  [ -n "$SERVER" ] && env_set LLAMA_SERVER "$(abs_path "$SERVER")"
  [ -n "$CPP" ] && env_set LLAMA_CPP_DIR "$(abs_path "$CPP")"
  if [ -n "$CLOUD" ]; then
    for part in brain hearing voice; do
      mode=local; [[ $CLOUD == all || ,$CLOUD, == *,$part,* ]] && mode=cloud
      env_set "SHAHRAZAD_${part^^}" "$mode"
    done
  fi
  [ -n "$KEY" ] && { env_set OPENROUTER_API_KEY "$KEY"; chmod 600 .env; }
fi
mode_of(){ local v; v=$(env_get "SHAHRAZAD_${1^^}"); echo "${v:-local}"; }
if [ "$CHECK" = 1 ] && [ -n "$CLOUD" ]; then   # --check doesn't write .env, so use the options given
  mode_of(){ [[ $CLOUD == all || ,$CLOUD, == *,$1,* ]] && echo cloud || echo local; }
fi
BRAIN=$(mode_of brain) HEARING=$(mode_of hearing) VOICE=$(mode_of voice)
ok "parts: brain $BRAIN, hearing $HEARING, voice $VOICE"
if [[ "$BRAIN$HEARING$VOICE" == *cloud* ]]; then
  K=$KEY; [ -n "$K" ] || K=$(env_get OPENROUTER_API_KEY)
  if [ -z "$K" ]; then todo "an OpenRouter API key for the cloud parts: re-run with --key KEY (https://openrouter.ai/keys)"
  elif [ "$CHECK" = 0 ] && ! timeout 30 curl -sf -o /dev/null -H "Authorization: Bearer $K" https://openrouter.ai/api/v1/key; then
    todo "a working OpenRouter key: the one given was refused"
  else ok "OpenRouter key"; fi
fi
NEED_DISK_GB=2; [ "$HEARING" = local ] && NEED_DISK_GB=$((NEED_DISK_GB + 14)); [ "$BRAIN" = local ] && NEED_DISK_GB=$((NEED_DISK_GB + 16)); [ "$VOICE" = local ] && NEED_DISK_GB=$((NEED_DISK_GB + 13))
[ "$free_gb" -ge "$NEED_DISK_GB" ] && ok "$free_gb GB free" || echo "   warning: $free_gb GB free; this setup needs about $NEED_DISK_GB GB"

# ---------------------------------------------------------------- hardware
# Before any download, so nothing is fetched for a part this machine can't run.
step "Hardware"
if [ "$CHECK" = 1 ] && [ -n "$CLOUD" ]; then
  timeout 120 python3 -I scripts/configure.py --cloud "$CLOUD" || die "this machine can't run the local parts (see above)."
else
  timeout 120 python3 -I scripts/configure.py $([ "$CHECK" = 0 ] && echo --write) || die "this machine can't run the local parts (see above)."
fi
M=$(env_get SHAHRAZAD_MODELS); M=${M:-./models}
V_TUTOR=$(env_get VENV_TUTOR); V_TUTOR=${V_TUTOR:-.venv-tutor}
V_SPARK=$(env_get VENV_SPARK); V_SPARK=${V_SPARK:-.venv-spark}
V_VOX=$(env_get VENV_VOXTRAL); V_VOX=${V_VOX:-.venv-voxtral}

# ---------------------------------------------------------------- python environments
new_env(){ if [ "$PY_TOOL" = uv ]; then timeout 300 uv venv "$1" --python 3.12 -q; else timeout 300 python3.12 -m venv "$1"; fi; }
pip_in(){ local env=$1; shift
  if [ "$PY_TOOL" = uv ]; then timeout 3600 uv pip install -p "$env/bin/python" -q "$@"
  else timeout 3600 "$env/bin/pip" install -q "$@"; fi; }
setup_env(){ local env=$1 label=$2 probe=$3 reqs=$4 torch=${5:-}
  if [ -x "$env/bin/python" ] && "$env/bin/python" -I -c "$probe" >/dev/null 2>&1; then ok "$label environment"; return; fi
  [ "$CHECK" = 1 ] && { todo "$label environment"; return; }
  echo "   installing $label environment..."
  [ -x "$env/bin/python" ] || new_env "$env" || die "couldn't create $env"
  if [ -n "$torch" ]; then pip_in "$env" torch==2.8.0 torchaudio==2.8.0 --index-url "$torch" || die "couldn't install PyTorch for $label"; fi
  pip_in "$env" -r "$reqs" || die "couldn't install $label requirements"
  "$env/bin/python" -I -c "$probe" || die "$label environment doesn't work after installing"
  ok "$label environment"
}
step "Python environments"
setup_env "$V_TUTOR" tutor "import fastapi, uvicorn, httpx, websockets, mcp, yaml, yt_dlp, defusedxml, huggingface_hub" requirements/tutor.txt
[ "$VOICE" = local ] && setup_env "$V_SPARK" voice "import torch, transformers, einx, soxr, fastapi, yaml" requirements/spark.txt https://download.pytorch.org/whl/cu128
[ "$HEARING" = local ] && setup_env "$V_VOX" "speech recognition" "import vllm, mistral_common" requirements/voxtral.txt

# ---------------------------------------------------------------- llama.cpp
server_ok(){ [ -x "$1" ] || command -v "$1" >/dev/null || return 1
  local h; h=$(timeout 30 "$1" --help 2>&1); [[ $h == *draft-mtp* && $h == *cache-idle-slots* ]]; }
fetch_llama(){ local dir=third_party/llama.cpp
  [ -f "$dir/convert_hf_to_gguf.py" ] && return 0
  mkdir -p "$dir" && git -C "$dir" init -q && { git -C "$dir" remote add origin https://github.com/ggml-org/llama.cpp.git 2>/dev/null; true; }
  timeout 900 git -C "$dir" fetch -q --depth 1 origin "$LLAMA_COMMIT" && git -C "$dir" checkout -q FETCH_HEAD; }
if [ "$BRAIN" = local ] || [ "$VOICE" = local ]; then   # Gemma and Spark's language model run in llama-server
step "llama.cpp"
L=$(env_get LLAMA_SERVER); FOUND=""
for candidate in "$L" third_party/llama.cpp/build/bin/llama-server llama-server; do
  [ -n "$candidate" ] && server_ok "$candidate" && { FOUND=$candidate; break; }
done
if [ -n "$FOUND" ]; then ok "$FOUND"
elif [ "$CHECK" = 1 ]; then todo "llama-server (will be built from source)"
else
  missing=(); for t in cmake g++ nvcc; do command -v "$t" >/dev/null || missing+=("$t"); done
  [ ${#missing[@]} -eq 0 ] || die "No suitable llama-server, and building one needs: ${missing[*]} (on Ubuntu: sudo apt install cmake g++ and the NVIDIA CUDA toolkit), or pass --llama-server."
  echo "   no suitable llama-server found; building one (this takes several minutes)..."
  fetch_llama || die "couldn't download llama.cpp"
  timeout 600 cmake -S third_party/llama.cpp -B third_party/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TOOLS=ON >/dev/null || die "cmake configuration failed"
  timeout 7200 cmake --build third_party/llama.cpp/build --target llama-server -j "$(nproc)" >/dev/null || die "llama.cpp build failed"
  FOUND=third_party/llama.cpp/build/bin/llama-server
  server_ok "$FOUND" || die "the built llama-server lacks the features this project needs"
  ok "built $FOUND"
fi
if [ "$CHECK" = 0 ] && [ -n "$FOUND" ]; then
  case "$FOUND" in */*) env_set LLAMA_SERVER "$(abs_path "$FOUND")" ;; *) env_set LLAMA_SERVER "$FOUND" ;; esac
fi
fi

# ---------------------------------------------------------------- models
hf_get(){ local repo=$1 dest=$2; shift 2
  PATH="$(abs_path "$V_TUTOR")/bin:$PATH" timeout 14400 hf download "$repo" "$@" --local-dir "$dest" >/dev/null || die "download failed: $repo (re-run to resume)"; }
have(){ local f; for f in "$@"; do [ -s "$M/$f" ] || return 1; done; }
step "Models (in $M)"
if [ "$HEARING" = cloud ]; then ok "Voxtral not needed (hearing in the cloud)"
elif have voxtral-ar/consolidated.safetensors voxtral-ar/params.json voxtral-ar/tekken.json; then ok "Voxtral"
elif [ "$CHECK" = 1 ]; then todo "Voxtral, 8 GB"
else echo "   downloading Voxtral (8 GB)..."; hf_get mistralai/Voxtral-Mini-4B-Realtime-Arabic "$M/voxtral-ar" consolidated.safetensors params.json tekken.json config.json generation_config.json processor_config.json; ok "Voxtral"; fi
if [ "$BRAIN" = cloud ]; then ok "Gemma 4 not needed (brain in the cloud)"
elif have gemma4-26b/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf gemma4-26b/MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf; then ok "Gemma 4"
elif [ "$CHECK" = 1 ]; then todo "Gemma 4, 14 GB"
else echo "   downloading Gemma 4 (14 GB)..."; hf_get unsloth/gemma-4-26B-A4B-it-qat-GGUF "$M/gemma4-26b" gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf; ok "Gemma 4"; fi
if [ "$VOICE" = cloud ]; then ok "Spark not needed (voice in the cloud)"
elif have spark/LLM/model.safetensors spark/BiCodec/model.safetensors spark/wav2vec2-large-xlsr-53/pytorch_model.bin spark/modeling_spark_tts.py; then ok "Spark"
elif [ "$CHECK" = 1 ]; then todo "Spark, 3 GB"
else
  echo "   downloading Spark (3 GB). Its license is non-commercial: https://huggingface.co/IbrahimSalah/Arabic-TTS-Spark"
  hf_get IbrahimSalah/Arabic-TTS-Spark "$M/spark" --exclude "src/*"; ok "Spark"
fi
# Must be BF16: an F16 conversion returns NaN predictions.
if [ "$VOICE" = cloud ]; then :
elif have spark-gguf/spark-llm-BF16.gguf; then ok "Spark converted for llama.cpp"
elif [ "$CHECK" = 1 ]; then todo "Spark conversion"
else
  D=$(env_get LLAMA_CPP_DIR)
  if [ ! -f "${D:-/nonexistent}/convert_hf_to_gguf.py" ]; then
    echo "   fetching llama.cpp's conversion script..."
    fetch_llama || die "couldn't download llama.cpp"
    D=third_party/llama.cpp; env_set LLAMA_CPP_DIR "$(abs_path "$D")"
  fi
  mkdir -p "$M/spark-gguf"
  echo "   converting Spark..."
  timeout 1800 "$V_SPARK/bin/python" "$D/convert_hf_to_gguf.py" "$M/spark/LLM" --outtype bf16 --outfile "$M/spark-gguf/spark-llm-BF16.gguf" >/dev/null 2>&1 || die "Spark conversion failed"
  ok "Spark converted for llama.cpp"
fi

# ---------------------------------------------------------------- voice
if [ "$VOICE" = local ]; then
step "Reference voice"
[ "$CHECK" = 0 ] && [ -n "$REF" ] && { [ -f "$REF" ] || die "reference audio not found: $REF"; env_set SHAHRAZAD_REF_AUDIO "$(abs_path "$REF")"; }
R=$(env_get SHAHRAZAD_REF_AUDIO)
if [ -z "$R" ]; then R=assets/default_voice.wav; [ "$CHECK" = 0 ] && env_set SHAHRAZAD_REF_AUDIO "$R"; fi
if [ -f "$R" ]; then ok "$R"; else todo "the voice recording $R: re-run with --ref-audio FILE"; fi
fi

# ---------------------------------------------------------------- network
if [ -n "$LAN" ]; then
  step "Network"
  [ "$LAN" = auto ] && LAN=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+')
  [ -n "$LAN" ] || die "couldn't detect this computer's network address; pass it: --lan 192.168.1.50"
  if [ "$CHECK" = 1 ]; then
    ok "would serve on https://$LAN"
  else
    mkdir -p certs
    timeout 60 openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=shahrazad" -addext "subjectAltName=IP:$LAN" -keyout certs/key.pem -out certs/cert.pem 2>/dev/null || die "couldn't create a certificate"
    chmod 600 certs/key.pem
    env_set TUTOR_HOST "$LAN"; env_set TUTOR_SSL_CERT certs/cert.pem; env_set TUTOR_SSL_KEY certs/key.pem
    ok "https://$LAN (self-signed certificate). There is no login, so keep it on a network you trust."
  fi
fi

# ---------------------------------------------------------------- done
if [ "$CHECK" = 1 ]; then
  step "Check finished: $MISSING item(s) needed"
elif [ "$MISSING" -gt 0 ]; then
  step "Almost done: fix the item(s) marked 'needed' above, then re-run ./install.sh"
  exit 1
else
  step "Installed. Start the tutor with: scripts/start.sh"
fi
