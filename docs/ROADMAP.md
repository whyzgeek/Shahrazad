# Roadmap

Shahrazad grows in small phases, and each one should work on its own before the next begins.

## Now

The tutor holds a push-to-talk conversation in Modern Standard Arabic, corrects mistakes, and speaks and shows fully vowelled replies. Everything runs locally.

## Phase 1: tools

Give the tutor read-only tools it can decide to use during a conversation, starting with web search for topics such as the latest news. Gemma 4 supports tool calling, so the main work is the tool loop in `app.py` and a spoken "one moment" while a search runs.

Tool results are untrusted text from the internet. They are treated only as material to discuss, sources are shown on screen, and tools are never given write access.

## Phase 2: discuss a YouTube video

The learner pastes a link, and the tutor discusses the video: it summarises it in simple Arabic, asks comprehension questions, answers the learner's questions, and argues a point with them.

Planned approach:

1. Fetch the video's Arabic captions when they exist.
2. When they don't, download the audio and transcribe it with Voxtral.
3. Fit the transcript into Gemma's context, using sections or a summary for long videos.
4. Add a discussion mode to the system prompt with a question-and-debate structure.

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
