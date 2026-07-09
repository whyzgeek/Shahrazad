"""Injectable lesson context for tutor prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

TOPICS_PATH = Path(__file__).resolve().parent / "topics.json"


class ContextAdapter(Protocol):
    def build_system_prompt_block(self, context_payload: dict) -> str: ...
    def get_comprehension_goals(self, context_payload: dict) -> list[str]: ...


class PresetTopicAdapter:
    def build_system_prompt_block(self, context_payload: dict) -> str:
        title_ar = context_payload.get("title_ar", "")
        title_en = context_payload.get("title_en", "")
        level = context_payload.get("level_hint", "")
        vocab = "، ".join(context_payload.get("key_vocab", []))
        goals = "\n".join(f"- {g}" for g in context_payload.get("comprehension_goals", []))
        agenda_steps = context_payload.get("conversation_agenda") or []
        agenda = "\n".join(f"{i}. {step}" for i, step in enumerate(agenda_steps, start=1))
        return (
            f"LESSON TOPIC (locked): {title_ar} / {title_en}\n"
            f"Learner level: {level}\n"
            f"Key MSA vocabulary to model: {vocab}\n"
            f"Comprehension goals:\n{goals}\n"
            f"Conversation agenda — follow in order; do not skip ahead or invent new themes:\n"
            f"{agenda}\n"
            "Stay inside this topic until the agenda is complete. "
            "If the learner digresses, acknowledge briefly then return to the current agenda step."
        )

    def get_comprehension_goals(self, context_payload: dict) -> list[str]:
        return list(context_payload.get("comprehension_goals", []))

    def get_opening_line(self, context_payload: dict) -> str:
        return (
            context_payload.get("opening_line_ar")
            or "أهلاً بك! أنا شهرزاد. تفضّل، لنبدأ محادثتنا."
        )


def load_topic_catalog() -> list[dict]:
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def get_topic(topic_id: str) -> dict | None:
    for topic in load_topic_catalog():
        if topic["topic_id"] == topic_id:
            return topic
    return None


def get_adapter(context_type: str) -> ContextAdapter:
    if context_type == "preset_topic":
        return PresetTopicAdapter()
    raise ValueError(f"Unsupported context_type: {context_type}")
