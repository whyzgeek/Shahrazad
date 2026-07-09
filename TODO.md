# Shahrazad — roadmap & checklist

Product overview and install: [README.md](README.md) · How to extend: [CONTRIBUTING.md](CONTRIBUTING.md)

**Legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[—]` deferred / not applicable

---

## Stage 1 — Usable product (current)

**Shipped:** OpenAI Realtime conversation, silent LLM judge notes, sidebar Practice drills (1–5 sentences), guided flow (conversation → review → summary), Next.js EN/AR UI.

### Stack (current truth)

- [x] OpenAI Realtime speech-to-speech (live chat)
- [x] OpenAI TTS for drills / flow `say()` / `/tts` proxy
- [x] GPT-4o-mini error judge (grammar, vocabulary, dialect_drift)
- [x] Mishkal tashkeel for text-TTS path only
- [x] LiveKit agent + FastAPI + SQLite
- [x] Next.js session UI with flow stepper + Practice
- [x] Lesson pause during Practice; separate transcript sections
- [x] Latin STT phantom filtering + drill re-transcription
- [x] Learner-chosen practice sentence count (1–5)
- [—] Azure STT / Neural TTS / Pronunciation Assessment on live path (removed; spikes are historical)

### Stage 1 validation (manual)

- [x] Voice round-trip via web session
- [x] Notes appear in sidebar with explanations
- [x] Practice completes without agenda chat overlapping
- [x] Transcript Conversation vs Practice sections
- [ ] Broader topic coverage / more agendas
- [ ] Multi-browser / mobile mic hardening

---

## Stage 2 — Harden & deepen learning

- [ ] Automated tests (scoring, judge filters, health, flow stage transitions)
- [ ] CI (lint + typecheck + pytest smoke)
- [ ] Richer end-of-session review UI (browse all notes, replay audio)
- [ ] Optional mid-session interval review (without breaking Realtime pause rules)
- [ ] Persist / resume incomplete sessions
- [ ] Better handling of proper nouns & company names in STT
- [ ] ESLint config for `shahrazad-web` (or drop unused lint script)
- [ ] Document production env (LiveKit + OpenAI quotas)

---

## Stage 3 — Ship / ops

- [ ] `docker-compose.yml` (api + worker + web)
- [ ] One-command local bootstrap script
- [ ] Consent / mic permission copy polish
- [ ] README walkthrough video or screenshots
- [ ] Deploy notes (LiveKit Cloud + hosted API/web)

---

## Later

- [ ] YouTube-grounded comprehension conversations (original Phase 7 idea in PLAN.md)
- [ ] Spaced repetition / SRS over resolved notes
- [ ] Postgres instead of SQLite for multi-user deploy
- [ ] Optional CAMeL-Tools packaging story

---

## Historical phases (archive)

Early build used Azure Speech spikes and a different pipeline. Decisions: [spikes/SPIKE_DECISIONS.md](spikes/SPIKE_DECISIONS.md). Original long-form plan: [PLAN.md](PLAN.md) (marked historical).

| Phase | Outcome |
|-------|---------|
| 0 Spikes | Complete — locale/tashkeel/LiveKit decisions recorded |
| 1 Voice round-trip | Complete — later migrated to OpenAI Realtime |
| 2 Error fan-out + DB | Complete — PA path removed; LLM judge remains |
| 3 Drill loop | Complete — text-match Practice; sidebar-driven |
| 4 Web UI | Complete — stage-1 session UX |
| 5–7 | See Stage 2 / 3 / Later above |

Detailed checkbox history from the Azure-era build was collapsed here to avoid contradicting the current stack. Use git history if you need the old line-by-line checklist.
