# VyaparMitra task list

Project name is **VyaparMitra** everywhere. Timezone: **Asia/Kolkata**. Stock updates use atomic SQLite transactions. Gnani credits: **not assumed**.

## Completed — Phase 1

- [x] Project setup, health API, logging, security headers, docs, Git hygiene

## Completed — Phase 2

- [x] Inventory and sales APIs, integer money, idempotency audit

## Completed — Phase 3

- [x] Flask Gnani Prisma V3 STT (`POST /api/voice/transcribe`)
- [x] Audio validation (magic bytes, 30s, documented formats)
- [x] React microphone capture as WAV (no browser SpeechRecognition)
- [x] Mocked STT error-path tests

## Completed — Phase 4

- [x] Rule-based intents: purchase, sale, stock check
- [x] Confirmation, cancel, pending supersede
- [x] Alias matching; reuse stock/sales services

## Completed — Phase 5 (started)

- [x] Dashboard API + shopkeeper UI (sales, stock, trends)

## Pending — later

- [ ] Gnani Timbre TTS (real API only)
- [ ] Analytics dashboard UI
- [ ] Reminders, briefing, notifications
- [ ] CSV / Excel / PDF export
- [ ] Authentication before public deploy

## Blocked

- Live Gnani transcription requires a configured `GNANI_API_KEY` and a spoken clip.

## Explicitly not done

- No Timbre TTS
- No Timbre / LLM Evon
- Parser is keyword-based, not full NLU
- No fake STT
- No profit calculation
