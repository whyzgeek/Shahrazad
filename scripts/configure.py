#!/usr/bin/env python3
"""Work out how to place Shahrazad's models on this machine's GPUs and write the result to .env.

Only the parts set to local in .env are placed (SHAHRAZAD_BRAIN, SHAHRAZAD_HEARING, SHAHRAZAD_VOICE).
If they don't fit, it names the fewest parts to move to the cloud.
Detects NVIDIA GPUs and system memory, or takes them from the command line to preview other hardware:
  scripts/configure.py                     # detect, show the plan
  scripts/configure.py --write             # detect, and save to .env
  scripts/configure.py --gpus 24 --ram 64  # preview one 24 GB card with 64 GB RAM
  scripts/configure.py --gpus 16,8         # preview two cards
  scripts/configure.py --gpus 8 --cloud hearing   # preview with speech recognition in the cloud

The memory figures below were measured with the models on two 12 GB cards. Other layouts are calculated from them.
"""
import argparse, itertools, math, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOXTRAL_MIB = 10850       # Voxtral under vLLM with 82 s sessions
VOXTRAL_ALLOC_MIB = 10837  # what --gpu-memory-utilization has to work out to
VOICE_MIB = 2100          # Spark language model + decoder
GEMMA_FULL_MIB = 14900    # Gemma 4 26B-A4B + draft head, 16K context, everything on the GPU
GEMMA_LAYER_MIB = 409     # GPU memory freed by each layer whose experts move to the CPU
GEMMA_LAYERS = 30
MARGIN_MIB = 650          # kept free on each GPU in use
DISPLAY_MIB = 850         # typical use by a desktop on the GPU driving a monitor
RESERVED_MIB = 377        # driver reservation, used when previewing hardware
RAM_BASE_GB = 17          # processes + operating system, before Gemma's CPU layers
RAM_LAYER_GB = 0.4        # system memory per Gemma layer on the CPU
RAM_SMALL_GB = 8          # without Gemma: the voice and/or Voxtral, the tutor and the operating system (estimate)

PARTS = ("brain", "hearing", "voice")
ENV_KEY = {"brain": "SHAHRAZAD_BRAIN", "hearing": "SHAHRAZAD_HEARING", "voice": "SHAHRAZAD_VOICE"}
# Order to suggest moving parts to the cloud: biggest GPU saving for the least cost first (docs/CLOUD.md).
CLOUD_PREFERENCE = ("hearing", "brain", "voice")

# Measured speeds, tokens/s, on a Xeon E5-2687W v2. A newer CPU should do better at high layer counts.
SPEED = [(10, 46), (14, 43), (22, 34), (30, 28)]


def detect_gpus():
    if not shutil.which("nvidia-smi"):
        return None
    out = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.total,memory.reserved,display_active,name", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=30).stdout
    gpus = []
    for line in out.strip().splitlines():
        i, total, reserved, disp, name = [x.strip() for x in line.split(",", 4)]
        gpus.append({"index": int(i), "name": name, "capacity": int(total) - int(reserved), "usable": int(total) - int(reserved) - (DISPLAY_MIB if disp == "Enabled" else 30)})
    return gpus


def detect_ram_gb():
    return int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1)) / 1048576


def preview_gpus(spec):
    """Hardware preview. Assumes the monitor is on the smallest card, which is the usual choice when cards differ."""
    sizes = [float(x) for x in spec.split(",")]
    display = sizes.index(min(sizes))
    gpus = []
    for i, gb in enumerate(sizes):
        cap = int(gb * 1024) - RESERVED_MIB
        gpus.append({"index": i, "name": f"{gb:g} GB card", "capacity": cap, "usable": cap - (DISPLAY_MIB if i == display else 30)})
    return gpus


def layers_for(available):
    if available >= GEMMA_FULL_MIB:
        return 0
    n = math.ceil((GEMMA_FULL_MIB - available) / GEMMA_LAYER_MIB)
    return n if n <= GEMMA_LAYERS else None


def best_plan(gpus, local=PARTS):
    """Try every placement of the local GPU workloads and keep the one that leaves the most of Gemma on the GPU.
    Returns (key, asr, llm, voice, moe), with None for a part that isn't local, or None if they don't fit."""
    if not any(local):
        return ((0, 0), None, None, None, 0)
    if not gpus:
        return None
    pick = lambda part: gpus if part in local else [None]
    best = None
    for asr, llm, voice in itertools.product(pick("hearing"), pick("brain"), pick("voice")):
        room = {g["index"]: g["usable"] - MARGIN_MIB for g in gpus}
        if asr:
            room[asr["index"]] -= VOXTRAL_MIB
        if voice:
            room[voice["index"]] -= VOICE_MIB
        if any(v < 0 for v in room.values()):
            continue
        moe, spare = 0, 0
        if llm:
            moe = layers_for(room[llm["index"]])
            if moe is None:
                continue
            spare = room[llm["index"]] - (GEMMA_FULL_MIB - GEMMA_LAYER_MIB * moe)
        key = (moe, -spare)
        if best is None or key < best[0]:
            best = (key, asr, llm, voice, moe)
    return best


