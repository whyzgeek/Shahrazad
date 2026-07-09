"""Spike 2: STT latency — Azure ar-SA vs Deepgram Nova-3 ar-SA (optional)."""

from __future__ import annotations

import time
from pathlib import Path

from common import FIXTURES, env, load_dotenv, ok, print_header, require_env, skip, write_result


def _audio_files() -> list[Path]:
    return sorted((FIXTURES / "audio").glob("*.wav"))


def _azure_stt(audio_path: Path, speech_key: str, region: str) -> dict:
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    speech_config.speech_recognition_language = "ar-SA"
    audio_config = speechsdk.audio.AudioConfig(filename=str(audio_path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    started = time.perf_counter()
    result = recognizer.recognize_once_async().get()
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    return {
        "provider": "azure",
        "elapsed_ms": elapsed_ms,
        "text": result.text if result.reason.name == "RecognizedSpeech" else None,
        "reason": str(result.reason),
    }


def _deepgram_stt(audio_path: Path, api_key: str) -> dict:
    import httpx

    started = time.perf_counter()
    with audio_path.open("rb") as handle:
        response = httpx.post(
            "https://api.deepgram.com/v1/listen",
            params={
                "model": "nova-3",
                "language": "ar-SA",
                "smart_format": "true",
            },
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "audio/wav",
            },
            content=handle.read(),
            timeout=60.0,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    payload = response.json()
    transcript = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript")
    )
    return {
        "provider": "deepgram",
        "elapsed_ms": elapsed_ms,
        "text": transcript,
    }


def run() -> dict:
    print_header("Spike 2: STT latency (Azure vs Deepgram)")
    load_dotenv()

    audio_files = _audio_files()
    if not audio_files:
        return skip(
            "stt_latency",
            "No WAV files in spikes/fixtures/audio/.",
        )

    try:
        creds = require_env("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
    except RuntimeError as exc:
        return skip("stt_latency", str(exc))

    try:
        import azure.cognitiveservices.speech  # noqa: F401
        import httpx  # noqa: F401
    except ImportError:
        return skip("stt_latency", "Install deps: pip install -r spikes/requirements.txt")

    rows = []
    for audio_path in audio_files:
        row = {"file": audio_path.name, "providers": []}
        row["providers"].append(_azure_stt(audio_path, creds["AZURE_SPEECH_KEY"], creds["AZURE_SPEECH_REGION"]))
        deepgram_key = env("DEEPGRAM_API_KEY")
        if deepgram_key:
            row["providers"].append(_deepgram_stt(audio_path, deepgram_key))
        rows.append(row)

    azure_ms = [p["elapsed_ms"] for row in rows for p in row["providers"] if p["provider"] == "azure"]
    deepgram_ms = [p["elapsed_ms"] for row in rows for p in row["providers"] if p["provider"] == "deepgram"]

    recommendation = "Azure only (no DEEPGRAM_API_KEY)"
    if deepgram_ms and azure_ms:
        avg_azure = sum(azure_ms) / len(azure_ms)
        avg_deepgram = sum(deepgram_ms) / len(deepgram_ms)
        if avg_deepgram + 100 < avg_azure:
            recommendation = "Prefer Deepgram for STT if WER acceptable in manual review"
        else:
            recommendation = "Prefer Azure STT (shared account with PA/TTS; latency acceptable)"

    result = {
        "rows": rows,
        "avg_azure_ms": round(sum(azure_ms) / len(azure_ms), 1) if azure_ms else None,
        "avg_deepgram_ms": round(sum(deepgram_ms) / len(deepgram_ms), 1) if deepgram_ms else None,
        "recommendation": recommendation,
    }
    path = write_result("stt_latency", result)
    print(f"Wrote {path}")
    print(f"Recommendation: {recommendation}")
    return ok("stt_latency", **result)


if __name__ == "__main__":
    run()
