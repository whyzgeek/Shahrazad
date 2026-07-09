"""LiveKit access token for browser clients."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shahrazad_agent.api.livekit_token import mint_learner_token
from shahrazad_agent.config import load_settings

router = APIRouter(prefix="/token", tags=["livekit"])


class TokenRequest(BaseModel):
    room_name: str | None = Field(default=None, description="LiveKit room; auto-generated if omitted")
    identity: str | None = Field(default=None, description="Participant identity")
    topic_id: str | None = Field(default="greetings", description="Preset topic for agent context")


class TokenResponse(BaseModel):
    token: str
    room_name: str
    livekit_url: str


@router.post("", response_model=TokenResponse)
def mint_token(body: TokenRequest | None = None) -> TokenResponse:
    settings = load_settings(require_openai=False)
    body = body or TokenRequest()
    topic_id = (body.topic_id or "greetings").strip()
    room_name = body.room_name or f"shahrazad-{topic_id}-{uuid.uuid4().hex[:8]}"

    try:
        jwt, _identity = mint_learner_token(
            settings,
            room_name=room_name,
            topic_id=topic_id,
            identity=body.identity,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Token mint failed: {exc}") from exc

    return TokenResponse(token=jwt, room_name=room_name, livekit_url=settings.livekit_url)
