"""Environment configuration loaded from repo-root .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
AGENT_ROOT = PACKAGE_ROOT.parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[2]
DATA_DIR = AGENT_ROOT / "data"
AUDIO_DIR = DATA_DIR / "audio"


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_realtime_model: str
    openai_realtime_voice: str
    openai_transcription_model: str
    openai_transcription_language: str
    openai_tts_model: str
    openai_tts_voice: str
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    tashkeel_timeout_ms: int
    database_url: str
    drill_accuracy_threshold: float
    drill_max_attempts: int
    drill_endpointing_min: float
    drill_endpointing_max: float
    conversation_endpointing_min: float
    conversation_endpointing_max: float
    grammar_drill_max_attempts_per_sentence: int
    grammar_drill_similar_count: int
    flow_conversation_turns: int
    flow_max_review_drills: int


def _load_env_files() -> None:
    for path in (REPO_ROOT / ".env", AGENT_ROOT / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


def bootstrap_env() -> None:
    """Load repo `.env` into os.environ for LiveKit CLI and plugins."""
    _load_env_files()


def load_settings(*, require_openai: bool = True) -> Settings:
    bootstrap_env()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if require_openai and not openai_key:
        raise RuntimeError("Missing required env var: OPENAI_API_KEY")
    return Settings(
        openai_api_key=openai_key,
        openai_realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime"),
        openai_realtime_voice=os.getenv("OPENAI_REALTIME_VOICE", "marin"),
        openai_transcription_model=os.getenv(
            "OPENAI_TRANSCRIPTION_MODEL",
            os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
        ),
        openai_transcription_language=os.getenv(
            "OPENAI_TRANSCRIPTION_LANGUAGE",
            os.getenv("OPENAI_STT_LANGUAGE", "ar"),
        ),
        openai_tts_model=os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        openai_tts_voice=os.getenv("OPENAI_TTS_VOICE", "shimmer"),
        livekit_url=_require("LIVEKIT_URL").rstrip("/"),
        livekit_api_key=_require("LIVEKIT_API_KEY"),
        livekit_api_secret=_require("LIVEKIT_API_SECRET"),
        tashkeel_timeout_ms=int(os.getenv("TASHKEEL_TIMEOUT_MS", "300")),
        database_url=os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'shahrazad.db'}"),
        drill_accuracy_threshold=float(os.getenv("DRILL_ACCURACY_THRESHOLD", "80")),
        drill_max_attempts=int(os.getenv("DRILL_MAX_ATTEMPTS", "5")),
        drill_endpointing_min=float(os.getenv("DRILL_ENDPOINTING_MIN", "0.7")),
        drill_endpointing_max=float(os.getenv("DRILL_ENDPOINTING_MAX", "1.0")),
        conversation_endpointing_min=float(os.getenv("CONVERSATION_ENDPOINTING_MIN", "0.35")),
        conversation_endpointing_max=float(os.getenv("CONVERSATION_ENDPOINTING_MAX", "0.9")),
        grammar_drill_max_attempts_per_sentence=int(
            os.getenv("GRAMMAR_DRILL_MAX_ATTEMPTS_PER_SENTENCE", "3")
        ),
        grammar_drill_similar_count=int(os.getenv("GRAMMAR_DRILL_SIMILAR_COUNT", "2")),
        flow_conversation_turns=int(os.getenv("FLOW_CONVERSATION_TURNS", "6")),
        flow_max_review_drills=int(os.getenv("FLOW_MAX_REVIEW_DRILLS", "3")),
    )


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value
