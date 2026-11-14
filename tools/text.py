"""The reply's text between the brain and the voice: which sentences can be spoken, and where sentences end."""
import re

ARABIC = re.compile(r"[ء-ي]")
LATIN = re.compile(r"[A-Za-z]")
DIAC = re.compile(r"[ً-ْٰ]")   # Arabic vowel marks
MAX_VOICE_WORDS = 20   # Spark stops at 18 s, about 30 words, so longer sentences are sent in parts
SENTENCE_END = re.compile(r"(?<=[.!؟?؛\n])\s+")


def speakable(s):
    """False for sentences that are mostly not Arabic: the Arabic voice would garble them, so they are shown only."""
    a, l = len(ARABIC.findall(s)), len(LATIN.findall(s))
    return a > 0 and l <= 0.3 * (a + l)


def clean_text(s):
    """Plain text ready for vowelling: no vowel marks, quotes or markdown; pauses as commas."""
    s = DIAC.sub("", s)
    s = re.sub(r"[«»\"“”*_`#]", "", s)
    s = re.sub(r"\s*(…|\.{2,})\s*", "، ", s)
    return " ".join(s.split()).strip(" ،")


def _sentences(t, finished):
    """Sentences, with one- or two-word fragments merged into the next. While the text is still arriving
    (finished=False), the last piece may change and a trailing fragment waits for the sentence it will join."""
    parts = [p.strip() for p in SENTENCE_END.split(t) if p.strip()]
    if not finished:
        parts = parts[:-1]
    out, carry = [], ""
    for p in parts:
        p = (carry + " " + p).strip() if carry else p
        carry = ""
        if len(p.split()) <= 2:
            carry = re.sub(r"[.!]+$", "،", p)
        else:
            out.append(p)
    if carry and finished:
        if out:
            out[-1] += " " + carry
        else:
            out.append(carry)
    return out


def split_sentences(t):
    return _sentences(t, True)


def complete_sentences(t):
    """Like split_sentences, for text that is still arriving: only sentences that can no longer change."""
    return _sentences(t, False)


def split_long(text, limit=MAX_VOICE_WORDS):
    """Split a long sentence into parts for the voice, at commas where possible."""
    parts, cur = [], []
    for clause in re.split(r"(?<=[،,؛:])\s+", text):
        words = clause.split()
        if cur and len(cur) + len(words) > limit:
            parts.append(" ".join(cur))
            cur = []
        while len(words) > limit:
            parts.append(" ".join(words[:limit]))
            words = words[limit:]
        cur += words
    if cur:
        parts.append(" ".join(cur))
    return parts
