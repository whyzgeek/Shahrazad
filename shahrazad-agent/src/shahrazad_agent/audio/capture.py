"""Buffer learner PCM during a turn and write mono 16 kHz WAV."""

from __future__ import annotations

import asyncio
import wave
from pathlib import Path

from livekit import rtc
from livekit.agents.voice import io

from shahrazad_agent.config import AUDIO_DIR

TARGET_SAMPLE_RATE = 16_000


class TurnAudioBuffer:
    def __init__(self) -> None:
        self._frames: list[rtc.AudioFrame] = []
        self._lock = asyncio.Lock()

    def push_frame(self, frame: rtc.AudioFrame) -> None:
        self._frames.append(frame)

    def reset(self) -> None:
        self._frames.clear()

    async def finalize_wav(self, session_id: str, turn_index: int) -> str | None:
        async with self._lock:
            if not self._frames:
                return None
            frames = list(self._frames)
            self._frames.clear()

        return await asyncio.to_thread(_write_wav, frames, session_id, turn_index)


class CapturingAudioInput(io.AudioInput):
    """Tee audio frames into a turn buffer while forwarding to STT."""

    def __init__(self, source: io.AudioInput, buffer: TurnAudioBuffer) -> None:
        super().__init__(label=f"capture-{source.label}", source=source)
        self._buffer = buffer

    async def __anext__(self) -> rtc.AudioFrame:
        frame = await super().__anext__()
        self._buffer.push_frame(frame)
        return frame


def _write_wav(frames: list[rtc.AudioFrame], session_id: str, turn_index: int) -> str | None:
    if not frames:
        return None

    session_dir = AUDIO_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / f"turn_{turn_index:04d}.wav"

    pcm = _resample_to_mono_16k(frames)
    if not pcm:
        return None

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_SAMPLE_RATE)
        wf.writeframes(pcm)

    return str(path)


def _resample_to_mono_16k(frames: list[rtc.AudioFrame]) -> bytes:
    resampler = rtc.AudioResampler(
        input_rate=frames[0].sample_rate,
        output_rate=TARGET_SAMPLE_RATE,
        num_channels=1,
    )
    chunks: list[bytes] = []
    for frame in frames:
        for out in resampler.push(frame):
            chunks.append(out.data.tobytes())
    for out in resampler.flush():
        chunks.append(out.data.tobytes())
    return b"".join(chunks)
