# shahrazad-agent

Python **LiveKit agent** + **FastAPI** for Shahrazad.

Parent install/run: [../README.md](../README.md) · Extending the product: [../CONTRIBUTING.md](../CONTRIBUTING.md)

---

## Install

```bash
cd shahrazad-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
# or: uv venv && source .venv/bin/activate && uv pip install -e .
```

Requires a repo-root `.env` (copy from `../.env.example`).

---

## Run

```bash
# API — http://localhost:8000
shahrazad-api

# Worker (separate terminal) — joins LiveKit rooms as the tutor
shahrazad-agent dev
```

Console mic test (optional; needs `libportaudio2` on Linux):

```bash
sudo apt-get install -y libportaudio2
shahrazad-agent console
```

---

## Package map

| Path | Responsibility |
|------|----------------|
| `agent/worker.py` | LiveKit entrypoint, session wiring, data handlers |
| `agent/tutor.py` | Agent class, drill tools (review-only) |
| `agent/flow.py` | Conversation → review → summary stages |
| `agent/speech.py` | Realtime model + TTS factories |
| `agent/realtime_control.py` | Pause chat during drills; STT prompt; drill speech speed |
| `agent/learner_turns.py` | Persist turns, fan-out, drop Latin phantoms |
| `agent/fanout.py` | Async judge + error publish |
| `agent/prompts.py` | System instructions |
| `drills/` | Practice loop, grammar sentences, scoring |
| `detectors/judge.py` | GPT-4o-mini MSA error judge |
| `detectors/camel.py` | Optional CAMeL dialect corroboration |
| `context/topics.json` | Preset topics + agendas |
| `api/routes/` | health, topics, token, sessions, errors, tts |
| `db/` | SQLAlchemy models + store |
| `audio/capture.py` | Learner turn WAV buffer |
| `diacritization/mishkal.py` | Tashkeel for text-TTS path only |

Runtime data (gitignored): `data/shahrazad.db`, `data/audio/`, `data/tts_cache/`.

---

## Speech stack

| Path | Implementation |
|------|----------------|
| Live conversation | OpenAI Realtime speech-to-speech |
| Input transcripts | `OPENAI_TRANSCRIPTION_*` (language `ar`) |
| Turn ending | Semantic VAD; web may send `commit_turn` |
| Drills / flow `say()` | OpenAI TTS (~1.2× speed during drills) |
| Review `/tts` | Same OpenAI TTS, disk-cached MP3 |
| Tashkeel | Mishkal for drill/review text only (not Realtime chat) |

During Practice, Realtime auto-replies are paused (`create_response=False`) so agenda chat does not overlap drills.

---

## Guided session flow

1. **conversation** — `FLOW_CONVERSATION_TURNS` (default 6) learner turns on a locked agenda.
2. **review** — pause chat; learner uses sidebar **Practice** (not auto-drilled).
3. **summary** → **complete** — spoken wrap-up + `session_summary` event.

Skip: web sends `{"type":"skip_stage"}` on `shahrazad-control`.

---

## Practice drills

Triggered by web:

```json
{"type": "start_drill", "error_entry_id": "<uuid>", "sentence_count": 3}
```

- `sentence_count` 1–5 = total practice lines (1 correction + N−1 similar).
- Grammar/vocab/dialect notes → short rule-focused sentences (`drills/grammar.py`).
- Scoring: Arabic text-match (`drills/scoring.py`); Latin STT is rescued or ignored.
- Intro speaks a short rule from `explanation_ar`, then model sentence → learner repeats (no “الآن كرّر” cue).

---

## Error fan-out

On each final learner transcript (non-drill):

1. Persist turn (+ optional WAV).
2. Background GPT-4o-mini judge → `ErrorEntry` rows.
3. Publish `shahrazad-errors` count.
4. Advance `SessionFlow` turn counter.

Latin-only phantoms are dropped and do not count as turns.

---

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/topics` | Topic catalog |
| POST | `/token` | LiveKit JWT (legacy/manual) |
| POST | `/sessions` | Create session row |
| POST | `/sessions/live` | Session + LiveKit token for web |
| GET | `/sessions/{id}` | Session metadata |
| GET | `/sessions/{id}/errors` | Notes for sidebar |
| GET | `/sessions/{id}/drills` | Drill attempt history |
| POST | `/errors/{id}/acknowledge` | Mark note acknowledged |
| GET | `/tts?text=…` | Cached MP3 of MSA text |

Examples:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/topics
curl -X POST http://localhost:8000/sessions/live \
  -H 'Content-Type: application/json' \
  -d '{"topic_id":"greetings"}' | jq
curl "http://localhost:8000/tts?text=أهلاً" --output /tmp/ahlan.mp3
```

---

## Environment variables

Loaded from repo-root `.env` (see `../.env.example`).

### Required

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Realtime, TTS, judge |
| `LIVEKIT_URL` | LiveKit Cloud URL |
| `LIVEKIT_API_KEY` | API key |
| `LIVEKIT_API_SECRET` | API secret |

### Speech (defaults shown)

| Variable | Default |
|----------|---------|
| `OPENAI_REALTIME_MODEL` | `gpt-realtime` |
| `OPENAI_REALTIME_VOICE` | `marin` |
| `OPENAI_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` |
| `OPENAI_TRANSCRIPTION_LANGUAGE` | `ar` |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` |
| `OPENAI_TTS_VOICE` | `shimmer` |
| `TASHKEEL_TIMEOUT_MS` | `300` |

### Flow & drills

| Variable | Default | Purpose |
|----------|---------|---------|
| `FLOW_CONVERSATION_TURNS` | `6` | Turns before review |
| `FLOW_MAX_REVIEW_DRILLS` | `3` | Legacy; UI `sentence_count` preferred |
| `GRAMMAR_DRILL_SIMILAR_COUNT` | `2` | Extra sentences if UI omits count |
| `GRAMMAR_DRILL_MAX_ATTEMPTS_PER_SENTENCE` | `3` | Retries per line |
| `DRILL_ACCURACY_THRESHOLD` | `80` | Text-match pass % |
| `DRILL_MAX_ATTEMPTS` | `5` | Pronunciation drill max |
| `DRILL_ENDPOINTING_MIN` / `MAX` | `0.7` / `1.0` | Drill VAD delays |
| `CONVERSATION_ENDPOINTING_MIN` / `MAX` | `0.35` / `0.9` | Chat VAD delays |
| `DATABASE_URL` | SQLite under `data/` | Override DB location |

---

## LiveKit data topics

See [CONTRIBUTING.md](../CONTRIBUTING.md#livekit-data-topics-contract).

---

## Extending

| Goal | Start here |
|------|------------|
| New topic | `context/topics.json` |
| Tutor persona / agenda discipline | `agent/prompts.py` |
| Judge quality | `detectors/judge.py` |
| Drill UX / speed | `drills/controller.py`, `agent/realtime_control.py` |
| Flow timing | `agent/flow.py` |
| New HTTP route | `api/routes/` + register in `api/main.py` |

Restart the worker after Python changes.
