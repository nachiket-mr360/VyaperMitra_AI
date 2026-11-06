"""Consistent JSON errors. No stack traces or DB internals to clients."""

from __future__ import annotations

import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger("vyaparmitra.errors")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.message}}), exc.status

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": (exc.name or "error").lower().replace(" ", "_"),
                        "message": exc.description or "Request failed.",
                    },
                }
            ),
            exc.code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        logger.exception("Unhandled exception: %s", type(exc).__name__)
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "internal_error",
                        "message": "Something went wrong. Please try again.",
                    },
                }
            ),
            500,
        )
