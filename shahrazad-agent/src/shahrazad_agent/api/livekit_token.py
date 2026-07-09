"""LiveKit access token helpers with explicit agent dispatch."""

from __future__ import annotations

import json
import uuid

from livekit import api
from livekit.protocol.agent_dispatch import RoomAgentDispatch
from livekit.protocol.room import RoomConfiguration

from shahrazad_agent.config import Settings

AGENT_NAME = "shahrazad"


def mint_learner_token(
    settings: Settings,
    *,
    room_name: str,
    topic_id: str,
    identity: str | None = None,
) -> tuple[str, str]:
    """Return (jwt, participant_identity)."""
    participant = identity or f"learner-{uuid.uuid4().hex[:8]}"
    metadata = json.dumps({"topic_id": topic_id})

    room_config = RoomConfiguration(
        name=room_name,
        agents=[RoomAgentDispatch(agent_name=AGENT_NAME, metadata=metadata)],
    )

    jwt = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant)
        .with_name("Shahrazad Learner")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_room_config(room_config)
        .to_jwt()
    )
    return jwt, participant
