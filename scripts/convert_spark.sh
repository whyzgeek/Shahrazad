#!/bin/bash
# Converts Spark's language model to GGUF for llama-server. Must be BF16: an F16 conversion returns NaN predictions.
# Needs LLAMA_CPP_DIR (a llama.cpp source checkout) in .env.
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a
M=${SHAHRAZAD_MODELS:-./models}; V=${VENV_SPARK:-.venv-spark}
[ -d "$LLAMA_CPP_DIR" ] || { echo "Set LLAMA_CPP_DIR in .env"; exit 1; }
mkdir -p "$M/spark-gguf"
timeout 1800 "$V/bin/python" "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" "$M/spark/LLM" --outtype bf16 --outfile "$M/spark-gguf/spark-llm-BF16.gguf"
