"""Shahrazad tutor agent — Realtime voice, error-aware prompts, and drills."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable

from livekit.agents import Agent, ModelSettings, llm
from livekit.agents.llm.tool_context import StopResponse, function_tool

from shahrazad_agent.agent.fanout import SessionRuntime
from shahrazad_agent.agent.learner_turns import process_learner_utterance
from shahrazad_agent.diacritization.mishkal import diacritize


class ShahrazadAgent(Agent):
    def __init__(
        self,
        *,
        instructions: str,
        runtime: SessionRuntime,
        tashkeel_timeout_ms: int = 300,
        **kwargs,
    ) -> None:
        super().__init__(instructions=instructions, **kwargs)
        self._runtime = runtime
        self._tashkeel_timeout_ms = tashkeel_timeout_ms

    def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        """Diacritize only when falling back to text TTS (drills / Realtime text-only)."""
        return Agent.default.tts_node(self, self._diacritize_stream(text), model_settings)

    async def _diacritize_stream(self, text: AsyncIterable[str]) -> AsyncGenerator[str, None]:
        async for chunk in text:
            yield await diacritize(chunk, timeout_ms=self._tashkeel_timeout_ms)

    def _drills_allowed(self) -> bool:
        flow = self._runtime.flow
        return flow is not None and flow.stage == "review"

    @function_tool
    async def start_practice_drill(self, error_entry_id: str) -> str:
        """Start a practice drill — only during the guided review stage."""
        if not self._drills_allowed():
            return (
                "Drills run in the guided review stage only. "
                "Continue the conversation with a natural recast."
            )
        controller = self._runtime.drill_controller
        if controller is None:
            return "Drill system unavailable."
        result = await controller.start_drill_from_error(error_entry_id)
        return str(result)

    @function_tool
    async def start_pronunciation_drill(
        self,
        target_phrase: str,
        error_entry_id: str | None = None,
    ) -> str:
        """Start a pronunciation drill — only during the guided review stage."""
        if not self._drills_allowed():
            return (
                "Drills run in the guided review stage only. "
                "Continue the conversation with a natural recast."
            )
        controller = self._runtime.drill_controller
        if controller is None:
            return "Drill system unavailable."
        result = await controller.start_drill(
            target_phrase,
            error_entry_id=error_entry_id,
            drill_type="pronunciation",
        )
        return str(result)

    @function_tool
    async def start_grammar_drill(self, error_entry_id: str) -> str:
        """Start a grammar drill — only during the guided review stage."""
        if not self._drills_allowed():
            return (
                "Drills run in the guided review stage only. "
                "Continue the conversation with a natural recast."
            )
        controller = self._runtime.drill_controller
        if controller is None:
            return "Drill system unavailable."
        result = await controller.start_grammar_drill(error_entry_id)
        return str(result)

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        # Under Realtime, text often arrives later via user_input_transcribed.
        learner_text = (new_message.text_content or "").strip()
        if not learner_text:
            return

        consumed = await process_learner_utterance(
            self._runtime,
            learner_text,
            turn_ctx=turn_ctx,
            stop_if_drill=True,
        )
        if consumed:
            raise StopResponse()
