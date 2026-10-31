"""Environment-based configuration. Secrets live only in backend/.env (never in the frontend)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM: "auto" uses Gemini when a key is present, otherwise the offline generator.
    llm_provider: str = os.getenv("LLM_PROVIDER", "auto")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "45"))

    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'adpilot.db'}")
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", str(BACKEND_DIR / "storage")))
    sample_data_dir: Path = REPO_DIR / "sample_data"
    fonts_dir: Path = Path(__file__).resolve().parent / "assets" / "fonts"

    frontend_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in os.getenv(
            "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
    )

    # Extraction safety
    fetch_timeout_s: float = float(os.getenv("FETCH_TIMEOUT_S", "10"))
    max_page_bytes: int = int(os.getenv("MAX_PAGE_BYTES", str(3 * 1024 * 1024)))
    max_image_bytes: int = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    # Hostname that maps to the bundled demo storefront (works fully offline).
    demo_store_host: str = os.getenv("DEMO_STORE_HOST", "demo.adpilot.local")

    # Video
    video_width: int = int(os.getenv("VIDEO_WIDTH", "1080"))
    video_height: int = int(os.getenv("VIDEO_HEIGHT", "1920"))
    video_fps: int = int(os.getenv("VIDEO_FPS", "30"))
    music_path: str = os.getenv("MUSIC_PATH", "")  # optional royalty-free track you own

    seed_demo: bool = _bool("SEED_DEMO", True)


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
