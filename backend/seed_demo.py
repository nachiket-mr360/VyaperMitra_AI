"""Seed ONLY a demo SQLite file. Never the shop database."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
SHOP_NAMES = frozenset({"vyaparmitra.db"})


def assert_demo_path(path: Path) -> None:
    resolved = path.resolve()
    name = resolved.name.lower()
    if name in SHOP_NAMES or "demo" not in resolved.stem.lower():
        raise SystemExit(f"Refusing to seed non-demo database: {resolved}")


def seed_demo_database(db_path: Path, *, reset: bool) -> dict:
    assert_demo_path(db_path)
    if reset and db_path.exists():
        db_path.unlink()
        for extra in (f"{db_path}-wal", f"{db_path}-shm"):
            p = Path(extra)
            if p.exists():
                p.unlink()

    os.environ.setdefault("FLASK_DEBUG", "1")
    os.environ.setdefault("FLASK_ENV", "development")

    import config as config_mod

    config_mod.Config.DATABASE_PATH = str(db_path.resolve())
    from app import create_app
    from db import atomic_connection
    from services import products as product_service
    from services import sales as sales_service
    from timeutil import business_date_str, now_business

    create_app()

    catalog = [
        ("DEMO Rice", "kg", 200, 25, 40),
        ("DEMO Wheat flour", "kg", 90, 20, 38),
        ("DEMO Sugar", "kg", 8, 20, 45),
        ("DEMO Cooking oil", "l", 35, 8, 140),
        ("DEMO Milk", "l", 6, 10, 60),
        ("DEMO Tea powder", "g", 800, 200, 0.4),
        ("DEMO Biscuits", "pcs", 80, 30, 12),
        ("DEMO Soap", "pcs", 48, 12, 25),
        ("DEMO Salt", "kg", 40, 8, 22),
        ("DEMO Dal", "kg", 70, 15, 90),
    ]
    ids: dict[str, int] = {}
    with atomic_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('demo_data', '1')"
        )
        for name, unit, opening, thresh, cost in catalog:
            row = product_service.create_product(
                name,
                unit,
                low_stock_threshold=thresh,
                opening_stock=opening,
                opening_unit_cost=cost,
                conn=conn,
            )
            ids[name] = int(row["id"])

        today = now_business().date()
        today_s = business_date_str()
        bills = 0
        amount = 0

        def bill(day, items, n):
            nonlocal bills, amount
            sale, _ = sales_service.create_sale(
                items,
                idempotency_key=f"demo-{day}-{n}",
                notes="DEMO DATA — fictional grocery shop",
                payment_status="unknown",
                transaction_date=day,
                conn=conn,
            )
            bills += 1
            amount += int(round(float(sale["total_amount"]) * 100))

        rice, wheat, sugar, oil, milk, tea, bisc, soap, salt, dal = (
            ids["DEMO Rice"],
            ids["DEMO Wheat flour"],
            ids["DEMO Sugar"],
            ids["DEMO Cooking oil"],
            ids["DEMO Milk"],
            ids["DEMO Tea powder"],
            ids["DEMO Biscuits"],
            ids["DEMO Soap"],
            ids["DEMO Salt"],
            ids["DEMO Dal"],
        )

        bill(
            today_s,
            [
                {"product_id": rice, "quantity": 5, "line_total": 220},
                {"product_id": dal, "quantity": 2, "line_total": 190},
            ],
            1,
        )
        bill(today_s, [{"product_id": milk, "quantity": 2, "line_total": 120}], 2)
        bill(
            today_s,
            [
                {"product_id": oil, "quantity": 1, "line_total": 145},
                {"product_id": soap, "quantity": 2, "line_total": 50},
            ],
            3,
        )

        yest = (today - timedelta(days=1)).isoformat()
        bill(yest, [{"product_id": wheat, "quantity": 4, "line_total": 160}], 1)
        bill(
            yest,
            [
                {"product_id": sugar, "quantity": 1, "line_total": 48},
                {"product_id": tea, "quantity": 100, "line_total": 80},
            ],
            2,
        )

        n = 1
        for offset in range(2, 31):
            day = (today - timedelta(days=offset)).isoformat()
            pick = offset % 5
            if pick == 0:
                bill(day, [{"product_id": rice, "quantity": 3, "line_total": 130}], n)
            elif pick == 1:
                bill(day, [{"product_id": dal, "quantity": 1.5, "line_total": 140}], n)
            elif pick == 2:
                bill(day, [{"product_id": bisc, "quantity": 4, "line_total": 48}], n)
            elif pick == 3:
                bill(
                    day,
                    [
                        {"product_id": salt, "quantity": 1, "line_total": 22},
                        {"product_id": soap, "quantity": 1, "line_total": 25},
                    ],
                    n,
                )
            else:
                bill(day, [{"product_id": wheat, "quantity": 2, "line_total": 80}], n)
            n += 1
            if offset % 4 == 0:
                bill(day, [{"product_id": oil, "quantity": 1, "line_total": 140}], n)
                n += 1

    return {"path": str(db_path), "bills": bills, "products": len(ids)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed isolated demo SQLite only.")
    parser.add_argument(
        "--db",
        default=str(BACKEND / "vyaparmitra_demo.db"),
        help="Demo database path (filename must contain 'demo').",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo database file first. Shop DB is never touched.",
    )
    args = parser.parse_args()
    info = seed_demo_database(Path(args.db), reset=args.reset)
    print("demo_seeded", info)
    print("Isolated seed only. Do not point Flask DATABASE_PATH at this file for shop use.")


if __name__ == "__main__":
    main()
    sys.exit(0)
