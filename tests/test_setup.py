"""GPU planning, the cloud request format, and the routes that need no model."""
import configure
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


client = TestClient(app.app)


def test_page_flags():
    page = client.get("/").text
    assert 'data-debug="0"' in page and 'data-newest="' in page


def test_health_reports_every_part():
    h = client.get("/health").json()
    assert set(h) == {"brain", "hearing", "voice"}
    assert all(p["ok"] is False and p["mode"] == "local" for p in h.values())   # nothing is running in the test


def test_gloss_and_translate_reject_empty_input():
    assert client.post("/gloss", json={"word": "hello", "sentence": ""}).status_code == 400
    assert client.post("/translate", json={"text": "hello"}).status_code == 400
