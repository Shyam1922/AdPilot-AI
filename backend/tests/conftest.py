"""Test setup: isolated temp database + storage, offline LLM (no network, deterministic)."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="adpilot-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["LLM_PROVIDER"] = "offline"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
