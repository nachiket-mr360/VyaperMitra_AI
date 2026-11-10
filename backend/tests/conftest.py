from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "vyaparmitra-test.db"
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setattr("config.Config.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("config.Config.LLM_PROVIDER", "")
    monkeypatch.setattr("config.Config.GEMINI_API_KEY", "")
    from app import create_app

    from intents import session_store

    session_store.reset()
    application = create_app()
    application.config["TESTING"] = True
    with application.test_client() as test_client:
        yield test_client
    session_store.reset()
    assert db_path.exists()
