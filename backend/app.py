"""VyaparMitra Flask application — Phase 1 health and reliability foundations."""

from __future__ import annotations

import logging

from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config, require_secure_secret
from db import get_connection, init_db
from errors import register_error_handlers
from logging_setup import setup_logging
from routes import register_blueprints
from security import apply_security
from timeutil import now_business

APP_NAME = "VyaparMitra"
APP_PHASE = 7

logger = logging.getLogger("vyaparmitra")


def create_app() -> Flask:
    setup_logging()
    require_secure_secret(Config.SECRET_KEY)
    app = Flask(__name__)
    app.config.from_object(Config)
    _loopback = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}
    if Config.DEBUG and str(Config.HOST).strip() not in _loopback:
        logger.warning("FLASK_DEBUG ignored because HOST is not loopback")
        app.config["DEBUG"] = False
    CORS(app, origins=Config.CORS_ORIGINS)
    apply_security(app)
    register_error_handlers(app)
    register_blueprints(app)
    init_db()
    logger.info("VyaparMitra starting phase=%s tz=%s", APP_PHASE, Config.BUSINESS_TIMEZONE)

    @app.get("/api/health")
    def health():
        db_ok = False
        try:
            conn = get_connection()
            row = conn.execute("SELECT 1 AS ok").fetchone()
            db_ok = bool(row and row["ok"] == 1)
            conn.close()
        except Exception:
            logger.exception("Health database check failed")
            db_ok = False

        now = now_business()
        payload = {
            "ok": db_ok,
            "app": APP_NAME,
            "phase": APP_PHASE,
            "timezone": Config.BUSINESS_TIMEZONE,
            "server_time": now.isoformat(),
            "database": {
                "connected": db_ok,
                "demo": False,
                "path": Config.DATABASE_PATH,
                "name": Path(Config.DATABASE_PATH).name,
            },
            "gnani": {
                "enabled": Config.GNANI_ENABLED,
                "configured": bool(Config.GNANI_API_KEY),
                "integration": "prisma_stt",
                "note": "Prisma STT. Optional Timbre TTS via Flask. Gemini optional for intent JSON.",
                "tts": bool((Config.GNANI_API_KEY or "").strip()),
                "tts_playback_rate": Config.TTS_PLAYBACK_RATE,
                "tts_voice": Config.GNANI_TTS_VOICE,
            },
            "llm": {
                "provider": Config.LLM_PROVIDER or None,
                "configured": bool((Config.GEMINI_API_KEY or "").strip())
                and Config.LLM_PROVIDER == "gemini",
                "model": Config.GEMINI_MODEL if Config.LLM_PROVIDER == "gemini" else None,
            },
        }
        return jsonify(payload), 200 if db_ok else 503

    return app


app = create_app()


if __name__ == "__main__":
    _loopback = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}
    debug = bool(Config.DEBUG) and str(Config.HOST).strip() in _loopback
    app.run(host=Config.HOST, port=Config.PORT, debug=debug)
