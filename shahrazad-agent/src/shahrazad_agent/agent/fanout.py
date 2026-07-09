"""Background error fan-out orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from livekit import rtc
from openai import AsyncOpenAI, RateLimitError

from shahrazad_agent.audio.capture import TurnAudioBuffer
from shahrazad_agent.config import Settings
from shahrazad_agent.db.store import SessionStore
from shahrazad_agent.detectors.camel import score_dialect
from shahrazad_agent.detectors.judge import run_judge

if TYPE_CHECKING:
    from livekit.agents import Agent

    from shahrazad_agent.agent.flow import SessionFlow
    from shahrazad_agent.drills.controller import DrillController

logger = logging.getLogger("shahrazad.fanout")

DATA_TOPIC = "shahrazad-errors"


@dataclass
class SessionRuntime:
    session_id: str
    topic_id: str
    topic_title: str
    store: SessionStore
    settings: Settings
    audio_buffer: TurnAudioBuffer = field(default_factory=TurnAudioBuffer)
    learner_turn_index: int = -1
    tutor_turn_index: int = -1
    room: rtc.Room | None = None
    openai_client: AsyncOpenAI | None = None
    drill_controller: DrillController | None = None
    flow: SessionFlow | None = None
    agent: Agent | None = None
    pending_fanouts: set[asyncio.Task] = field(default_factory=set)
    _last_learner_text: str | None = None

    def next_turn_index(self) -> int:
        base = max(self.learner_turn_index, self.tutor_turn_index)
        return base + 1

    def track_fanout(self, task: asyncio.Task) -> None:
        self.pending_fanouts.add(task)
        task.add_done_callback(self.pending_fanouts.discard)

    async def wait_for_fanouts(self, timeout: float = 12.0) -> None:
        if not self.pending_fanouts:
            return
        pending = list(self.pending_fanouts)
        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout)
        except TimeoutError:
            logger.warning("timed out waiting for %d fan-out task(s)", len(pending))


async def run_fanout(
    runtime: SessionRuntime,
    *,
    turn_id: str,
    learner_text: str,
    turn_index: int,
    audio_path: str | None = None,
) -> None:
    """Run all detectors independently; never raise to caller."""
    settings = runtime.settings

    rows: list[dict[str, Any]] = []

    try:
        client = runtime.openai_client or AsyncOpenAI(api_key=settings.openai_api_key)
        camel = await score_dialect(learner_text)
        tutor_context = await runtime.store.get_latest_tutor_text(runtime.session_id) or ""
        for hit in await run_judge(
            client=client,
            learner_text=learner_text,
            topic_hint=runtime.topic_title,
            tutor_context=tutor_context,
        ):
            score = camel.p_msa if hit.kind == "dialect_drift" and camel.p_msa is not None else None
            rows.append(
                _error_row(
                    runtime=runtime,
                    turn_id=turn_id,
                    kind=hit.kind,
                    severity=hit.severity,
                    learner_text=hit.learner_text,
                    learner_audio_path=audio_path,
                    correct_form=hit.correct_form,
                    explanation_ar=hit.explanation_ar,
                    explanation_en=hit.explanation_en,
                    detector="llm_judge",
                    score=score,
                )
            )
    except RateLimitError:
        logger.warning(
            "LLM judge skipped — OpenAI quota exceeded (grammar/dialect errors not recorded)"
        )
    except Exception:  # noqa: BLE001
        logger.exception("LLM judge failed for turn %d", turn_index)

    if rows:
        await runtime.store.add_errors(rows)
        await _publish_error_count(runtime)
        logger.info(
            "fan-out wrote %d errors for turn %d (session %s)",
            len(rows),
            turn_index,
            runtime.session_id,
        )
        await _inject_error_notes(runtime, turn_index)
    else:
        logger.debug("fan-out: no errors for turn %d", turn_index)


async def _inject_error_notes(runtime: SessionRuntime, turn_index: int) -> None:
    """Push silent error notes for recast only (no mid-chat drill tools)."""
    agent = runtime.agent
    if agent is None:
        return
    try:
        from shahrazad_agent.agent.prompts import build_error_summary_block

        errors = await runtime.store.get_errors_for_prompt(
            runtime.session_id,
            max_turn_index=turn_index,
        )
        summary = build_error_summary_block(errors)
        if not summary:
            return
        chat_ctx = agent.chat_ctx.copy()
        chat_ctx.add_message(role="system", content=summary)
        maybe_awaitable = agent.update_chat_ctx(chat_ctx)
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable
    except Exception:  # noqa: BLE001
        logger.warning("failed to inject error notes into agent", exc_info=True)


def _error_row(
    *,
    runtime: SessionRuntime,
    turn_id: str,
    kind: str,
    severity: str,
    learner_text: str,
    learner_audio_path: str | None,
    correct_form: str,
    explanation_ar: str,
    explanation_en: str,
    detector: str,
    score: float | None,
) -> dict[str, Any]:
    return {
        "session_id": runtime.session_id,
        "turn_id": turn_id,
        "kind": kind,
        "severity": severity,
        "learner_text": learner_text,
        "learner_audio_path": learner_audio_path,
        "correct_form": correct_form,
        "explanation_ar": explanation_ar,
        "explanation_en": explanation_en,
        "detector": detector,
        "score": score,
    }


async def _publish_error_count(runtime: SessionRuntime) -> None:
    if runtime.room is None:
        return
    total = await runtime.store.count_errors(runtime.session_id)
    payload = json.dumps({"type": "error_count", "total": total}).encode("utf-8")
    try:
        await runtime.room.local_participant.publish_data(payload, topic=DATA_TOPIC, reliable=True)
    except Exception:  # noqa: BLE001
        logger.warning("failed to publish error count", exc_info=True)
