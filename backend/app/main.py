"""AdPilot AI backend: one FastAPI app, one router per module (modular monolith).

Run:  uvicorn app.main:app --reload --port 8000     API docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import analytics, assets, brands, campaigns, concepts, integrations
from .config import settings
from .db import init_db
from .services.llm import active_provider, gemini_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="AdPilot AI API",
    version="0.1.0",
    description="Brand Memory → strategy → creatives → campaign → analytics → optimization. "
                "AI outputs carry `generation_mode`; metrics carry their data source.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origins, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

init_db()

# Generated files (videos, downloaded brand images) are served read-only from storage/.
app.mount("/files", StaticFiles(directory=str(settings.storage_dir)), name="files")
# The fictional demo storefront, so it can also be opened in a browser.
app.mount("/demo-store", StaticFiles(directory=str(settings.sample_data_dir / "demo_store"), html=True),
          name="demo-store")

for module in (brands, campaigns, concepts, assets, analytics, integrations):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_provider": active_provider(),
        "gemini": gemini_status(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "demo_store_url": f"https://{settings.demo_store_host}/",
    }
