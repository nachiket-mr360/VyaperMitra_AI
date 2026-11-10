from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from seed_demo import assert_demo_path, seed_demo_database
from timeutil import business_date_str

BACKEND = Path(__file__).resolve().parents[1]


def test_demo_env_does_not_switch_shop_database(tmp_path):
    shop = tmp_path / "vyaparmitra.db"
    script = (
        "import os\n"
        "os.environ['VYAPARMITRA_DEMO']='1'\n"
        f"os.environ['DATABASE_PATH']=r'{shop}'\n"
        "os.environ['FLASK_DEBUG']='1'\n"
        "from config import Config\n"
        "p=Config.DATABASE_PATH.replace('\\\\','/').lower()\n"
        "assert Config.DEMO_MODE is False\n"
        "assert p.endswith('vyaparmitra.db')\n"
        "assert 'vyaparmitra_demo.db' not in p\n"
        "print('ok')\n"
    )
    out = subprocess.check_output([sys.executable, "-c", script], cwd=BACKEND, text=True)
    assert "ok" in out


def test_refuses_shop_database_name(tmp_path):
    with pytest.raises(SystemExit):
        assert_demo_path(tmp_path / "vyaparmitra.db")


def test_seed_demo_and_dashboard_match(tmp_path, monkeypatch):
    db = tmp_path / "vyaparmitra_demo.db"
    monkeypatch.setenv("VYAPARMITRA_DEMO", "1")
    monkeypatch.setenv("DATABASE_PATH", str(db))
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("FLASK_ENV", "development")
    info = seed_demo_database(db, reset=True)
    assert info["products"] == 10
    assert info["bills"] > 20
    assert db.exists()
    shop = Path(__file__).resolve().parents[1] / "vyaparmitra.db"
    # Seeding must not require or rewrite the shop file.
    assert db.resolve() != shop.resolve()

    monkeypatch.setattr("config.Config.DATABASE_PATH", str(db))
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    today = business_date_str()
    dash = client.get(f"/api/analytics/dashboard?from={today}&to={today}").get_json()
    today_api = client.get("/api/analytics/sales/today").get_json()
    assert dash["today"]["date"] == today
    assert dash["today"]["total_amount"] == today_api["total_amount"]
    assert dash["today"]["transactions"] == today_api["transactions"]
    assert dash["today"]["transactions"] >= 1
    yest = client.get("/api/analytics/sales/yesterday").get_json()
    assert dash["yesterday"]["total_amount"] == yest["total_amount"]
    assert any(p["name"].startswith("DEMO ") for p in dash["inventory"])
    assert dash["low_stock"]
    month = client.get("/api/analytics/dashboard?from=2020-01-01&to=2099-01-01").get_json()
    assert month["period"]["transactions"] == info["bills"]
