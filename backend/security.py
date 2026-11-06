"""Baseline HTTP protections. Extra packages are not added unless justified."""

from __future__ import annotations

from flask import Flask


def apply_security(app: Flask) -> None:
    # Voice audio will raise this later; 1 MiB is enough for JSON in Phase 1.
    app.config.setdefault("MAX_CONTENT_LENGTH", 1 * 1024 * 1024)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response
