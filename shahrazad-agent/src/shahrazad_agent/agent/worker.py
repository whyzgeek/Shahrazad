"""LiveKit agent worker entrypoint — OpenAI Realtime speech-to-speech."""

from __future__ import annotations

import asyncio
import json
import logging

from livekit import rtc
from livekit.agents import AgentServer, AgentSession, JobContext, UserInputTranscribedEvent, cli, room_io
from livekit.agents.voice.events import ConversationItemAddedEvent
from openai import AsyncOpenAI

from shahrazad_agent.agent.fanout import SessionRuntime
from shahrazad_agent.agent.flow import SessionFlow
from shahrazad_agent.agent.learner_turns import process_learner_utterance
from shahrazad_agent.agent.prompts import build_instructions
from shahrazad_agent.agent.speech import create_realtime_model, create_tts
from shahrazad_agent.agent.tutor import ShahrazadAgent
from shahrazad_agent.api.livekit_token import AGENT_NAME
from shahrazad_agent.config import bootstrap_env, load_settings
from shahrazad_agent.context.adapters import PresetTopicAdapter, get_topic
from shahrazad_agent.db import get_session_factory, init_db
from shahrazad_agent.db.store import SessionStore
from shahrazad_agent.diacritization.mishkal import _engine, diacritize  # warm Mishkal at import
from shahrazad_agent.drills.controller import DrillController

bootstrap_env()

logger = logging.getLogger("shahrazad.agent")
server = AgentServer(multiprocessing_context="spawn")
_ = _engine()

DATA_TOPIC_ERRORS = "shahrazad-errors"
DATA_TOPIC_DRILL = "shahrazad-drill"
DATA_TOPIC_CONTROL = "shahrazad-control"
DATA_TOPIC_SESSION = "shahrazad-session"
DATA_TOPIC_TRANSCRIPT = "shahrazad-transcript"


def _topic_from_room(room_name: str) -> str | None:
    if not room_name.startswith("shahrazad-"):
        return None
    rest = room_name.removeprefix("shahrazad-")
    if "-" not in rest:
        return None
    topic_id, _suffix = rest.rsplit("-", 1)
    return topic_id or None


async def _publish_data(room: rtc.Room, topic: str, payload: dict) -> None:
    try:
        await room.local_participant.publish_data(
            json.dumps(payload).encode("utf-8"),
            topic=topic,
            reliable=True,
        )
    except Exception:  # noqa: BLE001
        logger.warning("failed to publish data topic=%s", topic, exc_info=True)


