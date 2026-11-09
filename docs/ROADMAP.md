# Roadmap

Shahrazad grows in small phases, and each one should work on its own before the next begins.

## Now

The tutor holds a push-to-talk conversation in Modern Standard Arabic, corrects mistakes, and speaks and shows fully vowelled replies. Everything runs locally.

## Phase 1: subjects (done)

The tutor can find a subject from a named news outlet or a web search, or from a pasted YouTube link with Arabic captions, and discuss it over many turns.

## Phase 2: access control

Add a login before the tutor is shared more widely.

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
- Lower delay, mainly by vowelling sentence by sentence while the reply is still being written.
- Speaking explanations in other languages.
- True full duplex, through an Arabic fine-tune of a full-duplex model.

## Hardware

- Support smaller GPUs by testing a smaller tutor model and a lighter speech recognizer.
- Confirm the calculated layouts in `scripts/configure.py` on real hardware beyond two 12 GB cards.

## Before publishing a model

Spark's weights are non-commercial, so its converted GGUF can be shared only if its terms allow redistribution. The default voice is a CC0 clip, so it can be shared.
