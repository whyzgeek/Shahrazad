# Running parts in the cloud

Shahrazad has three AI parts. Each one can run on your computer or in the cloud, chosen on its own in `.env`. That lets a computer keep what fits on its GPU and send the rest out. All cloud parts go through one [OpenRouter](https://openrouter.ai) key, so there's only one account and one bill.

| Part | `.env` setting | Local | Cloud |
|---|---|---|---|
| Teaching, tashkeel, error checks | `SHAHRAZAD_BRAIN` | Gemma 4 26B-A4B | the same Gemma 4 26B-A4B (`google/gemma-4-26b-a4b-it`) |
| Hearing | `SHAHRAZAD_HEARING` | Voxtral Mini 4B Realtime Arabic | Voxtral Mini Transcribe 3 (`mistralai/voxtral-mini-transcribe-3-0`) |
| Voice | `SHAHRAZAD_VOICE` | Arabic-TTS-Spark | Grok Voice TTS, voice Ara (`x-ai/grok-voice-tts-1.0`) |

The cloud brain is the same model as the local one, so the tutor behaves the same either way: the same prompts, the same «نقول» corrections, the same level judgement and the same vowelling. The cloud models are fixed rather than a free choice, because the tutor was tuned and measured on them. For experiments they can be changed in `.env` with `CLOUD_BRAIN_MODEL`, `CLOUD_HEARING_MODEL`, `CLOUD_VOICE_MODEL` and `CLOUD_VOICE_NAME`.

## Setting it up

1. Create a key at [openrouter.ai/keys](https://openrouter.ai/keys) and add credit. $5 lasts about 10 hours of practice.
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
| Brain | $0.01–0.13 / $0.04–0.40 per million tokens in / out, depending on the provider | about $0.05–0.10 |
| Hearing | $0.0035 per minute of audio | about $0.15–0.35 with live captions, $0.05–0.10 without |
| Voice | $15 per million characters | about $0.15–0.25 |
| **All three** | | **about $0.35–0.70** |

Live captions cost extra because the unfinished part of what the learner is saying is transcribed again every 1.5 seconds; see [Hearing](#hearing). Set `CLOUD_LIVE_CAPTIONS=0` to turn them off. The text then appears when the button is released, and hearing costs about a third as much.

OpenRouter holds back each request's maximum possible cost until it finishes. With very little credit left, a request can be refused with "payment required" even though it would cost only a fraction of a cent.

## How the models were chosen

The tests below use the same material as the local models: 20 learner sentences with errors plus 9 correct ones, 10 erroneous and 3 correct turns in a news discussion, and 40 paragraphs of the SadeedDiac-25 diacritization set.

### Brain

Other models were tried first. Each was set up as its maker recommends, with thinking turned off where possible.

| Model | Errors caught (of 20) | False corrections | Corrects with «نقول» (of 10 errors) |
|---|---|---|---|
| Gemma 4 26B-A4B, local | 16–17 | — | 10 |
| **Gemma 4 26B-A4B, cloud** | **15–16** | **0–1** | **10** |
| Claude Haiku 5.5 | 14–17 | 1 | 6–7 |
| Claude Sonnet 5.5 | 19 | 1 | — |
| Mistral Medium 3.5 | 14 | 4 | — |

Notes on the others:
- **Claude Haiku 5.5** was the first choice, but it behaves differently from Gemma with the same prompts. It often answers the content and lets the error pass, and with thinking off it sometimes writes its grammar check out in English before the Arabic reply. Making it match would have meant model-specific workarounds.
- **Claude Sonnet 5.5** catches the most errors, but costs about 20 times as much.
- **Mistral Large 4** can't turn its thinking off through OpenRouter. It spent about 1,000 tokens on every check and often ran out before answering.

**Providers.** Many providers serve Gemma 4, and they differ. The grammar checks need valid structured output, and some providers break it:
- Cloudflare, DekaLLM and Io Net don't support it for these requests.
- NextBit returned broken JSON on about 1 call in 3.

So the brain only uses Venice, PrimeIntellect and DeepInfra, in that order (`CLOUD_BRAIN_PROVIDERS`). Each made no failed calls on the 29-sentence set:

| Provider | Errors caught (of 20) | False corrections |
|---|---|---|
| Venice | 16 | 0 |
| PrimeIntellect | 16 | 0 |
| DeepInfra | 15 | 1 |

All three serve the model at full or 8-bit precision.

### Hearing

Voxtral Mini Transcribe 3 is the cloud version of the local Voxtral family. It got every letter right on 60 synthetic clips. OpenRouter only transcribes whole clips, not live audio, so the turn is cut into segments at natural pauses:
- Each finished segment is transcribed once.
- The unfinished one is transcribed again every 1.5 seconds for the live caption.
- On release only the last bit is left, so the final text arrives about 0.4 s after the learner lets go.

On a 19-second, three-sentence clip, the caption updated every 1.5–2 seconds while speaking, and the final text matched what was said.

### Voice

12 grammar sentences were read by each candidate. Each clip was then transcribed back by the cloud hearing model and compared letter by letter.

| Voice | Letter errors | Median pitch | Time per sentence |
|---|---|---|---|
| **Grok Ara** | 0% | 228 Hz | 0.8 s |
| Grok Eve | 0% | 204 Hz | 0.8 s |
| Gemini 3.8 Flash Lite TTS, Kore | 0% | 183 Hz | 2.1 s |
| Gemini 3.8 Flash Lite TTS, Leda | 1.3% | 200 Hz | 2.0 s |
| Voxtral TTS 3, voice_3150 | 0% | 128 Hz (male) | 1.0 s |

All are clear. Ara is the default: it's the fastest, and its pitch is closest to the local voice (233 Hz). Letter errors don't measure case endings, but the voice is given the same vowelled text as Spark.

### Whole turn

Four spoken learner turns, including a request for Al Jazeera's news, were sent through the all-cloud setup over its WebSocket:
- **Heard:** all four exactly.
- **Tools:** the news request called the news tool.
- **Corrections:** all three errors were corrected with «نقول» and became cards.
- **Speed:** first audio came 2.1–3.8 s after the button was released, against about 5 s for the local setup on two RTX 3060 cards.

## Differences from the local setup

- **Privacy.** What the learner says and the tutor's replies are sent to OpenRouter and the model providers. The learner record (`data/learner.db`) still stays on your computer.
- **Cost.** There's no login, so anyone who can open the tutor can spend the credit. Keep it on a network you trust.
- **License.** Spark's non-commercial license applies only when the voice runs locally.

## How it works

`tools/providers.py` holds all the cloud handling. The rest of the code builds the same requests as for the local models.

- **Brain.** `llm_body()` removes llama-server's own fields (`id_slot`, `chat_template_kwargs`), names the model and the providers, and gives structured-output schemas the name OpenRouter requires. Sampling stays at Google's recommended values, and thinking stays off, as locally. Streaming and tool calls use the same OpenAI-style format as llama-server.
- **Hearing.** `CloudEar` in `app.py` cuts the turn into segments and shows the captions. `transcribe()` sends each segment as a 16 kHz WAV file to `/api/v1/audio/transcriptions` with `language: "ar"`.
- **Voice.** `synth()` posts each sentence to `/api/v1/audio/speech`. It returns MP3, which the browser decodes as it does Spark's WAV. Gemini voices return raw 24 kHz PCM, which gets a WAV header.

The test scripts are in `run/cloud/`, which git ignores.
