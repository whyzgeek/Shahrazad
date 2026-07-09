"""Spike 3: CAMeL-Tools dialect identification on learner transcripts."""

from __future__ import annotations

from common import load_dotenv, load_learner_transcripts, ok, print_header, skip, write_result


def run() -> dict:
    print_header("Spike 3: CAMeL-Tools dialect ID")
    load_dotenv()

    try:
        from camel_tools.dialectid import DialectIdentifier
    except ImportError:
        return skip(
            "camel_dialect",
            "camel-tools not installed. Requires ~2GB+ disk for models/torch. "
            "Run: pip install 'camel-tools[all]' then camel_data -i dialectid.",
        )

    try:
        did = DialectIdentifier.pretrained()
    except Exception as exc:  # noqa: BLE001
        return skip("camel_dialect", f"CAMeL model load failed: {exc}. Run: camel_data -i dialectid")

    transcripts = load_learner_transcripts()
    rows = []
    for item in transcripts:
        text = item["text"]
        raw_predictions = did.predict(text)
        predictions = _normalize_predictions(raw_predictions)
        scores = _aggregate_scores(raw_predictions)
        top_label, top_score = predictions[0] if predictions else (None, None)
        rows.append(
            {
                "id": item["id"],
                "label": item["label"],
                "text": text,
                "top_dialect": top_label,
                "top_score": top_score,
                "p_msa": scores.get("MSA"),
                "predictions": predictions[:5],
                "drift_flag": _drift_flag(scores),
            }
        )

    result = {
        "rows": rows,
        "thresholds": {
            "msa_label": "MSA",
            "flag_if_top_not_msa_and_p_msa_lt": 0.05,
            "flag_if_top_non_msa_gt": 0.20,
        },
        "recommendation": (
            "CAMeL-Tools installed and runs (dialectid-model26). "
            "Text-only scores show very low P(MSA) even on clean MSA fixtures — "
            "use as a supplementary drift signal, not sole detector; "
            "re-tune thresholds on real learner audio in Phase 2; ADIDA fallback optional."
        ),
    }
    path = write_result("camel_dialect", result)
    print(f"Wrote {path}")
    for row in rows:
        print(f"  {row['id']}: {row['top_dialect']} ({row['top_score']}) drift={row['drift_flag']}")
    return ok("camel_dialect", **result)


def _aggregate_scores(raw_predictions) -> dict[str, float]:
    """Average word-level score vectors into one sentence-level distribution."""
    if not raw_predictions:
        return {}
    totals: dict[str, float] = {}
    count = 0
    for pred in raw_predictions:
        if not hasattr(pred, "scores"):
            continue
        count += 1
        for label, score in pred.scores.items():
            totals[label] = totals.get(label, 0.0) + float(score)
    if count == 0:
        return {}
    return {label: total / count for label, total in totals.items()}


def _normalize_predictions(raw_predictions) -> list[tuple[str, float]]:
    """CAMeL returns DIDPred objects (top + scores dict) or legacy tuples."""
    normalized: list[tuple[str, float]] = []
    for pred in raw_predictions or []:
        if hasattr(pred, "top") and hasattr(pred, "scores"):
            scores = pred.scores
            normalized.append((pred.top, float(scores.get(pred.top, 0.0))))
            continue
        if isinstance(pred, (list, tuple)) and len(pred) >= 2:
            normalized.append((str(pred[0]), float(pred[1])))
    if not normalized and raw_predictions:
        first = raw_predictions[0]
        if hasattr(first, "scores"):
            scores = first.scores
            normalized = sorted(
                ((label, float(score)) for label, score in scores.items()),
                key=lambda pair: pair[1],
                reverse=True,
            )
    return normalized


def _drift_flag(scores: dict[str, float]) -> bool:
    if not scores:
        return False
    p_msa = scores.get("MSA", 0.0)
    top_label = max(scores, key=scores.get)
    top_score = scores[top_label]
    if top_label == "MSA":
        return False
    return p_msa < 0.05 and top_score > 0.20


if __name__ == "__main__":
    run()
