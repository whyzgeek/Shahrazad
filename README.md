# Shahrazad (شهرزاد)

MSA (Modern Standard Arabic) voice tutor: full-duplex conversation, silent error capture, and on-demand practice drills.

**Stage 1 (usable product):** OpenAI Realtime voice chat on a topic → notes appear in the sidebar → learner taps **Practice** → short grammar drills → wrap-up.

More work remains (interval review, Docker, CI, YouTube comprehension). See [TODO.md](TODO.md) for the roadmap.

---

## What you get

| Piece | Role |
|-------|------|
| `shahrazad-agent/` | LiveKit voice agent + FastAPI (sessions, tokens, errors, TTS) |
| `shahrazad-web/` | Next.js UI (topic picker, live session, notes, Practice) |
| `spikes/` | Historical Phase 0 verification (not needed to run the product) |

**Session flow**

1. **Conversation** — Shahrazad follows a locked topic agenda (Realtime speech-to-speech).
2. **Review notes** — after enough turns the lesson pauses; notes list on the right.
3. **Practice** — choose 1–5 sentences, tap Practice; transcript shows a separate Practice section.
4. **Wrap-up** — spoken summary and session-complete card.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|--------|
| Python | **3.11+** | Agent + API (`uv` recommended) |
| Node.js | **18.18+** | Web UI (Next.js 15) |
| OpenAI API key | — | Realtime + TTS + LLM judge |
| LiveKit Cloud project | — | URL + API key + secret |

Optional: [uv](https://github.com/astral-sh/uv) for Python installs; PortAudio (`libportaudio2`) only if you use `shahrazad-agent console`.

---

## Install

### 1. Clone and env

```bash
git clone <your-remote-url> shahrazad
cd shahrazad

cp .env.example .env
# Fill at least:
#   OPENAI_API_KEY=
#   LIVEKIT_URL=
#   LIVEKIT_API_KEY=
#   LIVEKIT_API_SECRET=

cp shahrazad-web/.env.local.example shahrazad-web/.env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

Never commit `.env` or `.env.local`.

### 2. Agent + API

```bash
cd shahrazad-agent
python3.11 -m venv .venv          # or: uv venv
source .venv/bin/activate
pip install -e .                  # or: uv pip install -e .
```

### 3. Web

```bash
cd shahrazad-web
node -v                           # must be 18+
npm install
```

---

## Run (three terminals)

```bash
# Terminal 1 — API (port 8000)
cd shahrazad-agent && source .venv/bin/activate && shahrazad-api

# Terminal 2 — LiveKit agent worker
cd shahrazad-agent && source .venv/bin/activate && shahrazad-agent dev

# Terminal 3 — Web (port 3000)
cd shahrazad-web && npm run dev
# If system Node is too old: npm run dev:local
```

Open **http://localhost:3000** → pick a topic → allow the microphone → talk.

Quick health check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/topics
```

---

## Docs map

| Doc | Audience |
|-----|----------|
| [README.md](README.md) (this file) | Install, run, overview |
| [shahrazad-agent/README.md](shahrazad-agent/README.md) | Agent architecture, env vars, API, how to extend |
| [shahrazad-web/README.md](shahrazad-web/README.md) | Web UX, data topics, how to extend |
| [TODO.md](TODO.md) | Roadmap after stage 1 |
| [PLAN.md](PLAN.md) | Historical product/architecture notes (pre–Realtime) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev conventions and where to change things |
| [spikes/README.md](spikes/README.md) | Phase 0 spikes (historical) |

---

## Architecture (stage 1)

```
Browser (Next.js)
    │  LiveKit room (audio) + data messages
    ▼
LiveKit Cloud
    │
    ▼
shahrazad-agent worker          shahrazad-api (FastAPI)
  OpenAI Realtime (chat)          /token, /sessions, /topics
  LLM judge (fan-out)             /errors, /tts, /health
  Practice drills (TTS say)       SQLite: sessions, turns, errors
```

Speech is **OpenAI-only** (no Azure STT/TTS in the live path). Drills use `session.say()` + OpenAI TTS at a slightly higher speed than conversation.

---

## Develop further

Start with [CONTRIBUTING.md](CONTRIBUTING.md). Common entry points:

| Goal | Where |
|------|--------|
| Add a conversation topic | `shahrazad-agent/.../context/topics.json` |
| Change tutor behavior | `agent/prompts.py`, `agent/tutor.py` |
| Tune error detection | `detectors/judge.py` |
| Change drill loop / scoring | `drills/controller.py`, `drills/scoring.py`, `drills/grammar.py` |
| Session stages | `agent/flow.py` |
| Web session UI | `shahrazad-web/src/components/LiveSessionRoom.tsx` |
| Copy / i18n | `shahrazad-web/messages/en.json`, `ar.json` |

Suggested next product work is listed in [TODO.md](TODO.md) (interval review, Docker, tests, end-of-session review UI).

---

## Status

- [x] Stage 1 — Realtime conversation, notes, Practice drills, web UI
- [ ] Stage 2 — Interval review, richer review UI, tests/CI
- [ ] Stage 3 — Docker / deploy polish
- [ ] Later — YouTube comprehension (original Phase 7 idea)
