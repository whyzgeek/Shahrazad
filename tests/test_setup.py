"""GPU planning, the cloud request format, and the routes that need no model."""
import configure, pytest
from fastapi.testclient import TestClient
from tools import providers
import app


def plan(spec, local=configure.PARTS):
    p = configure.best_plan(configure.preview_gpus(spec), local)
    return None if p is None else {"cpu_layers": p[4], "hearing": p[1] and p[1]["index"], "brain": p[2] and p[2]["index"], "voice": p[3] and p[3]["index"]}


def test_two_12gb_cards_match_the_measured_layout():
    assert plan("12,12") == {"cpu_layers": 17, "hearing": 1, "brain": 0, "voice": 0}


def test_big_card_runs_everything_on_the_gpu():
    assert plan("48")["cpu_layers"] == 0


def test_small_cards_suggest_the_cloud():
    assert plan("16") is None
    assert configure.suggest_cloud(configure.preview_gpus("16"), configure.PARTS, 64) == ("hearing",)
    assert configure.suggest_cloud(configure.preview_gpus("8"), configure.PARTS, 24) == ("hearing", "brain")
    assert plan("16", ("brain", "voice")) is not None


def test_llm_body_local_is_unchanged(monkeypatch):
    monkeypatch.setattr(providers, "BRAIN", "local")
    body = {"messages": [], "id_slot": 1, "chat_template_kwargs": {"enable_thinking": False}}
    assert providers.llm_body(body) is body


def test_llm_body_cloud(monkeypatch):
    monkeypatch.setattr(providers, "BRAIN", "cloud")
    body = {"messages": [], "id_slot": 1, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"schema": {"type": "object"}}}}
    b = providers.llm_body(body)
    assert not set(providers.LLAMA_ONLY) & set(b)
    assert b["model"] == providers.BRAIN_MODEL and b["provider"]["allow_fallbacks"] is False
    assert b["response_format"]["json_schema"]["name"] == "out"


@pytest.fixture
def client():
    with TestClient(app.app) as c:   # runs the app's startup, as uvicorn does
        yield c


def test_page_flags(client):
    page = client.get("/").text
    assert 'data-debug="0"' in page and 'data-newest="' in page


def test_health_reports_every_part(client):
    h = client.get("/health").json()
    assert set(h) == {"brain", "hearing", "voice"}
    assert all(p["ok"] is False and p["mode"] == "local" for p in h.values())   # nothing is running in the test


def test_gloss_and_translate_reject_empty_input(client):
    assert client.post("/gloss", json={"word": "hello", "sentence": ""}).status_code == 400
    assert client.post("/translate", json={"text": "hello"}).status_code == 400


def test_hearing_choice(monkeypatch, client):
    """Which hearing is in use comes from the settings in one place, and the page and log name it."""
    import importlib
    try:
        monkeypatch.setenv("SHAHRAZAD_HEARING", "cloud")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test")
        assert importlib.reload(providers).PARTS["hearing"].health == ""
        assert client.get("/health").json()["hearing"]["mode"] == "cloud"
        monkeypatch.setenv("SHAHRAZAD_HEARING", "whisper")
        with pytest.raises(SystemExit):
            importlib.reload(providers)
    finally:
        for var in ("SHAHRAZAD_HEARING", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(var)
        importlib.reload(providers)
    assert providers.PARTS["hearing"].name == "Voxtral" and "hearing: Voxtral (local)" in providers.describe()


def test_clip_ear_cuts_at_pauses_and_keeps_order(monkeypatch):
    """Speech, a pause, more speech: two clips, transcribed separately and joined in order."""
    import array, asyncio, random
    from tools import hearing
    heard = []

    async def transcribe(http, pcm):
        heard.append(len(pcm))
        n = len(heard)
        await asyncio.sleep(0.01 * (3 - n))   # the first clip finishes last
        return f"clip{n}"
    monkeypatch.setattr(providers, "transcribe", transcribe)
    monkeypatch.setattr(hearing, "CAPTIONS", False)
    chunk = lambda loud: array.array("h", [random.randint(-3000, 3000) if loud else 0 for _ in range(1600)]).tobytes()   # 0.1 s

    async def go():
        ear = hearing.ClipEar(None, lambda **m: asyncio.sleep(0))
        for loud in [True] * 50 + [False] * 5 + [True] * 20:
            await ear.add(chunk(loud))
        return await ear.finish()
    assert asyncio.run(go()) == "clip1 clip2" and len(heard) == 2
