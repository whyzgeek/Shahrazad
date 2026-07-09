"""GPT-4o-mini error judge — grammar, vocabulary, dialect drift."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("shahrazad.judge")

JudgeKind = Literal["grammar", "vocabulary", "dialect_drift"]
Severity = Literal["info", "minor", "major"]

_VALID_KINDS = {"grammar", "vocabulary", "dialect_drift"}

_MSA_PRONOUNS = frozenset(
    {
        "أنا",
        "نحن",
        "أنت",
        "أنتَ",
        "أنتِ",
        "أنتم",
        "أنتن",
        "هو",
        "هي",
        "هما",
        "هم",
        "هن",
    }
)

_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_NAME_QUESTION = re.compile(
    r"(ما\s*اسمك|ما\s*اسمُك|اسمك\s*ما|what(?:'s| is)?\s+your\s+name)",
    re.IGNORECASE,
)

# Common MSA loanword spelling pairs — do not treat as vocabulary errors.
_LOANWORD_VARIANTS = (
    ("كومبيوتر", "كمبيوتر"),
    ("كمبيوتر", "كومبيوتر"),
    ("انترنت", "إنترنت"),
    ("إنترنت", "انترنت"),
    ("تلفون", "هاتف"),
)


class JudgeErrorItem(BaseModel):
    kind: JudgeKind
    severity: Severity = "minor"
    learner_text: str
    correct_form: str
    explanation_ar: str
    explanation_en: str


class JudgeResponse(BaseModel):
    errors: list[JudgeErrorItem] = Field(default_factory=list)


JUDGE_SYSTEM = """\
You are a strict MSA (Modern Standard Arabic) error detector for a language tutor.
Be thorough on real grammar/dialect mistakes, but NEVER invent errors on names or answers to identity questions.

Return JSON with this exact shape:
{
  "errors": [
    {
      "kind": "grammar",
      "severity": "minor",
      "learner_text": "problematic span copied from utterance",
      "correct_form": "MSA correction",
      "explanation_ar": "1–2 clear Arabic sentences: what is wrong and the rule",
      "explanation_en": "1–2 clear English sentences: what is wrong and the rule"
    }
  ]
}

kind must be one of: grammar, vocabulary, dialect_drift
severity must be one of: info, minor, major

Always scan for ALL of these (return a separate object per distinct issue):
1. Dialect drift: إنت/انتي، ليش، شو، بدي، حبيبي as address, diglossic verb forms, etc.
   Do NOT flag standard MSA أنت / أنتِ / أنتم as dialect.
2. Subject–verb agreement (gender/person/number): أنت يذهب → أنت تذهب
3. Demonstrative / noun agreement: هذا مدرسة → هذه مدرسة
4. Definite article mistakes: أذهب إلى مدرسة → أذهب إلى المدرسة (generic "school")
5. Wrong preposition or particle
6. Wrong lexical choice for MSA (true vocabulary mistakes only)
7. Word order that is clearly non-MSA

Names and identity answers (critical):
- If the tutor just asked for the learner's name (ما اسمك؟) and the learner replies with a
  short token (one word / name-like), treat it as a NAME. Return {"errors": []}.
- Do NOT "correct" names into dictionary words (تسميكية → تسمية is WRONG).
- Do NOT flag proper names, nicknames, or STT garbling of names as vocabulary errors.
- «أنا من نيويورك» / «أنا بخير» with no other issues → {"errors": []}.
- Do NOT flag transliteration variants of loanwords as vocabulary errors
  (الكومبيوتر vs الكمبيوتر, إنترنت spellings, etc.). Prefer silence over pedantry there.

Other rules:
- Scan EACH clause separately; do not merge distinct mistakes.
- One utterance can produce MULTIPLE real errors.
- Prefer severity "major" for agreement and dialect; "minor" for article/preposition.
- Explanations: teach the rule briefly (why it is wrong + how to fix it). Aim for
  about 15–35 words in each language — not a one-word label, not a lecture.
  Example AR: «استخدم "لست" مع اسم الفاعل المنصوب: مطمئناً، لأن "ليس" تنصب الخبر.»
  Example EN: «After ليس / لست the predicate takes the accusative: مطمئناً, not مطمئن.»
- When in doubt on a clear agreement/dialect/article issue, FLAG it.
- When in doubt on a name, identity answer, or loanword spelling, DO NOT FLAG.
- Do NOT flag stylistic redundancy or "unnecessary" words
  (e.g. «أنا في مدينتي هنا» → do not invent an error just to drop «هنا»).
- Do NOT flag vague but grammatical answers like «أنا من هنا» when answering origin.
- correct_form must be a SHORT clean MSA phrase/sentence (≤ 8 words), never a
  hesitation rewrite like «أنا أدرس، لا، أنا أعمل…». Fix only the error span.
- Do NOT invent gender/name patterns that the learner did not attempt
  (e.g. do not turn a job-title slip into «مبرمجة اسمها …» drills in the note itself).

Examples:
- Tutor asked name; learner «تسميكية» or «كيا» or «سعيد» → {"errors": []}
- «أنا مبرمج الكومبيوتر» → {"errors": []} (loanword spelling variant)
- «أنا في مدينتي هنا» → {"errors": []} (stylistic; not a real MSA error)
- Learner hesitation «أنا أدرس، لا، أنا أعمل في المدينة» with no real grammar error
  → {"errors": []} (self-correction is not an error to drill)
- «شركتي مبرمجة» (meant programming company) → one note with short correct_form
  like «شركة برمجة» — not a long rewritten monologue
