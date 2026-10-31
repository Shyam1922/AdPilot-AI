"""Reset the app to a clean, repeatable demo state.

Wipes the database and generated files, then builds the demo story through the real API:
Velvaa brand -> sales campaign -> 5 concepts -> one rendered 9:16 video -> simulated metrics
(labelled SIMULATED) -> one optimization round.

Stop the server first, or just run it while the server is up (tables are dropped, not the file).
Run (venv active):   python -m app.scripts.reset_demo            (uses Gemini if configured)
                     python -m app.scripts.reset_demo --offline   (deterministic, no network)
                     python -m app.scripts.reset_demo --no-video  (skip the ~10 s render)
"""
from __future__ import annotations

import os
import shutil
import sys
import time

if "--offline" in sys.argv:
    os.environ["LLM_PROVIDER"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import logging  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


def wipe() -> None:
    from app import models  # noqa: F401
    SQLModel.metadata.drop_all(engine)
    init_db()
    for child in settings.storage_dir.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger().setLevel(logging.WARNING)
    wipe()
    print("cleared database and storage")
    with TestClient(app) as c:
        brand = c.post("/api/brands/analyze", json={"url": f"https://{settings.demo_store_host}/"}).json()
        print(f"brand #{brand['id']} {brand['profile']['brand_name']}  mode={brand['generation_mode']}")
        camp = c.post("/api/campaigns", json={"brand_id": brand["id"], "objective": "sales",
                                              "channels": ["instagram", "meta_ads", "google_ads"]}).json()
        print(f"campaign #{camp['id']} objective=sales  strategy mode={camp['generation_mode']}")
        gen = c.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
        concepts = gen["concepts"] if isinstance(gen, dict) else gen
        print(f"{len(concepts)} concepts")

        if "--no-video" not in sys.argv:
            r = c.post(f"/api/concepts/{concepts[0]['id']}/video", json={})
            if r.status_code != 202:
                print("video skipped:", r.json().get("detail", r.status_code))
                a = None
            else:
                a = r.json()
            for _ in range(90 if a else 0):
                st = c.get(f"/api/assets/{a['id']}").json()
                if st["status"] in ("ready", "failed"):
                    break
                time.sleep(1)
            if a:
                print(f"video: {st['status']}  {st.get('url') or st.get('error') or ''}")

        c.post(f"/api/campaigns/{camp['id']}/metrics/simulate", json={})
        it = c.post(f"/api/campaigns/{camp['id']}/iterate", json={}).json()
        print(f"simulated metrics loaded; optimization round with {len(it['variants'])} variants")
    print("\nDEMO READY: start the server and open the campaign.")


if __name__ == "__main__":
    main()
