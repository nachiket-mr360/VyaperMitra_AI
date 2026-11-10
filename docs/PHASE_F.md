# Phase F — Conversational BI and interactive charts

Stopped after F. No Phase G, no `.env` / shop DB, no git commit.

## What shipped

- Flask `voice_query` / `compare_periods` / `sales_trend` remain the only source of figures.
- Parse responses may include additive `visualization` (line / bar / hbar / area / comparison).
- Gemini still interprets only; it never supplies totals, chart HTML, or SQLite.
- Voice overlay scrolls transcript + Recharts; mic orb stays at the bottom.
- Optional “Open in dashboard” deep-link (insights / sales / inventory / dashboard) with date range.
- Follow-ups reuse Phase D session (`last_analytics`). Profit / cash remain unsupported.

## Verification

- `backend`: `python -m pytest -q` → **163 passed**
- `frontend`: `npm run build`

## Not done

- Live Gnani credits
- Commit / production shop database
- Phase G
