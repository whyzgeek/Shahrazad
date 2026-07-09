"""OpenAI TTS proxy with on-disk cache for review UI."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from openai import OpenAI

from shahrazad_agent.agent.speech import OPENAI_TTS_INSTRUCTIONS
from shahrazad_agent.config import DATA_DIR, load_settings

router = APIRouter(prefix="/tts", tags=["tts"])

_TASHKEEL_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_CACHE_DIR = DATA_DIR / "tts_cache"


def _cache_path(text: str, voice: str, model: str) -> Path:
    key = hashlib.sha256(f"{model}:{voice}:{text}".encode("utf-8")).hexdigest()
    return _CACHE_DIR / f"{key}.mp3"


def _synthesize_sync(*, text: str, api_key: str, model: str, voice: str) -> bytes:
    client = OpenAI(api_key=api_key)
    response = client.audio.speech.create(
        model=model,
        voice=voice,
        input=text,
        instructions=OPENAI_TTS_INSTRUCTIONS,
    )
    return response.content


@router.get("")
async def synthesize(
    text: str = Query(..., min_length=1, max_length=500, description="MSA text to speak"),
) -> Response:
    cleaned = _TASHKEEL_RE.sub("", text).strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="empty text")

    settings = load_settings(require_openai=True)
    cache_file = _cache_path(cleaned, settings.openai_tts_voice, settings.openai_tts_model)

    if not _CACHE_DIR.exists():
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not cache_file.exists():
        try:
            audio = await asyncio.to_thread(
                _synthesize_sync,
                text=cleaned,
                api_key=settings.openai_api_key,
                model=settings.openai_tts_model,
                voice=settings.openai_tts_voice,
            )
            cache_file.write_bytes(audio)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {exc}") from exc

    return Response(
        content=cache_file.read_bytes(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
