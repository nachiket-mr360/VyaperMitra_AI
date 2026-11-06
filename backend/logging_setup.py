"""Central logging: application, errors, and debug files. No secrets."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
SENSITIVE_KEYS = ("api_key", "apikey", "password", "token", "secret", "authorization")


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        lower = msg.lower()
        for key in SENSITIVE_KEYS:
            if key in lower:
                record.msg = "[redacted log line contained a sensitive key name]"
                record.args = ()
                break
        return True


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger()
    if getattr(root, "_vyaparmitra_configured", False):
        return
    root.setLevel(logging.DEBUG)
    root.addFilter(RedactFilter())

    def add_file(name: str, level: int) -> None:
        handler = RotatingFileHandler(
            LOG_DIR / name, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setLevel(level)
        handler.setFormatter(fmt)
        root.addHandler(handler)

    add_file("app.log", logging.INFO)
    add_file("errors.log", logging.ERROR)
    add_file("debug.log", logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    root._vyaparmitra_configured = True  # type: ignore[attr-defined]
