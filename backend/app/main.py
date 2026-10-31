"""AdPilot AI backend: one FastAPI app, one router per module (modular monolith).

Run:  uvicorn app.main:app --reload --port 8000     API docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import shutil

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import analytics, assets, brands, campaigns, concepts, integrations, posts, socials
from .config import settings
from .db import init_db, recover_interrupted
from .services.video_service import ffmpeg_path
from .services.llm import active_provider, gemini_status, providers_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="AdPilot AI API",
    version="0.1.0",
    description="Brand Memory → strategy → creatives → campaign → analytics → optimization. "
                "AI outputs carry `generation_mode`; metrics carry their data source.",
)
log = logging.getLogger("adpilot")


@app.middleware("http")
async def never_crash(request: Request, call_next):
    """Turn any unexpected error into a JSON 500. Added before CORS so the response still carries CORS headers;
    otherwise the browser shows a vague 'network error' and the real cause is lost."""
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": f"Something went wrong on the server ({exc.__class__.__name__}). "
                                       "Please try again; if it repeats, check the backend log."}, status_code=500)


app.add_middleware(CORSMiddleware, allow_origins=settings.frontend_origins, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

init_db()
recovered = recover_interrupted()
if any(recovered.values()):
    log.warning("startup recovery: %s", recovered)

# Generated files (videos, downloaded brand images) are served read-only from storage/.
app.mount("/files", StaticFiles(directory=str(settings.storage_dir)), name="files")
# The fictional demo storefront, so it can also be opened in a browser.
app.mount("/demo-store", StaticFiles(directory=str(settings.sample_data_dir / "demo_store"), html=True),
          name="demo-store")

for module in (brands, campaigns, concepts, posts, socials, assets, analytics, integrations):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["system"])
def health() -> dict:
    from sqlmodel import Session, text

    from .db import engine
    try:
        with Session(engine) as s:
            s.exec(text("select 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": db_ok,
        "llm_provider": active_provider(),
        "gemini": gemini_status(),
        "providers": providers_status(),
        "ffmpeg": ffmpeg_path() is not None,
        "demo_store_url": f"https://{settings.demo_store_host}/",
    }
