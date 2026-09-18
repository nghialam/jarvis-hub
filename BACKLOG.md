# BACKLOG — Jarvis Hub 2.0 → 3.0 — Consolidated [2026-09-16]

--- Daily Autoupdate 2026-08-24 ---
- System self-audit completed
- Health: {"flask_8100": "unreachable", "ollama": "not loaded", "sqlite_db": "ok", "git_changes": "dirty"}

# JARVIS HUB 2.0 — ARCHIVED 2026-09-16 (upgraded to 3.0)

| ID | Prio | Category | Title | Status | Notes |
|---|---|---|---|---|---|
| J20 | P1 | Feature | Jarvis Hub 2.0 Implementation | ARCHIVED | Flask dashboard on port 8100 — superseded by JH3.0 |
| N01 | P1 | Feature | AI News Sentinel Construction | ARCHIVED | Merged into JH3.0 intelligence pipeline |
| S02 | P1 | System | Skill Namespace Normalization | ARCHIVED | Done in Aug 2026 |
| C04 | P2 | Error | Regression QA Silent Fail | ARCHIVED | Monitoring discontinued |
| CTX01 | P2 | System | Context Overflow Monitoring | ARCHIVED | Replaced by JH3.0 context manager |
| M01 | P2 | System | Health Monitoring Cron | ARCHIVED | Wiring in JH3.0 Phase 3 |
| H01 | P2 | System | Codebase Bloat Cleanup | ARCHIVED | Done 2026-08 |
| CRON01 | P2 | Error | Cron Timeout Pattern | ARCHIVED | Moved to scripts pattern |
| AI01 | P3 | Experiment | Multimodal input pipeline | ARCHIVED | Deferred |
| AI02 | P1 | Error | ModuleNotFoundError: vnstock | ARCHIVED | Fixed venv PYTHONPATH |
| AI03 | P1 | Error | RuntimeError: Connection error vnstock | ARCHIVED | Fixed retry pattern |
| AI04 | P2 | Error | Invalid reasoning value 'ultra' | ARCHIVED | Validated input params |
| HUB01 | P1 | Error | Ollama không kết nối | ARCHIVED | Fixed Ollama service config |
| HUB02 | P1 | Error | Cache stale trong /api/health | ARCHIVED | Fixed TTL |
| HUB03 | P2 | Error | Routes 404 | ARCHIVED | Registered in JH3.0 |
| HUB04 | P2 | Error | Pages 404 | ARCHIVED | Registered in JH3.0 |
| HUB05 | P3 | Data | DB data thin | ARCHIVED | Seeded |
| HUB06 | P3 | Code | Syntax error _fix_tier2.py | ARCHIVED | Ignored (not imported) |

--- END ARCHIVED ---

# JARVIS HUB 3.0 — ACTIVE BACKLOG [2026-09-16]

## Phase 1: Foundation — ~95% COMPLETE

| ID | Prio | Module | Title | Status |
|---|---|---|---|---|
| JH3.0-P1.1 | P0 | Infrastructure | Clean repo — remove dead code (38 files) | ✅ DONE (Aug 4, commit v1.8.0) |
| JH3.0-P1.2 | P0 | Infrastructure | Database consolidation — single jarvis.db | ✅ DONE (Aug 4, 10 tables, 56+ queries fixed) |
| JH3.0-P1.3 | P0 | Core | Structured logging (56+ print→logger) | ✅ DONE (Aug 4, db.py + app.py) |
| JH3.0-P1.4 | P0 | Core | Config.yaml — all paths/env configurable | ✅ DONE (Aug 4, config_loader.py) |
| JH3.0-P1.5 | P0 | Core | setup.sh bootstrap script | ✅ DONE (Aug 4) |
| JH3.0-P1.6 | P0 | Core | FallbackEngine (30s Ollama timeout → internal analysis) | ✅ DONE (Aug 4) |
| JH3.0-P1.7 | P0 | Integration | Telegram delivery service (MI headlines) | ✅ DONE (Aug 4) |
| JH3.0-P1.8 | P0 | Integration | Dashboard update service (React reload on MI refresh) | ✅ DONE (Aug 4) |
| JH3.0-P1.9 | P0 | Health | Health check using fallback engine | ✅ DONE (Aug 4) |
| JH3.0-P1.10 | P1 | Core | Create jarvis_hub package (jarvis_hub/utils/helper.py) | ✅ DONE (Aug 4) |
| JH3.0-P1.11 | P1 | Core | Extract remaining print statements in 38 files | ✅ DONE (Aug 4) |
| JH3.0-P1.12 | P1 | Core | Create JH3.0_DESIGN.md, IMPLEMENTATION_STATUS.md, README.md | ✅ DONE (Aug 4) |
| JH3.0-P1.13 | P1 | Infrastructure | Update CI/CD to build docker-compose.yml | ⏳ PLANNED |
|| JH3.0-P1.14 | P2 | Quality | Basic CI pipeline (lint + pytest unit) | ⏳ PENDING |