def suggest_cloud(gpus, local, ram):
    """The fewest local parts to move to the cloud so the rest fit, in GPU memory and in RAM."""
    movable = [p for p in CLOUD_PREFERENCE if p in local]
    for n in range(1, len(movable) + 1):
        for move in itertools.combinations(movable, n):
            rest = tuple(p for p in local if p not in move)
            plan = best_plan(gpus, rest)
            if plan and ("brain" not in rest or ram >= RAM_BASE_GB + RAM_LAYER_GB * plan[4]):
                return move
    return tuple(movable)


def env_modes():
    env = ROOT / ".env"
    text = env.read_text() if env.exists() else ""
    modes = {}
    for part in PARTS:
        m = re.search(rf"^{ENV_KEY[part]}=(\w+)", text, flags=re.M)
        modes[part] = (m.group(1).lower() if m else "local")
    return modes


def speed_note(moe):
    if moe <= SPEED[0][0]:
        return f"at least {SPEED[0][1]} tokens/s"
    for (a, sa), (b, sb) in zip(SPEED, SPEED[1:]):
        if moe <= b:
            return f"about {round(sa + (sb - sa) * (moe - a) / (b - a))} tokens/s"
    return f"about {SPEED[-1][1]} tokens/s"


def write_env(values):
    env = ROOT / ".env"
    text = env.read_text() if env.exists() else (ROOT / ".env.example").read_text()
    for k, v in values.items():
        line = f"{k}={v}"
        text, n = re.subn(rf"^{k}=.*$", line, text, flags=re.M)
        if not n:
            text = text.rstrip("\n") + "\n" + line + "\n"
    env.write_text(text)


def main():
    ap = argparse.ArgumentParser(description="Plan Shahrazad's GPU layout.")
    ap.add_argument("--gpus", help="preview instead of detecting: card sizes in GB, for example 24 or 16,8")
    ap.add_argument("--ram", type=float, help="preview system memory in GB")
    ap.add_argument("--cloud", help="preview with these parts in the cloud: all, none, or a list such as hearing,brain (default: as set in .env)")
    ap.add_argument("--write", action="store_true", help="save the plan to .env")
    a = ap.parse_args()
    if a.write and (a.gpus or a.cloud):
        sys.exit("--write uses the detected hardware and the parts set in .env, so it can't be combined with --gpus or --cloud.")
    modes = env_modes()
    if a.cloud:
        chosen = PARTS if a.cloud == "all" else () if a.cloud == "none" else tuple(x.strip() for x in a.cloud.split(","))
        bad = [x for x in chosen if x not in PARTS]
        if bad:
            sys.exit(f"Unknown part: {', '.join(bad)}. The parts are brain, hearing and voice.")
        modes = {p: "cloud" if p in chosen else "local" for p in PARTS}
    local = tuple(p for p in PARTS if modes[p] == "local")
    cloud = [p for p in PARTS if p not in local]
    gpus = preview_gpus(a.gpus) if a.gpus else detect_gpus()
    ram = a.ram if a.ram else detect_ram_gb()
    print("Hardware:", (", ".join(f"GPU {g['index']} {g['name']} ({g['usable']} MiB usable)" for g in gpus) if gpus else "no NVIDIA GPU"), f"| RAM {ram:.0f} GB")
    print("Parts:   ", ", ".join(f"{p} {modes[p]}" for p in PARTS))
    if not local:
        print("Plan:     everything runs in the cloud, so no GPU is needed. Set OPENROUTER_API_KEY in .env.")
        return
    plan = best_plan(gpus, local)
    if plan and "brain" in local and ram < RAM_BASE_GB + RAM_LAYER_GB * plan[4]:
        plan = None   # Gemma would need more system memory than there is
    if not plan:
        move = suggest_cloud(gpus, local, ram)
        reason = "No NVIDIA GPU was found" if not gpus else "This hardware can't run the local parts"
        sys.exit(f"{reason}. Run these in the cloud instead: {', '.join(move)}.\n"
                 f"Re-run the installer with: ./install.sh --cloud {','.join(sorted(set(move) | set(cloud), key=PARTS.index))} --key YOUR_OPENROUTER_KEY")
    _, asr, llm, voice, moe = plan
    where = lambda g, name: f"{name} on GPU {g['index']}" if g else f"{name} in the cloud"
    print("Plan:    ", ", ".join([where(asr, "Voxtral"), where(llm, "Gemma"), where(voice, "voice")]))
    values = {}
    if llm:
        print(f"Gemma:    {moe} of {GEMMA_LAYERS} layers' experts on the CPU, {speed_note(moe)}")
        values.update(GPU_LLM=llm["index"], GEMMA_CPU_MOE=moe)
    need_ram = RAM_BASE_GB + RAM_LAYER_GB * moe if llm else RAM_SMALL_GB
    print(f"RAM:      needs about {need_ram:.0f} GB")
    if asr:
        values.update(GPU_ASR=asr["index"], VOXTRAL_GPU_FRACTION=min(0.95, math.ceil(VOXTRAL_ALLOC_MIB / asr["capacity"] * 1000) / 1000))
    if voice:
        values.update(GPU_VOICE=voice["index"])
    if cloud:
        print(f"Cloud:    {', '.join(cloud)} through OpenRouter (set OPENROUTER_API_KEY in .env)")
    if a.write:
        write_env(values)
        print("Saved to .env")
    else:
        print("Preview only. Add --write to save." if not a.gpus else "Preview only.")


if __name__ == "__main__":
    main()
