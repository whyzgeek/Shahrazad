"""Shahrazad: an Arabic (MSA) speaking tutor, push-to-talk. This file is the web server: the page, its few routes,
and the WebSocket each open page talks over. The conversation itself is in tools/session.py.

Browser mic -> hearing (tools/hearing.py) -> Gemma 4 (tools/brain.py) -> vowel marks (tools/vowels.py) -> voice.
Any of the three parts can run in the cloud instead, through one OpenRouter key: see tools/providers.py.
Binds to localhost by default; set TUTOR_PASSWORD before exposing it. Started by scripts/start.sh.
"""
import asyncio, contextlib, csv, io, json, os, re, urllib.parse
from pathlib import Path

import httpx, uvicorn
from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from tools import auth, brain, learner, providers, status
from tools.hearing import stop_task
from tools.session import DEBUG_LOG, LEARNER, Session, retitle_old_sessions
from tools.text import ARABIC, DIAC

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("TUTOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("TUTOR_PORT", "8791"))
NEWEST = "top" if os.environ.get("TUTOR_NEWEST", "bottom").strip().lower() == "top" else "bottom"   # where new messages appear; each browser can change it
GLOSS_SCHEMA = {"type": "object", "properties": {"meaning": {"type": "string"}, "base": {"type": "string"}}, "required": ["meaning", "base"]}

HTTP: httpx.AsyncClient = None   # one connection pool for every request this app makes


@contextlib.asynccontextmanager
async def lifespan(_):
    global HTTP
    async with httpx.AsyncClient() as HTTP:
        retitle = asyncio.create_task(retitle_old_sessions(HTTP))   # earlier sessions get meaningful names, once
        yield
        await stop_task(retitle)


class PageFiles(StaticFiles):
    """The page's own files (web/). Browsers check for a newer copy on each load, so an update is never half-applied;
    an unchanged file costs only a "not modified" reply."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
app.mount("/web", PageFiles(directory=ROOT / "web"), name="web")


# ------------------------------------------------------------ login (tools/auth.py)
@app.middleware("http")
async def require_login(request: Request, call_next):
    if auth.needs_login(request.url.path, request.cookies):
        if request.url.path == "/":
            return RedirectResponse("login", status_code=303)
        return JSONResponse({"error": "login required"}, status_code=401)
    return await call_next(request)


@app.get("/login")
async def login_form():
    return HTMLResponse(auth.login_page())


@app.post("/login")
async def login(request: Request):
    given = urllib.parse.parse_qs((await request.body()).decode(errors="replace")).get("password", [""])[0]
    if not auth.password_ok(given):
        await asyncio.sleep(1)   # slows down guessing
        return HTMLResponse(auth.login_page("That password isn't right."))
    response = RedirectResponse(".", status_code=303)
    if auth.PASSWORD:
        response.set_cookie(auth.COOKIE, auth.make_cookie(), max_age=auth.COOKIE_DAYS * 86400, httponly=True,
                            samesite="strict", secure=request.url.scheme == "https")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("login" if auth.PASSWORD else ".", status_code=303)
    response.delete_cookie(auth.COOKIE)
    return response


# ------------------------------------------------------------ the page
@app.get("/")
async def index():
    """The page, with the server's settings it needs (see the top of web/index.html)."""
    page = (ROOT / "web/index.html").read_text()
    for name, value in (("newest", NEWEST), ("login", int(bool(auth.PASSWORD))), ("debug", int(bool(DEBUG_LOG)))):
        page = re.sub(f'data-{name}="[^"]*"', f'data-{name}="{value}"', page, count=1)
    return HTMLResponse(page)


@app.get("/health")
async def health():
    return JSONResponse(await status.health(HTTP))


@app.get("/status")
async def status_page():
    return JSONResponse(await status.status(HTTP))


# ------------------------------------------------------------ the learner's record
@app.get("/progress")
async def progress():
    return JSONResponse({**LEARNER.progress(), "cards": LEARNER.all_errors()})


@app.get("/cards.csv")
async def cards_csv():
    """All correction cards for flashcard apps such as Anki: front, back, tags."""
    out = io.StringIO()
    w = csv.writer(out)
    for e in LEARNER.all_errors():
        w.writerow([e["wrong"], f"{e['right']}<br><small>{e['reminder']}</small>" if e["reminder"] else e["right"], e["key"]])
    return Response(out.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="shahrazad-cards.csv"'})


@app.get("/lesson/{concept}")
async def lesson(concept: str):
    if concept not in learner.CARDS:
        return JSONResponse({"error": "unknown"}, status_code=404)
    return JSONResponse(learner.card_view(concept, LEARNER.band()))


# ------------------------------------------------------------ help with a reply
@app.post("/gloss")
async def gloss(req: dict = Body(...)):
    """The meaning of one word in a tutor's reply, in its sentence. Cached, so a word asked about twice costs nothing."""
    word, sentence = DIAC.sub("", str(req.get("word", ""))).strip()[:40], str(req.get("sentence", ""))[:600]
    if not ARABIC.search(word):
        return JSONResponse({"error": "not an Arabic word"}, status_code=400)
    hit = LEARNER.gloss(word, sentence)
    if hit:
        return JSONResponse(hit)
    ask = (f"Arabic sentence: «{sentence}»\nWhat does the word «{word}» mean in this sentence? Reply in JSON. meaning: its English meaning here, "
           "in at most 8 words. base: its dictionary form in Arabic with full vowel marks (for a verb, the past tense; for a noun, the singular without ال).")
    try:
        d = await brain.ask_json(HTTP, ask, 80, GLOSS_SCHEMA)
    except Exception as e:
        return JSONResponse({"error": type(e).__name__}, status_code=502)
    LEARNER.save_gloss(word, sentence, d["meaning"], d["base"])
    return JSONResponse({"meaning": d["meaning"], "base": d["base"]})


@app.post("/translate")
async def translate(req: dict = Body(...)):
    text = DIAC.sub("", str(req.get("text", "")))[:2000]
    if not ARABIC.search(text):
        return JSONResponse({"error": "nothing to translate"}, status_code=400)
    try:
        return JSONResponse({"english": await brain.ask(HTTP, "Translate this Arabic into natural English. Reply with the translation only.\n\n" + text, 400)})
    except Exception as e:
        return JSONResponse({"error": type(e).__name__}, status_code=502)


# ------------------------------------------------------------ the conversation
@app.websocket("/ws")
async def conversation(ws: WebSocket):
    if not auth.same_origin(ws.headers) or not auth.logged_in(ws.cookies):
        await ws.close(code=1008)   # refused before the connection opens
        return
    await ws.accept()
    session = Session(ws, HTTP)
    await session.resume_latest()
    try:
        while True:
            m = await ws.receive()
            if m["type"] == "websocket.disconnect":
                break
            if m.get("bytes") is not None:
                await session.audio(m["bytes"])   # the learner's voice
            else:
                await session.handle(json.loads(m["text"]))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await session.close()


if __name__ == "__main__":
    print("Shahrazad:", providers.describe(), flush=True)
    tls = {"ssl_certfile": os.environ["TUTOR_SSL_CERT"], "ssl_keyfile": os.environ["TUTOR_SSL_KEY"]} if os.environ.get("TUTOR_SSL_CERT") else {}
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", ws_max_size=2**22, **tls)
