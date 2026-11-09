#!/usr/bin/env python3
"""Work out how to place Shahrazad's models on this machine's GPUs and write the result to .env.

Detects NVIDIA GPUs and system memory, or takes them from the command line to preview other hardware:
  scripts/configure.py                     # detect, show the plan
  scripts/configure.py --write             # detect, and save to .env
  scripts/configure.py --gpus 24 --ram 64  # preview one 24 GB card with 64 GB RAM
  scripts/configure.py --gpus 16,8         # preview two cards

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
MARGIN_MIB = 500          # kept free on each GPU in use
DISPLAY_MIB = 850         # typical use by a desktop on the GPU driving a monitor
RESERVED_MIB = 377        # driver reservation, used when previewing hardware
RAM_BASE_GB = 17          # processes + operating system, before Gemma's CPU layers
RAM_LAYER_GB = 0.4        # system memory per Gemma layer on the CPU

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


def best_plan(gpus):
    """Try every placement of the three GPU workloads and keep the one that leaves the most of Gemma on the GPU."""
    best = None
    for asr, llm, voice in itertools.product(gpus, repeat=3):
        room = {g["index"]: g["usable"] - MARGIN_MIB for g in gpus}
        room[asr["index"]] -= VOXTRAL_MIB
        room[voice["index"]] -= VOICE_MIB
        if room[asr["index"]] < 0 or room[voice["index"]] < 0:
            continue
        moe = layers_for(room[llm["index"]])
        if moe is None:
            continue
        spare = room[llm["index"]] - (GEMMA_FULL_MIB - GEMMA_LAYER_MIB * moe)
        key = (moe, -spare)
        if best is None or key < best[0]:
            best = (key, asr, llm, voice, moe)
    return best


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
    ap.add_argument("--write", action="store_true", help="save the plan to .env")
    a = ap.parse_args()
    if a.write and a.gpus:
        sys.exit("--write uses the detected hardware, so it can't be combined with --gpus.")
    gpus = preview_gpus(a.gpus) if a.gpus else detect_gpus()
    if not gpus:
        sys.exit("No NVIDIA GPU found. Shahrazad currently needs CUDA: Voxtral runs on vLLM, and other GPUs are not supported yet.")
    ram = a.ram if a.ram else detect_ram_gb()
    print("Hardware:", ", ".join(f"GPU {g['index']} {g['name']} ({g['usable']} MiB usable)" for g in gpus), f"| RAM {ram:.0f} GB")
    plan = best_plan(gpus)
    if not plan:
        need = VOXTRAL_MIB + MARGIN_MIB
        sys.exit(f"This hardware can't run all the models.\nOne GPU needs about {need} MiB free for Voxtral (a 12 GB card), and the models need about "
                 f"{VOXTRAL_MIB + VOICE_MIB + GEMMA_FULL_MIB - GEMMA_LAYER_MIB * GEMMA_LAYERS + MARGIN_MIB} MiB across the GPUs at minimum.")
    _, asr, llm, voice, moe = plan
    fraction = min(0.95, math.ceil(VOXTRAL_ALLOC_MIB / asr["capacity"] * 1000) / 1000)
    print(f"Plan:     Voxtral on GPU {asr['index']}, Gemma on GPU {llm['index']}, voice on GPU {voice['index']}")
    print(f"Gemma:    {moe} of {GEMMA_LAYERS} layers' experts on the CPU, {speed_note(moe)}")
    need_ram = RAM_BASE_GB + RAM_LAYER_GB * moe
    print(f"RAM:      needs about {need_ram:.0f} GB" + ("" if ram >= need_ram else f", but this machine has {ram:.0f} GB. Expect swapping or failure."))
    values = {"GPU_ASR": asr["index"], "GPU_LLM": llm["index"], "GPU_VOICE": voice["index"], "GEMMA_CPU_MOE": moe, "VOXTRAL_GPU_FRACTION": fraction}
    if a.write:
        write_env(values)
        print("Saved to .env")
    else:
        print("Preview only. Add --write to save." if not a.gpus else "Preview only.")


if __name__ == "__main__":
    main()
