"""Spike 4b: Mishkal local diacritization (Farasa alternative — no API account)."""

from __future__ import annotations

import time

from common import load_tutor_phrases, ok, print_header, skip, write_result

TIMEOUT_MS = 300


def _diacritize_mishkal(text: str) -> tuple[str, float]:
    from mishkal.tashkeel import TashkeelClass

    started = time.perf_counter()
    engine = TashkeelClass()
    output = engine.tashkeel(text)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return output, elapsed_ms


def run() -> dict:
    print_header("Spike 4b: Mishkal tashkeel (local)")
    try:
        import mishkal  # noqa: F401
    except ImportError:
        return skip("tashkeel_mishkal", "pip install mishkal")

    phrases = load_tutor_phrases()
    rows = []
    for phrase in phrases:
        output, elapsed_ms = _diacritize_mishkal(phrase)
        rows.append({"input": phrase, "output": output, "elapsed_ms": elapsed_ms})
        print(f"  {elapsed_ms}ms  {phrase[:40]}... -> {output[:50]}...")

    latencies = [r["elapsed_ms"] for r in rows]
    avg_ms = round(sum(latencies) / len(latencies), 1)
    max_ms = max(latencies)
    recommendation = (
        "Use Mishkal as V1 tashkeel provider (local, no API key). "
        "First call loads model (~100-300ms); cache per text hash in agent. "
        "300ms timeout -> undiacritized fallback per plan invariant 3."
    )
    if max_ms > TIMEOUT_MS:
        recommendation += f" Note: cold-start max {max_ms}ms exceeds {TIMEOUT_MS}ms — warm engine at agent startup."

    result = {
        "provider": "mishkal",
        "rows": rows,
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "recommendation": recommendation,
    }
    path = write_result("tashkeel_mishkal", result)
    print(f"Wrote {path}")
    return ok("tashkeel_mishkal", **result)


if __name__ == "__main__":
    run()
