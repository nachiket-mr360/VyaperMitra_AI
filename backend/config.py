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
    if production_mode() and secret.strip().lower() in INSECURE_SECRET_KEYS:
        raise RuntimeError(
            "Refusing to start: set a strong SECRET_KEY; insecure defaults are not allowed in production."
        )


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))
    DEBUG = _bool("FLASK_DEBUG", True)

    BUSINESS_TIMEZONE = os.getenv("BUSINESS_TIMEZONE", "Asia/Kolkata")

    _db = os.getenv("DATABASE_PATH", "vyaparmitra.db")
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