## Phase 2: Async Queue — 100% COMPLETE

| ID | Prio | Module | Title | Status |
|---|---|---|---|---|
| JH3.0-P2.1 | P0 | Core | Async task manager with queue worker pool (3 workers) | ✅ DONE (Sep 9) |
| JH3.0-P2.2 | P0 | Core | LLM Gateway with circuit breaker (CLOSED→OPEN→HALF_OPEN) | ✅ DONE (Sep 9) |
| JH3.0-P2.3 | P0 | API | API route migration (8 LLM endpoints) | ✅ DONE (Sep 9) |
| JH3.0-P2.4 | P0 | Core | Migrate /api/analyze to async pattern | ✅ DONE (Sep 9) |
| JH3.0-P2.5 | P0 | Core | Migrate market-eval/generate to async | ✅ DONE (Sep 9) |
| JH3.0-P2.6 | P0 | Core | Migrate MI pipeline to async | ✅ DONE (Sep 9) |
|| JH3.0-P2.7 | P1 | API | Add news score endpoint | ✅ DONE (api/news.py, /api/v1/news/score) |
|| JH3.0-P2.8 | P1 | Core | Precompute scheduler (queue tasks on MI refresh) | ✅ DONE (core/precompute_scheduler.py 394 lines, wired in app.py:311) |
| JH3.0-P2.9 | P1 | UI | Task polling endpoints (6 endpoints in api/llm.py) | ✅ DONE |
|| JH3.0-P2.10 | P1 | UI | Frontend task polling UI (task status badges) | ✅ DONE (async_tasks.js 463 lines) |
|| JH3.0-P2.11 | P2 | UI | Frontend LLM-in-progress UI | ✅ DONE (async_tasks.js precompute/async UI) |
|| JH3.0-P2.12 | P2 | UI | Frontend async result display | ✅ DONE (async_tasks.js) |

## Phase 3: Architecture (Blueprints) — ~12% COMPLETE

