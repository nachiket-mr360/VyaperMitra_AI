"""VyaparMitra Flask application — Phase 1 health and reliability foundations."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from flask_cors import CORS

from config import Config
from db import get_connection, init_db
from errors import register_error_handlers
from logging_setup import setup_logging
from security import apply_security
from timeutil import now_business

APP_NAME = "VyaparMitra"
APP_PHASE = 1

logger = logging.getLogger("vyaparmitra")


def create_app() -> Flask:
    setup_logging()
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, origins=Config.CORS_ORIGINS)
    apply_security(app)
    register_error_handlers(app)
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
            },
            "gnani": {
                "enabled": Config.GNANI_ENABLED,
                "configured": bool(Config.GNANI_API_KEY),
                "integration": "not_started",
                "note": "Phase 1 does not call Gnani. No placeholder STT/TTS.",
            },
        }
        return jsonify(payload), 200 if db_ok else 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
