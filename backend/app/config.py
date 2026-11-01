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
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "20"))
    gemini_thinking: str = os.getenv("GEMINI_THINKING", "low")   # low | medium | high | default
    # Tried in order when the main model is busy (503), rate-limited (429) or retired (404).
    gemini_fallback_models: str = os.getenv(
        "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-flash-latest")

    # Extra providers tried (in LLM_PROVIDERS order) when Gemini is down, rate-limited or out of quota.
    # All use the OpenAI-compatible /chat/completions API, so any of them works with just a key + model.
    llm_providers: str = os.getenv("LLM_PROVIDERS", "gemini,groq,openrouter,mistral,cerebras,ollama,custom")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
    cerebras_api_key: str = os.getenv("CEREBRAS_API_KEY", "")
    cerebras_model: str = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "")            # local, no key: e.g. llama3.1:8b
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")
    custom_llm_url: str = os.getenv("CUSTOM_LLM_URL", "")        # any OpenAI-compatible endpoint
    custom_llm_key: str = os.getenv("CUSTOM_LLM_KEY", "")
    custom_llm_model: str = os.getenv("CUSTOM_LLM_MODEL", "")

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

    # Meko (Yugabyte) shared agent memory, over MCP. Optional: the app works without it.
    meko_api_key: str = os.getenv("MEKO_API_KEY", "")
    meko_url: str = os.getenv("MEKO_URL", "https://mcp.mekodata.ai/mcp")
    meko_auth_header: str = os.getenv("MEKO_AUTH_HEADER", "Authorization")
    meko_auth_scheme: str = os.getenv("MEKO_AUTH_SCHEME", "Bearer")
    meko_datapack_id: str = os.getenv("MEKO_DATAPACK_ID", "")        # optional: force an existing datapack
    meko_timeout_s: float = float(os.getenv("MEKO_TIMEOUT_S", "20"))

    # X (Twitter) publishing, optional. Create an app with Read and write permission at developer.x.com.
    x_api_key: str = os.getenv("X_API_KEY", "")
    x_api_secret: str = os.getenv("X_API_SECRET", "")
    x_access_token: str = os.getenv("X_ACCESS_TOKEN", "")
    x_access_secret: str = os.getenv("X_ACCESS_SECRET", "")

    seed_demo: bool = _bool("SEED_DEMO", True)


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
