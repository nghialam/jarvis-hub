# Jarvis Hub 2.0 — Execution Plan [2026-07-25]

**Status:** Active | **Author:** Auto-generated during backlog audit session
**Working Directory:** /Users/nghialam/jarvis-hub/

---

## System Baseline (at time of plan)

- app.py: 2124 lines, ~60 API routes (v1 + v2)
- core/db.py: 862 lines, 11 tables in SQLite
- dashboard/templates/hub2.html: 228 lines (backend >> frontend gap)
- CRM templates untracked: cms.html, article_page.html (need polish)

---

## Archived Items (no longer relevant)

| ID | Description | Reason Archived |
|----|-------------|-----------------|
| DBR01 | Daily Brief Data — 8 Silent Failures | Script `daily-brief-data.py` v17 fixed. Cron working. |
| S01 | Telegram Network Diagnosis | User infrastructure (VPN/proxy), not a code task |
| M03 | Telegram Proxy/VPN Setup | Duplicate of S01, same reason |

---

## Execution Plan — 5 Phases (sequential)

### PHASE A: Quick Wins (~30 min) — ✅ DONE 2026-07-25

- [x] **Archiving:** Remove DBR01, S01, M03 from BACKLOG.md active list (archive to HISTORY section)
- [x] **IMP01 — Stub files:** Create `~/.hermes/.learnings/ERRORS.md` and `SESSION_SUMMARY.md` so nightly jarvis-auto-improve job (e5ba0c0ca306) stops failing
- [x] **H01 partial — Delete orphan scripts:** Removed `_fix_db.py`, `_fix_indent.py`, `_fix_indent2.py`, `_fix_indent3.py`, `_insert_cms_routes.py`, `_insert_cms_routes2.py` from repo root

### PHASE B: vnstock4 Migration (~1 hr) — ✅ DONE 2026-07-25

- [x] **N02 — vnai upgrade:** Current `vnai v2.4.9` → upgraded to `v2.5.3`. Also `vnstock` upgraded from `v4.0.4` → `v4.0.5`
- [x] **Audit ALL `.history()` calls** across codebase — all use date-range params (`start=`/`end=`). No `limit=` usage found anywhere ✅
- [x] **Fix hardcoded dates:** Replaced stale dates in 3 core files with dynamic `(datetime.now() - timedelta(days=N))`:
  - `core/market.py:535` — was `"2026-04-01"`, now 120-day lookback
  - `core/market_overview.py:191` — was `"2026-04-01"`→`"2026-07-01"`, now 120-day lookback
  - `core/vn_market.py:38,102` — was `"2026-05-01"`→`"2026-07-01"`, now 90-day lookback
- [x] **Fix dependency conflict:** `huggingface-hub` upgraded from `1.2.3` → `1.24.0` to satisfy transformers requirement
- [x] **Integration test passed:** VIC returned ~213,100 VND on 2026-07-25 (correct)

### PHASE C: Hub2 Dashboard — Core UI (~2-3 hrs)

**Goal:** Close the gap between 228-line `hub2.html` and 60 backend API routes.

- [ ] **L2.1 — Chart integration:** Wire up lightweight-charts or chart.js for VNIndex + individual stock price charts (daily/weekly/monthly timeframes). Use data from `/api/v1/overview/chart`
- [ ] **L2.2 — Real-time data panels:** Add dashboard sections that consume:
  - Sector heatmap via `/api/v1/market/heatmap`
  - FII flow gauge via `/api/v1/overview` and news endpoints
  - Daily snapshot cards via `/api/snapshots` + `/api/v1/overview/indices`
- [ ] **L2.3 — CMS frontend polish:** `cms.html` and `article_page.html` exist but need: responsive layout, better rich-text editor for inline edit modal, CSS polish, category/tag filtering
- [ ] **Test:** Load all 60 API routes via dashboard UI, verify no broken links or 404s

### PHASE D: Hub2 Dashboard — Advanced Features (~2 hrs)

- [ ] **L2.4 — Portfolio P&L calculator + watchlist real-time binding:**
  - Current: `/api/v1/watchlist/portfolio/*` routes exist but UI doesn't connect
  - Build portfolio tab: shows holdings, buy/sell simulation, profit/loss calc from watchlist data
  - Real-time price updates via polling or SSE if feasible
- [ ] **L2.5 — Dark mode toggle + mobile responsive CSS:**
  - Add dark/light theme toggle (CSS variables)
  - Full mobile breakpoint grid (320px–1440px) for hub2.html and cms.html

### PHASE E: System Polish & Experiments (ongoing / low-priority)

- [ ] **S02 — Skill Namespace Normalization:** One-pass regex find/replace to strip `openclaw:*` and `finance:*` prefixes from skill references, converting to bare strings
- [ ] **H01 final** — Complete bloat cleanup: remove old files in `knowledge/` and `scripts/` dirs that are superseded
- [ ] **N01 — AI News Sentinel:** Re-evaluate feasibility. Bridge daily cron output (`3e4837759e26`) into dashboard UI under a "News/Sentiment" tab if backend endpoints support it
- [ ] **C04 — Regression QA Silent Fail:** Keep monitoring weekly, no action unless new failures occur
- [ ] **AI01 — Multimodal Vision Pipeline:** Parked. Revisit when core layers stable

---

## Cron Job Inventory (current state)

| ID | Name | Schedule | Model | Notes |
|----|------|----------|-------|-------|
| f5c44334ba87 | jarvis-backlog-sync | 22:00 daily | qwen3.6:35b | ok |
| e5ba0c0ca306 | jarvis-auto-improve | 01:00 daily | qwen3.6:35b | **FAILS — missing ERRORS.md & SESSION_SUMMARY.md (fix in Phase A)** |
| d6963ef570f3 | jarvis-memory-daily | 23:00 daily | qwen3.6:35b | ok |
| 12c502b4d2dc | memory-regression-test | 02:00 daily | qwen3.6:35b | telegram delivery timeout (minor) |
| 69d0e6570d3d | Jarvis Daily Autoupdate Pipeline | 08:45 weekdays | **qwen3.6:27b** | fixed model (was 35B timeout) |
| 3e4837759e26 | Daily News Aggregation | 06:00 weekdays | **qwen3.6:27b** | fixed model + expanded script |
| d7ab2f6a92ab | Daily Market Information | 16:00 weekdays | **qwen3.6:27b** | fixed model + expanded prompt to cover all 10 tickers |
| f156fde1bfb5 | AI Daily Intelligence Briefing | 08:00 weekdays | **qwen3.6:27b** | fixed model |
| 2cbb78fe8014 | Daily Stock Recommendations | 16:00 weekdays | qwen3.6:35b | paused, shares daily-brief-data.sh |

**Model migration note:** Jobs with 35B that timeout need to switch to 27B (already done for autoupdate, news aggregation, market info, AI briefing). Remaining jobs on 35B are low-frequency enough to not timeout.

---

## Decision Log

- **2026-07-25:** Full backlog re-sort. J20 promoted to P0 (dashboard UI is biggest gap). 3 items archived as stale. vnstock4 upgrade elevated to Phase B due to `vnai 2.5.x` bugs blocking data pipeline reliability. Cron jobs migrated from 35B → 27B model to fix 600s timeout errors.
