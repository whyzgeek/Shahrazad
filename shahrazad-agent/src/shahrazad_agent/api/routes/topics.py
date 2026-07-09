"""Preset topic catalog."""

from __future__ import annotations

from fastapi import APIRouter

from shahrazad_agent.context.adapters import load_topic_catalog

router = APIRouter(tags=["topics"])


@router.get("/topics")
def list_topics() -> list[dict]:
    return load_topic_catalog()
