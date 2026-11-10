from __future__ import annotations

import pytest

from config import require_secure_secret


def test_production_requires_long_secret(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        require_secure_secret("dev-only-change-me")


def test_production_accepts_long_secret(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")

    require_secure_secret("a" * 64)
