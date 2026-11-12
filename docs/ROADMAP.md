# Roadmap

Shahrazad grows in small phases, and each one should work on its own before the next begins.

## Now

The tutor holds a push-to-talk conversation in Modern Standard Arabic, corrects mistakes, and speaks and shows fully vowelled replies. It runs locally, or any of its three parts can run in the cloud through one OpenRouter key.

## Phase 1: subjects (done)

The tutor can find a subject from a named news outlet or a web search, or from a pasted YouTube link with Arabic captions, and discuss it over many turns.

## Phase 2: access control (done)

One shared password (`TUTOR_PASSWORD`) for the page and its WebSocket, with a signed cookie, and a check that a WebSocket comes from the tutor's own page. Separate accounts with separate learner records would come next if several people share one server.

## Phase 3: learning features

Everything here runs without setup screens or extra questions, and the conversation never pauses.

- Specific questions tied to the material, in place of generic ones (done).
- A local learner record of sessions and errors, by grammar concept (done).
- Every error is corrected. A brief card appears in a side panel, and a learner who wants more taps "Explain this" for a fuller lesson. A first error may be a slip, so nothing assumes they don't know the rule (done).
- Hints in place of answers for rules the learner has already seen (done).
- Sessions by topic that the learner can switch between and continue (done).
- Spaced follow-up over days, asked within whichever topic is active. A concept counts as learned only when it's used correctly in free speech on two different days (done).
- Continuous assessment of the learner's level, adjusting speech, corrections, cards and questions (done).

## Phase 4: more natural conversation

- Automatic detection of when the learner starts and stops talking, with no button.
- Lower delay, by vowelling and speaking each sentence while the reply is still being written (done).
- A dedicated vowelling model. Tashkeel-v3 (0.2B) was tested in November 2026: about 40 times faster than Gemma on the CPU, but it doubled marks and letters on real tutor replies, and on SadeedDiac-25 it got 3.3% of case endings wrong against Gemma's 2.2% (8.9% of words against 4.5%). Gemma stays until a model beats it on case endings.
- More of Gemma on the GPU. Its expert layers partly run on the CPU, which costs 1.7–3 s per reply before the first word. A smaller hearing model would free GPU memory for them.
- Speaking explanations in other languages.
- True full duplex, through an Arabic fine-tune of a full-duplex model.

## Hardware

- Support smaller GPUs by testing a smaller tutor model and a lighter speech recognizer.
- Confirm the calculated layouts in `scripts/configure.py` on real hardware beyond two 12 GB cards.

## Before publishing a model

Spark's weights are non-commercial, so its converted GGUF can be shared only if its terms allow redistribution. The default voice is a CC0 clip, so it can be shared.
