# BACKLOG — Jarvis Hub 3.0 — Production-Ready [2026-09-23]

--- Daily Autoupdate 2026-09-19 ---
- System self-audit completed
- Health: {flask_8100: "unreachable", ollama: "not loaded", sqlite_db: "ok", git_changes: "dirty"}

# JARVIS HUB 2.0 → 3.0 — ARCHIVED [2026-09-19]

## Phase 1: Foundation ✅ 100%
| ID | Prio | Title | Status | Notes |
|---|---|---|---|---|
| JH3.0-P1.1 | P0 | Clean repo — remove dead code (38 files) | ✅ DONE | commit v1.8.0 |
| JH3.0-P1.2 | P0 | Database consolidation (single jarvis.db) | ✅ DONE | 10 tables, 56+ queries fixed |
| JH3.0-P1.3 | P0 | Structured logging (print→logger) | ⚠️ PARTIAL | 56 print() removed in core/api, 62 remain in app.py |
| JH3.0-P1.4 | P0 | config.yaml — all paths/env configurable | ✅ DONE | config_loader.py |
| JH3.0-P1.5 | P0 | setup.sh bootstrap script | ✅ DONE |
| JH3.0-P1.6 | P0 | FallbackEngine (30s timeout → internal analysis) | ✅ DONE |
| JH3.0-P1.7 | P0 | Telegram delivery service | ✅ DONE |
| JH3.0-P1.8 | P0 | Dashboard update service | ✅ DONE |
| JH3.0-P1.9 | P0 | Health check with fallback | ✅ DONE |
| JH3.0-P1.10 | P1 | jarvis_hub package | ✅ DONE |
| JH3.0-P1.11 | P1 | Extract remaining print statements | ⚠️ PARTIAL | 62 print() remain in app.py |
| JH3.0-P1.12 | P1 | Design docs (DESIGN.md, README.md, etc.) | ✅ DONE |
| JH3.0-P1.13 | P1 | CI/CD docker-compose build | ✅ DONE |
| JH3.0-P1.14 | P2 | Basic CI pipeline (lint + pytest) | ✅ DONE |

## Phase 2: Async Queue ✅ 100%
| ID | Prio | Title | Status | Notes |
|---|---|---|---|---|
| JH3.0-P2.1 | P0 | Async task manager (queue worker pool, 3 workers) | ✅ DONE |
| JH3.0-P2.2 | P0 | LLM Gateway with circuit breaker | ✅ DONE |
| JH3.0-P2.3 | P0 | API route migration (8 LLM endpoints) | ✅ DONE |
| JH3.0-P2.4 | P0 | Migrate /api/analyze to async | ✅ DONE |
| JH3.0-P2.5 | P0 | Migrate market-eval/generate to async | ✅ DONE |
| JH3.0-P2.6 | P0 | Migrate MI pipeline to async | ✅ DONE |
| JH3.0-P2.7 | P1 | News score endpoint | ✅ DONE |
| JH3.0-P2.8 | P1 | Precompute scheduler (APScheduler) | ✅ DONE |
| JH3.0-P2.9 | P1 | Task polling endpoints (6 in api/llm.py) | ✅ DONE |
| JH3.0-P2.10 | P1 | Frontend task polling UI | ⚠️ CLAIMED (async_tasks.js) — static/js/ dir does NOT exist |
| JH3.0-P2.11 | P2 | Frontend LLM-in-progress UI | ⚠️ CLAIMED — static/js/ dir does NOT exist |
| JH3.0-P2.12 | P2 | Frontend async result display | ⚠️ CLAIMED — static/js/ dir does NOT exist |

## Phase 3: Blueprints ✅ 100%
| ID | Prio | Title | Status |
|---|---|---|---|
| JH3.0-P3.1 | P0 | 8 API blueprint files | ✅ DONE |
| JH3.0-P3.2 | P1 | api/main.py (home, MI, market, articles, news, health) | ✅ DONE |
| JH3.0-P3.3 | P1 | api/news.py (feed, hot, real-time, categories) | ✅ DONE |
| JH3.0-P3.4 | P1 | api/intelligence.py (MI, analysis, filters) | ✅ DONE |
| JH3.0-P3.5 | P1 | api/cms.py (articles CRUD) | ✅ DONE |
| JH3.0-P3.6 | P1 | api/stocks.py (quotes, watchlists, fundamentals) | ✅ DONE |
| JH3.0-P3.7 | P1 | api/screener.py (build, run, save, export) | ✅ DONE |
| JH3.0-P3.8 | P1 | api/research.py (search, portfolio) | ✅ DONE |
| JH3.0-P3.9 | P1 | api/portfolio.py (summary, holdings) | ✅ DONE |
| JH3.0-P3.10 | P0 | AppContext singleton | ✅ DONE |
| JH3.0-P3.11 | P0 | Wire blueprints into app.py (84 routes) | ✅ DONE |
| JH3.0-P3.12 | P1 | research_service.py | ✅ DONE |
| JH3.0-P3.13 | P1 | subscription_service.py | ✅ DONE |
| JH3.0-P3.14 | P2 | Gateway interface (LLM, VNStock, vnai, vnmarket, Remote) | ✅ DONE |
| JH3.0-P3.15 | P2 | workers/ directory (analyst, portfolio) | ✅ DONE |

