"""Repeat-until-perfect drill state machine (pronunciation + grammar)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from livekit.agents.voice.agent_session import AgentSession
from openai import AsyncOpenAI

from shahrazad_agent.diacritization.mishkal import diacritize
from shahrazad_agent.drills.grammar import generate_grammar_drill_sentences
from shahrazad_agent.drills.scoring import (
    looks_like_latin_stt,
    score_drill_attempt,
    score_grammar_drill,
)

if TYPE_CHECKING:
    from shahrazad_agent.agent.fanout import SessionRuntime

logger = logging.getLogger("shahrazad.drill")

DATA_TOPIC = "shahrazad-drill"
DrillPhase = Literal["idle", "reference", "repeat", "feedback"]
DrillType = Literal["pronunciation", "grammar"]

_GRAMMAR_KINDS = frozenset({"grammar", "vocabulary", "dialect_drift"})


@dataclass
class DrillRepeatPayload:
    learner_text: str
    audio_path: str | None


@dataclass
class ActiveDrill:
    drill_type: DrillType
    sentences: list[str]
    error_entry_id: str | None
    sentence_index: int = 0
    phase: DrillPhase = "reference"
    attempt: int = 0
    total_attempts: int = 0


@dataclass
class DrillController:
    runtime: SessionRuntime
    session: AgentSession | None = None
    tashkeel_timeout_ms: int = 300
    accuracy_threshold: float = 80.0
    max_attempts: int = 5
    grammar_max_attempts_per_sentence: int = 3
    grammar_similar_count: int = 2
    endpointing_min: float = 0.7
    endpointing_max: float = 1.0
    conversation_endpointing_min: float = 0.5
    conversation_endpointing_max: float = 3.0

    _active: ActiveDrill | None = field(default=None, init=False, repr=False)
    _repeat_event: asyncio.Event = field(default_factory=asyncio.Event, init=False, repr=False)
    _repeat_payload: DrillRepeatPayload | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def interruption_mode(self) -> str:
        return "drill" if self._active is not None else "conversation"

    @property
    def is_active(self) -> bool:
        return self._active is not None

    @property
    def awaiting_repeat(self) -> bool:
        return self._active is not None and self._active.phase == "repeat"

    def bind_session(self, session: AgentSession) -> None:
        self.session = session

    async def start_drill(
        self,
        target_text: str,
        *,
        error_entry_id: str | None = None,
        drill_type: DrillType = "pronunciation",
    ) -> dict:
        """Run a single-target pronunciation drill."""
        target = target_text.strip()
        if not target:
            return {"status": "error", "message": "empty target_text"}

        async with self._lock:
            if self._active is not None:
                return {"status": "busy", "message": "drill already in progress"}

            if error_entry_id is None:
                error_entry_id = await self._resolve_error_for_target(target)

            self._active = ActiveDrill(
                drill_type=drill_type,
                sentences=[target],
                error_entry_id=error_entry_id,
            )

        try:
            return await self._run_loop()
        finally:
            await self._finish_drill()

    async def start_grammar_drill(
        self,
        error_entry_id: str,
        *,
        similar_count: int | None = None,
    ) -> dict:
        """Run a multi-sentence grammar drill linked to an error entry."""
        err = await self.runtime.store.get_error(error_entry_id)
        if err is None:
            return {"status": "error", "message": "error not found"}

        extras = self.grammar_similar_count if similar_count is None else similar_count
        extras = max(0, min(4, int(extras)))

        client = self.runtime.openai_client or AsyncOpenAI(
            api_key=self.runtime.settings.openai_api_key
        )
        sentences = await generate_grammar_drill_sentences(
            client=client,
            learner_text=err.get("learner_text", ""),
            correct_form=err.get("correct_form", ""),
            explanation_en=err.get("explanation_en", ""),
            explanation_ar=err.get("explanation_ar", ""),
            topic_hint=self.runtime.topic_title,
            similar_count=extras,
        )
        if not sentences:
            return {"status": "error", "message": "could not build practice sentences"}

        async with self._lock:
            if self._active is not None:
                return {"status": "busy", "message": "drill already in progress"}

            self._active = ActiveDrill(
                drill_type="grammar",
                sentences=sentences,
                error_entry_id=error_entry_id,
            )

        try:
            return await self._run_loop()
        finally:
            await self._finish_drill()

    async def start_drill_from_error(
        self,
        error_entry_id: str,
        *,
        sentence_count: int | None = None,
    ) -> dict:
        err = await self.runtime.store.get_error(error_entry_id)
        if err is None:
            return {"status": "error", "message": "error not found"}

        # sentence_count = total practice lines (1 correction + N-1 similar).
        similar: int | None = None
        if sentence_count is not None:
            total = max(1, min(5, int(sentence_count)))
            similar = total - 1

        kind = err.get("kind", "")
        if kind in _GRAMMAR_KINDS:
            return await self.start_grammar_drill(error_entry_id, similar_count=similar)

        target = (err.get("correct_form") or err.get("learner_text") or "").strip()
        if not target:
            return {"status": "error", "message": "no target text on error"}
        return await self.start_drill(
            target,
            error_entry_id=error_entry_id,
            drill_type="pronunciation",
        )

    def consume_learner_repeat(self, learner_text: str, audio_path: str | None) -> bool:
        if not self.awaiting_repeat:
            return False
        self._repeat_payload = DrillRepeatPayload(learner_text=learner_text, audio_path=audio_path)
        self._repeat_event.set()
        return True

    async def _run_loop(self) -> dict:
        assert self._active is not None
        assert self.session is not None

        from shahrazad_agent.agent.realtime_control import pause_conversation_replies

        drill = self._active
        all_passed = True
        last_score: float | None = None
        sentences_completed = 0

        # Pause the main lesson so Realtime does not chat over the drill.
        await pause_conversation_replies(self.session)
        from shahrazad_agent.agent.realtime_control import set_drill_speech_pace

        set_drill_speech_pace(self.session, enabled=True)
        await self._publish_transcript_section("practice")

        await self._publish(
            {
                "type": "drill_started",
                "drill_type": drill.drill_type,
                "sentences": drill.sentences,
                "error_entry_id": drill.error_entry_id,
            }
        )
        self._enter_drill_mode()

        if drill.drill_type == "grammar":
            await self._say_grammar_intro(drill.error_entry_id)
        max_per_sentence = (
            self.grammar_max_attempts_per_sentence
            if drill.drill_type == "grammar"
            else self.max_attempts
        )

        for sentence_index, target in enumerate(drill.sentences):
            drill.sentence_index = sentence_index
            drill.attempt = 0
            sentence_passed = False

            # Play the model sentence once per target. Retries only re-prompt;
            # feedback already includes the sentence so we don't say it twice.
            first_attempt_for_sentence = True
            while drill.attempt < max_per_sentence and not sentence_passed:
                drill.attempt += 1
                await self._set_drill_transcription_prompt(target)

                if first_attempt_for_sentence:
                    drill.phase = "reference"
                    reference = await diacritize(target, timeout_ms=self.tashkeel_timeout_ms)
                    # After the model sentence, wait for the learner — no "repeat" cue.
                    ref_handle = self.session.say(reference, allow_interruptions=True)
                    await ref_handle.wait_for_playout()
                    first_attempt_for_sentence = False

                drill.phase = "repeat"
                self._repeat_event.clear()
                self._repeat_payload = None
                try:
                    await asyncio.wait_for(self._repeat_event.wait(), timeout=120.0)
                except TimeoutError:
                    logger.warning(
                        "drill repeat timed out sentence=%d attempt=%d",
                        sentence_index,
                        drill.attempt,
                    )
                    await self._say("لم أسمعك.")
                    continue

                payload = self._repeat_payload
                if payload is None:
                    continue

                learner_text = payload.learner_text
                if looks_like_latin_stt(learner_text, target_text=target):
                    rescued = await self._retranscribe_arabic(payload.audio_path, target)
                    if rescued and not looks_like_latin_stt(rescued, target_text=target):
                        logger.info(
                            "rescued latin STT → Arabic: %r → %r",
                            learner_text[:40],
                            rescued[:40],
                        )
                        learner_text = rescued
                    else:
                        # Do not burn an attempt on a transcription failure.
                        drill.attempt -= 1
                        await self._say("بالعربية من فضلك.")
                        continue

                if drill.drill_type == "grammar":
                    score = score_grammar_drill(
                        transcript=learner_text,
                        target_text=target,
                        accuracy_threshold=self.accuracy_threshold,
                    )
                else:
                    score = await score_drill_attempt(
                        transcript=learner_text,
                        target_text=target,
                        accuracy_threshold=self.accuracy_threshold,
                    )

                last_score = score.accuracy_score
                drill.total_attempts += 1

                await self.runtime.store.add_drill_attempt(
                    session_id=self.runtime.session_id,
                    error_entry_id=drill.error_entry_id,
                    target_text=target,
                    attempt_number=drill.total_attempts,
                    accuracy_score=score.accuracy_score,
                    completeness_score=score.completeness_score,
                    fluency_score=score.fluency_score,
                    scoring_mode=score.scoring_mode,
                    passed=score.passed,
                    learner_audio_path=payload.audio_path,
                )

                await self._publish(
                    {
                        "type": "drill_attempt",
                        "drill_type": drill.drill_type,
                        "sentence_index": sentence_index,
                        "sentence_total": len(drill.sentences),
                        "attempt": drill.attempt,
                        "accuracy_score": score.accuracy_score,
                        "scoring_mode": score.scoring_mode,
                        "passed": score.passed,
                        "target": target,
                    }
                )

                if score.passed:
                    sentence_passed = True
                    await self._say("ممتاز!")
                    sentences_completed += 1
                    break

                if drill.attempt < max_per_sentence:
                    # Replay the target once; learner repeats immediately (no extra cue).
                    await self._say(target)

            if not sentence_passed:
                all_passed = False
                break

        if all_passed and drill.error_entry_id:
            await self.runtime.store.resolve_error(drill.error_entry_id)
            if drill.drill_type == "grammar":
                await self._say("أحسنت!")
            else:
                await self._say("ممتاز!")
        elif not all_passed:
            await self._say("لا بأس، لاحقاً.")

        await self._publish(
            {
                "type": "drill_completed",
                "drill_type": drill.drill_type,
                "passed": all_passed,
                "sentences_completed": sentences_completed,
                "sentence_total": len(drill.sentences),
                "last_score": last_score,
                "error_entry_id": drill.error_entry_id,
            }
        )

        flow = self.runtime.flow
        if flow is not None:
            flow.on_manual_drill_completed(passed=all_passed)

        return {
            "status": "completed",
            "drill_type": drill.drill_type,
            "passed": all_passed,
            "sentences_completed": sentences_completed,
            "sentence_total": len(drill.sentences),
            "last_score": last_score,
            "error_entry_id": drill.error_entry_id,
            "resolved": all_passed and drill.error_entry_id is not None,
        }

    async def _finish_drill(self) -> None:
        self._active = None
        self._restore_conversation_mode()
        await self._publish_transcript_section("conversation")
        await self._clear_drill_transcription_prompt()
        if self.session is not None:
            from shahrazad_agent.agent.realtime_control import set_drill_speech_pace

            set_drill_speech_pace(self.session, enabled=False)

        # Only resume Realtime chat if the main lesson is still in conversation.
        # After review/summary the lesson stays paused so Practice cannot be
        # interrupted by agenda questions.
        flow = self.runtime.flow
        if flow is not None and flow.stage == "conversation" and self.session is not None:
            from shahrazad_agent.agent.realtime_control import resume_conversation_replies

            await resume_conversation_replies(self.session)

    async def _publish_transcript_section(self, section: str) -> None:
        if self.runtime.room is None:
            return
        try:
            await self.runtime.room.local_participant.publish_data(
                json.dumps({"type": "section", "section": section}).encode("utf-8"),
                topic="shahrazad-transcript",
                reliable=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning("failed to publish transcript section", exc_info=True)

    async def _set_drill_transcription_prompt(self, target: str) -> None:
        """Bias Realtime STT toward Arabic script for the current drill sentence."""
        if self.session is None:
            return
        from shahrazad_agent.agent.realtime_control import set_transcription_prompt

        await set_transcription_prompt(
            self.session,
            language=self.runtime.settings.openai_transcription_language or "ar",
            model=self.runtime.settings.openai_transcription_model,
            prompt=(
                "Transcribe Modern Standard Arabic in Arabic script only. "
                f"The learner is repeating: {target}"
            ),
        )

    async def _clear_drill_transcription_prompt(self) -> None:
        if self.session is None:
            return
        from shahrazad_agent.agent.realtime_control import set_transcription_prompt
        from shahrazad_agent.agent.speech import _ARABIC_STT_PROMPT

        await set_transcription_prompt(
            self.session,
            language=self.runtime.settings.openai_transcription_language or "ar",
            model=self.runtime.settings.openai_transcription_model,
            prompt=_ARABIC_STT_PROMPT,
        )

    async def _retranscribe_arabic(self, audio_path: str | None, target: str) -> str | None:
        """Force Arabic STT on saved drill audio when Realtime returned Latin."""
        if not audio_path:
            return None
        from pathlib import Path

        path = Path(audio_path)
        if not path.is_file():
            return None

        client = self.runtime.openai_client or AsyncOpenAI(
            api_key=self.runtime.settings.openai_api_key
        )
        model = self.runtime.settings.openai_transcription_model
        try:
            with path.open("rb") as audio_file:
                result = await client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    language="ar",
                    prompt=(
                        "Modern Standard Arabic in Arabic script only. "
                        f"Expected sentence: {target}"
                    ),
                )
            text = (getattr(result, "text", None) or str(result) or "").strip()
            return text or None
        except Exception:  # noqa: BLE001
            logger.warning("Arabic re-transcription failed", exc_info=True)
            return None

    async def _resolve_error_for_target(self, target: str) -> str | None:
        errors = await self.runtime.store.list_errors(self.runtime.session_id)
        for err in reversed(errors):
            if err.get("resolved_at"):
                continue
            if err.get("correct_form") == target or err.get("learner_text") == target:
                return err["id"]
        return None

    def _enter_drill_mode(self) -> None:
        if self.session is None:
            return
        self.session.update_options(
            endpointing_opts={"min_delay": self.endpointing_min, "max_delay": self.endpointing_max}
        )

    def _restore_conversation_mode(self) -> None:
        if self.session is None:
            return
        self.session.update_options(
            endpointing_opts={
                "min_delay": self.conversation_endpointing_min,
                "max_delay": self.conversation_endpointing_max,
            }
        )

    async def _say_grammar_intro(self, error_entry_id: str | None) -> None:
        """One short rule explanation, then jump into the first model sentence."""
        explanation = ""
        if error_entry_id:
            err = await self.runtime.store.get_error(error_entry_id)
            if err:
                explanation = (err.get("explanation_ar") or "").strip()
        if explanation:
            # Keep spoken intro to ~2 sentences max.
            await self._say(f"قاعدة سريعة: {explanation}")
        else:
            await self._say("استمع وكرّر.")

    async def _say(self, text: str) -> None:
        if self.session is None:
            return
        spoken = await diacritize(text, timeout_ms=self.tashkeel_timeout_ms)
        handle = self.session.say(spoken, allow_interruptions=False)
        await handle.wait_for_playout()

    async def _publish(self, payload: dict) -> None:
        if self.runtime.room is None:
            return
        try:
            await self.runtime.room.local_participant.publish_data(
                json.dumps(payload).encode("utf-8"),
                topic=DATA_TOPIC,
                reliable=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning("failed to publish drill event", exc_info=True)
