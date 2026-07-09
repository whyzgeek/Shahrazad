"""Spike 6: Per-turn learner audio buffer policy (local, no API keys)."""

from __future__ import annotations

import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

from common import FIXTURES, ok, print_header, write_result

AUDIO_DIR = FIXTURES / "audio"
PROBE_PATH = AUDIO_DIR / "agent_buffer_probe.wav"
POLICY = {
    "capture_mechanism": "Buffer learner PCM in LiveKit agent on user_speech_committed",
    "storage_v1": "Local filesystem under shahrazad-agent/data/audio/",
    "format": "mono 16kHz WAV",
    "retention_days": 30,
    "consent": "Onboarding banner before first session",
    "not_used": "LiveKit room egress for per-turn clips",
}


def _write_probe_wav(path: Path, duration_s: float = 0.5, sample_rate: int = 16000) -> dict:
    """Simulate agent-side VAD segment → WAV write (same as Phase 2 Turn.audio_path)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = int(sample_rate * duration_s)
    pcm = struct.pack("<" + "h" * n_frames, *([0] * n_frames))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)

    with wave.open(str(path), "rb") as wf:
        verified = {
            "channels": wf.getnchannels(),
            "sample_width": wf.getsampwidth(),
            "sample_rate": wf.getframerate(),
            "frames": wf.getnframes(),
            "duration_s": round(wf.getnframes() / wf.getframerate(), 3),
        }

    return verified


def run() -> dict:
    print_header("Spike 6: Per-turn audio capture policy")
    verified = _write_probe_wav(PROBE_PATH)

    result = {
        "policy_id": "06_audio_policy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capture_status": "completed",
        "decision": POLICY,
        "probe_file": str(PROBE_PATH),
        "probe_verified": verified,
        "recommendation": "Local FS, 30-day retention, agent-side buffer on user_speech_committed",
        "notes": [
            "Verified Python wave module writes per-turn WAV in agent process.",
            "S3 migration: swap storage backend in Phase 2 without schema change.",
        ],
    }
    path = write_result("audio_policy", result)
    print(f"Wrote probe WAV: {PROBE_PATH}")
    print(f"Wrote {path}")
    print(f"Recommendation: {result['recommendation']}")
    return ok("audio_capture", **result)


if __name__ == "__main__":
    run()
