# JH3.0 — Production Readiness Plan

**Date:** 2026-10-13
**Goal:** Make JH3.0 usable for daily operations

## Assumptions & Open Questions

1. **Blueprint wiring issue**: Blueprints register correctly when imported directly but not via `import app`. Likely a missing dependency or import error swallowed by try/except. Need to fix — this is **blocker** since all `/api/v1/*` routes fail without it.
2. **No frontend**: The old templates/ static/ directories were removed during the v3 rewrite. New HTML pages + JS must be regenerated. **This is a blocker** — no UI = not usable.
3. **Print statements (357 total)**: These don't block usability but reduce logging quality. Will upgrade to `logging` module systematically.
4. **Missing packages**: python-dotenv, jproperties need installing in venv.

## Phase 1: Backend — Wiring & Startup [P0]

### P1.1 Fix blueprint registration in app.py
- Root cause: `import app` from system Python fails silently due to try/except wrapping blueprints
- Fix: Add error reporting, ensure dependencies are available before reaching `register_blueprints()` call

### P1.2 Install missing venv dependencies
- `pip install python-dotenv jproperties flask-cors pydantic` in venv

### P1.3 Verify app startup & all 75+ routes work
- Start server, curl `/api/v1/health`, `/api/v1/stocks/analyze?symbol=VIC`

## Phase 2: Frontend — Regenerate UI [P0]

### P2.1 Create `templates/` directory with minimal pages
- `index.html` — dashboard overview
- `hub2.html` — main hub with sidebar navigation (8 tabs)
- Templates for: market, news, company, research, screener, portfolio, market-intel

### P2.2 Create `static/css/` with base styles
- Dark theme CSS from v2 preserved
- Layout: sidebar + main content

### P2.3 Create `static/js/` with core JS
- `hub.js` — navigation, page switching, API calls to `/api/v1/*`
- Async task polling (polls LLM tasks every 5s)
- Market data auto-refresh

## Phase 3: Logging Cleanup [P1]

### P3.1 Replace print() in app.py (71 instances) → logging module
### P3.2 Replace print() in core/ & api/ (286 instances) → logging module  
### P3.3 Verify log file writes to `data/jarvis-hub.log`

## Phase 4: Data Validation [P1]

### P4.1 Verify OHLCV data exists for all tickers (already has 1224 rows)
### P4.2 Test screener, portfolio, CMS APIs return useful data
### P4.3 Run integration test suite

## Phase 5: Polish & Release [P2]

### P5.1 Add health check endpoint verification
### P5.2 Docker compose file update (if needed)
### P5.3 Update BACKLOG.md → mark complete
### P5.4 Version bump to 3.0.0

## Execution Order

```
Phase 1 → Phase 2 → Phase 4 → Phase 3 → Phase 5
```

Phase 1 & 2 are the critical path — without a working app (P1) and frontend UI (P2), nothing else matters.
