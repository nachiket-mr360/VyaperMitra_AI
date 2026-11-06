# VyaparMitra task list

Project name is **VyaparMitra** everywhere. Timezone: **Asia/Kolkata**. Stock updates use atomic SQLite transactions. Gnani credits: **not assumed**.

## Completed — Phase 1

- [x] Project setup, health API, logging, security headers, docs, Git hygiene

## Completed — Phase 2

- [x] Versioned SQLite migrations (`001`, `002`)
- [x] products, product_aliases, stock_movements, sales, sale_items
- [x] Product CRUD, deactivate, aliases, low-stock threshold
- [x] Opening / purchase / adjustment stock APIs
- [x] Sales with multi-item, stock decrement, idempotency
- [x] Analytics endpoints (today, date, summary, by-product, stock, low-stock)
- [x] Isolated pytest DB (17 tests)

## Pending — Phase 3+ (not started)

- [ ] Intent processing / voice command mapping
- [ ] Gnani Prisma STT (real API only)
- [ ] Gnani Timbre TTS (real API only)
- [ ] Analytics dashboard UI
- [ ] Reminders, briefing, notifications
- [ ] CSV / Excel / PDF export
- [ ] Authentication before public deploy

## Blocked

- None.

## Explicitly not done

- No Gnani calls
- No placeholder / fake AI
- No profit calculation
- No full analytics frontend
