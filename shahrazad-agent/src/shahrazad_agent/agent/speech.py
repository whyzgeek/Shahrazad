"""OpenAI Realtime (conversation) + TTS (review proxy) factories."""

from __future__ import annotations

from livekit.plugins import openai
from openai.types import realtime

from shahrazad_agent.agent.realtime_control import _CONVERSATION_VAD
from shahrazad_agent.config import Settings

OPENAI_TTS_INSTRUCTIONS = """\
You are Shahrazad, a warm and encouraging Modern Standard Arabic (MSA) tutor.
Speak with natural, lively Arabic intonation that matches the meaning:
- Questions sound genuinely curious, rising at the end.
- Praise sounds delighted and warm.
- Corrections sound gentle and reassuring, never scolding.
- Keep a moderate, clear pace suitable for a language learner.
Pronounce MSA precisely, respecting the written diacritics.
"""

# Drills use session.say() → TTS (slower than Realtime chat). Speak briskly.
DRILL_TTS_INSTRUCTIONS = """\
You are Shahrazad leading a quick MSA practice drill.
Speak clearly but briskly — slightly faster than a normal lesson.
Short cues and model sentences only; no dramatic pauses.
Pronounce MSA precisely, respecting the written diacritics.
"""

DRILL_TTS_SPEED = 1.2
CONVERSATION_TTS_SPEED = 1.0

_ARABIC_STT_PROMPT = (
    "Transcribe Modern Standard Arabic (الفصحى) in Arabic script only. "
    "Never use Latin letters or romanization."
)


def create_realtime_model(settings: Settings) -> openai.realtime.RealtimeModel:
    """Speech-in / speech-out model for the live tutor session."""
    return openai.realtime.RealtimeModel(
        model=settings.openai_realtime_model,
        voice=settings.openai_realtime_voice,
        api_key=settings.openai_api_key,
        modalities=["text", "audio"],
        input_audio_transcription=realtime.AudioTranscription(
            model=settings.openai_transcription_model,
            language=settings.openai_transcription_language or "ar",
            prompt=_ARABIC_STT_PROMPT,
        ),
        input_audio_noise_reduction="near_field",
        turn_detection=_CONVERSATION_VAD,
        speed=1.0,
    )


def create_tts(settings: Settings) -> openai.TTS:
    """Text TTS for drills/flow say() and the FastAPI /tts review proxy."""
    return openai.TTS(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        instructions=OPENAI_TTS_INSTRUCTIONS,
        speed=CONVERSATION_TTS_SPEED,
        api_key=settings.openai_api_key,
    )
