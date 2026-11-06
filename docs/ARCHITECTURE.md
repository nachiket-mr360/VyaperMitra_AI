# VyaparMitra architecture (Phase 1)

Project name: **VyaparMitra**. Business dates and reminders use **Asia/Kolkata**.

## System

```
Browser (React + Vite, port 5173)
    │  /api  (dev proxy)
    ▼
Flask (127.0.0.1:5000)
    ├── config.py          environment
    ├── security.py        size limit, headers
    ├── errors.py          JSON errors
    ├── logging_setup.py   app / error / debug logs
    ├── db.py              SQLite + atomic_connection
    ├── timeutil.py        Asia/Kolkata
    └── routes             Phase 1: GET /api/health only
```

Gnani Prisma / Timbre / Evon are **not** integrated. The backend will be the only process that talks to Gnani later. Credit usage will be measured from real responses, not assumed.

## Component responsibilities

| Layer | Role |
| --- | --- |
| Frontend | UI, loading/error states, no business totals, no secrets |
| Flask routes | HTTP, validation (later), status codes |
| Services (later) | Sales, stock, intent — not in Phase 1 |
| `db.py` | Connections, WAL, foreign keys, transactions |
| Gnani clients (later) | Timeouts, auth failures, no fake success |

## Data flow (Phase 1)

1. UI calls `GET /api/health`.
2. Flask checks SQLite with a parameterized `SELECT 1`.
3. Response includes timezone and Gnani `not_started`.

Stock and balances will use `atomic_connection` so failed sales do not leave partial updates.

## Schema

Phase 1 only: `app_meta(key, value)`. Products, aliases, stock_movements, sales, sale_items, reminders, and alerts are Phase 2.

## Single-shop MVP

One local shop, no auth. Future tables should include shop identity so multi-owner isolation is possible without a rewrite.
