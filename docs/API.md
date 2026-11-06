# VyaparMitra API (Phase 2)

Base URL (local): `http://127.0.0.1:5000`

Authentication is **not implemented** (single-shop local MVP). Vite proxies `/api` to Flask.

## Error shape

```json
{
  "ok": false,
  "error": {
    "code": "insufficient_stock",
    "message": "Insufficient stock"
  }
}
```

Codes include `missing_field`, `invalid_type`, `invalid_value`, `duplicate`, `not_found`, `insufficient_stock`, `inactive_product`, `conflict`, `internal_error`.

HTTP: `400` validation, `404` missing, `409` conflict/stock, `413` too large, `500` unexpected, `503` health if SQLite is down.

---

## `GET /api/health`

Same as Phase 1. `phase` is `2`. Gnani remains `not_started`.

---

## Products

### `POST /api/products`

```json
{
  "name": "Rice",
  "unit": "kg",
  "low_stock_threshold": 5,
  "opening_stock": 20,
  "opening_unit_cost": 40
}
```

`201`:

```json
{
  "ok": true,
  "product": {
    "id": 1,
    "name": "Rice",
    "normalized_name": "rice",
    "unit": "kg",
    "current_stock": 20,
    "low_stock_threshold": 5,
    "active": true,
    "low_stock": false,
    "created_at": "...",
    "updated_at": "..."
  }
}
```

Duplicate normalized names → `409`.

### `GET /api/products`

Optional `?include_inactive=true`. Returns `{ "ok": true, "products": [ ... ] }`.

### `GET /api/products/<id>`

Includes `aliases`.

### `PATCH /api/products/<id>`

Any of `name`, `unit`, `low_stock_threshold`, `active`.

### `PUT /api/products/<id>/low-stock-threshold`

```json
{ "low_stock_threshold": 8 }
```

### `POST /api/products/<id>/deactivate`

Sets `active` false. Product remains in history.

### `POST /api/products/<id>/aliases`

```json
{ "alias": "chawal", "language": "hi" }
```

`201`. Duplicate `normalized_alias` → `409`.

Units must be one of: kg, g, l, ml, pcs, pc, packet, pkts, dozen, bag, box, bunch, piece, pieces.

`current_stock` cannot be set via create/update (use stock APIs). Sending it returns `400 protected_field`.

---

## Stock

Quantities for opening and purchase must be **> 0**. Adjustments are **signed** (negative reduces stock). Resulting on-hand cannot go below 0.

### `POST /api/stock/opening`

```json
{ "product_id": 1, "quantity": 20, "unit_cost": 40, "notes": "start" }
```

Only once per product (`409` if repeated).

### `POST /api/stock/purchase`

```json
{ "product_id": 1, "quantity": 10, "unit_cost": 38 }
```

### `POST /api/stock/adjustment`

```json
{ "product_id": 1, "quantity": -0.5, "notes": "spoilage" }
```

### `GET /api/stock`

Current balances for active products.

### `GET /api/stock/low`

Active products where `current_stock <= low_stock_threshold`.

### `GET /api/stock/movements`

Optional `?product_id=1`. Ledger rows; sale rows have **negative** `quantity`.

---

## Sales

Never send purchase cost. Totals are **recorded sale amounts**, not assumed cash received. No profit is computed.

### `POST /api/sales`

Example: Rice 5 kg for ₹200 total.

```json
{
  "idempotency_key": "pos-2026-11-06-001",
  "payment_status": "unknown",
  "items": [
    { "product_id": 1, "quantity": 5, "line_total": 200 }
  ]
}
```

`unit_price` may be sent instead of `line_total`. Multiple items allowed.

`201` new sale, `200` if the same `idempotency_key` **and same payload** is replayed (`replayed: true`) without changing stock again. Same key, different items → `409 idempotency_conflict`.

Insufficient stock → `409`. Negative prices/qty → `400`.

All of: sale row, sale items, stock decrement, ledger `sale` movement — one SQLite transaction.

### `GET /api/sales`

Optional `?date=YYYY-MM-DD` (Asia/Kolkata calendar date).

### `GET /api/sales/<id>`

---

## Analytics (backend only)

Dates use **Asia/Kolkata**.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/analytics/sales/today` | Totals and product breakdown for today |
| GET | `/api/analytics/sales?date=YYYY-MM-DD` | Same for one date |
| GET | `/api/analytics/sales/summary` | All-time total and transaction count |
| GET | `/api/analytics/sales/by-product` | Quantity and amount per product |
| GET | `/api/analytics/stock` | Current stock |
| GET | `/api/analytics/stock/low` | Low-stock list |
