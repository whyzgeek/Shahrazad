"""Error acknowledgement endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shahrazad_agent.config import load_settings
from shahrazad_agent.db import get_session_factory, init_db
from shahrazad_agent.db.store import SessionStore

router = APIRouter(prefix="/errors", tags=["errors"])


class AcknowledgeResponse(BaseModel):
    error_id: str
    acknowledged: bool


def _store() -> SessionStore:
    settings = load_settings(require_openai=False)
    init_db(settings.database_url)
    return SessionStore(get_session_factory(settings.database_url))


@router.post("/{error_id}/acknowledge", response_model=AcknowledgeResponse)
async def acknowledge_error(error_id: str) -> AcknowledgeResponse:
    store = _store()
    ok = await store.acknowledge_error(error_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Error not found")
    return AcknowledgeResponse(error_id=error_id, acknowledged=True)
