"""Tests run without GPUs, models or keys. The learner record goes to a temporary file, and the brain is never called.

The `tutor` fixture runs the real app against stand-ins for the models (tests/fakes/backends.py), for the tests that
hold a whole conversation: over the WebSocket (test_conversation.py) and in a phone-sized browser (browser/).
"""
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path

import httpx, pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
# Set before anything imports tools.learner, which reads it once.
os.environ["SHAHRAZAD_LEARNER_DB"] = str(Path(tempfile.mkdtemp(prefix="shahrazad-test-")) / "learner.db")
for var in ("SHAHRAZAD_BRAIN", "SHAHRAZAD_HEARING", "SHAHRAZAD_VOICE", "OPENROUTER_API_KEY", "TUTOR_DEBUG_LOG", "TUTOR_PASSWORD"):
    os.environ.pop(var, None)
# Nothing listens on these, so health checks fail fast instead of finding a running tutor.
for var, port in (("GEMMA_PORT", "1"), ("VOXTRAL_PORT", "2"), ("SPARK_PORT", "3")):
    os.environ[var] = port

STARTUP_S = 30


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_up(url, process, name):
    deadline = time.time() + STARTUP_S
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited at start-up: see its output above")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{name} didn't start within {STARTUP_S} s")


class Tutor:
    """The running app (url, ws_url) and the fake models behind it (calls: what the app asked them for)."""

    def __init__(self, url, fakes_url, data):
        self.url, self.fakes_url, self.data = url, fakes_url, data   # data: the folder of its learner record and logs
        self.ws_url = url.replace("http", "ws", 1) + "/ws"

    def calls(self, part=None):
        return [c for c in httpx.get(self.fakes_url + "/calls", timeout=5).json() if part in (None, c["part"])]

    def reset_calls(self):
        httpx.post(self.fakes_url + "/reset", timeout=5)


@pytest.fixture(scope="session")
def tutor():
    fakes_port, app_port = free_port(), free_port()
    data = Path(tempfile.mkdtemp(prefix="shahrazad-e2e-"))
    env = {**os.environ, "GEMMA_PORT": str(fakes_port), "VOXTRAL_PORT": str(fakes_port), "SPARK_PORT": str(fakes_port),
           "TUTOR_PORT": str(app_port), "TUTOR_HOST": "127.0.0.1", "TUTOR_SSL_CERT": "",
           "SHAHRAZAD_LEARNER_DB": str(data / "learner.db")}
    fakes = subprocess.Popen([sys.executable, "-I", str(ROOT / "tests/fakes/backends.py"), str(fakes_port)], env=env)
    app = subprocess.Popen([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=env)
    try:
        wait_until_up(f"http://127.0.0.1:{fakes_port}/health", fakes, "the fake models")
        wait_until_up(f"http://127.0.0.1:{app_port}/health", app, "the app")
        yield Tutor(f"http://127.0.0.1:{app_port}", f"http://127.0.0.1:{fakes_port}", data)
    finally:
        for process in (app, fakes):
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
