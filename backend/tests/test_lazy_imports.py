"""
Startup speed: pymupdf and the openai SDK must not load when the app is imported.
Runs in a fresh interpreter so other tests' imports don't mask a regression.
"""
import os
import subprocess
import sys

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_app_import_does_not_load_pymupdf_or_openai():
    code = (
        "import sys\n"
        "import app.main\n"
        "loaded = [m for m in ('pymupdf', 'fitz', 'openai') if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code], cwd=_BACKEND, capture_output=True, text=True, timeout=120
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "", f"loaded at import time: {res.stdout.strip()}"


def test_llm_fallback_builds_client_on_first_use(monkeypatch):
    try:
        from app.engine import llm_fallback
        from app.core.config import settings
    except ImportError:
        from backend.app.engine import llm_fallback
        from backend.app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    fb = llm_fallback.MicroLLMFallback()
    assert fb.client is None
    assert fb.parse_ambiguous_lines(["SECJ1013 PROGRAMMING 3 A"]) == []

    monkeypatch.setattr(settings, "LLM_API_KEY", "mock-key")
    assert fb.client is not None
    assert fb.client is fb.client
