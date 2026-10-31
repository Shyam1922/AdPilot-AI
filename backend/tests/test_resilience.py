"""Backend resilience: restart recovery, unexpected errors return JSON (with CORS), health reports the database."""
from sqlmodel import Session

from app.db import engine, recover_interrupted
from app.models import Asset, Brand


def test_recover_marks_stuck_work(client):
    with Session(engine) as s:
        b = Brand(name="Analyzing…", website="x")
        s.add(b)
        a = Asset(campaign_id=1, concept_id=1, brand_id=1, kind="video", fmt="9:16", status="rendering")
        s.add(a)
        s.commit()
        aid = a.id
    out = recover_interrupted()
    assert out["renders_marked_failed"] >= 1 and out["brands_removed"] >= 1
    with Session(engine) as s:
        got = s.get(Asset, aid)
        assert got.status == "failed" and "restart" in got.error


def test_health_has_database_and_providers(client):
    h = client.get("/api/health").json()
    assert h["database"] is True and h["status"] == "ok" and isinstance(h["providers"], list)


def test_unhandled_error_is_json_with_cors(client, monkeypatch):
    from app.main import app

    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("kaboom")

    r = client.get("/api/_boom", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 500 and "detail" in r.json()
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
