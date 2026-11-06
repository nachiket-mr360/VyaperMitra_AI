# VyaparMitra task list

Project name is **VyaparMitra** everywhere. Timezone: **Asia/Kolkata**. Stock updates will be atomic SQLite transactions (Phase 2+). Gnani credits: **not assumed**; unused until real API calls.

## Completed — Phase 1

- [x] Initial folder structure
- [x] Flask backend with SQLite connection and WAL-ready helper
- [x] Environment files (`.env.example`, `backend/.env` placeholders)
- [x] `GET /api/health`
- [x] React + TypeScript + Vite + Tailwind frontend
- [x] Frontend health fetch via Vite proxy
- [x] Central logging (`backend/logs/`, gitignored `*.log`)
- [x] JSON error handlers (no stack traces to clients)
- [x] CORS allowlist, request size limit, security headers
- [x] README, ARCHITECTURE, API, SECURITY, TROUBLESHOOTING, TASKS, BUGS
- [x] Comprehensive `.gitignore`
- [x] Backend pytest for health, 404 JSON, headers

## Pending — Phase 2+ (not started until Phase 1 review is accepted)

- [ ] Relational schema (products, aliases, stock_movements, sales, sale_items, reminders, alerts)
- [ ] Product and inventory APIs
- [ ] Sales APIs (no purchase-cost prompt on sale)
- [ ] Gnani Prisma STT (real API only)
- [ ] Intent processing
- [ ] Gnani Timbre TTS (real API only)
- [ ] Evon only if an official API exists
- [ ] Analytics APIs and dashboard charts
- [ ] Reminders, briefing, notifications
- [ ] Multilingual UX (after verifying Gnani language support in docs)
- [ ] CSV / Excel / PDF export
- [ ] Wake-word, customer credit, expenses (after core MVP)
- [ ] Authentication before public deploy

## Blocked

- None for Phase 1.

## Explicitly not done

- No Gnani calls
- No placeholder / fake AI transcripts or audio
- No multi-shop auth (documented single-shop MVP)
