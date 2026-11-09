# Shahrazad architecture

Shahrazad is an AI-based speaking tutor. It holds a spoken conversation in Modern Standard Arabic (MSA), corrects the learner's mistakes, and shows and speaks fully vowelled Arabic. All of its AI models run locally on one machine.

## At a glance

GPU numbers below describe the tested layout of two 12 GB cards. `scripts/configure.py` chooses the placement for other hardware.

| Job | Model | Runtime | Device |
|---|---|---|---|
| Hear the learner | Voxtral Mini 4B Realtime Arabic | vLLM, WebSocket | GPU1 |
| Tutor reply, and adding tashkeel | Gemma 4 26B-A4B QAT + MTP draft head | llama-server | GPU0, with 17 layers of experts on the CPU |
| Generate speech tokens | Arabic-TTS-Spark language model (converted to BF16 GGUF) | llama-server | GPU0 |
| Turn speech tokens into audio | Spark BiCodec decoder | `spark_service.py` (PyTorch) | GPU0 |
| Conversation logic | None | `app.py` (FastAPI) | CPU |
| User interface | None | `index.html` in the browser | Learner's device |

The interaction is push-to-talk with interruption: the learner holds a button or the space bar, and pressing it again while the tutor is speaking stops the reply. It is not full duplex, because the tutor does not listen while it speaks.

## How the parts connect

```mermaid
flowchart LR
  subgraph Browser
    UI[index.html<br/>mic capture, captions,<br/>audio queue]
  end
  subgraph Server["Server (all ports on 127.0.0.1)"]
    APP[app.py :8791<br/>session logic]
    VOX[Voxtral on vLLM :18098<br/>GPU1]
    GEMMA[Gemma 4 on llama-server :18099<br/>GPU0 + CPU]
    SPARK[spark_service.py :18096<br/>BiCodec decoder, GPU0]
    SPLM[Spark LM on llama-server :18097<br/>GPU0]
  end
  UI <-->|"WebSocket /ws<br/>PCM up, text and WAV down"| APP
  APP <-->|"WebSocket /v1/realtime"| VOX
  APP -->|"HTTP chat completions (streamed)"| GEMMA
  APP -->|"HTTP POST /synth"| SPARK
  SPARK -->|"HTTP /completion (token ids, streamed)"| SPLM
```

Each model runs as its own process because their dependencies conflict. Voxtral needs vLLM with PyTorch 2.14, Spark's custom code needs transformers 4.51, and the app needs no PyTorch at all.

## One conversation turn

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as app.py
  participant V as Voxtral
  participant G as Gemma 4
  participant S as Spark service
  participant L as Spark LM
  B->>A: start, then 80 ms PCM frames while held
  A->>V: stream audio
  V-->>A: text deltas
  A-->>B: partial (live captions)
  B->>A: stop (button released)
  V-->>A: final transcript
  A-->>B: final
  A->>G: history + system prompt
  G-->>A: reply (streamed)
  A-->>B: assistant (reply text grows)
  loop For each speakable sentence
    A->>G: add full tashkeel (temperature 0)
    G-->>A: vowelled sentence
    A-->>B: tashkeel (exactly what the voice receives)
    A->>S: POST /synth with vowelled text
    S->>L: prompt token ids
    L-->>S: speech tokens until silence
    S-->>A: WAV
    A-->>B: WAV (queued for playback)
  end
  A-->>B: timing
