# Contributing / developing Shahrazad

This guide is for people extending the stage-1 product. Install and run steps: [README.md](README.md).

## Repo layout

```
shahrazad/
├── .env.example                 # Agent/API secrets template (repo root)
├── shahrazad-agent/             # Python 3.11+ LiveKit agent + FastAPI
│   ├── pyproject.toml
│   ├── data/                    # Runtime SQLite + audio (gitignored)
│   └── src/shahrazad_agent/
│       ├── agent/               # worker, flow, Realtime, fan-out, prompts
│       ├── api/                 # FastAPI routes
│       ├── drills/              # Practice loop + scoring
│       ├── detectors/           # LLM judge (+ optional CAMeL)
│       ├── context/             # topics.json + adapters
│       ├── db/                  # SQLAlchemy models + store
│       ├── audio/               # Learner WAV capture
│       └── diacritization/      # Mishkal (drill/review TTS only)
└── shahrazad-web/               # Next.js 15 session UI
    ├── messages/                # en.json / ar.json
    └── src/components/LiveSessionRoom.tsx
```

## Dev loop

1. Keep three processes running (API, agent worker, web) — see root README.
2. After **agent** code changes, restart `shahrazad-agent dev` (worker does not hot-reload reliably).
3. After **web** changes, Next.js hot-reloads; hard-refresh if data-message handlers look stale.
4. After **API-only** changes, restart `shahrazad-api`.

## Environment

- Agent loads **repo-root** `.env` (see `config.py`).
- Web loads `shahrazad-web/.env.local` (`NEXT_PUBLIC_API_URL`).
- Full variable list: [shahrazad-agent/README.md](shahrazad-agent/README.md#environment-variables).

## Conventions

- Prefer small, focused changes; match existing naming and logging style.
- Do not commit `.env`, `.env.local`, SQLite DBs, learner audio, `.next/`, or venvs.
- Arabic UI strings live in `messages/ar.json` and `messages/en.json` together.
- LiveKit data topics are the contract between web and agent — keep payloads documented when you change them.

## LiveKit data topics (contract)

| Topic | Direction | Main payloads |
|-------|-----------|----------------|
| `shahrazad-session` | agent → web | `session_ready` |
| `shahrazad-control` | web → agent | `commit_turn`, `skip_stage` |
| `shahrazad-drill` | web → agent | `start_drill` (`error_entry_id`, `sentence_count`) |
| `shahrazad-drill` | agent → web | `drill_started`, `drill_attempt`, `drill_completed` |
| `shahrazad-errors` | agent → web | `error_count` |
| `shahrazad-flow` | agent → web | `stage`, `session_summary` |
| `shahrazad-transcript` | agent → web | `transcript` (`section`: `conversation` \| `practice`), `section` |

## How to extend (recipes)

### Add a topic

Edit `shahrazad-agent/src/shahrazad_agent/context/topics.json`:

- `topic_id`, titles, level
- `agenda` steps (locked conversation path)
- `opening_line` (first spoken line)

Restart the agent. Topics appear via `GET /topics`.

### Tighten or loosen the judge

Edit `detectors/judge.py` (`JUDGE_SYSTEM` and `_is_spurious`). Prefer fewer false positives on names, loanwords, and hesitation.

### Change Practice behavior

| Change | File |
|--------|------|
| Loop / cues / speed | `drills/controller.py` |
| Sentence generation | `drills/grammar.py` |
| Pass/fail scoring | `drills/scoring.py` |
| When review starts | `agent/flow.py` (`FLOW_CONVERSATION_TURNS`) |
| Sentence count UI | `LiveSessionRoom.tsx` + `start_drill` payload |

### Change conversation prompts

`agent/prompts.py` (`build_instructions`) and topic blocks from `context/adapters.py`.

### Change the web session UX

`shahrazad-web/src/components/LiveSessionRoom.tsx` — transcript sections, Practice controls, flow stepper, notes sidebar.

## Testing (current)

There is **no automated test suite yet**. Manual checks:

1. `curl http://localhost:8000/health` and `/topics`
2. Full session: greetings topic → notes appear → Practice 1–3 sentences → Skip → summary
3. Confirm Practice lines sit under a **Practice** transcript heading
4. Confirm Latin-only phantom lines do not appear mid-conversation

Adding pytest smoke tests (scoring, judge filters, health) is a good first contribution — see [TODO.md](TODO.md).

## Optional: CAMeL-Tools

Dialect corroboration is optional. If installed in the agent venv, `detectors/camel.py` will use it; otherwise the LLM judge alone is enough.

## Do not

- Reintroduce Azure STT/TTS/PA on the live path without an explicit product decision (spikes are historical).
- Auto-start drills during conversation (review is learner-driven via Practice).
- Commit runtime data under `shahrazad-agent/data/` (except `.gitkeep`).
