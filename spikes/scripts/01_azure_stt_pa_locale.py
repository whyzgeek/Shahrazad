"""Spike 1: Azure STT + Pronunciation Assessment locale parity (ar-SA vs ar-EG)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from common import FIXTURES, fail, load_dotenv, ok, print_header, require_env, skip, write_result

LOCALES = ("ar-SA", "ar-EG")


def _audio_files() -> list[Path]:
    audio_dir = FIXTURES / "audio"
    return sorted(audio_dir.glob("*.wav"))


def _run_pa(audio_path: Path, reference_text: str, locale: str, speech_key: str, region: str) -> dict:
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    speech_config.speech_recognition_language = locale

    audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    pa_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Word,
        enable_miscue=False,
    )
    pa_config.apply_to(recognizer)

    started = time.perf_counter()
    result = recognizer.recognize_once_async().get()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        return {
            "locale": locale,
            "elapsed_ms": elapsed_ms,
            "error": str(result.reason),
            "details": result.cancellation_details.error_details if result.cancellation_details else None,
        }

    pa_result = speechsdk.PronunciationAssessmentResult(result)
    words = []
    if pa_result.words:
        for word in pa_result.words:
            words.append(
                {
                    "word": word.word,
                    "accuracy": word.accuracy_score,
                    "error_type": word.error_type,
                }
            )

    return {
        "locale": locale,
        "elapsed_ms": elapsed_ms,
        "recognized_text": result.text,
        "accuracy_score": pa_result.accuracy_score,
        "fluency_score": pa_result.fluency_score,
        "completeness_score": pa_result.completeness_score,
        "pronunciation_score": pa_result.pronunciation_score,
        "words": words,
    }


def _run_stt(audio_path: Path, locale: str, speech_key: str, region: str) -> dict:
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    speech_config.speech_recognition_language = locale
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    started = time.perf_counter()
    result = recognizer.recognize_once_async().get()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        return {
            "locale": locale,
            "elapsed_ms": elapsed_ms,
            "error": str(result.reason),
        }

    detailed = json.loads(result.json)
    return {
        "locale": locale,
        "elapsed_ms": elapsed_ms,
        "text": result.text,
        "confidence": detailed.get("NBest", [{}])[0].get("Confidence"),
    }


def run() -> dict:
    print_header("Spike 1: Azure STT + PA locale parity")
    load_dotenv()

    try:
        creds = require_env("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
    except RuntimeError as exc:
        return skip("azure_stt_pa_locale", str(exc))

    audio_files = _audio_files()
    if not audio_files:
        return skip(
            "azure_stt_pa_locale",
            "No WAV files in spikes/fixtures/audio/. Add learner MSA clips (16 kHz mono PCM recommended).",
        )

    try:
        import azure.cognitiveservices.speech  # noqa: F401
    except ImportError:
        return skip("azure_stt_pa_locale", "Install deps: pip install -r spikes/requirements.txt")

    # Default reference text for PA; override by naming audio `<id>.wav` matching fixtures.
    default_reference = "مرحباً، كيف حالك اليوم؟"

    results = {"audio_files": [], "recommendation": None}
    for audio_path in audio_files:
        entry = {"file": audio_path.name, "locales": {}}
        reference = default_reference
        for locale in LOCALES:
            stt = _run_stt(audio_path, locale, creds["AZURE_SPEECH_KEY"], creds["AZURE_SPEECH_REGION"])
            pa = _run_pa(
                audio_path,
                reference,
                locale,
                creds["AZURE_SPEECH_KEY"],
                creds["AZURE_SPEECH_REGION"],
            )
            entry["locales"][locale] = {"stt": stt, "pa": pa}
        results["audio_files"].append(entry)

    # Simple heuristic: prefer locale with PA word scores present and higher accuracy.
    sa_scores = []
    eg_scores = []
    for entry in results["audio_files"]:
        for locale_key, bucket in (("ar-SA", sa_scores), ("ar-EG", eg_scores)):
            pa = entry["locales"][locale_key]["pa"]
            if pa.get("accuracy_score") is not None:
                bucket.append(pa["accuracy_score"])

    if sa_scores and max(sa_scores) >= 50:
        results["recommendation"] = "Use ar-SA for both STT and PA"
    elif eg_scores:
        results["recommendation"] = "Use ar-EG for both STT and PA (ar-SA PA weak or missing)"
    else:
        results["recommendation"] = "Inconclusive — inspect word-level PA output manually"

    path = write_result("azure_stt_pa_locale", results)
    print(f"Wrote {path}")
    print(f"Recommendation: {results['recommendation']}")
    return ok("azure_stt_pa_locale", **results)


if __name__ == "__main__":
    run()
