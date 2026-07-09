"""Process learner turns for persistence, fan-out, and session flow.

Under OpenAI Realtime, `on_user_turn_completed` often sees empty text because
audio replies are generated before input transcription finishes. Final
`user_input_transcribed` events are the reliable source of learner text.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from livekit.agents import llm

from shahrazad_agent.agent.fanout import SessionRuntime, run_fanout
from shahrazad_agent.agent.prompts import build_error_summary_block
from shahrazad_agent.drills.scoring import looks_like_latin_stt

logger = logging.getLogger("shahrazad.learner")


async def process_learner_utterance(
    runtime: SessionRuntime,
    learner_text: str,
    *,
    turn_ctx: llm.ChatContext | None = None,
    stop_if_drill: bool = False,
) -> bool:
    """Persist a learner turn, run fan-out, and advance SessionFlow.

    Returns True if a drill consumed the utterance (caller may raise StopResponse).
    """
    text = (learner_text or "").strip()
    if not text:
        return False

    # Deduplicate: Realtime may deliver the same final transcript via multiple hooks.
    if runtime._last_learner_text == text and runtime.learner_turn_index >= 0:
        logger.debug("skipping duplicate learner utterance: %s", text[:40])
        return False

    controller = runtime.drill_controller
    # Phantom Latin STT (noise / echo / romanization) — never treat as a real turn
    # outside an active drill (drills have their own rescue path).
    if looks_like_latin_stt(text) and not (controller is not None and controller.is_active):
        logger.info("dropping latin STT phantom in conversation: %r", text[:60])
        # Discard buffered audio so it does not attach to the next real turn.
        runtime.audio_buffer.reset()
        return False

    turn_index = runtime.next_turn_index()
    runtime.learner_turn_index = turn_index
    runtime._last_learner_text = text
    turn_id = str(uuid.uuid4())

    audio_path = await runtime.audio_buffer.finalize_wav(runtime.session_id, turn_index)

    if controller is not None and controller.consume_learner_repeat(text, audio_path):
        await runtime.store.add_turn(
            session_id=runtime.session_id,
            speaker="learner",
            text=text,
            turn_index=turn_index,
            turn_id=turn_id,
            audio_path=audio_path,
        )
        logger.info("drill consumed learner turn %d", turn_index)
        return True if stop_if_drill else False

    await runtime.store.add_turn(
        session_id=runtime.session_id,
        speaker="learner",
        text=text,
        turn_index=turn_index,
        turn_id=turn_id,
    )
    if audio_path:
        await runtime.store.update_turn_audio(turn_id, audio_path)

    task = asyncio.create_task(
        run_fanout(
            runtime,
            turn_id=turn_id,
            learner_text=text,
            turn_index=turn_index,
            audio_path=audio_path,
        )
    )
    runtime.track_fanout(task)

    if runtime.flow is not None:
        runtime.flow.on_learner_turn()

    if turn_ctx is not None and turn_index >= 2:
        errors = await runtime.store.get_errors_for_prompt(
            runtime.session_id,
            max_turn_index=turn_index - 2,
        )
        summary = build_error_summary_block(errors)
        if summary:
            turn_ctx.add_message(role="system", content=summary)

    logger.info("processed learner turn %d (%d chars)", turn_index, len(text))
    return False
