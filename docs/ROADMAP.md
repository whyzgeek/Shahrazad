# Roadmap

Shahrazad grows in small phases, and each one should work on its own before the next begins.

## Now

The tutor holds a push-to-talk conversation in Modern Standard Arabic, corrects mistakes, and speaks and shows fully vowelled replies. Everything runs locally.

## Phase 1: subjects (done)

The tutor can find a subject from a named news outlet or a web search, or from a pasted YouTube link with Arabic captions, and discuss it over many turns.

## Phase 2: access control

Add a login before the tutor is shared more widely.

## Phase 3: learning features

- Save the learner's mistakes during conversation, and review them as notes.
- Practice drills built from those mistakes, then a short wrap-up.
- Choose a topic and level when starting a session.
- Interval review over multiple sessions.

## Phase 4: more natural conversation

- Automatic detection of when the learner starts and stops talking, with no button.
- Lower delay, mainly by vowelling sentence by sentence while the reply is still being written.
- Speaking English and Persian explanations.
- True full duplex, through an Arabic fine-tune of a full-duplex model.

## Hardware

- Support smaller GPUs by testing a smaller tutor model and a lighter speech recognizer.
- Confirm the calculated layouts in `scripts/configure.py` on real hardware beyond two 12 GB cards.

## Before publishing a model

Spark's weights are non-commercial, so its converted GGUF can be shared only if its terms allow redistribution. The current reference voice is not part of this repository and has to be replaced by one with clear rights.
