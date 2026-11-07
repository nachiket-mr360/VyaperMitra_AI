# VyaparMitra architecture (Phase 2)

Project name: **VyaparMitra**. Business dates and reminders use **Asia/Kolkata**.

## System

```
Browser (React + Vite)
    │  /api
    ▼
Flask
    ├── routes/           HTTP + validation
    ├── services/         products, stock, sales, analytics
    ├── db.py             SQLite, migrations, atomic_connection
    ├── migrations/       001_foundation, 002_inventory
    ├── gnani/            Prisma V3 STT (Timbre not started)
    └── intents/          Rule parser + confirm executor
```

Gnani Prisma V3 STT is called only from Flask (`backend/gnani/stt.py`). Transcripts are parsed by a **rule-based** intent layer (`backend/intents/`). There is no documented Evon/LLM key in this project, so no LLM HTTP calls are made. Purchase and sale require confirmation (`pending_voice_actions`) then reuse stock/sales services. The React UI never talks to SQLite.

## Frontend / backend boundary (mandatory)

VyaparMitra is a **Python + Flask** application. React + TypeScript + Vite is the UI only.

| Layer | Allowed | Forbidden |
| --- | --- | --- |
| Flask | Business logic, SQLite, inventory, sales, analytics, reminders, validation, Gnani Prisma/Timbre | None of this in the browser |
| React | Screens, forms, charts, calling `/api` | SQLite, Gnani keys/HTTP, stock/sale/profit math, schema |

Vite’s `/api` proxy is development-only; it still terminates on Flask. Do not convert the stack or move logic into the frontend.

## Schema (SQLite)

- `schema_migrations` — versioned `.sql` files; do not delete the DB to change schema
- `app_meta`
- `products` — unique `normalized_name`, `current_stock >= 0`
- `product_aliases` — unique `normalized_alias`
- `stock_movements` — `opening | purchase | sale | adjustment`; sale quantities are negative deltas
- `sales` — unique `idempotency_key`, `transaction_date` as `YYYY-MM-DD` in Asia/Kolkata
- `sale_items`

Foreign keys are on. Write paths use `BEGIN IMMEDIATE` so concurrent sales serialize. Stock updates are `UPDATE ... WHERE current_stock + delta >= 0`.

**Money and quantity:** JSON still uses rupees and unit quantities. SQLite stores **integer paise** (₹1 = 100) and **integer micro-units** (1 kg = 1_000_000). Conversion uses `decimal.Decimal` with ROUND_HALF_UP. See `backend/money.py`.

## Data flow (sale)

1. Validate items (qty > 0, prices ≥ 0).
2. If `idempotency_key` exists, return the original sale.
3. Check stock for every line.
4. Insert `sales` + `sale_items`.
5. Decrement `products.current_stock` and insert `stock_movements` (`sale`).
6. Commit.

## Single-shop MVP

No auth. Future shop_id should be added before multi-tenant deploy.
