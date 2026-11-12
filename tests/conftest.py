"""Tests run without GPUs, models or keys. The learner record goes to a temporary file, and the brain is never called."""
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
# Set before anything imports tools.learner, which reads it once.
os.environ["SHAHRAZAD_LEARNER_DB"] = str(Path(tempfile.mkdtemp(prefix="shahrazad-test-")) / "learner.db")
for var in ("SHAHRAZAD_BRAIN", "SHAHRAZAD_HEARING", "SHAHRAZAD_VOICE", "OPENROUTER_API_KEY", "TUTOR_DEBUG_LOG"):
    os.environ.pop(var, None)
# Nothing listens on these, so health checks fail fast instead of finding a running tutor.
for var, port in (("GEMMA_PORT", "1"), ("VOXTRAL_PORT", "2"), ("SPARK_PORT", "3")):
    os.environ[var] = port
