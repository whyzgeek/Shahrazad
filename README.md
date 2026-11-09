# Shahrazad (شهرزاد)

A spoken Modern Standard Arabic tutor that runs entirely on your own computer. You talk to it, it corrects your mistakes gently, and it replies aloud with fully vowelled Arabic so you can hear and read the correct case endings.

- **Hearing:** Voxtral Mini 4B Realtime Arabic
- **Teaching:** Gemma 4 26B-A4B
- **Tashkeel:** Gemma 4 adds full vowel marks before each sentence is spoken
- **Voice:** Arabic-TTS-Spark

It takes about 5 seconds from when you stop speaking to when you hear the reply, measured on two RTX 3060 12 GB cards. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it works and [docs/ROADMAP.md](docs/ROADMAP.md) for what's next.

This project is early and has only been run on that one machine.

## Requirements

- Two NVIDIA GPUs with 12 GB each, or an equivalent setup, and about 40 GB of disk
- A recent llama.cpp build with `draft-mtp` support
- Python 3.12, and the `hf` CLI for downloads
- A short recording of an Arabic voice you have the right to use

## Setup

```bash
cp .env.example .env     # then set SHAHRAZAD_REF_AUDIO and the other paths

python3.12 -m venv .venv-tutor   && .venv-tutor/bin/pip install -r requirements/tutor.txt
python3.12 -m venv .venv-voxtral && .venv-voxtral/bin/pip install -r requirements/voxtral.txt
python3.12 -m venv .venv-spark
.venv-spark/bin/pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.venv-spark/bin/pip install -r requirements/spark.txt

scripts/download_models.sh
scripts/convert_spark.sh
```

## Run

```bash
scripts/start.sh
```

Open `http://localhost:8791`, allow the microphone, then hold the button or the space bar while you speak. `scripts/stop.sh` shuts everything down, and every process also stops by itself after 8 hours.

Browsers only allow the microphone on `localhost` or HTTPS, so from another computer use an SSH tunnel:

```bash
ssh -L 8791:127.0.0.1:8791 <user>@<server>
```

The server has no login, so don't expose it to a network without adding HTTPS and authentication.

## Models and licenses

The models are downloaded from their original repositories, and each has its own license.

| Model | License |
|---|---|
| [Voxtral Mini 4B Realtime Arabic](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-Arabic) | Apache-2.0 |
| [Gemma 4 26B-A4B QAT GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF) | Apache-2.0 |
| [Arabic-TTS-Spark](https://huggingface.co/IbrahimSalah/Arabic-TTS-Spark) | Non-commercial |

Because of Spark's license, the tutor as a whole is for personal, educational and research use.
