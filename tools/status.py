"""Whether each part of the tutor is working, for the page's banner (health) and its Status page (status)."""
import asyncio, os, time
from pathlib import Path

from . import providers

ROOT = Path(__file__).resolve().parent.parent
STARTED = time.time()
MAX_HOURS = float(os.environ.get("TUTOR_MAX_HOURS", "8") or 0)   # scripts/start.sh stops each process after this long


async def part_ok(http, part):
    """Whether one part answers. Cloud parts only need the key: checking them would spend credit."""
    if part.mode == "cloud":
        return bool(providers.KEY)
    try:
        return (await http.get(part.health, timeout=2)).status_code == 200
    except Exception:
        return False


async def _checked(http):
    oks = await asyncio.gather(*(part_ok(http, p) for p in providers.PARTS.values()))
    return zip(providers.PARTS.items(), oks)


async def health(http):
    return {kind: {"ok": ok, "mode": p.mode, "name": p.name} for (kind, p), ok in await _checked(http)}


def process_started(name):
    """When a process scripts/start.sh started (run/<name>.pid) began, from Linux's process table; None if it isn't running."""
    try:
        pid = (ROOT / "run" / f"{name}.pid").read_text().strip()
        ticks = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])   # start time, in clock ticks after boot
        boot = next(int(line.split()[1]) for line in open("/proc/stat") if line.startswith("btime"))
        return boot + ticks / os.sysconf("SC_CLK_TCK")
    except Exception:
        return None


def lifetime(started):
    """Since when something runs, and when TUTOR_MAX_HOURS stops it (None: never)."""
    return {"since": started, "stops": started + MAX_HOURS * 3600 if started and MAX_HOURS > 0 else None}


async def status(http):
    """Each part, where it runs and whether it answers, when things stop, and the cloud credit left."""
    parts = [{"kind": kind, "ok": ok, "mode": p.mode, "name": p.name, "gpu": p.gpu,
              **(lifetime(process_started(p.process)) if p.mode == "local" else {})}
             for (kind, p), ok in await _checked(http)]
    credit = None
    if any(p.mode == "cloud" for p in providers.PARTS.values()):
        try:
            credit = await providers.credit(http)
        except Exception:
            credit = {"error": "OpenRouter didn't say"}
    return {"parts": parts, "app": lifetime(STARTED), "credit": credit}
