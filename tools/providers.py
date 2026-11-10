"""Where each part runs: on this machine, or in the cloud through one OpenRouter key.

Each of the three parts is chosen on its own in .env, so a machine can keep what fits and send the rest out:
  SHAHRAZAD_BRAIN=local|cloud     the tutor, vowelling and error checks (local: Gemma 4 in llama-server)
  SHAHRAZAD_HEARING=local|cloud   speech recognition (local: Voxtral Realtime in vLLM)
  SHAHRAZAD_VOICE=local|cloud     the spoken reply (local: Spark)
The cloud models are fixed on purpose: the prompts are tuned and measured for them (docs/CLOUD.md).
"""
import base64, io, os, wave

import httpx

BRAIN = os.environ.get("SHAHRAZAD_BRAIN", "local").strip().lower()
HEARING = os.environ.get("SHAHRAZAD_HEARING", "local").strip().lower()
VOICE = os.environ.get("SHAHRAZAD_VOICE", "local").strip().lower()
for _name, _value in (("SHAHRAZAD_BRAIN", BRAIN), ("SHAHRAZAD_HEARING", HEARING), ("SHAHRAZAD_VOICE", VOICE)):
    if _value not in ("local", "cloud"):
        raise SystemExit(f"{_name} must be local or cloud, not {_value!r}")

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

LLM_URL = f"{CLOUD}/chat/completions" if BRAIN == "cloud" else f"http://127.0.0.1:{os.environ.get('GEMMA_PORT', '18099')}/v1/chat/completions"
LLM_HEADERS = HEADERS if BRAIN == "cloud" else {}
VOX_URL = f"ws://127.0.0.1:{os.environ.get('VOXTRAL_PORT', '18098')}/v1/realtime"
SPARK_URL = f"http://127.0.0.1:{os.environ.get('SPARK_PORT', '18096')}/synth"
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


async def transcribe(http, pcm16k):
    """Cloud hearing: the whole turn at once, after the learner lets go of the button."""
    body = {"model": HEARING_MODEL, "input_audio": {"data": base64.b64encode(wav(pcm16k, 16000)).decode(), "format": "wav"}, "language": "ar"}
    r = await http.post(f"{CLOUD}/audio/transcriptions", json=body, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return (r.json().get("text") or "").strip()


async def synth(http, text):
    """One sentence of speech, as bytes the browser can decode (WAV or MP3)."""
    if VOICE != "cloud":
        r = await http.post(SPARK_URL, json={"text": text}, timeout=60)
        r.raise_for_status()
        return r.content
    raw_pcm = VOICE_MODEL.startswith("google/")   # Gemini's voices only return raw 24 kHz PCM
    body = {"model": VOICE_MODEL, "input": text, "voice": VOICE_NAME, "response_format": "pcm" if raw_pcm else "mp3"}
    r = await http.post(f"{CLOUD}/audio/speech", json=body, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return wav(r.content, 24000) if raw_pcm else r.content


def describe():
    part = lambda kind, local, cloud: f"{kind}: {cloud if kind_mode[kind] == 'cloud' else local}"
    kind_mode = {"brain": BRAIN, "hearing": HEARING, "voice": VOICE}
    return ", ".join([part("brain", "Gemma 4 (local)", BRAIN_MODEL), part("hearing", "Voxtral (local)", HEARING_MODEL), part("voice", "Spark (local)", f"{VOICE_MODEL} {VOICE_NAME}")])
