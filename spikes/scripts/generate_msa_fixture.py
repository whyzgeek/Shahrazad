#!/usr/bin/env python3
"""Generate spikes/fixtures/audio/msa_greeting.wav via Azure Neural TTS (needs .env)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from common import FIXTURES, load_dotenv, require_env  # noqa: E402

TEXT = "مرحباً، كيف حالك اليوم؟"
OUT = FIXTURES / "audio" / "msa_greeting.wav"
VOICE = "ar-SA-HamedNeural"


def main() -> int:
    load_dotenv()
    try:
        creds = require_env("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
    except RuntimeError as exc:
        print(f"Cannot generate fixture: {exc}")
        return 1

    import azure.cognitiveservices.speech as speechsdk

    OUT.parent.mkdir(parents=True, exist_ok=True)
    speech_config = speechsdk.SpeechConfig(
        subscription=creds["AZURE_SPEECH_KEY"],
        region=creds["AZURE_SPEECH_REGION"],
    )
    speech_config.speech_synthesis_voice_name = VOICE
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
    )
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(OUT))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )
    result = synthesizer.speak_text_async(TEXT).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"TTS failed: {result.reason}")
        if result.cancellation_details:
            print(result.cancellation_details.error_details)
        return 1

    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"Reference text for PA spike: {TEXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
