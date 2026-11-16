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


def test_capped_log_drops_its_older_half(tmp_path):
    from tools.session import write_capped
    log = tmp_path / "log.jsonl"
    for i in range(40):
        write_capped(log, f"line {i:02d}", limit=200)
    lines = log.read_text().splitlines()
    assert log.stat().st_size <= 200 + 10 and lines[-1] == "line 39" and "line 00" not in lines


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


def test_status_page_names_each_part_and_where_it_runs(client):
    s = client.get("/status").json()
    assert [p["kind"] for p in s["parts"]] == ["brain", "hearing", "voice"]
    assert {(p["name"], p["gpu"]) for p in s["parts"]} == {("Gemma 4", "0"), ("Voxtral", "1"), ("Spark", "0")}
    assert all(p["ok"] is False for p in s["parts"]) and s["credit"] is None   # all local, nothing running in the test
    assert s["app"]["since"] and (s["app"]["stops"] or 0) > s["app"]["since"]


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


def test_clip_ear_hears_a_short_last_piece_with_the_one_before(monkeypatch):
    """Alone, a short trailing-off piece can come back in English, so it's transcribed with the piece before it."""
    import array, asyncio, random
    from tools import hearing

    async def transcribe(http, pcm):
        return str(len(pcm) // 3200)   # tenths of a second heard
    monkeypatch.setattr(providers, "transcribe", transcribe)
    monkeypatch.setattr(hearing, "CAPTIONS", False)
    chunk = lambda loud: array.array("h", [random.randint(-3000, 3000) if loud else 0 for _ in range(1600)]).tobytes()   # 0.1 s

    async def go():
        ear = hearing.ClipEar(None, lambda **m: asyncio.sleep(0))
        for loud in [True] * 50 + [False] * 5 + [True] * 8:   # cut after 5.4 s, then a 0.9 s tail
            await ear.add(chunk(loud))
        return await ear.finish()
    assert asyncio.run(go()) == "63"


def test_clip_ear_drops_a_last_piece_without_speech(monkeypatch):
    """A pause or background noise before tapping Send isn't transcribed, since the model would make words up."""
    import array, asyncio, random
    from tools import hearing

    async def transcribe(http, pcm):
        return str(len(pcm) // 3200)
    monkeypatch.setattr(providers, "transcribe", transcribe)
    monkeypatch.setattr(hearing, "CAPTIONS", False)
    sound = lambda amp: array.array("h", [random.randint(-amp, amp) for _ in range(1600)]).tobytes()   # 0.1 s

    async def go(parts):
        ear = hearing.ClipEar(None, lambda **m: asyncio.sleep(0))
        for amp in parts:
            await ear.add(sound(amp))
        return await ear.finish()
    assert asyncio.run(go([3000] * 50 + [0] * 5 + [150] * 30)) == "54"   # 3 s of quiet room noise after speaking
    assert asyncio.run(go([150] * 20)) == ""                              # tapped twice without speaking


def test_after_two_rounds_of_questions_the_tutor_offers_something_new():
    from tools.session import Session, OFFER_NEW_EVERY
    from tools.subjects import Subject
    session = Session(None, None)
    s = session.ctx.subject = Subject("video", "قصر الحمراء", "https://youtu.be/x", ["نص"] * 2)
    session.history = [{"role": "user", "content": "مرحبا"}]
    note = lambda: session.messages()[-1]["content"]
    for round_no in range(OFFER_NEW_EVERY // 6):
        s.questions, s.next_q, s.planned_for = [f"سؤال {round_no}-{n}؟" for n in range(6)], 0, 0   # as plan_questions does
        for n in range(6):
            assert not s.offer_new and f"سؤال {round_no}-{n}؟" in note()
            session.next_question(None)
    assert s.offer_new and "offer to move on" in note() and "the next part" in note()
    s.questions, s.next_q, s.planned_for = ["سؤال جديد؟"] * 6, 0, 0   # planned meanwhile, for if they carry on
    session.next_question(None)
    assert not s.offer_new and s.next_q == 0, "the offer took this turn: the new questions start next"
    assert "سؤال جديد؟" in note()
