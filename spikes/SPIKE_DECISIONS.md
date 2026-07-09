# Phase 0 spike decisions

> **Note:** These decisions guided the early Azure-based prototype. The **live product**
> now uses **OpenAI Realtime** for conversation (no Azure STT/TTS/PA on the hot path).
> Still relevant: **Mishkal** for text-TTS tashkeel, **LiveKit**, and **LLM judge primary**
> for dialect (CAMeL optional). See [../README.md](../README.md).

| Decision | Choice | Evidence | Date |
|----------|--------|----------|------|
| STT + PA locale | **Both `ar-SA`** (historical Azure path) | `results/*_azure_stt_pa_locale.json` | 2026-07-02 |
| STT provider (Azure vs Deepgram) | **Azure** at the time; later replaced by OpenAI Realtime | `results/*_stt_latency.json` | 2026-07-02 |
| Dialect detector (CAMeL thresholds) | **GPT-4o-mini judge primary**; CAMeL-Tools corroborating only | `results/*_camel_dialect.json` | 2026-07-02 |
| Tashkeel provider | **Mishkal** (local pip, no API account) — Farasa skipped | `results/*_tashkeel_mishkal.json` | 2026-07-02 |
| LiveKit Cloud OK | **Yes — JWT mint + HTTP 200** | `results/*_livekit_connectivity.json` | 2026-07-02 |
| Per-turn audio storage | **Local FS, 30-day retention, agent buffer** | `results/*_audio_policy.json` | 2026-07-02 |

## Run log

### 2026-07-02 — Phase 0 complete (Mishkal replaces Farasa)

- **Azure TTS/STT/PA:** OK — `ar-SA` for both STT and PA.
- **STT latency:** ~751 ms batch on 3s greeting clip.
- **CAMeL:** Installed (`dialectid-model26`); supplementary drift signal only.
- **Tashkeel:** Farasa skipped (no QCRI account). **Mishkal** OK — ~77–114 ms/chunk after warm-up; 300 ms timeout + undiacritized fallback in agent.
- **LiveKit:** JWT mint + HTTP 200.
- **Audio policy:** Local FS, 30-day retention.

### Mishkal notes (spike 4b)

- No API key; `pip install mishkal`.
- First `TashkeelClass()` load can exceed 300 ms — warm engine at agent startup.
- Cache diacritized outputs by text hash (drill phrases repeat).

## Phase 0 → Phase 1 handoff

1. `.env` at repo root: Azure + LiveKit + OpenAI (for agent worker).
2. Phase 1 package: `shahrazad-agent/` (Python 3.11, FastAPI token API, LiveKit worker).
3. Run agent: `cd shahrazad-agent && shahrazad-api` and `shahrazad-agent dev`.
