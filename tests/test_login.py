"""The shared password, the WebSocket origin check, and the progress and card export routes."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import app


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setattr(app, "PASSWORD", "sesame")
    monkeypatch.setattr(app, "KEY", b"k" * 32)
    with TestClient(app.app, base_url="https://testserver") as c:
        yield c


def test_no_password_means_no_login():
    c = TestClient(app.app)
    assert c.get("/").status_code == 200
    assert c.get("/progress").status_code == 200


def test_page_and_routes_need_the_password(locked):
    r = locked.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "login"
    assert locked.get("/health").status_code == 401
    assert locked.get("/assets/logo.png").status_code == 200
    assert locked.get("/login").status_code == 200


def test_wrong_password_then_right(locked):
    r = locked.post("/login", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 200 and "isn't right" in r.text and "shahrazad" not in r.cookies
    r = locked.post("/login", data={"password": "sesame"}, follow_redirects=False)
    assert r.status_code == 303 and "shahrazad" in r.cookies
    assert 'data-login="1"' in locked.get("/").text
    assert locked.get("/health").status_code == 200


def test_forged_or_expired_cookie_is_refused(locked):
    locked.cookies.set("shahrazad", "9999999999.deadbeef")
    assert locked.get("/health").status_code == 401
    until = "1000"
    import hmac
    locked.cookies.set("shahrazad", until + "." + hmac.new(app.KEY, until.encode(), "sha256").hexdigest())
    assert locked.get("/health").status_code == 401


def test_websocket_needs_login_and_its_own_origin(locked):
    with pytest.raises(WebSocketDisconnect):
        with locked.websocket_connect("/ws"):
            pass
    locked.post("/login", data={"password": "sesame"})
    # The test client opens WebSockets as ws://, which withholds the HTTPS-only cookie, so it's passed by hand.
    cookie = "shahrazad=" + locked.cookies["shahrazad"]
    with pytest.raises(WebSocketDisconnect):
        with locked.websocket_connect("/ws", headers={"origin": "https://evil.example", "cookie": cookie}):
            pass
    with locked.websocket_connect("/ws", headers={"origin": "https://testserver", "cookie": cookie}) as ws:
        assert ws.receive_json()["type"] == "session"


def test_progress_and_csv():
    c = TestClient(app.app)
    p = c.get("/progress").json()
    assert {"band", "turns", "practising", "learned", "cards"} <= set(p)
    r = c.get("/cards.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
