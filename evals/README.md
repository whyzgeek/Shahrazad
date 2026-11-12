# Evals

The measurements behind the model choices in this repo. Each script uses the tutor's own code (prompts, filters,
vowelling with its safety nets), so the numbers describe the tutor, not the bare model. They read the repo's `.env`,
so they measure whichever parts are set to `local` or `cloud` there. Run them from the repo root with the tutor's
environment, and with the local models running (`scripts/start.sh`) or an OpenRouter key set for cloud parts.

| Script | What it measures | Needs |
|---|---|---|
| `errors.py` | Error detection: mistakes found, correct words wrongly flagged | brain |
| `naqool.py` | Whether a reply with a mistake starts with «نقول» (the corrected sentence), and how often a correct sentence gets one anyway | brain |
| `tashkeel.py` | Vowelling: case endings and words wrong, letters changed, time per call | brain, internet (downloads SadeedDiac-25) |
| `spoken.py` | Delay from the end of speech to the first audio, over five spoken turns | a running test copy of the tutor, ffmpeg |

```bash
.venv-tutor/bin/python evals/errors.py
.venv-tutor/bin/python evals/naqool.py
.venv-tutor/bin/python evals/tashkeel.py
# spoken.py: against a test copy, so its deliberate mistakes don't enter your progress
SHAHRAZAD_LEARNER_DB=/tmp/eval.db TUTOR_PORT=8794 .venv-tutor/bin/python app.py &
.venv-tutor/bin/python evals/spoken.py --url https://127.0.0.1:8794
```

`errors.py --url` points the error check at any OpenAI-style chat endpoint, for trying another model.

## Reference results

Local setup (Gemma 4 26B-A4B, Voxtral, Spark) on two RTX 3060 12 GB cards, November 2026:

| Eval | Result |
|---|---|
| `errors.py` | 15 of 20 mistakes found; 3 words flagged wrongly; no failed calls |
| `naqool.py` | «نقول» on 10 of 10 sentences with mistakes at both levels; on 4 of 24 correct sentences (3 beginner, 1 intermediate) |
| `tashkeel.py`, grammar sentences | No case ending wrong (of 50); 1 word in 67 wrong; no letters changed |
| `tashkeel.py`, SadeedDiac-25 | 2.1% of case endings wrong (of 1,146); 4.4% of words; letters changed in 4 of 40 paragraphs; 5.6 s per paragraph |
| `spoken.py` | First audio 6.7 s after the first turn's speech, 6.9–7.9 s after later turns (median 7.8 s). Of that: hearing 0.8 s, the brain's first word 2.5–3.1 s, vowelling the first sentence 2.5–2.9 s, the voice 1.1–1.8 s |

With the cloud brain (same Gemma on OpenRouter), `errors.py` found 15–16 of 20 and `naqool.py` gave 10 of 10.
Two other models were tried in the cloud and not chosen: Claude Haiku added «نقول» on 6–7 of 10 and sometimes wrote
English, and Mistral Large's thinking could not be turned off there.

Tashkeel-v3 (0.2B), a dedicated vowelling model, was also tested: about 40 times faster on the CPU, but 3.3% of
case endings and 8.9% of words wrong on the same paragraphs, and it doubled marks and letters on real tutor
replies. Gemma stayed.

Each run differs a little: the tutor samples its replies at Gemma's recommended temperature of 1.0, and cloud
providers vary. Compare a candidate model against these on the same hardware, two or three runs each.
