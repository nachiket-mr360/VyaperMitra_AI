# VyaparMitra API (Phase 1)

Base URL (local): `http://127.0.0.1:5000`

The Vite dev server proxies `/api` to Flask. Authentication is **not implemented** in Phase 1 (single-shop local MVP).

## Error shape

All error responses are JSON. Stack traces and database messages are not returned.

```json
{
  "ok": false,
  "error": {
    "code": "internal_error",
    "message": "Something went wrong. Please try again."
  }
}
```

Typical HTTP codes: `400` validation, `404` unknown route, `413` body too large, `500` unexpected, `503` health when SQLite is down.

## `GET /api/health`

No request body. Used by the Phase 1 UI to confirm the API and database.

Success (`200`) when SQLite answers `SELECT 1`:

```json
{
  "ok": true,
  "app": "VyaparMitra",
  "phase": 1,
  "timezone": "Asia/Kolkata",
  "server_time": "2026-11-06T14:35:05+05:30",
  "database": { "connected": true },
  "gnani": {
    "enabled": false,
    "configured": false,
    "integration": "not_started",
    "note": "Phase 1 does not call Gnani. No placeholder STT/TTS."
  }
}
```

If the database check fails: `503`, `"ok": false`, `"database.connected": false`.

`gnani.configured` is a boolean only (whether `GNANI_API_KEY` is non-empty). The key itself is never returned.

## Future endpoints

Product, inventory, sales, voice, analytics, reminders, and export APIs are **not** available until later phases. They will validate types, quantities, prices, dates, and identifiers on the server.
