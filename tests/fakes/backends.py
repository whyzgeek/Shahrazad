"""Stand-ins for the three local parts, on one port, so the whole tutor can run in tests without GPUs, models or a key.

  brain    POST /v1/chat/completions   like llama-server: a streamed tutor reply, a JSON answer for a schema, or text
  hearing  WS   /v1/realtime           like Voxtral Realtime: a partial while audio arrives, the full text at the end
  voice    POST /synth                 like spark_service.py: a short tone per sentence, as a WAV file
  GET /calls lists what the app asked for, so tests can check it; POST /reset clears that list.

Run on its own: python tests/fakes/backends.py PORT
"""
import asyncio, io, json, math, struct, sys, wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response, StreamingResponse

ROOT = Path(__file__).resolve().parents[2]
VOWEL_PROMPT = (ROOT / "prompts/vowelize.txt").read_text().strip() + "\n"

# What the fake tutor says: three sentences, so a reply is three pieces of audio, as with the real voice.
REPLY = ["أهلا بك يا صديقي.", "هذه جملة ثانية من الرد.", "كيف حالك اليوم؟"]
HEARD_PARTIAL, HEARD = "مرحبا", "مرحبا كيف حالك"
# A learner's sentence with one mistake the fake error check finds: the adjective doesn't agree with its noun.
MISTAKE, CORRECTION = "تفاحة كبير", "تفاحة كبيرة"
FATHA = "\u064e"
TITLE = "محادثة تجريبية"
TONE_S = 0.4   # each sentence's audio: long enough for a browser to really play it

calls = []
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/calls")
async def list_calls():
    return calls


@app.post("/reset")
async def reset():
    calls.clear()
    return {}


# ------------------------------------------------------------ brain
def minimal(schema):
    """The smallest value that fits a JSON schema: what a model that finds nothing to say would return."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {k: minimal(schema["properties"][k]) for k in schema.get("required", ())}
    if kind == "array":
        return [minimal(schema.get("items", {"type": "string"})) for _ in range(schema.get("minItems", 0))]
    return {"string": "سؤال", "boolean": False, "integer": 0, "number": 0}.get(kind)


def vowelled(text):
    """Each word gets a vowel mark after its first letter: enough for the page to have marks to show or hide."""
    return " ".join(word[0] + FATHA + word[1:] if "\u0621" <= word[0] <= "\u064a" else word for word in text.split(" "))


def found_errors(schema, body):
    """The error check: the one known mistake, if the learner made it, else nothing."""
    answer = minimal(schema)
    said = json.dumps(body["messages"], ensure_ascii=False)
    if MISTAKE in said and "errors" in schema["properties"]:
        concepts = [c for c in schema["properties"]["errors"]["items"]["properties"]["concept"]["enum"] if c != "misheard"]
        concept = "adjective_gender" if "adjective_gender" in concepts else concepts[0]
        answer["errors"] = [{"wrong": MISTAKE, "right": CORRECTION, "concept": concept}]
    return answer


def completion(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


async def stream_reply():
    words = " ".join(REPLY).split(" ")
    for i, word in enumerate(words):
        piece = word if i == len(words) - 1 else word + " "
        yield "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}, ensure_ascii=False) + "\n\n"
        await asyncio.sleep(0.01)
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    last = body["messages"][-1]["content"]
    last = last if isinstance(last, str) else json.dumps(last, ensure_ascii=False)
    if body.get("stream"):
        calls.append({"part": "brain", "kind": "turn"})
        return StreamingResponse(stream_reply(), media_type="text/event-stream")
    schema = (body.get("response_format") or {}).get("json_schema", {}).get("schema")
    if schema:
        calls.append({"part": "brain", "kind": "json"})
        return completion(json.dumps(found_errors(schema, body), ensure_ascii=False))
    if last.startswith(VOWEL_PROMPT):
        calls.append({"part": "brain", "kind": "vowels"})
        return completion(vowelled(last[len(VOWEL_PROMPT):]))
    calls.append({"part": "brain", "kind": "text"})
    return completion(TITLE)


# ------------------------------------------------------------ voice
def tone(seconds=TONE_S, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(seconds * rate))))
    return out.getvalue()


TONE = tone()


@app.post("/synth")
async def synth(request: Request):
    calls.append({"part": "voice", "text": (await request.json())["text"]})
    return Response(TONE, media_type="audio/wav")


# ------------------------------------------------------------ hearing
@app.websocket("/v1/realtime")
async def realtime(ws: WebSocket):
    await ws.accept()
    await ws.send_text(json.dumps({"type": "session.created"}))
    audio = 0
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if m["type"] == "input_audio_buffer.append":
                audio += 1
                if audio == 1:
                    await ws.send_text(json.dumps({"type": "transcription.delta", "delta": HEARD_PARTIAL}, ensure_ascii=False))
            elif m["type"] == "input_audio_buffer.commit" and m.get("final"):
                calls.append({"part": "hearing", "chunks": audio})
                await ws.send_text(json.dumps({"type": "transcription.done", "text": HEARD if audio else ""}, ensure_ascii=False))
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
