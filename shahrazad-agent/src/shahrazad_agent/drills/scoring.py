"""Drill scoring — text-match with content-word checks for grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_TASHKEEL_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_PUNCT_RE = re.compile(r"[^\w\u0600-\u06FF\s]+", re.UNICODE)
_WORD_RE = re.compile(r"[\u0600-\u06FF]+|[A-Za-z0-9]+")
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")

# Function words we don't require exact match on for "content coverage".
_FUNCTION_WORDS = frozenset(
    {
        "في",
        "من",
        "إلى",
        "على",
        "عن",
        "مع",
        "و",
        "أو",
        "ثم",
        "أن",
        "إن",
        "ما",
        "لا",
        "لم",
        "لن",
        "قد",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "هو",
        "هي",
        "هم",
        "أنا",
        "أنت",
        "نحن",
        "التي",
        "الذي",
        "الذين",
    }
)


@dataclass(frozen=True)
class DrillScore:
    accuracy_score: float
    completeness_score: float | None
    fluency_score: float | None
    scoring_mode: str  # text_match | grammar
    passed: bool


def strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text).strip()


def normalize_for_match(text: str) -> str:
    """Strip tashkeel + punctuation and collapse whitespace for comparison."""
    plain = strip_tashkeel(text)
    plain = _PUNCT_RE.sub(" ", plain)
    return re.sub(r"\s+", " ", plain).strip()


def arabic_letter_ratio(text: str) -> float:
    """Share of letters that are Arabic script (ignores digits/spaces)."""
    ar = len(_ARABIC_LETTER_RE.findall(text))
    la = len(_LATIN_LETTER_RE.findall(text))
    total = ar + la
    if total == 0:
        return 0.0
    return ar / total


def looks_like_latin_stt(transcript: str, *, target_text: str = "") -> bool:
    """True when the transcript is mostly Latin but we expected Arabic.

    Realtime STT sometimes returns phonetic English spellings of Arabic
    (e.g. "hov w Mubarmiju") which must not be scored as a failed attempt.
    """
    text = (transcript or "").strip()
    if not text:
        return False
    target = target_text or ""
    # Only relevant when the drill target is Arabic.
    if target and arabic_letter_ratio(target) < 0.5:
        return False
    return arabic_letter_ratio(text) < 0.4


def tokenize_ar(text: str) -> list[str]:
    return _WORD_RE.findall(strip_tashkeel(text))


def text_match_score(transcript: str, target: str) -> float:
    a = normalize_for_match(transcript)
    b = normalize_for_match(target)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio() * 100.0


def _content_words(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _FUNCTION_WORDS and len(t) > 1]


def _word_close(a: str, b: str) -> bool:
    if a == b:
        return True
    # Allow missing/extra definite article only when the stem matches.
    if a.removeprefix("ال") == b.removeprefix("ال") and (
        a.startswith("ال") or b.startswith("ال")
    ):
        # Article presence differs — not close enough for grammar drills.
        return False
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio >= 0.86


def content_coverage(transcript: str, target: str) -> float:
    """Fraction of target content words that appear (closely) in the transcript."""
    target_words = _content_words(tokenize_ar(target))
    if not target_words:
        return 1.0
    heard = tokenize_ar(transcript)
    matched = 0
    used: set[int] = set()
    for tw in target_words:
        for i, hw in enumerate(heard):
            if i in used:
                continue
            if _word_close(tw, hw):
                matched += 1
                used.add(i)
                break
    return matched / len(target_words)


def article_ok(transcript: str, target: str) -> bool:
    """Fail if a target noun with ال is repeated without ال (same stem)."""
    target_tokens = tokenize_ar(target)
    heard = tokenize_ar(transcript)
    heard_set = set(heard)
    for tw in target_tokens:
        if not tw.startswith("ال") or len(tw) < 4:
            continue
        stem = tw[2:]
        # Learner said the bare stem but not the definite form.
        if stem in heard_set and tw not in heard_set:
            return False
    return True


async def score_drill_attempt(
    *,
    transcript: str,
    target_text: str,
    accuracy_threshold: float,
) -> DrillScore:
    """Score a pronunciation drill repeat using normalized text match."""
    ratio = text_match_score(transcript, target_text.strip())
    return DrillScore(
        accuracy_score=ratio,
        completeness_score=None,
        fluency_score=None,
        scoring_mode="text_match",
        passed=ratio >= accuracy_threshold,
    )


def score_grammar_drill(
    *,
    transcript: str,
    target_text: str,
    accuracy_threshold: float,
) -> DrillScore:
    """Score a grammar drill: overall similarity + content words + articles."""
    target = target_text.strip()
    ratio = text_match_score(transcript, target)
    coverage = content_coverage(transcript, target)
    articles = article_ok(transcript, target)

    # Content words must mostly match; article mistakes fail even if ratio is high.
    passed = (
        ratio >= accuracy_threshold
        and coverage >= 0.85
        and articles
    )
    return DrillScore(
        accuracy_score=ratio,
        completeness_score=coverage * 100.0,
        fluency_score=None,
        scoring_mode="grammar",
        passed=passed,
    )
