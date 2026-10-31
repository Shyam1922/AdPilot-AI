"""Capture REAL API responses into sample_data/fixtures/ so the frontend can mock the API exactly.

Run: python -m app.scripts.export_fixtures      (uses a throwaway database; your real one is untouched)
"""
from __future__ import annotations

import json
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="adpilot-fixtures-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/fx.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ.setdefault("LLM_PROVIDER", "offline")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

OUT = settings.sample_data_dir / "fixtures"


def save(name: str, data) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT / f"{name}.json")


def main() -> None:
    with TestClient(app) as c:
        save("health", c.get("/api/health").json())
        brand = c.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
        save("brand", brand)
        camp = c.post("/api/campaigns", json={"brand_id": brand["id"], "objective": "sales",
                                              "channels": ["instagram", "meta_ads", "google_ads"]}).json()
        save("campaign", camp)
        concepts = c.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
        save("concepts", concepts)
        c.patch(f"/api/concepts/{concepts[0]['id']}", json={"status": "approved"})
        save("campaign_detail", c.get(f"/api/campaigns/{camp['id']}").json())
        save("integrations", c.get("/api/integrations").json())


if __name__ == "__main__":
    main()
