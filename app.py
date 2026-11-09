"""Shahrazad: Arabic (MSA) speaking tutor, push-to-talk.

Browser mic -> Voxtral (vLLM) -> Gemma 4 (llama-server) -> Spark voice (spark_service.py).
Binds to localhost by default; there is no login, so don't expose it directly. Started by scripts/start.sh.
"""
import asyncio, base64, difflib, json, os, re, time
from pathlib import Path

import httpx, uvicorn, websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent
VOX = f"ws://127.0.0.1:{os.environ.get('VOXTRAL_PORT', '18098')}/v1/realtime"
LLM = f"http://127.0.0.1:{os.environ.get('GEMMA_PORT', '18099')}/v1/chat/completions"
SPARK = f"http://127.0.0.1:{os.environ.get('SPARK_PORT', '18096')}/synth"
HOST = os.environ.get("TUTOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("TUTOR_PORT", "8791"))

SYSTEM = (ROOT / "prompts/system.txt").read_text().strip()
VOWEL_PROMPT = (ROOT / "prompts/vowelize.txt").read_text().strip() + "\n"
SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}  # Google's recommended values for Gemma 4
HISTORY_MESSAGES = 24
LOG = ROOT / "data/sessions_timing.jsonl"

app = FastAPI()

ARABIC = re.compile(r"[ء-ي]")
LATIN = re.compile(r"[A-Za-z]")
PERSIAN = re.compile(r"[پچژگکی]")
DIAC = re.compile(r"[ً-ْٰ]")


def speakable(s):
    """False for English or Persian sentences: the Arabic voice would garble them, so they are shown only."""
    a, l = len(ARABIC.findall(s)), len(LATIN.findall(s))
    if a == 0 or l > 0.3 * (a + l):
        return False
    words = s.split()
    return sum(1 for w in words if PERSIAN.search(w)) <= 0.3 * max(len(words), 1)


def clean_text(s):
    """Plain text ready for vowelling: no vowel marks, quotes or markdown; pauses as commas."""
    s = DIAC.sub("", s)
    s = re.sub(r"[«»\"“”*_`#]", "", s)
    s = re.sub(r"\s*(…|\.{2,})\s*", "، ", s)
    return " ".join(s.split()).strip(" ،")


def split_sentences(t):
    """Split into sentences, merging one- or two-word fragments into the next sentence."""
    parts = [p.strip() for p in re.split(r"(?<=[.!؟?؛\n])\s+", t) if p.strip()]
    out, carry = [], ""
    for p in parts:
        p = (carry + " " + p).strip() if carry else p
        carry = ""
        if len(p.split()) <= 2:
            carry = re.sub(r"[.!]+$", "،", p)
        else:
            out.append(p)
    if carry:
        if out:
            out[-1] += " " + carry
        else:
            out.append(carry)
    return out


async def chat(messages, http, sampling=SAMPLING, max_tokens=300):
    body = {"messages": messages, "stream": True, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False}, **sampling}
    async with http.stream("POST", LLM, json=body, timeout=120) as r:
        async for line in r.aiter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                d = json.loads(line[6:])
                if d.get("choices"):
                    piece = d["choices"][0].get("delta", {}).get("content")
                    if piece:
                        yield piece


def merge_vowels(plain, vowelled):
    """Keep the tutor's exact words: take a vowelled word only where its letters match the original."""
    a, b = plain.split(), vowelled.split()
    sm = difflib.SequenceMatcher(None, [DIAC.sub("", w) for w in a], [DIAC.sub("", w) for w in b], autojunk=False)
    out = list(a)
    for m in sm.get_matching_blocks():
        out[m.a:m.a + m.size] = b[m.b:m.b + m.size]
    return " ".join(out)


async def vowelize(plain, http):
    out = ""
    async for piece in chat([{"role": "user", "content": VOWEL_PROMPT + plain}], http, {"temperature": 0}, 600):
        out += piece
    return merge_vowels(plain, out.strip())


