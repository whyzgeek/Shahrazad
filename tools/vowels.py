"""Vowel marks for the voice: the brain writes them, and these checks keep the tutor's own words."""
import difflib, json, re
from pathlib import Path

from . import brain
from .text import ARABIC, DIAC

PROMPT = (Path(__file__).resolve().parent.parent / "prompts/vowelize.txt").read_text().strip() + "\n"
SIMILAR = 0.7   # a vowelled word this close to the original counts as a small spelling fix, not a different word


def similar_pairs(a, b):
    """Index pairs of words in a and b that line up one to one, as equal or as a small spelling change."""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                if tag == "equal" or (a[i1 + k] and difflib.SequenceMatcher(None, a[i1 + k], b[j1 + k]).ratio() >= SIMILAR):
                    yield i1 + k, j1 + k, tag == "equal"


def merge_vowels(plain, vowelled):
    """Keep the tutor's words: take a vowelled word where its letters match the original or differ only slightly."""
    a, b = plain.split(), vowelled.split()
    out = list(a)
    for i, j, _ in similar_pairs([DIAC.sub("", w) for w in a], [DIAC.sub("", w) for w in b]):
        out[i] = b[j]   # a small spelling fix like عرج to أعرج beats sending the word without vowels
    return " ".join(out)


def apply_spelling(original, vowelled):
    """Carry a spelling fix from the vowelled text into the displayed sentence, so what's shown matches what's spoken."""
    core = lambda w: re.sub(r"[^\u0621-\u064A]", "", DIAC.sub("", w))
    a, b = original.split(), vowelled.split()
    ca, cb = [core(w) for w in a], [core(w) for w in b]
    for i, j, equal in similar_pairs(ca, cb):
        if not equal:
            a[i] = a[i].replace(ca[i], cb[j], 1)
    return " ".join(a)


def fix_initial_sukun(text):
    """Arabic words can't start with a vowelless consonant, so foreign names like تْرَامْب get a short vowel to be readable."""
    return " ".join(re.sub(r"^([\u0621-\u064A])\u0652", "\\1\u0650", w) for w in text.split())


def bare_words(text):
    """Positions of Arabic words that came back with no vowel marks at all."""
    return [i for i, w in enumerate(text.split()) if len(ARABIC.findall(w)) > 1 and not DIAC.search(w)]


async def vowel_words(sentence, words, http):
    """Vowel specific words on their own, for when the first pass changed their letters. Only exact-letter results are accepted."""
    schema = {"type": "object", "properties": {"words": {"type": "array", "items": {"type": "string"}, "minItems": len(words), "maxItems": len(words)}}, "required": ["words"]}
    ask = f"Add full Arabic vowel marks to each listed word, as it is used in this sentence. Keep every word exactly as written: don't change, add or remove any letter, even if the word looks wrong.\nSentence: {sentence}\nWords: {json.dumps(words, ensure_ascii=False)}"
    got = (await brain.ask_json(http, ask, 300, schema))["words"]
    return [g if DIAC.sub("", g) == w else w for g, w in zip(got, words)]


async def vowelize(plain, http):
    """The sentence with full vowel marks, as the voice should read it."""
    text = merge_vowels(plain, await brain.ask(http, PROMPT + plain, 600))
    bare = bare_words(text)
    if bare:
        tokens = text.split()
        parts = [re.match(r"^(\W*)(.*?)(\W*)$", tokens[i]).groups() for i in bare]
        try:
            fixed = await vowel_words(plain, [p[1] for p in parts], http)
            for i, (lead, _, tail), word in zip(bare, parts, fixed):
                tokens[i] = lead + word + tail
            text = " ".join(tokens)
        except Exception as e:  # a bare word is still better than losing the sentence
            print(f"word vowelling failed: {type(e).__name__}", flush=True)
    return fix_initial_sukun(text)
