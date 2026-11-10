"""VyaparMitra backend configuration. Secrets come from environment only."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env")


INSECURE_SECRET_KEYS = frozenset(
    {"", "dev-only-change-me", "changeme", "secret", "secret_key"}
)


def _float(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.getenv(name)
    try:
        val = float(raw) if raw is not None and str(raw).strip() else default
    except (TypeError, ValueError):
        val = default
    return max(lo, min(hi, val))


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def production_mode() -> bool:
    env = (os.getenv("FLASK_ENV") or "").strip().lower()
    if env == "production":
        return True
    if env == "development":
        return False
    return not _bool("FLASK_DEBUG", True)


def require_secure_secret(secret: str) -> None:
    normalized = secret.strip().lower()
    if production_mode() and (
        normalized in INSECURE_SECRET_KEYS or len(secret.strip()) < 32
    ):
        raise RuntimeError(
            "Refusing to start: set a strong SECRET_KEY of at least 32 characters; "
            "insecure defaults are not allowed in production."
        )


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = _bool("FLASK_DEBUG", False)

    BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")
    # Normal operation always uses the shop SQLite file. VYAPARMITRA_DEMO is ignored.
    DEMO_MODE = False

    _db_env = (os.getenv("DATABASE_PATH") or "").strip()
    _db = _db_env or "vyaparmitra.db"
    DATABASE_PATH = str(Path(_db) if Path(_db).is_absolute() else BACKEND_DIR / _db)

    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]

    GNANI_API_KEY = os.getenv("GNANI_API_KEY", "")
    GNANI_ENABLED = _bool("GNANI_ENABLED", False)
    GNANI_PRISMA_VERSION = os.getenv("GNANI_PRISMA_VERSION", "3.0")
    GNANI_TIMBRE_VERSION = os.getenv("GNANI_TIMBRE_VERSION", "3.0")
    GNANI_STT_URL = os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3")
    GNANI_STT_MODEL = os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
    GNANI_STT_TIMEOUT = int(os.getenv("GNANI_STT_TIMEOUT", "60"))
    GNANI_STT_MAX_BYTES = int(os.getenv("GNANI_STT_MAX_BYTES", str(5 * 1024 * 1024)))
    GNANI_STT_MAX_SECONDS = float(os.getenv("GNANI_STT_MAX_SECONDS", "30"))
    # Timbre REST documents text/voice/model/language/audio_config only.
    # Speed/pitch/SSML are not sent. Playback rate is applied in the browser
    # with preservesPitch so speech is ~12% faster without a chipmunk pitch shift.
    GNANI_TTS_VOICE = (os.getenv("GNANI_TTS_VOICE") or "Lakshmi").strip() or "Lakshmi"
    GNANI_TTS_MODEL = (os.getenv("GNANI_TTS_MODEL") or "timbre-v3.0").strip() or "timbre-v3.0"
    TTS_PLAYBACK_RATE = _float("TTS_PLAYBACK_RATE", 1.12, 1.0, 1.25)
    INTENT_PENDING_TTL_SECONDS = int(os.getenv("INTENT_PENDING_TTL_SECONDS", "900"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "12"))
    LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    SHOP_ID = (os.getenv("SHOP_ID") or "default").strip() or "default"
    SESSION_CONTEXT_TURNS = int(os.getenv("SESSION_CONTEXT_TURNS", "12"))
