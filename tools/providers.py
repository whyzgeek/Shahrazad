"""Where each part runs: on this machine, or in the cloud through one OpenRouter key.

Each of the three parts is chosen on its own in .env, so a machine can keep what fits and send the rest out:
  SHAHRAZAD_BRAIN=local|cloud     the tutor, vowelling and error checks (local: Gemma 4 in llama-server)
  SHAHRAZAD_HEARING=local|cloud   speech recognition (local: Voxtral Realtime)
  SHAHRAZAD_VOICE=local|cloud     the spoken reply (local: Spark)
The cloud models are fixed on purpose: the prompts are tuned and measured for them (docs/CLOUD.md).
"""
import base64, io, os, wave
from dataclasses import dataclass


def setting(name, default, allowed):
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        raise SystemExit(f"{name} must be {' or '.join(allowed)}, not {value!r}")
    return value


def local_url(port_var, default_port, path):
    return f"127.0.0.1:{os.environ.get(port_var, default_port)}{path}"


BRAIN = setting("SHAHRAZAD_BRAIN", "local", ("local", "cloud"))
HEARING = setting("SHAHRAZAD_HEARING", "local", ("local", "cloud"))
VOICE = setting("SHAHRAZAD_VOICE", "local", ("local", "cloud"))

CLOUD = "https://openrouter.ai/api/v1"
KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if "cloud" in (BRAIN, HEARING, VOICE) and not KEY:
    raise SystemExit("A part is set to cloud, so OPENROUTER_API_KEY must be set in .env.")
HEADERS = {"Authorization": f"Bearer {KEY}", "X-Title": "Shahrazad"} if KEY else {}

# Measured choices (docs/CLOUD.md). The cloud brain is the same Gemma 4 model as the local one, so the tutor
# behaves the same either way and the prompts tuned on it apply unchanged.
BRAIN_MODEL = os.environ.get("CLOUD_BRAIN_MODEL", "google/gemma-4-26b-a4b-it")
HEARING_MODEL = os.environ.get("CLOUD_HEARING_MODEL", "mistralai/voxtral-mini-transcribe-3-0")
VOICE_MODEL = os.environ.get("CLOUD_VOICE_MODEL", "x-ai/grok-voice-tts-1.0")
VOICE_NAME = os.environ.get("CLOUD_VOICE_NAME", "ara")
# Gemma is served by many providers, and some return invalid structured output, which the grammar checks need
# (in November 2026: Cloudflare, DekaLLM, Io Net, and NextBit about 1 call in 3). So only these, tested on the
# 29-sentence error set with no failed calls, in order of how many errors they caught.
BRAIN_PROVIDERS = [p.strip() for p in os.environ.get("CLOUD_BRAIN_PROVIDERS", "Venice,PrimeIntellect,DeepInfra").split(",") if p.strip()]
BRAIN_ROUTING = {"order": BRAIN_PROVIDERS, "allow_fallbacks": False, "require_parameters": True}


@dataclass(frozen=True)
class Part:
    mode: str     # local or cloud
    name: str     # what runs it, as the page and the log show it
    health: str   # the local service's health check; a cloud part is checked by its key, since a call would spend credit


def part(mode, local_name, port_var, default_port, cloud_name):
    if mode == "cloud":
        return Part(mode, cloud_name, "")
    return Part(mode, local_name, "http://" + local_url(port_var, default_port, "/health"))


PARTS = {"brain": part(BRAIN, "Gemma 4", "GEMMA_PORT", "18099", BRAIN_MODEL),
         "hearing": part(HEARING, "Voxtral", "VOXTRAL_PORT", "18098", HEARING_MODEL),
         "voice": part(VOICE, "Spark", "SPARK_PORT", "18096", f"{VOICE_MODEL} {VOICE_NAME}")}

LLM_URL = f"{CLOUD}/chat/completions" if BRAIN == "cloud" else "http://" + local_url("GEMMA_PORT", "18099", "/v1/chat/completions")
LLM_HEADERS = HEADERS if BRAIN == "cloud" else {}
VOX_URL = "ws://" + local_url("VOXTRAL_PORT", "18098", "/v1/realtime")
LLAMA_ONLY = ("id_slot", "chat_template_kwargs", "cache_prompt")


def llm_body(body):
    """The same request for the cloud brain: llama-server's own fields removed, the model named. Thinking stays off,
    as it is locally. Local requests pass through unchanged."""
    if BRAIN != "cloud":
        return body
    b = {k: v for k, v in body.items() if k not in LLAMA_ONLY}
    b["model"] = BRAIN_MODEL
    b["provider"] = BRAIN_ROUTING
    rf = b.get("response_format")
    if rf and rf.get("type") == "json_schema":
        b["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", **rf["json_schema"]}}
    return b


def wav(pcm, rate):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return out.getvalue()


async def post(http, url, **kw):
    r = await http.post(url, timeout=60, **kw)
    r.raise_for_status()
    return r


# ------------------------------------------------------------ cloud hearing: one clip (16 kHz 16-bit mono PCM) to text.
# Local hearing streams to Voxtral instead (tools/hearing.py).
async def transcribe(http, pcm16k):
    body = {"model": HEARING_MODEL, "input_audio": {"data": base64.b64encode(wav(pcm16k, 16000)).decode(), "format": "wav"}, "language": "ar"}
    return ((await post(http, f"{CLOUD}/audio/transcriptions", json=body, headers=HEADERS)).json().get("text") or "").strip()


# ------------------------------------------------------------ voice: one sentence as bytes the browser can decode (WAV or MP3)
async def _spark(http, text):
    return (await post(http, "http://" + local_url("SPARK_PORT", "18096", "/synth"), json={"text": text})).content


async def _cloud_voice(http, text):
    raw_pcm = VOICE_MODEL.startswith("google/")   # Gemini's voices only return raw 24 kHz PCM
    body = {"model": VOICE_MODEL, "input": text, "voice": VOICE_NAME, "response_format": "pcm" if raw_pcm else "mp3"}
    r = await post(http, f"{CLOUD}/audio/speech", json=body, headers=HEADERS)
    return wav(r.content, 24000) if raw_pcm else r.content


VOICES = {"local": _spark, "cloud": _cloud_voice}


async def synth(http, text):
    return await VOICES[VOICE](http, text)


def describe():
    return ", ".join(f"{kind}: {p.name}" + (" (local)" if p.mode == "local" else "") for kind, p in PARTS.items())
