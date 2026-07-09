"""CAMeL-Tools corroborating dialect signal (never sole error source)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class CamelSignal:
    top_dialect: str | None
    p_msa: float | None
    available: bool


def _score_sync(text: str) -> CamelSignal:
    try:
        from camel_tools.dialectid import DialectIdentifier
    except ImportError:
        return CamelSignal(top_dialect=None, p_msa=None, available=False)

    try:
        did = DialectIdentifier.pretrained()
    except Exception:  # noqa: BLE001
        return CamelSignal(top_dialect=None, p_msa=None, available=False)

    predictions = did.predict(text)
    if not predictions:
        return CamelSignal(top_dialect=None, p_msa=None, available=True)

    totals: dict[str, float] = {}
    count = 0
    for pred in predictions:
        if not hasattr(pred, "scores"):
            continue
        count += 1
        for label, score in pred.scores.items():
            totals[label] = totals.get(label, 0.0) + float(score)

    if count == 0:
        return CamelSignal(top_dialect=None, p_msa=None, available=True)

    averaged = {k: v / count for k, v in totals.items()}
    top = max(averaged, key=averaged.get)
    return CamelSignal(
        top_dialect=top,
        p_msa=averaged.get("MSA"),
        available=True,
    )


async def score_dialect(text: str) -> CamelSignal:
    if not text.strip():
        return CamelSignal(top_dialect=None, p_msa=None, available=False)
    return await asyncio.to_thread(_score_sync, text)
