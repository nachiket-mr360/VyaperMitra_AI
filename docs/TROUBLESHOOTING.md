# Troubleshooting

## Backend will not start

**Cause:** Missing dependencies or wrong directory.

**Fix:** From `backend/`, run `python -m pip install -r requirements.txt` then `python app.py`. Use Python 3.12+.

## `ModuleNotFoundError: flask`

**Cause:** Packages installed in a different interpreter.

**Fix:** Use the same `python` for pip and `python app.py`. Prefer a venv.

## Frontend shows “Cannot reach the VyaparMitra server”

**Cause:** Flask is not running, or not on port 5000.

**Fix:** Start `python app.py` in `backend/`. Vite proxies `/api` to `http://127.0.0.1:5000`. Health without UI: `curl http://127.0.0.1:5000/api/health`.

## Health returns 503 / database not connected

**Cause:** SQLite path not writable, or disk error.

**Fix:** Check `DATABASE_PATH` in `backend/.env`. Default `vyaparmitra.db` is created next to `app.py`. Inspect `backend/logs/errors.log`.

## CORS errors in the browser

**Cause:** UI origin not in `CORS_ORIGINS`.

**Fix:** Default allows `http://localhost:5173` and `http://127.0.0.1:5173`. Add other origins in `.env` and restart Flask.

## Gnani / speech not working

**Cause:** Phase 1 does not call Gnani. Empty `GNANI_API_KEY` is expected.

**Fix:** Do not add fake STT/TTS. Real Prisma/Timbre comes in later phases.

## `npm run build` fails

**Cause:** TypeScript errors or missing `npm install`.

**Fix:** From `frontend/`, `npm install` then `npm run build`.

## Tests fail

**Cause:** Run from the wrong folder.

**Fix:** `cd backend` then `python -m pytest tests -q`.

## Accidentally committing `.env` or `*.db`

**Fix:** Confirm `.gitignore` lists them. If Git already tracks them: `git rm --cached backend/.env backend/vyaparmitra.db` then commit. Rotate any leaked secrets.