```

The complete reply is generated before vowelling starts. Gemma has two slots, one for the discussion and one for vowelling, so vowelling doesn't push the discussion out of its cache.

### Text handling between the models

1. `split_sentences` splits the reply and merges one- or two-word fragments forward.
2. `speakable` holds back sentences that are mostly not Arabic. These are shown on screen but not spoken, because the voice only reads Arabic.
3. `clean_text` removes quotes, markdown and any existing vowel marks, and turns "…" into a comma.
4. `vowelize` asks Gemma to add full tashkeel, including case endings.
5. `merge_vowels` keeps the tutor's exact words. A vowelled word is accepted only if its letters match the original; otherwise the original word is kept, without vowels.

### How Spark stops

Spark tends to keep generating silence after the sentence ends. After speech, the token stream is almost entirely tokens 3140, 7645 and 6627. `spark_service.py` stops generation after 25 of these in a row (0.5 s of silence), keeps six for a natural decay, and caps a sentence at 900 tokens (18 s).

### Long turns and long sentences

A Voxtral session holds about 82 s. After 55 s, `app.py` waits for a pause, or forces it at 72 s, then finishes that session and starts another. Audio arriving meanwhile is held and sent afterwards, and the transcripts are joined.

Spark stops at 18 s per sentence, about 30 words, so vowelled text over 20 words is sent in parts, split at commas where possible.

### How interruption works

Pressing talk stops local playback, and the app cancels the running reply task. A generation counter discards audio that was already in progress. In the end-to-end test, no stale audio arrived after an interruption.

## Subjects, tools and skills

A conversation has a **current subject**: an article or a video. Tools are used only to find one, so ordinary discussion turns have no searching. The subject stays in the system prompt, separate from the chat history, until the learner moves on.

| Part | Where | To add one |
|---|---|---|
| Tools | `tools.yaml`, code in `tools/` | Add an entry. A tool is either a Python function or a tool on any MCP server |
| News outlets | `sources.yaml` | Add its name, the words learners use for it, and its RSS feed |
| Teaching modes | `skills/<name>/SKILL.md` (Agent Skills format) | Add a folder with instructions and `allowed-tools` |

**Finding a subject**

- *Named outlet:* `find_news` reads the outlet's RSS feed. The code matches the outlet's name itself, including when Gemma calls web search instead.
- *Topic:* `web_search` goes through the `donsetch` MCP server.
- *Choosing:* results are a numbered list, and `open_item` takes a number. The model never supplies an address, so it can only open what a search returned.
- *Video:* a pasted YouTube link is detected by the code. `yt-dlp` fetches human-written Arabic captions, or automatic captions if the video's own language is Arabic. Machine-translated tracks are refused, and a video with no Arabic captions is declined.
- *Long videos:* captions are split into sections of about 14,000 characters, and `next_section` moves on.

Tool results go into the system prompt instead of tool-role messages, because Gemma sometimes emits only its thinking marker right after a tool message. Results and subjects are marked as untrusted, and all tools are read-only.

After a subject's first reply, Gemma prepares six questions from it: the main idea, why and what it means, larger ideas to argue about, and the learner's own views. They avoid small details, because the goal is practising Arabic, and where it fits they steer toward the structures this learner gets wrong. Each turn offers the next one, which it can adapt to what the learner just said.

Opening a subject costs one slow turn, because Gemma has to read it: about 20 s for a 5,000-token video section on the test machine. The spoken "one moment" plays first, and later turns are cached.

## Learner record

Sessions, what was said, and errors by grammar concept are stored locally in `data/learner.db`. After each reply is spoken, Gemma checks what the learner said, so this never delays the conversation.

An error is kept only if its wrong words really appear in what was said. Cards are only for the Arabic language: facts, names, numbers and foreign words never get one. Speech recognition can mishear words but rarely invents a grammar pattern, so word-choice errors in speech don't get cards. Words Gemma judges misheard are dropped, and the learner can remove any card with "That's not what I said".

Each error is matched to a grammar concept in `cards.yaml`, which holds a hand-written one-line reminder and a lesson that opens only when the learner taps "Explain this". For rules the learner has already met, the tutor gives a hint and lets them try again, and gives the correct form if they get it wrong again.

## Sessions and follow-up

Each topic is its own session, saved with its history, subject and list of options. Opening a new subject starts a new session and keeps the old one to return to. The page lists sessions with their turn counts, and reconnecting resumes the latest.

Concepts the learner has got wrong come back on a schedule of 1, 3, 7 and 21 days, moving further out after a success and back after a failure. A follow-up isn't a separate exercise: at most every four turns, the tutor asks a question about whichever topic is active that the answer needs that structure for, without saying it's a review. A focused check then decides whether the learner used it correctly. A concept counts as learned after correct, unprompted use on two different days.

## Level

The learner's level is estimated continuously, with no setup. After each turn of four words or more, Gemma rates what was said, and the estimate moves toward that rating, adjusted for how many errors there were. Saying they don't understand lowers it. Levels only change past a clear margin, so they don't flip back and forth.

The level sets how the tutor speaks, how directly it corrects, and how demanding its questions are. Cards switch to Arabic, with proper grammar terms, for advanced learners. It's stored in `data/learner.db`.

## Models and settings

| Model | Source | Files used | Size | License |
|---|---|---|---|---|
| Voxtral Mini 4B Realtime Arabic | `mistralai/Voxtral-Mini-4B-Realtime-Arabic` | `consolidated.safetensors`, `params.json`, `tekken.json` | 8.25 GB | Apache-2.0 |
| Gemma 4 26B-A4B QAT | `unsloth/gemma-4-26B-A4B-it-qat-GGUF` | `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` | 13.3 GB | Apache-2.0 |
| Gemma MTP draft head | Same repository | `MTP/mtp-gemma-4-26B-A4B-it-Q4_0.gguf` | 0.23 GB | Apache-2.0 |
| Arabic-TTS-Spark | `IbrahimSalah/Arabic-TTS-Spark` | `LLM/` (converted), `BiCodec/`, `wav2vec2-large-xlsr-53/`, code and config | 1.0 GB GGUF, 0.6 GB decoder, 1.2 GB wav2vec | Non-commercial (`fair-noncommercial-research-license`) |

| Part | Settings |
|---|---|
| Voxtral | Greedy (temperature 0, fixed by vLLM). `--max-model-len 1024` (82 s per session; longer turns continue in a new session), `--max-num-seqs 1`, `--gpu-memory-utilization 0.91`, PIECEWISE CUDA graphs, `VLLM_USE_FLASHINFER_SAMPLER=0`, `ninja` on `PATH` |
| Gemma, tutor reply | Temperature 1.0, top_p 0.95, top_k 64 (Google's values). Thinking forced off with `--reasoning off` and `enable_thinking: false`. Maximum 300 tokens; last 24 messages of history |
| Gemma, vowelling | Temperature 0, maximum 600 tokens |
| Gemma server | `-c 16384`, KV cache `q8_0`, `--n-cpu-moe 17`, `--spec-type draft-mtp --spec-draft-n-max 4`, `--parallel 2 -kvu --no-cache-idle-slots` |
| Spark language model | BF16 GGUF, `-c 2048`. Temperature 0.8, top_p 0.95, top_k 50 (vendor card), min_p 0, repeat penalty 1.0 |
| Spark voice | No-transcript cloning mode; the reference voice is read once at startup. Output is 16 kHz |

The tutor's system prompt tells Gemma to begin with «نقول: » and the corrected sentence when the learner makes a mistake. It is in `prompts/system.txt`.

### Things that are easy to get wrong

- **Convert Spark to BF16, not F16.** The F16 GGUF returns NaN predictions.
- **Force Gemma's thinking off.** llama.cpp enables it by default, which adds 4–12 s and can return empty replies.
- **Give Spark full tashkeel.** It is trained only on vowelled text.
- **Load Spark's service on the CPU first.** The full model does not fit on GPU0 at startup. The service reads the reference voice, drops the language model and wav2vec, then moves only the decoder to the GPU (0.59 GB).
- **Expect occasional startup crashes on this CPU.** Fresh PyTorch processes sometimes die with "Illegal instruction" on this non-AVX2 Xeon, at the first `torch.cos` call. The cause is unknown, and `ATEN_CPU_CAPABILITY` and `MKL_ENABLE_INSTRUCTIONS` did not stop it. `scripts/start.sh` retries up to four times.

## Frontend

The frontend is one static file, `index.html`, with no build step or external libraries. FastAPI serves it at `/`.

- **Microphone:** an inline AudioWorklet downsamples to 16 kHz mono and sends 80 ms frames of PCM16 (1280 samples). Echo cancellation, noise suppression and automatic gain are on.
- **Secure context:** browsers only allow the microphone on HTTPS or `localhost`. The page is reached through a self-signed HTTPS address on the local network, or an SSH tunnel to `localhost:8791`.
- **Controls:** hold the button or the space bar to talk, with a 5-minute limit per turn. A text box allows typing instead, and "New conversation" clears the history.
- **Display:** each tutor message shows the reply, then the vowelled text the voice received, then the time to first audio.
- **Playback:** WAV sentences are queued with the Web Audio API so they play back to back.

### WebSocket protocol (`/ws`)

| Direction | Message | Meaning |
|---|---|---|
| Browser to server | `{"type":"start"}` | The learner started talking |
| Browser to server | Binary | 80 ms of PCM16 at 16 kHz |
| Browser to server | `{"type":"stop"}` | The learner stopped talking |
| Browser to server | `{"type":"text","text":…}` | Typed message |
| Browser to server | `{"type":"reset"}` | Clear the conversation |
| Server to browser | `partial` | Live transcript so far |
| Server to browser | `final` | Final transcript |
| Server to browser | `assistant` | Reply text so far |
| Server to browser | `tashkeel` | Vowelled text spoken so far |
| Server to browser | `text_only` | A sentence was shown but not spoken |
| Server to browser | `timing` | Stage timings for the turn |
| Server to browser | `error` | Error message for the status line |
| Server to browser | Binary | One WAV sentence |

## Hardware and performance

Measured on an HP Z820 with two RTX 3060 12 GB cards, 125 GB RAM and a Xeon E5-2687W v2 (no AVX2). Timing comes from an end-to-end test using synthetic speech over the real WebSocket, 10 turns.

| Measure | Result |
|---|---|
| Time from end of speech to first audio | 5.0 s median, 4.6–6.3 s; 8.0 s on the first turn |
| Transcript ready | 0.75 s |
| Reply complete | about 1.6 s after end of speech |
| Vowelling the first sentence | about 2.1 s |
| Spark for the first sentence | about 1.2 s |
| GPU memory free with everything running | GPU0 about 600 MiB, GPU1 about 1050 MiB |

| Quality check | Result |
|---|---|
| Voxtral on human MSA | 0.12 % character error on 12 clips, 0.24 % on 20 clips by an earlier method |
| Gemma vowelling, 40 MSA paragraphs of SadeedDiac-25 | 2.1 % case-ending errors, 4.5 % word errors, ignoring sukun. 3 paragraphs had changed letters and are excluded |
| Tutor corrections, 7 error types | 6 of 7 caught in a text-only test; 5 of 7 right through the full chain with synthetic speech |
| Blind listening, 12 sentences with grammar-dependent endings | Spark marked wrong on 0 or 1, the earlier Habibi voice on 9 |

## Adapting to other hardware

`scripts/configure.py` detects the NVIDIA GPUs and system memory, or previews other hardware with `--gpus` and `--ram`. It tries every placement of the three GPU workloads, keeps the one that leaves the most of Gemma on the GPU, and writes `GPU_ASR`, `GPU_LLM`, `GPU_VOICE`, `GEMMA_CPU_MOE` and `VOXTRAL_GPU_FRACTION` to `.env`.

| Workload | GPU memory | Can it shrink? |
|---|---|---|
| Voxtral with 82 s sessions | 10.85 GB | No, it needs one card with about 11.4 GB free |
| Spark language model and decoder | 2.1 GB | No |
| Gemma 4 26B-A4B + draft head | 14.9 GB with everything on the GPU | Yes, 409 MB less per layer moved to the CPU, down to 2.6 GB at 30 layers |

The planner keeps 650 MB free on each GPU in use and allows for a desktop on the GPU driving a monitor. System memory use was measured at about 17 GB at 16 layers, and each extra layer on the CPU adds about 0.4 GB.

Gemma's speed depends on the CPU as layers move there. On the test machine it ran at 46 tokens/s with 10 layers on the CPU, 43 with 14, 34 with 22 and 28 with 30. Only the two-card layout has been run end to end; the others are calculated from these measurements.

## Running it

```bash
scripts/start.sh     # starts all five processes, each with an 8-hour limit
scripts/stop.sh      # stops them
```

From another device, run `./install.sh --lan` to enable HTTPS, because browsers only allow the microphone on HTTPS or `localhost`. Alternatively, open a tunnel and visit `http://localhost:8791`:

```bash
ssh -L 8791:127.0.0.1:8791 <user>@<server>
```

The tutor needs both GPUs, so other GPU workloads have to be stopped first.

## Current limits

- The tutor is push-to-talk, not full duplex.
- Explanations in other languages are text only.
- Voxtral sometimes corrects a learner's mistake while transcribing, which hides it from the tutor. This has been seen once on synthetic speech and has not been measured on real learners.
- About 1 word in 50 can still get a wrong ending from Gemma's vowelling, and Spark reads what it is given.
- Gemma can still make grammar errors of its own.
- The possessive-phrase (إضافة) correction is unreliable.
- There are no user accounts, and conversations are not saved. Only stage timings are logged.

See [ROADMAP.md](ROADMAP.md) for what comes next.
