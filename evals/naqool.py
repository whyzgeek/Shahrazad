"""Corrections in conversation: does the tutor start its reply with «نقول» (the corrected sentence) when the learner
made a mistake, and not when the sentence was right?

10 sentences with mistakes and 3 correct ones (each asked several times), after the same short discussion, with the
real system prompt, level note and tools, at both levels the tutor adapts to.

    .venv-tutor/bin/python evals/naqool.py [--repeat 4]
"""
import argparse, asyncio, json
import _setup
import httpx, app
from tools import brain, learner, providers

p = argparse.ArgumentParser()
p.add_argument("--repeat", type=int, default=4, help="how many times each correct sentence is asked")
args = p.parse_args()
D = json.loads((_setup.DATA / "naqool.json").read_text())


async def reply(h, said, band):
    note = f"[Private note to the tutor, not from the learner. Never correct it or mention it. The learner's current level is {band}. {learner.BAND_STYLE[band]}]"
    msgs = [{"role": "system", "content": app.SYSTEM}] + D["context"] + [{"role": "user", "content": said + "\n\n" + note}]

    async def ignore(_):
        pass
    text, _ = await brain.turn(h, msgs, app.REGISTRY.schemas(list(app.REGISTRY.tools)), ignore)
    return text.strip()


async def main():
    print(providers.describe())
    async with httpx.AsyncClient() as h:
        for band in ("beginner", "intermediate"):
            hits, misses = 0, []
            for s in D["with_errors"]:
                t = await reply(h, s, band)
                if t.startswith("نقول"):
                    hits += 1
                else:
                    misses.append(f"{s[:40]} -> {t[:60]}")
            false = sum([(await reply(h, s, band)).startswith("نقول") for s in D["correct"] * args.repeat])
            print(f"{band:12} «نقول» on {hits}/{len(D['with_errors'])} sentences with mistakes, on {false}/{len(D['correct']) * args.repeat} correct ones", flush=True)
            for m in misses:
                print("    missed:", m)

asyncio.run(asyncio.wait_for(main(), 1500))
