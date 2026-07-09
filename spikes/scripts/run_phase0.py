#!/usr/bin/env python3
"""Run all Phase 0 spikes and write PHASE0_REPORT.md."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SPIKES_ROOT = SCRIPTS_DIR.parent
RESULTS = SPIKES_ROOT / "results"
sys.path.insert(0, str(SCRIPTS_DIR))

SPIKES = [
    "01_azure_stt_pa_locale",
    "02_stt_latency",
    "03_camel_dialect",
    "04_tashkeel_mishkal",
    "05_livekit_connectivity",
    "06_audio_capture",
]


def load_module(name: str):
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _latest_result_files() -> dict[str, Path]:
    """Map spike stem -> newest timestamped JSON in results/."""
    by_stem: dict[str, Path] = {}
    for path in sorted(RESULTS.glob("*.json")):
        if path.name in ("phase0_summary.json",):
            continue
        stem = path.name.split("_", 1)[-1].removesuffix(".json")
        # timestamp prefix: 20260629T..._azure_stt_pa_locale.json
        if "_" in path.name and path.name[0].isdigit():
            parts = path.name.split("_", 1)
            if len(parts) == 2:
                stem = parts[1].removesuffix(".json")
        by_stem[stem] = path
    return by_stem


def write_report(summary: list[dict]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Shahrazad Phase 0 Report",
        "",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        "| Spike | Status | Recommendation |",
        "|-------|--------|----------------|",
    ]

    decisions: dict[str, str] = {}
    for row in summary:
        status = row.get("status", "unknown")
        rec = row.get("recommendation") or row.get("reason") or "—"
        lines.append(f"| {row['spike']} | **{status}** | {rec} |")
        if row.get("recommendation"):
            decisions[row["spike"]] = row["recommendation"]

    lines.extend(["", "## Spike results", ""])
    for row in summary:
        lines.extend(
            [
                f"### {row['spike']}",
                "",
                f"- **Status:** {row.get('status')}",
            ]
        )
        if row.get("reason"):
            lines.append(f"- **Reason:** {row['reason']}")
        if row.get("recommendation"):
            lines.append(f"- **Recommendation:** {row['recommendation']}")
        lines.append("")

    lines.extend(
        [
            "## Decisions",
            "",
            "| Decision | Choice |",
            "|----------|--------|",
            f"| STT + PA locale | {_decision(decisions, '01_azure_stt_pa_locale')} |",
            f"| STT provider | {_decision(decisions, '02_stt_latency')} |",
            f"| Dialect detector | {_decision(decisions, '03_camel_dialect')} |",
            f"| Tashkeel provider | {_decision(decisions, '04_tashkeel_mishkal')} |",
            f"| LiveKit | {_decision(decisions, '05_livekit_connectivity')} |",
            f"| Audio storage | {_decision(decisions, '06_audio_capture', 'Local FS, 30-day retention')} |",
            "",
            "## Next steps",
            "",
            "1. Copy `.env.example` → `.env` and fill Azure + LiveKit keys (Mishkal needs no key).",
            "2. Run `python scripts/generate_msa_fixture.py` to create learner WAV (or record your own).",
            "3. Re-run `python scripts/run_phase0.py` until all blocking spikes are **ok**.",
            "4. Update `SPIKE_DECISIONS.md` and mark Phase 0 complete in root `TODO.md`.",
            "",
        ]
    )

    report_path = RESULTS / "PHASE0_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _decision(decisions: dict[str, str], spike: str, default: str = "_pending — spike skipped or inconclusive_") -> str:
    return decisions.get(spike, default)


def main() -> int:
    from common import load_dotenv

    load_dotenv()
    print("Shahrazad Phase 0 — external verification spikes\n")

    # Optional: generate MSA fixture when Azure creds present
    try:
        gen = load_module("generate_msa_fixture")
        if hasattr(gen, "main"):
            gen.main()
    except Exception as exc:  # noqa: BLE001
        print(f"(fixture generation skipped: {exc})")

    summary = []
    for spike_name in SPIKES:
        module = load_module(spike_name)
        result = module.run()
        summary.append({"spike": spike_name, **result})

    summary_path = RESULTS / "phase0_summary.json"
    summary_path.write_text(
        json.dumps(
            {"generated": datetime.now(timezone.utc).isoformat(), "spikes": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report_path = write_report(summary)

    print("\n=== Summary ===")
    for row in summary:
        status = row.get("status", "unknown")
        print(f"  [{status.upper():7}] {row['spike']}")
        if row.get("recommendation"):
            print(f"           -> {row['recommendation']}")
        elif row.get("reason"):
            print(f"           -> {row['reason']}")

    failed = sum(1 for row in summary if row.get("status") == "failed")
    skipped = sum(1 for row in summary if row.get("status") == "skipped")
    ok_count = sum(1 for row in summary if row.get("status") == "ok")
    print(f"\nDone: {ok_count} ok, {skipped} skipped, {failed} failed")
    print(f"Report: {report_path}")
    print(f"Summary JSON: {summary_path}")

    blocking = {"01_azure_stt_pa_locale", "05_livekit_connectivity"}
    blocking_ok = all(
        row.get("status") == "ok"
        for row in summary
        if row["spike"] in blocking
    )
    if blocking_ok and ok_count >= 4:
        print("\nPhase 0 GO: blocking spikes passed — proceed to Phase 1.")
        return 0
    if skipped and not blocking_ok:
        print("\nPhase 0 BLOCKED: fill .env and re-run (Azure + LiveKit required for Phase 1).")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
