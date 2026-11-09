# Shahrazad (شهرزاد)

An AI-based spoken Modern Standard Arabic tutor that runs entirely on your own computer. You talk to it, it corrects your mistakes gently, and it replies aloud with fully vowelled Arabic so you can hear and read the correct case endings.

The tutor and its voice are AI models, not a human teacher, so its Arabic can occasionally be wrong.

- **Hearing:** Voxtral Mini 4B Realtime Arabic
- **Teaching:** Gemma 4 26B-A4B
- **Tashkeel:** Gemma 4 adds full vowel marks before each sentence is spoken
- **Voice:** Arabic-TTS-Spark

Ask it to discuss the latest news from a named outlet or a topic, or paste a YouTube link with Arabic captions, and it will discuss that subject with you. Searches go to the internet; everything else stays on your machine.

It takes about 5 seconds from when you stop speaking to when you hear the reply, measured on two RTX 3060 12 GB cards. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how it works and [docs/ROADMAP.md](docs/ROADMAP.md) for what's next.

This project is early and has only been run on that one machine.

## Requirements

- NVIDIA GPU memory as described below, and about 40 GB of disk
- A recent llama.cpp build with `draft-mtp` support
- Python 3.12, and the `hf` CLI for downloads
- A short recording of an Arabic voice you have the right to use

### Which hardware works

You don't need two identical cards. The installer detects your GPUs and system memory and works out where each model should go. The key limits are that one card needs about 11.4 GB free for the speech recognizer, and the tutor model can move parts of itself to the CPU and system memory when GPU memory is short.

| GPUs | System memory | What to expect |
|---|---|---|
| 2 × 12 GB | 24 GB or more | Tested. 17 of Gemma's 30 layers on the CPU |
| 1 × 24 GB | 24 GB or more | Calculated: fits, with 13 layers on the CPU |
| 1 × 20 GB | 32 GB or more | Calculated: fits, with 23 layers on the CPU |
| 16 GB + 8 GB | 32 GB or more | Calculated: fits, with the monitor on the smaller card |
| 12 GB + 8 GB | 32 GB or more | Calculated: fits, but only with the monitor on the smaller card |
| 1 × 16 GB or less | | Doesn't fit |
| No NVIDIA GPU | | Not supported yet |

To preview other hardware, run for example `scripts/configure.py --gpus 16,8 --ram 64`. Only the first row has actually been run. The others are calculated from its measurements, and speed depends on your CPU when many layers are on it: on the test machine Gemma ran at 46 tokens/s with 10 layers on the CPU and 28 with all 30.

## Install

```bash
./install.sh --ref-audio voice.wav
```

The installer checks what your machine already has and does only what's missing: Python environments, a llama.cpp build, about 28 GB of model downloads, the Spark conversion, and the GPU layout for your hardware. It's safe to run again, and an interrupted download resumes. `./install.sh --check` reports what's needed without changing anything.

To use the tutor from other devices on your network, add `--lan`. If you already have models or a llama.cpp build, point to them with `--models` and `--llama-server`. See `./install.sh --help`.

## Run

```bash
scripts/start.sh
```

Open `http://localhost:8791`, allow the microphone, then hold the button or the space bar while you speak. `scripts/stop.sh` shuts everything down. Every process also stops by itself after 8 hours; change `TUTOR_MAX_HOURS` in `.env` to adjust that.

Browsers only allow the microphone on `localhost` or HTTPS. `./install.sh --lan` sets up HTTPS so other devices can open the tutor at `https://<server-address>:8791`; accept the browser's warning about the self-signed certificate. An SSH tunnel to `localhost:8791` also works.

The server has no login, so anyone who can reach that address can use the tutor. Keep it on a network you trust.

## Models and licenses

The models are downloaded from their original repositories, and each has its own license.

| Model | License |
|---|---|
| [Voxtral Mini 4B Realtime Arabic](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-Arabic) | Apache-2.0 |
| [Gemma 4 26B-A4B QAT GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-qat-GGUF) | Apache-2.0 |
| [Arabic-TTS-Spark](https://huggingface.co/IbrahimSalah/Arabic-TTS-Spark) | Non-commercial |

Because of Spark's license, the tutor as a whole is for personal, educational and research use.
