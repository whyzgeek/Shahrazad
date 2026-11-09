"""Spark Arabic voice as a local service, for fully vowelled text.
The language model runs in llama-server (BF16 GGUF, about 200 tokens/s). This process only prepares the
reference voice once and decodes audio. Generation stops as soon as the token stream turns to silence.
Started by scripts/start.sh.
"""
import asyncio, io, json, os, re, time
from pathlib import Path

import httpx, numpy as np, soundfile as sf, torch, uvicorn
from fastapi import FastAPI, Response
from pydantic import BaseModel
from transformers import AutoModel, AutoProcessor

M = str(Path(os.environ.get("SHAHRAZAD_MODELS", "models")) / "spark")
LLAMA = f"http://127.0.0.1:{os.environ.get('SPARK_LM_PORT', '18097')}/completion"
DEV = os.environ.get("SPARK_DEVICE", "cuda:0")
REF = os.environ["SHAHRAZAD_REF_AUDIO"]
SIL = {3140, 7645, 6627}  # token ids that make up the silence after speech
SIL_RUN = 25              # 25 tokens = 0.5 s of silence ends generation; shorter pauses (commas) are kept
KEEP_TAIL = 6             # 0.12 s of the silence stays, so the last word decays naturally
MAX_TOK = 900             # 18 s, safety limit
SAMPLING = {"temperature": 0.8, "top_p": 0.95, "top_k": 50, "min_p": 0, "repeat_penalty": 1.0}  # vendor card values

proc = AutoProcessor.from_pretrained(M, trust_remote_code=True)
model = AutoModel.from_pretrained(M, trust_remote_code=True).eval()  # on CPU until the parts not needed are dropped
proc.model = model
first = proc(text="أ", prompt_speech_path=REF, prompt_text=None, return_tensors="pt")  # reference voice, once
ids = first["input_ids"][0].tolist()
GLOBAL = first["global_token_ids_prompt"]
tk = proc.tokenizer
SC, EC = tk.convert_tokens_to_ids("<|start_content|>"), tk.convert_tokens_to_ids("<|end_content|>")
PREFIX, SUFFIX = ids[: ids.index(SC) + 1], ids[ids.index(EC):]
SEM = {i: int(m.group(1)) for t, i in tk.get_added_vocab().items() if (m := re.fullmatch(r"<\|bicodec_semantic_(\d+)\|>", t))}
model.llm = None  # the language model lives in llama-server
model.wav2vec2_model = None  # only needed to read the reference voice, which is done
model.to(DEV)
GLOBAL = GLOBAL.to(DEV)
torch.cuda.empty_cache()
print("voice ready, GPU GB", round(torch.cuda.memory_allocated(DEV) / 2**30, 2), flush=True)

app = FastAPI()
lock = asyncio.Lock()


class Req(BaseModel):
    text: str
    seed: int | None = None


async def generate(text, seed):
    prompt = PREFIX + tk(text, add_special_tokens=False)["input_ids"] + SUFFIX
    body = {"prompt": prompt, "n_predict": MAX_TOK, "stream": True, "cache_prompt": False, "return_tokens": True, "seed": seed if seed is not None else -1, **SAMPLING}
    sem, run, speech = [], 0, False
    async with httpx.AsyncClient(timeout=120) as c:
        async with c.stream("POST", LLAMA, json=body) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                d = json.loads(line[6:])
                for t in d.get("tokens") or []:
                    if t in SEM:
                        v = SEM[t]
                        sem.append(v)
                        if v in SIL:
                            run += 1
                        else:
                            run, speech = 0, True
                if (speech and run >= SIL_RUN) or d.get("stop"):
                    break  # closing the connection cancels generation in llama-server
    while sem and sem[-1] in SIL and run > KEEP_TAIL:
        sem.pop()
        run -= 1
    return sem


@app.post("/synth")
async def synth(q: Req):
    async with lock:
        t0 = time.time()
        sem = await generate(q.text, q.seed)
        t1 = time.time()
        if not sem:
            return Response(status_code=500, content="no speech tokens")
        with torch.no_grad():
            wav = model.detokenize_audio(GLOBAL, torch.tensor([sem], device=DEV))
        wav = np.asarray(wav).reshape(-1)
        t2 = time.time()
    b = io.BytesIO()
    sf.write(b, wav, 16000, format="WAV", subtype="PCM_16")
    return Response(b.getvalue(), media_type="audio/wav", headers={"X-LLM-S": f"{t1-t0:.3f}", "X-Decode-S": f"{t2-t1:.3f}", "X-Audio-S": f"{len(wav)/16000:.2f}", "X-Tokens": str(len(sem))})


@app.get("/health")
async def health():
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SPARK_PORT", "18096")), log_level="warning")
