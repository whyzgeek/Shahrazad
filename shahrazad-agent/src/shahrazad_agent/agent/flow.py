"""Guided session flow: conversation → review notes → summary.

The system drives the lesson so the learner always knows where they are.
Each stage auto-advances when its goal is met; the learner may skip a stage
at any time (`skip_stage` control message). Progress is published on the
`shahrazad-flow` data topic so the UI can render a stepper.

Practice drills are started manually from the sidebar (Practice button).
The review stage pauses the main lesson and points the learner at notes;
it does not auto-run drills.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from livekit import rtc
from livekit.agents.voice.agent_session import AgentSession

from shahrazad_agent.diacritization.mishkal import diacritize

if TYPE_CHECKING:
    from shahrazad_agent.agent.fanout import SessionRuntime
    from shahrazad_agent.drills.controller import DrillController

logger = logging.getLogger("shahrazad.flow")

DATA_TOPIC_FLOW = "shahrazad-flow"

Stage = Literal["conversation", "review", "summary", "complete"]


@dataclass
class SessionFlow:
    runtime: SessionRuntime
    drill_controller: DrillController
    session: AgentSession
    conversation_turns_target: int = 6
    max_review_drills: int = 3
    tashkeel_timeout_ms: int = 300

    stage: Stage = "conversation"
    turns_done: int = 0
    drills_done: int = 0
    drills_target: int = 0
    drills_passed: int = 0

    _skip_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _advance_task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        await self._publish_stage()

    def on_learner_turn(self) -> None:
        """Called for every normal (non-drill) learner turn."""
        if self.stage != "conversation":
            return
        self.turns_done += 1
        asyncio.create_task(self._publish_stage())
        if self.turns_done >= self.conversation_turns_target:
            self._begin_advance("review")

    def on_manual_drill_completed(self, *, passed: bool) -> None:
        """Track sidebar Practice drills for the session summary."""
        self.drills_done += 1
        if passed:
            self.drills_passed += 1
        asyncio.create_task(self._publish_stage())

    def skip_stage(self) -> None:
        """Learner chose to skip the current stage."""
        logger.info("skip requested at stage=%s", self.stage)
        if self.stage == "conversation":
            self._begin_advance("review")
        elif self.stage == "review":
            self._skip_event.set()
        elif self.stage == "summary":
            self._skip_event.set()

    def _begin_advance(self, target: Stage) -> None:
        if self._advance_task is not None and not self._advance_task.done():
            return
        self._advance_task = asyncio.create_task(self._run_from(target))

    async def _run_from(self, target: Stage) -> None:
        try:
            if target == "review":
                await self._run_review()
            await self._run_summary()
        except Exception:  # noqa: BLE001
            logger.exception("session flow failed at stage=%s", self.stage)

    async def _run_review(self) -> None:
        from shahrazad_agent.agent.realtime_control import pause_conversation_replies

        self.stage = "review"
        self._skip_event.clear()

        # Pause the main lesson for the rest of the session. Practice drills
        # run from the sidebar; Realtime must not keep chatting over them.
        await pause_conversation_replies(self.session)

        # Fan-out is async; wait so the sidebar shows the latest notes.
        await self.runtime.wait_for_fanouts(timeout=12.0)

        errors = await self.runtime.store.list_errors(self.runtime.session_id)
        open_notes = [e for e in errors if not e.get("resolved_at")]
        self.drills_target = len(open_notes)
        self.drills_done = 0
        await self._publish_stage()

        if open_notes:
            await self._say(
                "انتهت المحادثة. راجع الملاحظات على الشاشة، "
                "واضغط «تدرّب» على ما تريد. عندما تنتهي، اضغط تخطّي."
            )
        else:
            await self._say("لم أسجّل ملاحظات. أحسنت!")

        # Stay in review until the learner skips (after optional Practice).
        await self._skip_event.wait()

    async def _run_summary(self) -> None:
        self.stage = "summary"
        self._skip_event.clear()
        await self._publish_stage()

        errors = await self.runtime.store.list_errors(self.runtime.session_id)
        total = len(errors)
        resolved = sum(1 for e in errors if e.get("resolved_at"))

        summary_ar = (
            f"أحسنت! تحدثنا {self.turns_done} مرات، "
            f"وسجّلت {total} ملاحظات، عالجنا منها {resolved}. "
            "راجع الملاحظات على الشاشة، وإلى اللقاء!"
        )
        await self._say(summary_ar)

        self.stage = "complete"
        await self._publish(
            {
                "type": "session_summary",
                "turns_done": self.turns_done,
                "errors_total": total,
                "errors_resolved": resolved,
                "drills_done": self.drills_done,
                "drills_passed": self.drills_passed,
            }
        )
        await self._publish_stage()

    async def _say(self, text: str) -> None:
        try:
            spoken = await diacritize(text, timeout_ms=self.tashkeel_timeout_ms)
            handle = self.session.say(spoken, allow_interruptions=False)
            await handle.wait_for_playout()
        except Exception:  # noqa: BLE001
            logger.warning("flow say failed", exc_info=True)

    async def _publish_stage(self) -> None:
        await self._publish(
            {
                "type": "stage",
                "stage": self.stage,
                "progress": {
                    "turns_done": self.turns_done,
                    "turns_target": self.conversation_turns_target,
                    "drills_done": self.drills_done,
                    "drills_target": self.drills_target,
                    "drills_passed": self.drills_passed,
                },
            }
        )

    async def _publish(self, payload: dict) -> None:
        room: rtc.Room | None = self.runtime.room
        if room is None:
            return
        try:
            await room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                topic=DATA_TOPIC_FLOW,
                reliable=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning("failed to publish flow event", exc_info=True)
