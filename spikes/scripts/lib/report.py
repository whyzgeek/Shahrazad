"""Write Phase 0 markdown report from spike results."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from lib.env import RESULTS, SpikeResult


def render_report(results: Iterable[SpikeResult], out_path: Path | None = None) -> str:
    out_path = out_path or (RESULTS / "PHASE0_REPORT.md")
    rows = list(results)

    lines = [
        "# Shahrazad Phase 0 Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Spike | Status | Summary |",
        "|-------|--------|---------|",
    ]

    for r in rows:
        lines.append(f"| {r.name} | **{r.status}** | {r.summary} |")

    lines.extend(["", "## Details", ""])

    for r in rows:
        lines.extend(
            [
                f"### {r.name} (`{r.id}`)",
                "",
                f"- **Status:** {r.status}",
                f"- **Duration:** {r.duration_ms} ms",
                f"- **Summary:** {r.summary}",
                "",
            ]
        )
        if r.details:
            lines.append("```json")
            import json

            lines.append(json.dumps(r.details, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    lines.extend(
        [
            "## Decisions (fill after review)",
            "",
            "1. STT/PA locale: _pending_",
            "2. STT vendor: _pending_",
            "3. Dialect drift thresholds: _pending_",
            "4. Tashkeel provider: _pending_",
            "5. LiveKit hosting: _pending_",
            "6. Audio retention: local FS, 30 days",
            "",
        ]
    )

    text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return text
