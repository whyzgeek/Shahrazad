"""End-to-end delay: five spoken turns over the real WebSocket, timed from the end of speech to the first audio.

The learner's sentences (with typical mistakes) are spoken by the tutor's own voice part, so no microphone or extra
service is needed; ffmpeg converts them to 16 kHz. They are cached in evals/.cache.

Run it against a test copy with its own learner record: the mistakes would otherwise go into your progress.
    SHAHRAZAD_LEARNER_DB=/tmp/eval.db TUTOR_PORT=8794 .venv-tutor/bin/python app.py &
    .venv-tutor/bin/python evals/spoken.py --url https://127.0.0.1:8794 [--pause 10]
"""
import argparse, asyncio, hashlib, json, ssl, subprocess, time
import _setup
import httpx, websockets
from tools import providers
from tools.vowels import vowelize

p = argparse.ArgumentParser()
p.add_argument("--url", default="https://127.0.0.1:8794")
p.add_argument("--pause", type=float, default=10, help="seconds between turns, as a learner listens to the reply")
args = p.parse_args()
SAY = ["مرحبا، اسمي سامي وأنا أتعلم العربية منذ سنة.", "أمس أنا يذهب إلى السوق مع أختي واشتريت خبز طازج.", "أحب السفر كثيرا، وزرت مصر والمغرب في السنة الماضية.",
       "أنا أفكر عن العمل في بلد عربي بعد الجامعة.", "عندي ثلاث إخوة وخمسة أخت وكلهم يسكنون في القاهرة."]
CACHE = _setup.ROOT / "evals/.cache"


async def clip(h, text):
    f = CACHE / (hashlib.sha1(f"{providers.VOICE}:{text}".encode()).hexdigest()[:16] + ".pcm")
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        audio = await providers.synth(h, await vowelize(text, h))
        pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"], input=audio, capture_output=True, timeout=60, check=True).stdout
        f.write_bytes(pcm)
    return f.read_bytes()


async def main():
    async with httpx.AsyncClient() as h:
        clips = [await clip(h, s) for s in SAY]
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE   # the tutor's certificate is self-signed
    ws_url = args.url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws"
    firsts = []
    async with websockets.connect(ws_url, ssl=ctx if ws_url.startswith("wss") else None, max_size=None) as ws:
        await ws.send(json.dumps({"type": "reset"}))
        sid = None
        while sid is None:
            m = await asyncio.wait_for(ws.recv(), 30)
            if isinstance(m, str) and json.loads(m)["type"] == "session":
                sid = json.loads(m)["id"]
        await asyncio.sleep(8)   # a moment before speaking, as a learner would
        for i, pcm in enumerate(clips):
            await ws.send(json.dumps({"type": "start"}))
            for k in range(0, len(pcm), 2560):   # real time: 80 ms of audio every 80 ms
                await ws.send(pcm[k:k + 2560]); await asyncio.sleep(0.08)
            await ws.send(json.dumps({"type": "stop"}))
            t_stop, first, reply = time.time(), None, ""
            while True:
                m = await asyncio.wait_for(ws.recv(), 120)
                if isinstance(m, bytes):
                    first = first or time.time() - t_stop
                    continue
                d = json.loads(m)
                if d["type"] == "assistant":
                    reply = d["text"]
                if d["type"] == "timing":
                    firsts.append(first or 0)
                    print(f"turn {i + 1}: first audio {firsts[-1]:.2f} s (brain's first word {d.get('llm_first_token_s')} s, vowelling {d.get('first_vowel_s')} s, voice {d.get('first_voice_s')} s) | {reply[:50]}", flush=True)
                    break
            await asyncio.sleep(args.pause)
        await ws.send(json.dumps({"type": "delete", "id": sid}))   # leave no test conversation behind
    later = sorted(firsts[1:])
    print(f"first turn {firsts[0]:.2f} s; later turns median {later[len(later) // 2]:.2f} s, {later[0]:.2f}–{later[-1]:.2f} s")

asyncio.run(asyncio.wait_for(main(), 900))
