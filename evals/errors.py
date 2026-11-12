"""Error detection: does the brain find the learner's mistakes, and only those?

29 sentences as heard from speech: 17 with mistakes (20 wrong words in all) and 12 correct ones, some answering a
question about numbers or names that differ from what the tutor said (a different fact is not a grammar mistake).
Uses the tutor's own find_errors(), so the prompt and the filtering are the real ones.

    .venv-tutor/bin/python evals/errors.py            # the brain set in .env
    .venv-tutor/bin/python evals/errors.py --url URL  # another OpenAI-style chat endpoint
"""
import argparse, asyncio, json
import _setup
import httpx
from tools import learner, providers

p = argparse.ArgumentParser()
p.add_argument("--url", default=providers.LLM_URL)
args = p.parse_args()
CASES = json.loads((_setup.DATA / "errors.json").read_text())


async def main():
    caught = missed = extra = failed = 0
    async with httpx.AsyncClient() as h:
        for c in CASES:
            try:
                found, *_ = await learner.find_errors(c["said"], c["tutor_before"], h, args.url, "voice")
            except Exception as e:
                failed += 1
                print(f"FAILED {type(e).__name__}: {c['said'][:40]}", flush=True)
                continue
            got = [learner.normal(e["wrong"]) for e in found]
            want = [learner.normal(w) for w in c["wrong"]]
            hit = [w for w in want if any(w in g.split() for g in got)]
            wrong_flags = [g for g in got if not any(w in g.split() for w in want)]
            caught += len(hit); missed += len(want) - len(hit); extra += len(wrong_flags)
            if len(hit) < len(want) or wrong_flags:
                print(f"  {c['said'][:45]:45} expected {c['wrong']} got {[(e['wrong'], e['right']) for e in found]}", flush=True)
    print(f"{providers.describe()}\ncaught {caught} of {caught + missed} mistakes; flagged {extra} words wrongly; {failed} failed calls")

asyncio.run(asyncio.wait_for(main(), 900))
