"""Generate grammar drill sentence sets (target + similar pattern)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger("shahrazad.drill.grammar")

GRAMMAR_DRILL_SYSTEM = """\
You create short MSA (Modern Standard Arabic) sentence drills for ONE grammar mistake.

Return JSON with this exact shape:
{"sentences": ["...", "...", "..."]}

Rules:
- Identify the SINGLE grammar rule from the note (agreement, article, preposition, connector, etc.).
- sentences[0]: one clean MSA sentence that uses the corrected form naturally.
- sentences[1..N]: NEW short MSA sentences that practice ONLY that same rule.
- Prefer the given "MSA correction" as the core of sentences[0] when it is already a short phrase/sentence.
- Each sentence: at most 8 words, one clause, conversational MSA.
- Keep vocabulary inside the lesson topic when possible.

FORBIDDEN in every sentence:
- Hesitation / self-correction: «لا،»، «يعني»، «أقصد»، «أو»، mid-sentence restarts
- Run-on sentences that rewrite the learner's whole messy utterance
- Odd or unnatural patterns (e.g. «أنت مبرمجة اسمها فاطمة»)
- Teaching multiple rules at once

Good example:
- Mistake: wrong gender on demonstrative (هذا مدرسة)
- sentences: ["هذه مدرسة كبيرة.", "هذه جامعة جديدة.", "هذه مكتبة قريبة."]

Bad example (never do this):
- "أنا أدرس، لا، أنا أعمل، ولكنني أعمل في المدينة."
- "أنت مبرمجة اسمها فاطمة." (unnatural; do not invent name+job gender puzzles)
"""


class GrammarDrillResponse(BaseModel):
    sentences: list[str] = Field(min_length=1)


_HESITATION_RE = re.compile(
    r"(?:^|[\s،,])(?:لا|يعني|أقصد|عفواً|أو)(?:[\s،,]|$)|،\s*لا\s*،"
)


def _is_clean_drill_sentence(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    words = re.findall(r"[\u0600-\u06FF]+", s)
    if len(words) > 8:
        return False
    if _HESITATION_RE.search(s):
        return False
    # Multiple clause restarts (more than one ، لا / restart markers already caught).
    if s.count("،") >= 3:
        return False
    return True


def _clean_correct_form(correct_form: str) -> str:
    """Prefer a short correction; strip hesitation-style rewrites."""
    base = correct_form.strip().rstrip(".؟!").strip()
    if not base:
        return ""
    if _is_clean_drill_sentence(base) and "ولكنني" not in base and "ولكن" not in base:
        return base

    # Drop hesitation markers, then split into clauses.
    text = re.sub(r"(?:^|،\s*)(?:لا|يعني|أقصد)\s*،?\s*", "، ", base)
    clauses = [c.strip(" ،") for c in text.split("،") if c.strip(" ،")]
    pronouns = ("أنا", "هو", "هي", "أنت", "أنتِ", "نحن", "هم", "هن")

    for clause in reversed(clauses):
        clause = re.sub(r"^(?:ولكنني|ولكن|و)\s+", "", clause).strip()
        words = re.findall(r"[\u0600-\u06FF]+", clause)
        if not words:
            continue
        if words[0] not in pronouns:
            for prev in reversed(clauses):
                pw = re.findall(r"[\u0600-\u06FF]+", prev)
                if pw and pw[0] in pronouns:
                    clause = f"{pw[0]} {clause}"
                    break
        word_count = len(re.findall(r"[\u0600-\u06FF]+", clause))
        if word_count == 0 or word_count > 8:
            continue
        if _HESITATION_RE.search(clause):
            continue
        return clause

    words = re.findall(r"[\u0600-\u06FF]+", base)
    return " ".join(words[:8]).strip()


def _fallback_sentences(correct_form: str, similar_count: int) -> list[str]:
    """Minimal fallback when the LLM call fails."""
    base = _clean_correct_form(correct_form)
    if not base:
        return []
    out = [base if base.endswith((".", "؟", "!")) else f"{base}."]
    return out[: 1 + similar_count]


async def generate_grammar_drill_sentences(
    *,
    client: AsyncOpenAI,
    learner_text: str,
    correct_form: str,
    explanation_en: str = "",
    explanation_ar: str = "",
    topic_hint: str = "",
    similar_count: int = 2,
) -> list[str]:
    """Return [corrected sentence, ...similar pattern sentences]."""
    correct = _clean_correct_form(correct_form)
    if not correct:
        return []

    user_content = (
        f"Topic: {topic_hint}\n"
        f"Learner said (problem span): {learner_text}\n"
        f"MSA correction (use as core of sentence 0 if short/clean): {correct}\n"
        f"Original judge correction (may be messy — do NOT copy hesitations): {correct_form}\n"
        f"Grammar note (EN): {explanation_en}\n"
        f"Grammar note (AR): {explanation_ar}\n"
        f"Number of similar-pattern sentences to add: {similar_count}\n"
        "Remember: short clean sentences only; never practice hesitation or self-correction."
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": GRAMMAR_DRILL_SYSTEM},
                {"role": "user", "content": user_content},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        payload: dict[str, Any] = json.loads(raw)
        parsed = GrammarDrillResponse.model_validate(payload)
        sentences = [s.strip() for s in parsed.sentences if s.strip()]
        sentences = [s for s in sentences if _is_clean_drill_sentence(s)]
        if not sentences:
            return _fallback_sentences(correct, similar_count)
        # Prefer cleaned correction as sentence 0 when the model still drifts.
        if not _is_clean_drill_sentence(sentences[0]) or len(
            re.findall(r"[\u0600-\u06FF]+", sentences[0])
        ) > 8:
            sentences[0] = correct if correct.endswith((".", "؟", "!")) else f"{correct}."
        if len(sentences) < 1 + similar_count:
            # Do not pad with awkward templates; fewer clean sentences is better.
            pass
        return sentences[: 1 + similar_count]
    except (ValidationError, json.JSONDecodeError, IndexError, KeyError) as exc:
        logger.warning("grammar drill sentence generation failed: %s", exc)
        return _fallback_sentences(correct, similar_count)
