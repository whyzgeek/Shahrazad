"""Helpers to pause/resume OpenAI Realtime auto-replies during drills."""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents.voice.agent_session import AgentSession
from openai.types import realtime

logger = logging.getLogger("shahrazad.realtime_control")

_CONVERSATION_VAD = realtime.realtime_audio_input_turn_detection.SemanticVad(
    type="semantic_vad",
    create_response=True,
    eagerness="auto",
    interrupt_response=True,
)

# Keep VAD for end-of-turn / transcripts, but do not auto-create tutor replies.
_DRILL_VAD = realtime.realtime_audio_input_turn_detection.SemanticVad(
    type="semantic_vad",
    create_response=False,
    eagerness="auto",
    interrupt_response=True,
)


def _realtime_model(session: AgentSession) -> Any | None:
    model = session.llm
    if model is None:
        return None
    if not hasattr(model, "update_options"):
        return None
    return model


async def pause_conversation_replies(session: AgentSession) -> None:
    """Stop Realtime from chatting over drills."""
    try:
        await session.interrupt(force=True)
    except Exception:  # noqa: BLE001
        logger.debug("interrupt before review failed", exc_info=True)

    model = _realtime_model(session)
    if model is None:
        return
    try:
        model.update_options(turn_detection=_DRILL_VAD)
        logger.info("Realtime auto-replies paused for review/drills")
    except Exception:  # noqa: BLE001
        logger.warning("failed to pause Realtime turn detection", exc_info=True)


async def resume_conversation_replies(session: AgentSession) -> None:
    """Restore normal Realtime conversation turn detection."""
    model = _realtime_model(session)
    if model is None:
        return
    try:
        model.update_options(turn_detection=_CONVERSATION_VAD)
        logger.info("Realtime auto-replies resumed")
    except Exception:  # noqa: BLE001
        logger.warning("failed to resume Realtime turn detection", exc_info=True)


async def set_transcription_prompt(
    session: AgentSession,
    *,
    language: str = "ar",
    model: str | None = None,
    prompt: str,
) -> None:
    """Update Realtime input transcription (language + prompt) for drills."""
    rt = _realtime_model(session)
    if rt is None:
        return
    try:
        kwargs: dict[str, Any] = {
            "language": language or "ar",
            "prompt": prompt,
        }
        if model:
            kwargs["model"] = model
        rt.update_options(input_audio_transcription=realtime.AudioTranscription(**kwargs))
        logger.info("Realtime transcription prompt updated for drill")
    except Exception:  # noqa: BLE001
        logger.warning("failed to update Realtime transcription prompt", exc_info=True)


def set_drill_speech_pace(session: AgentSession, *, enabled: bool) -> None:
    """Speed up TTS/Realtime speech during drills (say() path is slower than chat)."""
    from shahrazad_agent.agent.speech import (
        CONVERSATION_TTS_SPEED,
        DRILL_TTS_INSTRUCTIONS,
        DRILL_TTS_SPEED,
        OPENAI_TTS_INSTRUCTIONS,
    )

    speed = DRILL_TTS_SPEED if enabled else CONVERSATION_TTS_SPEED
    instructions = DRILL_TTS_INSTRUCTIONS if enabled else OPENAI_TTS_INSTRUCTIONS

    tts = getattr(session, "tts", None)
    if tts is not None and hasattr(tts, "update_options"):
        try:
            tts.update_options(speed=speed, instructions=instructions)
        except Exception:  # noqa: BLE001
            logger.debug("failed to update TTS pace", exc_info=True)

    rt = _realtime_model(session)
    if rt is not None:
        try:
            rt.update_options(speed=speed)
        except Exception:  # noqa: BLE001
            logger.debug("failed to update Realtime speech speed", exc_info=True)

    logger.info("drill speech pace %s (speed=%.2f)", "on" if enabled else "off", speed)
