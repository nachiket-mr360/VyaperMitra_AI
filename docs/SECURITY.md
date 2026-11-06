# VyaparMitra security (Phase 2)

## Decisions already in place

- Secrets load from environment (`python-dotenv`). Development may use `SECRET_KEY=dev-only-change-me`. If `FLASK_ENV=production` (or debug is off without `FLASK_ENV=development`), the process **refuses to start** on that default or other insecure keys.
- Flask CORS is limited to `CORS_ORIGINS` (default Vite: `http://localhost:5173`, `http://127.0.0.1:5173`).
- `MAX_CONTENT_LENGTH` is 1 MiB (JSON-only Phase 1). Voice uploads will raise this later with type checks.
- Response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`.
- SQLite uses parameterized queries and `PRAGMA foreign_keys = ON`. Writes use `BEGIN IMMEDIATE` and roll back as a unit.
- Idempotency keys are hashed with the sale payload; a reused key with a different body is `409 idempotency_conflict`. Failed sales do not keep the key.
- Product PATCH cannot set `current_stock` or other protected fields.
- Errors: clients get generic JSON; details go to rotating logs under `backend/logs/` (gitignored).
- Logs redact lines that mention `api_key`, `password`, `token`, `secret`, `authorization`.
- Gnani keys stay on the backend. React never receives them.

## Environment variables

See `.env.example`. Copy to `backend/.env`. Never commit `.env`.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Flask signing; change for any non-local use |
| `HOST` / `PORT` | Bind address (default loopback `:5000`) |
| `FLASK_DEBUG` | Local debug only; must be off in production |
| `DATABASE_PATH` | SQLite file (gitignored) |
| `BUSINESS_TIMEZONE` | Must remain `Asia/Kolkata` for business dates |
| `GNANI_API_KEY` | Empty until real Gnani integration |
| `GNANI_ENABLED` | Feature flag; false in Phase 1 |
| `CORS_ORIGINS` | Comma-separated allowed origins |

## Authentication assumptions (MVP)

- **Single shop, local machine.** No login, no multi-tenant isolation.
- The data model must still use shop/owner identifiers later so one shop cannot read another’s rows.
- Before public deployment: password hashing, session/token protection, authorization on every mutating route, no default credentials.

## Not added in Phase 1 (and why)

- **Rate limiting packages:** local single-shop MVP; add when the API is exposed.
- **CSRF tokens:** no cookie session auth yet; revisit with login.
- **Helmet-style extra packages:** headers above are enough for local JSON API.

## Deployment requirements (not Phase 1)

- HTTPS, `FLASK_DEBUG=0`, strong `SECRET_KEY`, restricted CORS, hashed auth, backups of SQLite, rotate any key that was ever committed.
- Bind to loopback or a reverse proxy; do not expose Flask debug to the internet.

## Known limitations

- Anyone who can reach the local API can mutate products, stock, and sales until auth exists.
- Weak default `SECRET_KEY` is allowed only in development.
- SQLite file lives on disk; OS file permissions matter.
- No CSRF, rate limit, or auth yet.
