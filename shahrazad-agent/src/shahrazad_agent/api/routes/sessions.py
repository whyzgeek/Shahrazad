"""Session start and error review endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shahrazad_agent.config import load_settings
from shahrazad_agent.api.livekit_token import mint_learner_token
from shahrazad_agent.context.adapters import get_topic
from shahrazad_agent.db import get_session_factory, init_db
from shahrazad_agent.db.store import SessionStore

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    topic_id: str = Field(..., description="Preset topic id from catalog")


class LessonContextOut(BaseModel):
    context_type: str
    context_payload: dict


class StartSessionResponse(BaseModel):
    session_id: str
    topic_id: str
    lesson_context: LessonContextOut


class ErrorListResponse(BaseModel):
    session_id: str
    errors: list[dict]
    grouped: dict[str, list[dict]]


class DrillListResponse(BaseModel):
    session_id: str
    drills: list[dict]


class LiveSessionResponse(BaseModel):
    session_id: str
    topic_id: str
    room_name: str
    token: str
    livekit_url: str
    lesson_context: LessonContextOut


def _store() -> SessionStore:
    settings = load_settings(require_openai=False)
    init_db(settings.database_url)
    return SessionStore(get_session_factory(settings.database_url))


@router.post("", response_model=StartSessionResponse)
async def start_session(body: StartSessionRequest) -> StartSessionResponse:
    topic = get_topic(body.topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Unknown topic_id: {body.topic_id}")

    session_id = str(uuid.uuid4())
    store = _store()
    await store.create_session(
        session_id=session_id,
        topic_id=body.topic_id,
        room_name=None,
        context_type="preset_topic",
        context_payload=topic,
    )

    return StartSessionResponse(
        session_id=session_id,
        topic_id=body.topic_id,
        lesson_context=LessonContextOut(
            context_type="preset_topic",
            context_payload=topic,
        ),
    )


@router.post("/live", response_model=LiveSessionResponse)
async def start_live_session(body: StartSessionRequest) -> LiveSessionResponse:
    """Create a DB session, mint a LiveKit token, and return connection details for the web UI."""
    topic = get_topic(body.topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Unknown topic_id: {body.topic_id}")

    settings = load_settings(require_openai=False)
    session_id = str(uuid.uuid4())
    room_name = f"shahrazad-{body.topic_id}-{session_id[:8]}"
    identity = f"learner-{session_id[:8]}"

    store = _store()
    await store.create_session(
        session_id=session_id,
        topic_id=body.topic_id,
        room_name=room_name,
        context_type="preset_topic",
        context_payload=topic,
    )

    try:
        jwt, _identity = mint_learner_token(
            settings,
            room_name=room_name,
            topic_id=body.topic_id,
            identity=identity,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Token mint failed: {exc}") from exc

    return LiveSessionResponse(
        session_id=session_id,
        topic_id=body.topic_id,
        room_name=room_name,
        token=jwt,
        livekit_url=settings.livekit_url,
        lesson_context=LessonContextOut(
            context_type="preset_topic",
            context_payload=topic,
        ),
    )


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    store = _store()
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/errors", response_model=ErrorListResponse)
async def list_session_errors(session_id: str) -> ErrorListResponse:
    store = _store()
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    errors = await store.list_errors(session_id)
    grouped: dict[str, list[dict]] = {}
    for err in errors:
        grouped.setdefault(err["kind"], []).append(err)

    return ErrorListResponse(session_id=session_id, errors=errors, grouped=grouped)


@router.get("/{session_id}/drills", response_model=DrillListResponse)
async def list_session_drills(session_id: str) -> DrillListResponse:
    store = _store()
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    drills = await store.list_drills(session_id)
    return DrillListResponse(session_id=session_id, drills=drills)
