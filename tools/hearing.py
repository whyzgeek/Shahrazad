"""Hearing one push-to-talk turn. Both kinds of ear take audio with add() and return the whole turn's text from finish():

- StreamEar: Voxtral Realtime, which writes the words as they're spoken.
- ClipEar: cloud hearing, which transcribes whole clips. The turn is cut at natural pauses: each finished segment is
  transcribed once, and the unfinished one again every so often for the live caption.

16 kHz 16-bit mono PCM throughout. Partial text goes to the page through send(type="partial", ...).
"""
import array, asyncio, base64, json, os, time

import websockets

from . import providers

BYTES_PER_S = 32000
MAX_TURN_S = 180          # the clip ear keeps at most this much of one turn
SEGMENT_MIN_S = 4         # the clip ear cuts the turn at the next pause after this long...
SEGMENT_MAX_S = 15        # ...and at a shorter pause, or regardless, by this long
ROLL_AFTER_S = 55         # Voxtral: look for a pause to begin a new session (a session holds about 82 s)
ROLL_FORCE_S = 72         # ...and begin one regardless, before the session runs out
# Each live caption is a paid transcription of the unfinished segment, so they can be turned off to save credit.
CAPTION_EVERY_S = 1.5
CAPTIONS = os.environ.get("CLOUD_LIVE_CAPTIONS", "1").strip() not in ("0", "false", "no")


