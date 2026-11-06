# Bugs

No open defects from Phase 3 mocked tests.

## Known limitations (not bugs)

- Browser `ScriptProcessorNode` is deprecated; it is used only to capture PCM/WAV.
- Mixed-language / auto-detect accuracy is whatever Prisma returns; not claimed.
- Live Gnani connectivity is not proven by mocked tests.
- No authentication on `/api/voice/transcribe`.
- Recordings are not persisted (by design).
