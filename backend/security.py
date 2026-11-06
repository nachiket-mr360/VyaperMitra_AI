"""Baseline HTTP protections. Extra packages are not added unless justified."""

from __future__ import annotations

from flask import Flask

from config import Config


def apply_security(app: Flask) -> None:
    # Voice clips up to ~30s; JSON APIs stay small within this cap.
    app.config.setdefault("MAX_CONTENT_LENGTH", Config.GNANI_STT_MAX_BYTES + 64 * 1024)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
