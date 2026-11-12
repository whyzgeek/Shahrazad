"""Vowelling: how often the tutor's vowelled text gets a case ending or a word wrong, and whether it changes letters.

- 40 Modern Standard Arabic paragraphs from SadeedDiac-25 (Misraj/SadeedDiac-25 on Hugging Face, downloaded at run
  time; the classical-text files are left out).
- 12 short sentences built around common grammar points (data/grammar_vowelled.json).
Uses the tutor's own vowelize(), with its safety nets. Sukun is ignored, and so is the order of tanween and alef.

    .venv-tutor/bin/python evals/tashkeel.py [--paragraphs 40]
"""
import argparse, asyncio, json, re, statistics as st, time, unicodedata as ud
import _setup
import httpx, app
from tools import providers

p = argparse.ArgumentParser()
p.add_argument("--paragraphs", type=int, default=40)
args = p.parse_args()
MARK = "ًٌٍَُِّْ"


def norm_word(w):
    w = ud.normalize("NFD", w).replace("ْ", "")
    w = re.sub(f"([{MARK}]+)", lambda m: "".join(sorted(m.group(1))), w)
    return ud.normalize("NFC", re.sub("ًا", "اً", w))


strip = lambda w: re.sub(f"[{MARK}ٰ]", "", ud.normalize("NFD", w))
words = lambda s: re.findall(rf"[ء-ي{MARK}ٰ]+", s)


def ending(w):
    m = re.search(f"([^{MARK}])([{MARK}]*)$", norm_word(w))
    return (m.group(1), m.group(2)) if m else ("", "")


def score(gold, hyp):
    """(words, words wrong, words with a marked ending, endings wrong), or None if letters changed."""
    g, h = words(gold), words(hyp)
    if [strip(x) for x in g] != [strip(x) for x in h]:
        return None
    ends = [(a, b) for a, b in zip(g, h) if ending(a)[1]]
    return len(g), sum(norm_word(a) != norm_word(b) for a, b in zip(g, h)), len(ends), sum(ending(a) != ending(b) for a, b in ends)


async def sadeed(h, n):
    rows, offset = [], 0
    while True:
        r = await h.get("https://datasets-server.huggingface.co/rows", params={"dataset": "Misraj/SadeedDiac-25", "config": "default", "split": "train", "offset": offset, "length": 100}, timeout=60)
        r.raise_for_status()
        batch = [x["row"] for x in r.json()["rows"]]
        rows += batch
        offset += len(batch)
        if len(batch) < 100:
            break
    rows = [r for r in rows if not str(r["filename"]).lower().startswith(("fadel", "ca"))]
    return [{"plain": r["input"], "gold": r["output"]} for r in rows[::max(len(rows) // n, 1)][:n]]


async def run(h, name, items):
    tot = wrong = ends = bad_ends = changed = 0
    secs = []
    for it in items:
        t = time.time()
        out = await app.vowelize(it["plain"], h)
        secs.append(time.time() - t)
        s = score(it["gold"], out)
        if s is None:
            changed += 1
            continue
        tot += s[0]; wrong += s[1]; ends += s[2]; bad_ends += s[3]
    print(f"{name:9} case endings wrong {100 * bad_ends / max(ends, 1):.1f}% of {ends}; words wrong {100 * wrong / max(tot, 1):.1f}% of {tot}; "
          f"letters changed in {changed} of {len(items)}; median {st.median(secs):.2f} s each", flush=True)


async def main():
    print(providers.describe())
    grammar = [{"plain": re.sub(f"[{MARK}ٰ]", "", s), "gold": s} for s in json.loads((_setup.DATA / "grammar_vowelled.json").read_text())]
    async with httpx.AsyncClient() as h:
        await run(h, "grammar", grammar)
        await run(h, "SadeedDiac", await sadeed(h, args.paragraphs))

asyncio.run(asyncio.wait_for(main(), 3000))
