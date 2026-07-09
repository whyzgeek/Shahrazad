"""Shared helpers for Phase 0 spikes."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
SPIKES = ROOT / "spikes"
FIXTURES = SPIKES / "fixtures"
RESULTS = SPIKES / "results"


def load_env() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(SPIKES / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass
class SpikeResult:
    id: str
    name: str
    status: str  # pass | fail | skip | blocked
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def timed(fn):
    def wrapper(*args, **kwargs) -> SpikeResult:
        start = time.perf_counter()
        result: SpikeResult = fn(*args, **kwargs)
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        return result

    return wrapper
