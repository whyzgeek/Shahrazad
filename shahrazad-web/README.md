# Shahrazad Web

Next.js **15** live session UI for Shahrazad.

Parent install/run: [../README.md](../README.md) · Extending: [../CONTRIBUTING.md](../CONTRIBUTING.md)

**Requires Node.js 18.18+.** Check with `node -v`. On Ubuntu, system Node is often too old — use nvm, fnm, or a local Node under `~/.local/node` (see `.nvmrc` and `npm run dev:local`).

---

## Install

```bash
cd shahrazad-web
cp .env.local.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000

npm install
```

---

## Run

Start API + agent first (see root README), then:

```bash
npm run dev
# or, if PATH needs ~/.local/node:
npm run dev:local
```

Open **http://localhost:3000**.

| Script | Purpose |
|--------|---------|
| `npm run dev` | Next.js dev server |
| `npm run dev:local` | Same, with Node path helper |
| `npm run build` / `start` | Production build |
| `npm run lint` | Lint (ESLint may need config on a fresh clone) |

---

## App map

| Path | Role |
|------|------|
| `src/app/[locale]/page.tsx` | Topic picker |
| `src/app/[locale]/session/page.tsx` | Live session page |
| `src/components/LiveSessionRoom.tsx` | LiveKit room, transcript, notes, Practice |
| `src/lib/api.ts` | REST helpers (errors, TTS URL, acknowledge) |
| `src/middleware.ts` | next-intl locale routing |
| `messages/en.json`, `ar.json` | UI copy |

---

## Session UX

1. Pick a topic → `POST /sessions/live` → join LiveKit room.
2. **Conversation** — speak with Shahrazad; optional **Done speaking** → `commit_turn`.
3. After enough turns → **Review notes** (lesson paused).
4. Choose **1–5** sentences → **Practice** on a note → listen/repeat.
5. Transcript splits **Conversation** vs **Practice**.
6. **Skip** → wrap-up summary card.

Notes sidebar shows learner span, correction, Arabic explanation, English explanation (when different), TTS audio, Practice, and Got it.

---

## LiveKit integration

Uses `@livekit/components-react` (`LiveKitRoom`, voice assistant, audio renderer).

Listens for agent data messages:

| Topic | UI effect |
|-------|-----------|
| `shahrazad-session` | Agent ready |
| `shahrazad-transcript` | Lines + section headers |
| `shahrazad-errors` | Refresh notes / badge |
| `shahrazad-drill` | Practice active / done |
| `shahrazad-flow` | Stepper + summary |
| `shahrazad-control` | Commit ack/error |

Publishes:

| Topic | Payload |
|-------|---------|
| `shahrazad-control` | `commit_turn`, `skip_stage` |
| `shahrazad-drill` | `start_drill` + `sentence_count` |

---

## Environment

| Variable | Example | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | FastAPI base URL |

---

## Extending

| Goal | Start here |
|------|------------|
| Session layout / Practice UX | `LiveSessionRoom.tsx` |
| New strings | `messages/en.json` + `ar.json` |
| API client | `src/lib/api.ts` |
| Topic picker | `src/app/[locale]/page.tsx` |

Keep EN and AR strings in sync. Prefer the existing sand/gold visual language when editing UI.

## npm notes

- `fsevents` optional dependency skipped on Linux — harmless.
- Prefer fixing real type errors over ignoring `tsc` failures when you add a check script.
