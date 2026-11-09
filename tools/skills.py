"""Skills are folders with a SKILL.md in the Agent Skills format: teaching instructions plus the tools they may use."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_skills():
    skills = {}
    for f in sorted((ROOT / "skills").glob("*/SKILL.md")):
        _, head, body = f.read_text().split("---", 2)
        meta = yaml.safe_load(head)
        skills[meta["name"]] = {"tools": (meta.get("allowed-tools") or "").split(), "body": body.strip()}
    return skills
