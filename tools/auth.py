"""Login: one shared password (TUTOR_PASSWORD in .env) for the page and the WebSocket. Without it there is no login.

A browser that logs in gets a signed cookie, valid for COOKIE_DAYS. It's signed with a secret made once per install and
mixed with the password, so changing the password logs every browser out.
"""
import hashlib, hmac, html, os, secrets, string, time, urllib.parse
from pathlib import Path

from . import learner

PASSWORD = os.environ.get("TUTOR_PASSWORD", "")
COOKIE, COOKIE_DAYS = "shahrazad", 30
PUBLIC = ("/login", "/favicon.ico")   # and everything under /assets/: the login page uses them
LOGIN_PAGE = string.Template((Path(__file__).resolve().parent.parent / "web/login.html").read_text())


def _signing_key():
    secret_file = learner.DB_PATH.with_name(".cookie_secret")
    if not secret_file.exists():
        secret_file.parent.mkdir(exist_ok=True)
        secret_file.write_bytes(secrets.token_bytes(32))
        secret_file.chmod(0o600)
    return hashlib.sha256(secret_file.read_bytes() + PASSWORD.encode()).digest()


KEY = _signing_key() if PASSWORD else b""


def _signature(until):
    return hmac.new(KEY, until.encode(), "sha256").hexdigest()


def make_cookie():
    until = str(int(time.time()) + COOKIE_DAYS * 86400)
    return until + "." + _signature(until)


def logged_in(cookies):
    if not PASSWORD:
        return True
    until, _, signature = cookies.get(COOKIE, "").partition(".")
    return until.isdigit() and int(until) > time.time() and hmac.compare_digest(signature, _signature(until))


def password_ok(given):
    return not PASSWORD or hmac.compare_digest(given.encode(), PASSWORD.encode())


def needs_login(path, cookies):
    return bool(PASSWORD) and path not in PUBLIC and not path.startswith("/assets/") and not logged_in(cookies)


def same_origin(headers):
    """A browser always sends Origin with a WebSocket: it must be this page, so another site can't open the tutor's
    WebSocket with the learner's cookie. Non-browser clients send none."""
    origin = headers.get("origin")
    return not origin or urllib.parse.urlparse(origin).netloc == headers.get("host")


def login_page(error=""):
    return LOGIN_PAGE.substitute(error=f'<p class="err">{html.escape(error, quote=False)}</p>' if error else "")
