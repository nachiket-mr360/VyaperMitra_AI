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

## Pending — Phase 4+ (not started)

- [ ] Intent processing / voice command mapping
- [ ] Gnani Timbre TTS (real API only)
- [ ] Analytics dashboard UI
- [ ] Reminders, briefing, notifications
- [ ] CSV / Excel / PDF export
- [ ] Authentication before public deploy

## Blocked

- Live Gnani transcription requires a configured `GNANI_API_KEY` and a spoken clip.

## Explicitly not done

- No Timbre TTS
- No sales/stock from transcripts
- No fake STT
- No profit calculation
