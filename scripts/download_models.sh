#!/bin/bash
# Downloads the models from their original Hugging Face repositories into $SHAHRAZAD_MODELS (about 28 GB).
# Requires the `hf` CLI. Spark is non-commercial: read its license before using it.
cd "$(dirname "$0")/.." || exit 1
[ -f .env ] && { set -a; . ./.env; set +a; }
M=${SHAHRAZAD_MODELS:-./models}; mkdir -p "$M"
LIMIT=14400
timeout $LIMIT hf download mistralai/Voxtral-Mini-4B-Realtime-Arabic consolidated.safetensors params.json tekken.json config.json generation_config.json processor_config.json --local-dir "$M/voxtral-ar" || exit 1
timeout $LIMIT hf download unsloth/gemma-4-26B-A4B-it-qat-GGUF gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf --local-dir "$M/gemma4-26b" || exit 1
timeout $LIMIT hf download IbrahimSalah/Arabic-TTS-Spark --exclude "src/*" --local-dir "$M/spark" || exit 1
echo "Done. Next: scripts/convert_spark.sh"
