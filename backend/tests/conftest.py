"""Test setup: isolated temp database + storage, offline LLM (no network, deterministic)."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so `app` imports work however pytest is started

_tmp = tempfile.mkdtemp(prefix="adpilot-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["LLM_PROVIDER"] = "offline"
os.environ["GEMINI_API_KEY"] = ""   # tests never use real keys from backend/.env
os.environ["MEKO_API_KEY"] = ""
for _k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "CEREBRAS_API_KEY", "OLLAMA_MODEL", "CUSTOM_LLM_URL"):
    os.environ[_k] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