@server.rtc_session(agent_name=AGENT_NAME)
async def shahrazad_session(ctx: JobContext) -> None:
    settings = load_settings(require_openai=True)
    init_db(settings.database_url)
    store = SessionStore(get_session_factory(settings.database_url))

    await ctx.connect()

    topic_id = "greetings"
    if ctx.job.metadata:
        try:
            meta = json.loads(ctx.job.metadata)
            topic_id = meta.get("topic_id", topic_id)
        except json.JSONDecodeError:
            logger.warning("Invalid job metadata JSON; using default topic")
    elif ctx.room.name:
        topic_id = _topic_from_room(ctx.room.name) or topic_id

    topic = get_topic(topic_id) or get_topic("greetings")
    if topic is None:
        raise RuntimeError("Topic catalog is empty")

    existing = await store.get_session_by_room(ctx.room.name) if ctx.room.name else None
    if existing:
        session_id = existing["id"]
        topic_id = existing.get("topic_id") or topic_id
        topic = get_topic(topic_id) or topic
        logger.info("reusing session id=%s room=%s", session_id, ctx.room.name)
    else:
        session_id = await store.create_session(
            topic_id=topic_id,
            room_name=ctx.room.name,
            context_type="preset_topic",
            context_payload=topic,
        )
        logger.info("session started id=%s room=%s", session_id, ctx.room.name)

    runtime = SessionRuntime(
        session_id=session_id,
        topic_id=topic_id,
        topic_title=topic.get("title_en", topic_id),
        store=store,
        settings=settings,
        room=ctx.room,
        openai_client=AsyncOpenAI(api_key=settings.openai_api_key),
    )

    adapter = PresetTopicAdapter()
    instructions = build_instructions(adapter.build_system_prompt_block(topic))
    opening_line = adapter.get_opening_line(topic)

    # Realtime speech-to-speech: no separate STT/LLM/TTS pipeline.
    # TTS fallback covers session.say() if Realtime returns text-only (drills / flow).
    session = AgentSession(
        llm=create_realtime_model(settings),
        tts=create_tts(settings),
    )

    drill_controller = DrillController(
        runtime=runtime,
        tashkeel_timeout_ms=settings.tashkeel_timeout_ms,
        accuracy_threshold=settings.drill_accuracy_threshold,
        max_attempts=settings.drill_max_attempts,
        grammar_max_attempts_per_sentence=settings.grammar_drill_max_attempts_per_sentence,
        grammar_similar_count=settings.grammar_drill_similar_count,
        endpointing_min=settings.drill_endpointing_min,
        endpointing_max=settings.drill_endpointing_max,
        conversation_endpointing_min=settings.conversation_endpointing_min,
        conversation_endpointing_max=settings.conversation_endpointing_max,
    )
    runtime.drill_controller = drill_controller
    drill_controller.bind_session(session)

    flow = SessionFlow(
        runtime=runtime,
        drill_controller=drill_controller,
        session=session,
        conversation_turns_target=settings.flow_conversation_turns,
        max_review_drills=settings.flow_max_review_drills,
        tashkeel_timeout_ms=settings.tashkeel_timeout_ms,
    )
    runtime.flow = flow

    agent = ShahrazadAgent(
        instructions=instructions,
        runtime=runtime,
        tashkeel_timeout_ms=settings.tashkeel_timeout_ms,
    )
    runtime.agent = agent

    @ctx.room.on("data_received")
    def _on_data(pkt: rtc.DataPacket) -> None:
        if pkt.participant is None:
            return
        try:
            msg = json.loads(pkt.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if pkt.topic == DATA_TOPIC_CONTROL and msg.get("type") == "skip_stage":
            flow.skip_stage()
            return

        if pkt.topic == DATA_TOPIC_CONTROL and msg.get("type") == "commit_turn":

            async def _commit() -> None:
                try:
                    logger.info("commit_turn from %s", pkt.participant.identity)
                    # Under Realtime, Semantic VAD usually ends turns; this forces
                    # an early commit when the learner taps "Done speaking".
                    fut = session.commit_user_turn(
                        transcript_timeout=8.0,
                        stt_flush_duration=0.3,
                    )
                    transcript = await fut
                    await _publish_data(
                        ctx.room,
                        DATA_TOPIC_CONTROL,
                        {"type": "commit_ack", "transcript": transcript or ""},
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("commit_user_turn failed")
                    await _publish_data(
                        ctx.room,
                        DATA_TOPIC_CONTROL,
                        {"type": "commit_error", "message": "commit failed"},
                    )

            asyncio.create_task(_commit())
            return

        if pkt.topic == DATA_TOPIC_DRILL and msg.get("type") == "start_drill":

            async def _start() -> None:
                error_id = msg.get("error_entry_id")
                target = msg.get("target_text")
                raw_count = msg.get("sentence_count")
                sentence_count: int | None = None
                if raw_count is not None:
                    try:
                        sentence_count = int(raw_count)
                    except (TypeError, ValueError):
                        sentence_count = None
                if error_id:
                    await drill_controller.start_drill_from_error(
                        error_id,
                        sentence_count=sentence_count,
                    )
                elif target:
                    await drill_controller.start_drill(target)

            asyncio.create_task(_start())
            return

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
            audio_output=room_io.AudioOutputOptions(),
            text_output=room_io.TextOutputOptions(sync_transcription=True),
        ),
    )

    await _publish_data(
        ctx.room,
        DATA_TOPIC_SESSION,
        {"type": "session_ready", "session_id": session_id, "agent": AGENT_NAME},
    )
    await flow.start()

    # Start on the locked topic agenda — do not ask the learner to pick a subject.
    async def _open_lesson() -> None:
        try:
            spoken = await diacritize(opening_line, timeout_ms=settings.tashkeel_timeout_ms)
            handle = session.say(spoken, allow_interruptions=True)
            await handle.wait_for_playout()
        except Exception:  # noqa: BLE001
            logger.warning("opening line failed", exc_info=True)

    asyncio.create_task(_open_lesson())

    @session.on("user_input_transcribed")
    def _on_user_transcribed(ev: UserInputTranscribedEvent) -> None:
        # Realtime often finishes the audio reply before input transcription is
        # ready, so on_user_turn_completed sees empty text. Final transcripts here
        # are what drive fan-out, SessionFlow, and drill scoring.
        if not ev.is_final:
            return
        text = (ev.transcript or "").strip()
        if not text:
            return

        async def _handle() -> None:
            from shahrazad_agent.drills.scoring import looks_like_latin_stt

            # Skip publishing phantom Latin STT in conversation (noise/echo).
            if looks_like_latin_stt(text) and not drill_controller.is_active:
                await process_learner_utterance(runtime, text)
                return

            await process_learner_utterance(runtime, text)
            section = "practice" if drill_controller.is_active else "conversation"
            await _publish_data(
                ctx.room,
                DATA_TOPIC_TRANSCRIPT,
                {
                    "type": "transcript",
                    "role": "learner",
                    "text": text,
                    "section": section,
                },
            )

        asyncio.create_task(_handle())

    @session.on("conversation_item_added")
    def _on_item_added(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if not hasattr(item, "role"):
            return
        role = item.role
        text = item.text_content if hasattr(item, "text_content") else None
        if not text or not str(text).strip():
            return

        # Learner lines are published from user_input_transcribed (more reliable
        # under Realtime). Still persist/publish tutor lines here.
        if role == "user":
            return

        if role == "assistant":

            async def _publish_line() -> None:
                section = "practice" if drill_controller.is_active else "conversation"
                await _publish_data(
                    ctx.room,
                    DATA_TOPIC_TRANSCRIPT,
                    {
                        "type": "transcript",
                        "role": "tutor",
                        "text": str(text).strip(),
                        "section": section,
                    },
                )

            asyncio.create_task(_publish_line())

            turn_index = runtime.next_turn_index()
            runtime.tutor_turn_index = turn_index

            async def _persist() -> None:
                await store.add_turn(
                    session_id=session_id,
                    speaker="tutor",
                    text=str(text),
                    turn_index=turn_index,
                )

            asyncio.create_task(_persist())


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    cli.run_app(server)