- «أنا من هنا» → {"errors": []}
- «أنا وبرمج» → grammar: أنا وبرمج → أنا أبرمج
- «إنت يذهب» → dialect إنت→أنت; agreement يذهب→تذهب
- «أنت يذهب إلى مدرسة» → يذهب→تذهب; إلى مدرسة→إلى المدرسة
- «أنا أذهب إلى مدرسة» → إلى مدرسة → إلى المدرسة
- «أنا بخير.» → no errors
- «أنا من نيويورك.» → no errors
"""


@dataclass
class JudgeHit:
    kind: str
    severity: str
    learner_text: str
    correct_form: str
    explanation_ar: str
    explanation_en: str


def _strip_tashkeel(text: str) -> str:
    return _TASHKEEL.sub("", text).strip()


def _looks_like_name_answer(learner_text: str, tutor_context: str) -> bool:
    """Heuristic: short reply after a name question is almost certainly a name."""
    if not tutor_context or not _NAME_QUESTION.search(tutor_context):
        return False
    tokens = [t for t in re.split(r"\s+", learner_text.strip()) if t]
    if len(tokens) > 4:
        return False
    # Full sentence with clear grammar words is not "just a name"
    joined = " ".join(tokens)
    if any(w in joined for w in ("يذهب", "تذهب", "مدرسة", "هذا", "هذه", "إنت")):
        return False
    return True


def _is_spurious(kind: str, learner_text: str, correct_form: str, explanation_en: str = "") -> bool:
    learner = _strip_tashkeel(learner_text)
    correct = _strip_tashkeel(correct_form)
    if kind == "dialect_drift" and learner in _MSA_PRONOUNS:
        return True
    if learner and correct and learner == correct:
        return True
    if kind == "vocabulary":
        for a, b in _LOANWORD_VARIANTS:
            if a in learner and b in correct:
                return True
            if b in learner and a in correct:
                return True
    # Style-only notes ("unnecessary", "redundant", "here is not needed")
    expl = (explanation_en or "").lower()
    if any(
        phrase in expl
        for phrase in (
            "unnecessary",
            "redundant",
            "not needed",
            "not necessary",
            "superfluous",
            "can be omitted",
            "omit ",
            "hesitation",
            "self-correction",
            "self correction",
            "rephrasing",
        )
    ):
        return True
    # Hesitation rewrites are not drillable grammar notes.
    if "، لا،" in correct or "، لا ،" in correct:
        return True
    if correct.count("،") >= 3:
        return True
    return False


def _shorten_correct_form(correct_form: str) -> str:
    """Keep sidebar/drill targets short and clean."""
    base = correct_form.strip()
    if not base:
        return base
    words = re.findall(r"[\u0600-\u06FF]+", base)
    if len(words) <= 8 and "، لا،" not in base:
        return base
    # Prefer the last clause after a hesitation restart.
    parts = re.split(r"(?:،\s*)?(?:لا|يعني|أقصد)\s*،?\s*", base)
    parts = [p.strip(" ،") for p in parts if p and p.strip(" ،")]
    if parts:
        candidate = parts[-1]
        w = re.findall(r"[\u0600-\u06FF]+", candidate)
        if 0 < len(w) <= 8:
            return candidate
    return " ".join(words[:8])


def _normalize_errors(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_errors = payload.get("errors") or []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for item in raw_errors:
        if not isinstance(item, dict):
            continue

        kind = item.get("kind") or item.get("flag") or item.get("type") or "grammar"
        if kind not in _VALID_KINDS:
            kind = "grammar"

        learner_text = (item.get("learner_text") or item.get("text") or "").strip()
        correct_form = (item.get("correct_form") or item.get("correction") or "").strip()
        if not learner_text or not correct_form:
            continue

        explanation_ar = item.get("explanation_ar") or ""
        explanation_en = item.get("explanation_en") or ""
        explanations = item.get("explanations")
        if isinstance(explanations, list):
            if not explanation_ar and len(explanations) > 0:
                explanation_ar = str(explanations[0])
            if not explanation_en and len(explanations) > 1:
                explanation_en = str(explanations[1])

        if _is_spurious(kind, learner_text, correct_form, explanation_en):
            continue

        correct_form = _shorten_correct_form(correct_form)
        if not correct_form:
            continue

        dedupe_key = (kind, _strip_tashkeel(learner_text))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        severity = item.get("severity") or "minor"
        if severity not in ("info", "minor", "major"):
            severity = "minor"

        normalized.append(
            {
                "kind": kind,
                "severity": severity,
                "learner_text": learner_text,
                "correct_form": correct_form,
                "explanation_ar": explanation_ar or correct_form,
                "explanation_en": explanation_en or correct_form,
            }
        )

    return normalized


async def run_judge(
    *,
    client: AsyncOpenAI,
    learner_text: str,
    topic_hint: str = "",
    tutor_context: str = "",
) -> list[JudgeHit]:
    if not learner_text.strip():
        return []

    if _looks_like_name_answer(learner_text, tutor_context):
        logger.info("judge skipped — treating utterance as name answer: %s", learner_text[:40])
        return []

    user_content = (
        f"Topic context: {topic_hint}\n"
        f"Previous tutor line (for context): {tutor_context or '(none)'}\n"
        f"Learner utterance (flag every distinct MSA issue; never invent name corrections):\n"
        f"{learner_text}"
    )
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_content},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        payload = json.loads(raw)
        normalized = _normalize_errors(payload)
        parsed = JudgeResponse.model_validate({"errors": normalized})
    except (ValidationError, json.JSONDecodeError, IndexError, KeyError) as exc:
        logger.warning("judge parse failed: %s", exc)
        return []

    return [
        JudgeHit(
            kind=item.kind,
            severity=item.severity,
            learner_text=item.learner_text,
            correct_form=item.correct_form,
            explanation_ar=item.explanation_ar,
            explanation_en=item.explanation_en,
        )
        for item in parsed.errors
    ]
