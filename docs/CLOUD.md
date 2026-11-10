# Running parts in the cloud

Shahrazad has three AI parts. Each one can run on your computer or in the cloud, chosen on its own in `.env`. That lets a computer keep what fits on its GPU and send the rest out. All cloud parts go through one [OpenRouter](https://openrouter.ai) key, so there's only one account and one bill.

| Part | `.env` setting | Local | Cloud |
|---|---|---|---|
| Teaching, tashkeel, error checks | `SHAHRAZAD_BRAIN` | Gemma 4 26B-A4B | Claude Haiku 5.5 (`anthropic/claude-haiku-5.5`) |
| Hearing | `SHAHRAZAD_HEARING` | Voxtral Mini 4B Realtime Arabic | Voxtral Mini Transcribe 3 (`mistralai/voxtral-mini-transcribe-3-0`) |
| Voice | `SHAHRAZAD_VOICE` | Arabic-TTS-Spark | Grok Voice TTS, voice Ara (`x-ai/grok-voice-tts-1.0`) |

The cloud models are fixed rather than a free choice. The tutor's prompts, error checks and vowelling were tuned and measured on these models, so another model would need the same testing. Each model can still be changed in `.env`, with `CLOUD_BRAIN_MODEL`, `CLOUD_HEARING_MODEL`, `CLOUD_VOICE_MODEL` and `CLOUD_VOICE_NAME`, for experiments.

## Setting it up

1. Create a key at [openrouter.ai/keys](https://openrouter.ai/keys) and add credit. $5 lasts about 10–15 hours of practice.
2. Run the installer with the parts you want in the cloud:

   ```bash
   ./install.sh --cloud all --key sk-or-...        # no GPU needed
   ./install.sh --cloud hearing --key sk-or-...    # for example, an 8 GB or 16 GB card
   ```

   Run `./install.sh` without `--cloud` and it plans for your hardware. If the local parts don't fit, it stops and tells you which parts to move.
3. Start it as usual with `scripts/start.sh`. Only the local parts are started.

## Cost

These are estimates for one hour of conversation, about 60 turns, at the prices of November 2026.

| Part | Price | Per hour |
|---|---|---|
| Brain | $0.10 / $0.50 per million tokens in / out | about $0.08 |
| Hearing | $0.0035 per minute of speech | about $0.05–0.20 |
| Voice | $15 per million characters | about $0.15–0.25 |
| **All three** | | **about $0.30–0.50** |

In tests, one grammar check cost $0.0004 and one sentence of vowelling about $0.0002. To keep costs low:
- Replies and vowelling run with the model's thinking turned off.
- Only the grammar checks use a little thinking, because it raised the number of errors caught from 14 to 17 of 20.

OpenRouter holds back each request's maximum possible cost until it finishes. With very little credit left, a request can be refused with "payment required" even though it would cost only a fraction of a cent.

## How the models were chosen

The tests below use the same material as the local models: 20 learner sentences with errors plus 9 correct ones, and 40 paragraphs of the SadeedDiac-25 diacritization set.

**Brain.** Each model was set up as its maker recommends, and thinking was turned off where possible.

| Model | Errors caught (of 20) | False corrections | Time per check | Cost per check |
|---|---|---|---|---|
| Gemma 4 26B-A4B, local | 16–17 | — | — | free |
| **Claude Haiku 5.5, light thinking** | **17** | 1 (actually a correct catch) | 2.7 s | $0.0004 |
| Claude Haiku 5.5, no thinking | 14 | 1 | about 1 s | less |
| Claude Sonnet 5.5 | 19 | 1 | 1.4 s | $0.005 |
| Mistral Medium 3.5 | 14 | 4 | 1.2 s | $0.002 |
| Mistral Large 4 | — | — | 15 s | $0.003 |

- **Sonnet** is the most accurate, but costs about 13 times as much.
- **Mistral Large 4** can't turn its thinking off through OpenRouter. It spent about 1,000 tokens on every check and often ran out before answering.

**Tashkeel with Haiku 5.5.** On case endings it is close to Gemma, and it's more than twice as fast.

| | Haiku 5.5 | Gemma 4, local |
|---|---|---|
| Case-ending errors | 2.3–3.0% | 2.1% |
| Words with wrong or extra vowels | about 3% | 4.5% |
| Time per sentence | 0.8 s | 2.1 s |

Haiku tends to leave out obvious vowels inside words. Of the words that differed from the reference, 242 of 280 only had fewer marks, such as «في» for «فِي». The voice reads those correctly anyway.

**Voice.** 12 grammar sentences were read by each candidate. Each clip was then transcribed back by the cloud hearing model and compared letter by letter.

| Voice | Letter errors | Median pitch | Time per sentence |
|---|---|---|---|
| **Grok Ara** | 0% | 228 Hz | 0.8 s |
| Grok Eve | 0% | 204 Hz | 0.8 s |
| Gemini 3.8 Flash Lite TTS, Kore | 0% | 183 Hz | 2.1 s |
| Gemini 3.8 Flash Lite TTS, Leda | 1.3% | 200 Hz | 2.0 s |
| Voxtral TTS 3, voice_3150 | 0% | 128 Hz (male) | 1.0 s |

All are clear. Ara is the default: it's the fastest, and its pitch is closest to the local voice (233 Hz). Letter errors don't measure case endings, which still need a listener's ear.

**Whole turn.** Two spoken learner turns were sent through the all-cloud setup over its WebSocket. Both were heard exactly, and both errors were corrected and became cards. Releasing the button to the first audio took **3.0–3.4 s**, against about 5 s for the local setup on two RTX 3060 cards:
- hearing: 0.5 s
- reply: 1.1 s
- vowelling: 0.8 s
- voice: 0.7–1.1 s

## Differences from the local setup

- **No live captions.** Cloud hearing transcribes the whole turn when the button is released, so the learner's words appear then. One turn can be up to 3 minutes long.
- **Privacy.** What the learner says and the tutor's replies are sent to OpenRouter and the model providers. The learner record (`data/learner.db`) still stays on your computer.
- **Cost.** There's no login, so anyone who can open the tutor can spend the credit. Keep it on a network you trust.
- **License.** Spark's non-commercial license applies only when the voice runs locally.

## How it works

Two things are handled differently for the cloud brain, because Claude behaves differently from Gemma:
- **The private note.** For Gemma, the per-turn guidance (the learner's level, which rule to practise, the next question) is added to the end of the learner's message, which keeps the rest of the prompt in its cache. Claude reads text added there as an injected instruction and comments on it in English. For Claude, the note goes in its own system message after the learner's message instead.
- **Reasoning written out.** With thinking turned off for speed, Claude sometimes writes its grammar check or its plan as an English paragraph before the Arabic reply ("The learner's last sentence has an error…"), or before calling a tool. The prompt tells it that everything it writes is spoken. As a safety net, `spoken_part()` in `app.py` drops leading English paragraphs that read as reasoning (about "the learner", "I should", and similar) while the reply streams. English addressed to the learner, such as an explanation they asked for, is kept. In a 6-turn browser test, no English was shown and every reply streamed in 11–32 steps.

`tools/providers.py` holds all the cloud handling. The rest of the code builds the same requests as for the local models:

- **Brain.** `llm_body()` removes llama.cpp-only fields (`id_slot`, `chat_template_kwargs`) and the sampling settings, which current Claude models don't accept. It names the model, sets the thinking level, and converts structured-output schemas to OpenRouter's form. Streaming and tool calls use the same OpenAI-style format as llama-server.
- **Hearing.** `transcribe()` sends the turn's 16 kHz audio as one WAV file to `/api/v1/audio/transcriptions` with `language: "ar"`.
- **Voice.** `synth()` posts each sentence to `/api/v1/audio/speech`. It returns MP3, which the browser decodes as it does Spark's WAV. Gemini voices return raw 24 kHz PCM, which gets a WAV header.

The test scripts are in `run/cloud/`, which git ignores.
