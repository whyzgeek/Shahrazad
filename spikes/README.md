# Phase 0 spikes (historical)

Pre-build verification from the **Azure Speech** era. **Not required** to install or run the current OpenAI Realtime product.

For the live app, see [../README.md](../README.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md).

## What was decided

Summary: [SPIKE_DECISIONS.md](SPIKE_DECISIONS.md) · Report: [results/PHASE0_REPORT.md](results/PHASE0_REPORT.md)

Many spike recommendations (Azure STT/PA) were later superseded when the live path moved to OpenAI Realtime. Mishkal and LiveKit decisions still apply.

## Scripts (`scripts/`)

| Script | Validates |
|--------|-----------|
| `01_azure_stt_pa_locale.py` | Azure STT + PA locale (historical) |
| `02_stt_latency.py` | STT latency comparison |
| `03_camel_dialect.py` | CAMeL-Tools dialect ID |
| `04_tashkeel_mishkal.py` | Mishkal diacritization |
| `05_livekit_connectivity.py` | LiveKit JWT + connectivity |
| `06_audio_capture.py` | Per-turn WAV buffer |
| `run_phase0.py` | Runs the suite |

## Re-run (optional)

```bash
cd spikes
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# May need Azure / Deepgram keys in ../.env for some scripts
python scripts/run_phase0.py
```

JSON/log artifacts under `results/` are gitignored; keep `PHASE0_REPORT.md` in git.