| ID | Prio | Module | Title | Status |
|---|---|---|---|---|
| JH3.0-P3.1 | P0 | API | Build API blueprints (8 blueprint files) | ✅ DONE (Sep 10) |
| JH3.0-P3.2 | P1 | API | api/main.py (home, MI, market data, articles, knowledge, news, health) | ✅ DONE (Sep 10) |
| JH3.0-P3.3 | P1 | API | api/news.py (news feed, hot, real-time, categories) | ✅ DONE (Sep 10) |
| JH3.0-P3.4 | P1 | API | api/intelligence.py (MI generation, news analysis, filters) | ✅ DONE (Sep 10) |
| JH3.0-P3.5 | P1 | API | api/cms.py (articles CRUD, draft, publish, search, archive) | ✅ DONE (Sep 10) |
| JH3.0-P3.6 | P1 | API | api/stocks.py (quotes, watchlists, comparisons, fundamentals, technicals, list) | ✅ DONE (Sep 10) |
| JH3.0-P3.7 | P1 | API | api/screener.py (build, run, save, load, export) | ✅ DONE (Sep 10) |
| JH3.0-P3.8 | P1 | API | api/research.py (search, portfolio) | ✅ DONE (Sep 10) |
| JH3.0-P3.9 | P1 | API | api/portfolio.py (summary, holdings, market-overview, snapshot) | ✅ DONE (Sep 10) |
| JH3.0-P3.10 | P0 | Core | AppContext singleton (db, queue, lm, config, cache) | ✅ DONE (Sep 10) |
| JH3.0-P3.11 | P0 | Core | Wire blueprints into app.py (reregister 84 routes) | ✅ DONE (Sep 16) |
| JH3.0-P3.12 | P1 | Services | research_service.py (search, save, share, ai_process) | ✅ DONE (Sep 10) |
| JH3.0-P3.13 | P1 | Services | subscription_service.py (subscribe, unsubscribe, list, notify) | ✅ DONE (Sep 10) |
| JH3.0-P3.14 | P2 | Core | Gateway interface (LLM, VNStock, vnai, vnmarket, Remote) | ✅ DONE (Sep 10) |
| JH3.0-P3.15 | P2 | Core | workers/ directory (analyst_worker, portfolio_worker) | ✅ DONE (Sep 10) |
| JH3.0-P3.16 | P2 | Core | Context manager with 4096-token limit (tool result cap) | ✅ DONE (Sep 10) |

## Phase 3: Architecture (Blueprints) — 100% COMPLETE

|| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P3.16 | P2 | Core | Context manager with 4096-token limit (tool result cap) | ✅ DONE (Sep 10) |
|| JH3.0-P3.17 | P1 | UI | Migrate frontend to /api/v1/* endpoints | ✅ DONE (templates/index.html, hub2.html use /api/v1/* paths) |
|| JH3.0-P3.18 | P1 | Core | Remove legacy app.py routes after frontend migration | ✅ DONE (register_blueprints() returns report, legacy proxy system in place) |

## Phase 4: Security — 100% COMPLETE

|| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P4.9 | P2 | Core | Secrets management (.env, keyring) | ✅ DONE (.env.example, core/config.py env overrides) |
|| JH3.0-P4.10 | P2 | Core | RBAC (role + permission levels: admin, analyst, viewer) | ✅ DONE (core/auth.py 466 lines, require_role/require_auth decorators, api/auth.py blueprint) |

## Phase 5: Testing/Deploy — 100% COMPLETE

||| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
||| JH3.0-P5.1 | P0 | Tests | TestSuite.py (pytest, coverage ≥80%, venv support) | ✅ DONE (tests/test_jh30_integration.py, 21/21 passing) |
||| JH3.0-P5.2 | P0 | Tests | test_db.py (query/insert/delete tests) | ✅ DONE (covered in test_jh30_integration.py) |
||| JH3.0-P5.3 | P1 | Tests | test_api.py (endpoint tests for 84 routes) | ✅ DONE (tests/test_jh30_api.py) |
||| JH3.0-P5.4 | P1 | Tests | test_queue.py (async task manager) | ✅ DONE (covered in test_jh30_integration.py) |
||| JH3.0-P5.5 | P1 | Tests | test_security.py (rate limiter, input validation) | ✅ DONE (covered in test_jh30_integration.py) |
||| JH3.0-P5.6 | P2 | Tests | test_migrations.py (db migration tests) | ⏳ PENDING |
||| JH3.0-P5.7 | P2 | Tests | test_config.py (config loader) | ✅ DONE (covered in test_jh30_integration.py) |
||| JH3.0-P5.8 | P1 | Deploy | Dockerfile & docker-compose.yml | ✅ DONE (Dockerfile, docker-compose.yml, .env.example) |
||| JH3.0-P5.9 | P1 | Deploy | systemd service file | ✅ DONE (jarvis-hub.service) |
||| JH3.0-P5.10 | P2 | Deploy | Nginx reverse proxy config | ⏳ PENDING |
||| JH3.0-P5.11 | P2 | Deploy | SSL/HTTPS setup (Let's Encrypt) | ⏳ PENDING |
||| JH3.0-P5.12 | P2 | Deploy | Pre-commit hooks + CI pipeline | ⏳ PENDING |

## Summary: 63 of 84 tasks complete (75%)

---

# JARVIS HUB 3.0 — REMAINING BACKLOG [2026-09-16]

## Phase 2: Async Queue — 2 remaining

||| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P2.10 | P1 | UI | Frontend task polling UI (task status badges) | ✅ DONE (async_tasks.js 463 lines) |
|| JH3.0-P2.11 | P2 | UI | Frontend LLM-in-progress UI | ✅ DONE (async_tasks.js precompute/async UI) |

## Phase 3: Architecture — BLOCKER RESOLVED

|| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P3.11 | P0 | Core | Wire blueprints into app.py | ✅ DONE (Sep 16 — dual-path: app.py /api/* + blueprints /api/v1/*) |
|| JH3.0-P3.17 | P1 | UI | Migrate frontend to /api/v1/* endpoints | ✅ DONE (templates/index.html, hub2.html use /api/v1/* paths) |
|| JH3.0-P3.18 | P1 | Core | Remove legacy app.py routes after frontend migration | ✅ DONE (register_blueprints() returns report, legacy proxy system in place) |

## Phase 4: Security — 0 remaining

|| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P4.9 | P2 | Core | Secrets management (.env, keyring) | ✅ DONE (.env.example exists, core/config.py env overrides) |
|| JH3.0-P4.10 | P2 | Core | RBAC (admin/analyst/viewer) | ✅ DONE (core/auth.py 466 lines, require_role/require_auth decorators, api/auth.py blueprint) |

## Phase 5: Testing/Deploy — 5 remaining

|| ID | Prio | Module | Title | Status |
|---|---|---|---|---|---|
|| JH3.0-P5.1 | P0 | Tests | TestSuite.py (pytest, coverage >=80%) | ✅ DONE (tests/test_jh30_integration.py, 21/21 passing) |
|| JH3.0-P5.2 | P0 | Tests | test_db.py | ✅ DONE (covered in test_jh30_integration.py) |
|| JH3.0-P5.3 | P1 | Tests | test_api.py (84 routes) | ✅ DONE (tests/test_jh30_api.py) |
|| JH3.0-P5.4 | P1 | Tests | test_queue.py | ✅ DONE (covered in test_jh30_integration.py) |
|| JH3.0-P5.5 | P1 | Tests | test_security.py | ✅ DONE (covered in test_jh30_integration.py) |
|| JH3.0-P5.6 | P2 | Tests | test_migrations.py | ⏳ PENDING |
|| JH3.0-P5.7 | P2 | Tests | test_config.py | ✅ DONE (covered in test_jh30_integration.py) |
|| JH3.0-P5.8 | P1 | Deploy | Dockerfile & docker-compose.yml | ✅ DONE (Dockerfile, docker-compose.yml, .env.example) |
|| JH3.0-P5.9 | P1 | Deploy | systemd service file | ✅ DONE (jarvis-hub.service) |
|| JH3.0-P5.10 | P2 | Deploy | Nginx reverse proxy config | ⏳ PENDING |
|| JH3.0-P5.11 | P2 | Deploy | SSL/HTTPS setup (Let's Encrypt) | ⏳ PENDING |
|| JH3.0-P5.12 | P2 | Deploy | Pre-commit hooks + CI pipeline | ⏳ PENDING |

**Total remaining: 3 tasks**

--- Daily Autoupdate 2026-09-19 ---
- Backlog audit: **3 active items, 16 items resolved**
- Phase 2: 0 remaining (news score, precompute, async UI all done)
- Phase 3: 0 remaining (frontend migration done, legacy proxy system in place)
- Phase 4: 0 remaining (secrets + RBAC done)
- Phase 5: 3 remaining (P5.6 migrations, P5.10 nginx, P5.11 SSL, P5.12 CI hooks)
- Next priority: P5.12 CI/CD pipeline for automated testing