## Phase 4: Security ✅ 100%
| ID | Prio | Title | Status |
|---|---|---|---|
| JH3.0-P4.9 | P2 | Secrets management (.env, keyring) | ✅ DONE |
| JH3.0-P4.10 | P2 | RBAC (admin/analyst/viewer) | ✅ DONE |

## Phase 5: Testing/Deploy ✅ 100%
| ID | Prio | Title | Status |
|---|---|---|---|
| JH3.0-P5.1 | P0 | TestSuite.py (pytest, 21/21 passing) | ✅ DONE |
| JH3.0-P5.2 | P0 | test_db.py | ✅ DONE (in test_jh30_integration.py) |
| JH3.0-P5.3 | P1 | test_api.py (84 routes) | ✅ DONE |
| JH3.0-P5.4 | P1 | test_queue.py | ✅ DONE |
| JH3.0-P5.5 | P1 | test_security.py | ✅ DONE |
| JH3.0-P5.6 | P2 | test_migrations.py | ✅ DONE (10 tests) |
| JH3.0-P5.7 | P2 | test_config.py | ✅ DONE |
| JH3.0-P5.8 | P1 | Dockerfile & docker-compose.yml | ✅ DONE |
| JH3.0-P5.9 | P1 | systemd service file | ✅ DONE |
| JH3.0-P5.10 | P2 | Nginx reverse proxy config | ✅ DONE |
| JH3.0-P5.11 | P2 | SSL/HTTPS (Let's Encrypt) | ✅ DONE |
| JH3.0-P5.12 | P2 | Pre-commit hooks + CI | ✅ DONE |

---

# JARVIS HUB 3.0 — PRODUCTION READINESS BACKLOG [2026-09-23]

Real gap analysis: 46 files, 17,768 LOC, 11 blueprints, 90+ routes. 36 DB tables. BUT:
- 62 print() in app.py (claimed logging done, but app.py untouched)
- static/js/ directory does NOT exist (async_tasks.js claimed done — likely committed then lost)
- No frontend assets at all (no static/html/, static/css/, static/js/)
- Stock screener table not created, screener API not wired
- Portfolio tables exist but no transactions (data is empty)
- OHLCV fetcher cron script exists but never executed
- CMS articles table exists but no articles published

## Phase 6: Logging Fix — Replace 62 print() in app.py
| ID | Prio | File | Task | Acceptance Criteria |
|---|---|---|---|---|
| P6.1 | P1 | app.py | Replace 62 print() calls with logging module | Zero print() left in app.py; all use app.logger or logging.getLogger('jh') |
| P6.2 | P0 | core/logging_config.py | Verify config works — console + file handlers | Import logging_config in app.py; log to file/data/jarvis-hub.log; console level = INFO, file level = DEBUG |
| P6.3 | P1 | api/screener.py | Wire screener API to app.py routes | /api/v1/screener/* endpoints respond; get_signals returns[]; add_alert creates entry |
| P6.4 | P1 | core/market_overview.py | Audit print() statements | grep print() on all core/*.py and api/*.py; migrate remaining |
| P6.5 | P0 | tests/ | Add logging unit test | test_logging_config.py: verify log output to file, verify log levels |

## Phase 7: Frontend — Build from Scratch
| ID | Prio | Path | Task | Acceptance Criteria |
|---|---|---|---|---|
| P7.1 | P0 | static/{html,js,css}/ | Create static directory structure | ls static/html/, static/js/, static/css/ all exist |
| P7.2 | P1 | static/js/async_tasks.js | Async polling UI (463 lines spec) | Task status badges update every 5s; loading spinner on pending; error state on failed |
| P7.3 | P1 | static/js/dashboard.js | Dashboard async polling | Market overview auto-refreshes; error handling for 500; rate-limited polling |
| P7.4 | P2 | static/html/ | Dashboard HTML templates | templates/index.html renders; hub2.html renders; all API calls use /api/v1/* |
| P7.5 | P1 | tests/ | Frontend integration tests | GET /, GET /hub2, GET /api/v1/health all return 200; JS loading states verified via Selenium or pytest-playwright |

## Phase 8: Stock Screener — Functional
| ID | Prio | File | Task | Acceptance Criteria |
|---|---|---|---|---|
| P8.1 | P1 | core/db_hub2_schema.py | Add stock_screener table | CREATE TABLE stock_screener (id INTEGER PRIMARY KEY, symbol TEXT, signal TEXT, strength TEXT, created_at TIMESTAMP, updated_at TIMESTAMP); migrate on startup |
| P8.2 | P1 | api/screener.py | Wire up API routes to routes | GET /screener/signal returns[]; POST /screener/alert creates entry; GET /screener/watchlist returns[] |
| P8.3 | P2 | static/html/ | Screener UI page | Table of signals with filter dropdown; add/remove watchlist items; save/load custom filters |
| P8.4 | P1 | tests/ | Screener tests | test_screener.py: DB migration runs; API endpoints return correct data; test signal creation flow |

## Phase 9: OHLCV Data Pipeline
| ID | Prio | File | Task | Acceptance Criteria |
|---|---|---|---|---|
| P9.1 | P1 | cron/vn-ohlcv-fetch.sh | Make cron script executable + fix paths | chmod +x; PYTHONPATH set correctly; runs without error |
| P9.2 | P1 | core/ | Run fetcher against VN stocks | Fetch VIC, VCI, HDC, SSI OHLCV for last 30 days; aggregated_data has 120+ new rows (4 tickers × 30 days) |
| P9.3 | P1 | core/ | Add to crontab | `crontab -l` includes daily 09:00 fetch; no duplicate entries |
| P9.4 | P2 | tests/ | OHLCV data validation tests | test_ohlcv_fetch.py: verify no NaN prices; verify OHLCV schema matches spec; verify timestamps are sequential |

## Phase 10: Portfolio Tracking
| ID | Prio | File | Task | Acceptance Criteria |
|---|---|---|---|---|
| P10.1 | P1 | core/db_hub2_schema.py | Portfolio transactions table | CREATE TABLE portfolio_transactions (id, symbol, type TEXT, quantity REAL, price REAL, total REAL, date TIMESTAMP, notes TEXT); existing table has 0 rows |
| P10.2 | P1 | api/portfolio.py | Portfolio API endpoints | POST /portfolio/transaction creates entry; GET /portfolio/summary returns balance; GET /portfolio/history returns transactions |
| P10.3 | P2 | static/html/ | Portfolio UI | Transaction entry form (symbol, type [BUY/SELL], qty, price); summary card showing total value; transaction history table |
| P10.4 | P1 | tests/ | Portfolio CRUD tests | test_portfolio.py: create transaction → verify count; calculate totals; verify balance computation |

## Phase 11: CMS Content Publishing
| ID | Prio | File | Task | Acceptance Criteria |
|---|---|---|---|---|
| P11.1 | P1 | core/db_hub2_schema.py | Verify CMS articles table | articles table exists with all required columns (title, slug, content, summary, tags, category, status, created_at, published_at) |
| P11.2 | P2 | static/html/ | CMS article editor | Markdown editor UI; draft/publish workflow; tag management; preview mode |
| P11.3 | P1 | tests/ | CMS tests | test_cms.py: create → publish → archive cycle; search by tag/category; verify markdown rendering |

## Phase 12: End-to-End Integration
| ID | Prio | Task | Acceptance Criteria |
|---|---|---|
| P12.1 | P0 | Login → Data → Insights flow | Login as admin → trigger MI generation → verify MI in DB → verify Telegram delivery → verify precompute ran |
| P12.2 | P1 | API stress test | 50 concurrent requests to /api/v1/health → all return 200; no crashes; circuit breaker activates if needed |
| P12.3 | P1 | DB backup/restore test | Backup jarvis.db → drop tables → restore → verify 36 tables + data integrity |

## Phase 13: Documentation
| ID | Prio | Task | Acceptance Criteria |
|---|---|---|---|
| P13.1 | P0 | README.md update | Setup steps, architecture diagram, deploy guide, API reference |
| P13.2 | P1 | API docs | OpenAPI/Swagger spec generated; all 90+ routes documented |
| P13.3 | P1 | User guide | How to use each feature: screener, portfolio, CMS, news, MI |
| P13.4 | P2 | CHANGES.md | Changelog from v1.8 → v3.0 |

## Phase 14: Release
| ID | Prio | Task | Acceptance Criteria |
|---|---|---|---|
| P14.1 | P0 | Version bump to v3.0.0 | __version__ = '3.0.0' in setup.py or app.py |
| P14.2 | P0 | Docker Compose production | docker-compose up works end-to-end (app + DB) |
| P14.3 | P1 | GitHub release page | Tag v3.0.0, screenshots, feature list |
| P14.4 | P1 | Deployment on production | Deploy to Mac Mini, verify all endpoints, cron jobs running |

---

# Summary

| Metric | Value |
|---|---|
| Total Phase 1-5 tasks | 84 (claimed done) |
| Phase 6-14 (new backlog) | 40 tasks |
| Current date | 2026-09-23 |
| Priority focus | P6.1-P7.5 (logging + frontend — block delivery) |
| Data readiness | OHLCV data NOT populated; portfolio empty; screener unused |
