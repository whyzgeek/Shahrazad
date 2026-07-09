"""Local Arabic diacritization via Mishkal with timeout and passthrough fallback."""

from __future__ import annotations

import asyncio
import hashlib
from functools import lru_cache

from mishkal.tashkeel import TashkeelClass


@lru_cache(maxsize=1)
def _engine() -> TashkeelClass:
    return TashkeelClass()


def _diacritize_sync(text: str) -> str:
    if not text.strip():
        return text
    return _engine().tashkeel(text)


async def diacritize(text: str, timeout_ms: int = 300) -> str:
    """Return vocalized MSA text, or original on timeout/error."""
    if not text.strip():
        return text
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_diacritize_sync, text),
            timeout=timeout_ms / 1000.0,
        )
    except (asyncio.TimeoutError, Exception):
        return text


def cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