class Session:
    def __init__(self, ws, http):
        self.ws, self.http = ws, http
        self.history = []
        self.vox = self.vox_rx = self.reply = self.final = None
        self.gen = 0

    async def send(self, **m):
        await self.ws.send_text(json.dumps(m, ensure_ascii=False))

    async def cancel_reply(self):
        self.gen += 1
        if self.reply and not self.reply.done():
            self.reply.cancel()
            try:
                await self.reply
            except (asyncio.CancelledError, Exception):
                pass

    async def start_talk(self):
        await self.cancel_reply()
        await self.close_vox()
        self.vox = await websockets.connect(VOX, max_size=None)
        json.loads(await self.vox.recv())
        await self.vox.send(json.dumps({"type": "session.update", "model": "voxtral-ar"}))
        await self.vox.send(json.dumps({"type": "input_audio_buffer.commit"}))
        self.final = asyncio.get_running_loop().create_future()
        self.vox_rx = asyncio.create_task(self.read_vox(self.vox, self.final))

    async def read_vox(self, vox, final):
        text = ""
        try:
            async for m in vox:
                d = json.loads(m)
                if d["type"] == "transcription.delta":
                    text += d["delta"]
                    await self.send(type="partial", text=text)
                elif d["type"] == "transcription.done":
                    final.done() or final.set_result(d["text"].strip())
                    return
                elif d["type"] == "error":
                    await self.send(type="error", text=str(d.get("error")))
                    final.done() or final.set_result("")
                    return
        except websockets.ConnectionClosed:
            final.done() or final.set_result(text.strip())

    async def audio(self, pcm):
        if self.vox:
            await self.vox.send(json.dumps({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()}))

    async def close_vox(self):
        if self.vox:
            await self.vox.close()
        self.vox = None

    async def stop_talk(self):
        if not self.vox:
            return
        t_end = time.time()
        await self.vox.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))
        try:
            heard = await asyncio.wait_for(self.final, 20)
        except asyncio.TimeoutError:
            heard = ""
        await self.close_vox()
        await self.send(type="final", text=heard)
        if heard:
            self.reply = asyncio.create_task(self.respond(heard, t_end))
        else:
            await self.send(type="error", text="No speech was recognized. Please try again.")

    async def respond(self, user, t_end):
        gen = self.gen
        self.history.append({"role": "user", "content": user})
        self.history = self.history[-HISTORY_MESSAGES:]
        msgs = [{"role": "system", "content": SYSTEM}] + self.history
        t = {"stt_s": round(time.time() - t_end, 3)}
        full, first_token, shown = "", None, []
        try:
            # The whole reply comes first: vowelling needs the same Gemma server, which runs one job at a time.
            async for piece in chat(msgs, self.http):
                first_token = first_token or time.time()
                full += piece
                await self.send(type="assistant", text=full)
            t["llm_first_token_s"] = round((first_token or time.time()) - t_end, 3)
            t["llm_done_s"] = round(time.time() - t_end, 3)
            for s in split_sentences(full):
                if not speakable(s):
                    await self.send(type="text_only", text=s)
                    continue
                t0 = time.time()
                vowelled = await vowelize(clean_text(s), self.http)
                t1 = time.time()
                shown.append(vowelled)
                await self.send(type="tashkeel", text=" ".join(shown))  # exactly what the voice is given
                r = await self.http.post(SPARK, json={"text": vowelled}, timeout=60)
                r.raise_for_status()
                if gen != self.gen:
                    return
                await self.ws.send_bytes(r.content)
                if "end_of_speech_to_first_audio_s" not in t:
                    t.update(first_vowel_s=round(t1 - t0, 3), first_voice_s=round(time.time() - t1, 3), end_of_speech_to_first_audio_s=round(time.time() - t_end, 3))
        except asyncio.CancelledError:
            self.history.append({"role": "assistant", "content": full})  # keep what was said before the interruption
            raise
        self.history.append({"role": "assistant", "content": full})
        await self.send(type="timing", **t)
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a") as f:  # timings only, never the conversation text
            f.write(json.dumps({"at": int(time.time()), "reply_chars": len(full), **t}) + "\n")


@app.get("/")
async def index():
    return HTMLResponse((ROOT / "index.html").read_text())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    async with httpx.AsyncClient() as http:
        s = Session(ws, http)
        try:
            while True:
                m = await ws.receive()
                if m["type"] == "websocket.disconnect":
                    break
                if m.get("bytes") is not None:
                    await s.audio(m["bytes"])
                    continue
                d = json.loads(m["text"])
                if d["type"] == "start":
                    await s.start_talk()
                elif d["type"] == "stop":
                    await s.stop_talk()
                elif d["type"] == "text":
                    await s.cancel_reply()
                    s.reply = asyncio.create_task(s.respond(d["text"], time.time()))
                elif d["type"] == "reset":
                    await s.cancel_reply()
                    s.history = []
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await s.cancel_reply()
            await s.close_vox()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", ws_max_size=2**22)
