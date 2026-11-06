# VyaparMitra security (Phase 1)

## Decisions already in place

- Secrets load from environment (`python-dotenv`). Nothing is hardcoded except a **development-only** `SECRET_KEY` fallback (`dev-only-change-me`). Replace it before any shared or public deploy.
- Flask CORS is limited to `CORS_ORIGINS` (default Vite: `http://localhost:5173`, `http://127.0.0.1:5173`).
- `MAX_CONTENT_LENGTH` is 1 MiB (JSON-only Phase 1). Voice uploads will raise this later with type checks.
- Response headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`.
- SQLite uses parameterized queries and `PRAGMA foreign_keys = ON`. `atomic_connection` commits or rolls back as a unit.
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

- **Rate limiting packages:** only a health GET exists; add limits when write/voice endpoints exist.
- **CSRF tokens:** no cookie session auth yet; revisit with login.
- **Helmet-style extra packages:** headers above are enough for local JSON API.

## Deployment requirements (not Phase 1)

- HTTPS, `FLASK_DEBUG=0`, strong `SECRET_KEY`, restricted CORS, hashed auth, backups of SQLite, rotate any key that was ever committed.
- Bind to loopback or a reverse proxy; do not expose Flask debug to the internet.

## Known limitations

- Anyone who can reach the local API can call `/api/health` (and future APIs until auth exists).
- Weak default `SECRET_KEY` if env is missing.
- SQLite file lives on disk; OS file permissions matter.
- No CSRF, rate limit, or auth yet.
