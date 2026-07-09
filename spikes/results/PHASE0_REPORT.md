# Shahrazad Phase 0 Report

Generated: 2026-07-02T14:06:50.172125+00:00

## Summary

| Spike | Status | Recommendation |
|-------|--------|----------------|
| 01_azure_stt_pa_locale | **ok** | Use ar-SA for both STT and PA |
| 02_stt_latency | **ok** | Azure only (no DEEPGRAM_API_KEY) |
| 03_camel_dialect | **ok** | CAMeL-Tools installed and runs (dialectid-model26). Text-only scores show very low P(MSA) even on clean MSA fixtures — use as a supplementary drift signal, not sole detector; re-tune thresholds on real learner audio in Phase 2; ADIDA fallback optional. |
| 04_tashkeel_mishkal | **ok** | Use Mishkal as V1 tashkeel provider (local, no API key). First call loads model (~100-300ms); cache per text hash in agent. 300ms timeout -> undiacritized fallback per plan invariant 3. |
| 05_livekit_connectivity | **ok** | LiveKit credentials valid — proceed with LiveKit Agents backbone |
| 06_audio_capture | **ok** | Local FS, 30-day retention, agent-side buffer on user_speech_committed |

## Spike results

### 01_azure_stt_pa_locale

- **Status:** ok
- **Recommendation:** Use ar-SA for both STT and PA

### 02_stt_latency

- **Status:** ok
- **Recommendation:** Azure only (no DEEPGRAM_API_KEY)

### 03_camel_dialect

- **Status:** ok
- **Recommendation:** CAMeL-Tools installed and runs (dialectid-model26). Text-only scores show very low P(MSA) even on clean MSA fixtures — use as a supplementary drift signal, not sole detector; re-tune thresholds on real learner audio in Phase 2; ADIDA fallback optional.

### 04_tashkeel_mishkal

- **Status:** ok
- **Recommendation:** Use Mishkal as V1 tashkeel provider (local, no API key). First call loads model (~100-300ms); cache per text hash in agent. 300ms timeout -> undiacritized fallback per plan invariant 3.

### 05_livekit_connectivity

- **Status:** ok
- **Recommendation:** LiveKit credentials valid — proceed with LiveKit Agents backbone

### 06_audio_capture

- **Status:** ok
- **Recommendation:** Local FS, 30-day retention, agent-side buffer on user_speech_committed

## Decisions

| Decision | Choice |
|----------|--------|
| STT + PA locale | Use ar-SA for both STT and PA |
| STT provider | Azure only (no DEEPGRAM_API_KEY) |
| Dialect detector | CAMeL-Tools installed and runs (dialectid-model26). Text-only scores show very low P(MSA) even on clean MSA fixtures — use as a supplementary drift signal, not sole detector; re-tune thresholds on real learner audio in Phase 2; ADIDA fallback optional. |
| Tashkeel provider | Use Mishkal as V1 tashkeel provider (local, no API key). First call loads model (~100-300ms); cache per text hash in agent. 300ms timeout -> undiacritized fallback per plan invariant 3. |
| LiveKit | LiveKit credentials valid — proceed with LiveKit Agents backbone |
| Audio storage | Local FS, 30-day retention, agent-side buffer on user_speech_committed |

## Next steps

1. Copy `.env.example` → `.env` and fill Azure + LiveKit keys (Mishkal needs no key).
2. Run `python scripts/generate_msa_fixture.py` to create learner WAV (or record your own).
3. Re-run `python scripts/run_phase0.py` until all blocking spikes are **ok**.
4. Update `SPIKE_DECISIONS.md` and mark Phase 0 complete in root `TODO.md`.
