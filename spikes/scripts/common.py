"""Shared helpers for Phase 0 spikes."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SPIKES_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SPIKES_ROOT / "fixtures"
RESULTS = SPIKES_ROOT / "results"
REPO_ROOT = SPIKES_ROOT.parent


def load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def require_env(*names: str) -> dict[str, str]:
    missing = [name for name in names if not env(name)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)} (copy .env.example to .env)")
    return {name: env(name) for name in names}


def load_learner_transcripts() -> list[dict[str, str]]:
    return json.loads((FIXTURES / "learner_transcripts.json").read_text(encoding="utf-8"))


def load_tutor_phrases() -> list[str]:
    return [
        line.strip()
        for line in (FIXTURES / "tutor_phrases.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_result(name: str, payload: dict[str, Any]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS / f"{stamp}_{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def skip(name: str, reason: str) -> dict[str, Any]:
    print(f"SKIP {name}: {reason}")
    return {"status": "skipped", "reason": reason}


def fail(name: str, reason: str) -> dict[str, Any]:
    print(f"FAIL {name}: {reason}")
    return {"status": "failed", "reason": reason}


def ok(name: str, **payload: Any) -> dict[str, Any]:
    print(f"OK   {name}")
    return {"status": "ok", **payload}


def main_guard(fn):
    def wrapper(*args, **kwargs):
        load_dotenv()
        try:
            result = fn(*args, **kwargs)
            if isinstance(result, dict):
                write_result(fn.__name__, result)
            return result
        except Exception as exc:  # noqa: BLE001 - spike scripts should surface errors
            result = fail(fn.__name__, str(exc))
            write_result(fn.__name__, result)
            print(exc, file=sys.stderr)
            return result

    return wrapper