class Pauses:
    """Counts quiet chunks in a row, relative to the loudest recent speech."""

    def __init__(self):
        self.level, self.quiet = 0.0, 0

    def hear(self, pcm):
        a = array.array("h", pcm)
        rms = (sum(x * x for x in a[::4]) / max(len(a) // 4, 1)) ** 0.5
        self.level = max(self.level * 0.995, rms)
        self.quiet = self.quiet + 1 if rms < 0.12 * self.level else 0
        return self.quiet


async def stop_task(task):
    """Cancel a task and wait until it has stopped."""
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


class ClipEar:
    def __init__(self, http, send):
        self.http, self.send = http, send
        self.pcm, self.segments, self.caption = bytearray(), [], ""
        self.pauses, self.total, self.caption_task, self.caption_at = Pauses(), 0, None, time.time()
        self.finished = False

    async def start(self):
        await self.send(type="partial", text="…")

    async def add(self, pcm):
        if self.total >= MAX_TURN_S * BYTES_PER_S:
            return
        self.pcm.extend(pcm); self.total += len(pcm)
        quiet = self.pauses.hear(pcm)
        seconds = len(self.pcm) / BYTES_PER_S
        if (seconds >= SEGMENT_MIN_S and quiet >= 4) or (seconds >= SEGMENT_MAX_S and quiet >= 1) or seconds >= SEGMENT_MAX_S + 5:
            self.cut()
        elif CAPTIONS and seconds >= 1 and time.time() - self.caption_at >= CAPTION_EVERY_S and not (self.caption_task and not self.caption_task.done()):
            self.caption_at = time.time()
            self.caption_task = asyncio.create_task(self.update_caption(bytes(self.pcm), len(self.segments)))

    def cut(self):
        if len(self.pcm) > BYTES_PER_S * 0.3:   # under 0.3 s is a click, not speech
            task = asyncio.create_task(providers.transcribe(self.http, bytes(self.pcm)))
            task.add_done_callback(lambda _: CAPTIONS and asyncio.ensure_future(self.show()))
            self.segments.append(task)
        self.pcm, self.pauses.quiet, self.caption = bytearray(), 0, ""

    async def update_caption(self, pcm, index):
        try:
            text = await providers.transcribe(self.http, pcm)
        except Exception:
            return
        if index == len(self.segments):   # still the unfinished segment
            self.caption = text
            await self.show()

    def known(self):
        return [t.result() for t in self.segments if t.done() and not t.cancelled() and t.exception() is None]

    async def show(self):
        if self.finished:
            return   # the final text has been sent; a late caption mustn't replace it
        try:
            await self.send(type="partial", text=(" ".join(self.known() + [self.caption]).strip() or "…") + " …")
        except Exception:
            pass   # the connection may have closed

    async def finish(self):
        """The whole turn's text, in order. Raises if every segment failed."""
        self.finished = True
        self.cut()
        if not self.segments:
            return ""
        results = await asyncio.wait_for(asyncio.gather(*self.segments, return_exceptions=True), 60)
        texts = [r for r in results if isinstance(r, str)]
        if not texts and results:
            raise results[0]
        return " ".join(t for t in texts if t).strip()

    async def close(self):
        self.finished = True
        for t in self.segments + [self.caption_task]:
            await stop_task(t)


class StreamEar:
    """Voxtral's session holds about 82 s, so a longer turn continues in a new session at a pause ("rolling").
    Audio arriving while it rolls is held and sent afterwards, so none is lost."""

    def __init__(self, http, send):
        self.send = send
        self.vox = self.final = self.roll_task = self.reader = None
        self.parts, self.held, self.rolling, self.samples, self.pauses = [], [], False, 0, Pauses()

    async def start(self):
        self.vox = await websockets.connect(providers.VOX_URL, max_size=None)
        json.loads(await self.vox.recv())
        await self.vox.send(json.dumps({"type": "session.update", "model": "voxtral-ar"}))
        await self.vox.send(json.dumps({"type": "input_audio_buffer.commit"}))
        self.final = asyncio.get_running_loop().create_future()
        self.reader = asyncio.create_task(self.read(self.vox, self.final))   # kept, so it isn't garbage-collected

    async def read(self, vox, final):
        text = ""
        try:
            async for m in vox:
                d = json.loads(m)
                if d["type"] == "transcription.delta":
                    text += d["delta"]
                    await self.send(type="partial", text=" ".join(self.parts + [text]).strip())
                elif d["type"] == "transcription.done":
                    final.done() or final.set_result(d["text"].strip())
                    return
                elif d["type"] == "error":
                    await self.send(type="error", text=str(d.get("error")))
                    final.done() or final.set_result("")
                    return
        except websockets.ConnectionClosed:
            final.done() or final.set_result(text.strip())

    async def push(self, pcm):
        await self.vox.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()}))
        self.samples += len(pcm) // 2

    async def add(self, pcm):
        if self.rolling:
            self.held.append(pcm)
            return
        if not self.vox:
            return
        await self.push(pcm)
        seconds = self.samples / 16000
        if seconds >= ROLL_AFTER_S and (self.pauses.hear(pcm) >= 2 or seconds >= ROLL_FORCE_S):
            self.rolling = True
            self.roll_task = asyncio.create_task(self.roll())

    async def end_session(self, wait):
        """Ask Voxtral for the session's final text, then close it."""
        await self.vox.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
        try:
            return await asyncio.wait_for(self.final, wait)
        finally:
            await self.vox.close()
            self.vox = None

    async def roll(self):
        try:
            heard = await self.end_session(30)
            if heard:
                self.parts.append(heard)
            await self.start()
            self.samples, self.pauses = 0, Pauses()
            while self.held:
                await self.push(self.held.pop(0))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.send(type="error", text=f"Part of your speech may be missing ({type(e).__name__}).")
        finally:
            self.rolling = False

    async def finish(self):
        if self.roll_task:
            try:
                await self.roll_task
            except (asyncio.CancelledError, Exception):
                pass
        last = ""
        if self.vox:
            try:
                last = await self.end_session(20)
            except asyncio.TimeoutError:
                pass
        return " ".join(self.parts + [last]).strip()

    async def close(self):
        await stop_task(self.roll_task)
        if self.vox:
            await self.vox.close()
            self.vox = None


async def listen(http, send):
    """A started ear of the kind set in .env, for one turn."""
    ear = (StreamEar if providers.HEARING == "local" else ClipEar)(http, send)
    await ear.start()
    return ear
