# Jarvis Hub Audit & Backlog
**Date:** 2026-08-24
**Scope:** Full-stack review of `jarvis-hub` from a user standpoint
**Verdict:** Functionally rich but operationally fragile. Several critical issues prevent reliable deployment.

---

## 1. Executive Summary

Jarvis Hub is a Vietnamese stock intelligence dashboard with:
- **84+ Flask routes** (app.py ~2,500 lines)
- **12 database tables** (SQLite)
- **Market data pipelines** (vnstock4 → Yahoo Finance → CafeF fallback chain)
- **News ingestion** (RSS feeds via feedparser, heuristic sentiment analysis)
- **LLM integration** (Ollama + oMLX via `core/llm_client.py`)
- **Market Intelligence pipeline** (multi-stage: crawl → analyze → synthesize)
- **Background scheduling** (APScheduler for periodic data refresh)
- **CLI interface** (`cli.py` with ~20 commands)
- **Full frontend** (Flask templates, CSS/JS charts)

The project has significant depth and ambition, but suffers from architectural debt, dead code, and configuration fragility that undermine its usability.

---

## 2. Critical Issues (Block Users Immediately)

### 🔴 C1: Zero Dependencies Installed / No Reproducible Install
**Impact:** Cannot start the application without manually installing every dependency.
- `requirements.txt` exists but no `pip install -r requirements.txt` has been run recently (venv is stale)
- `app.py` has **soft-fail imports** everywhere — if `apscheduler`, `vnstock`, or `numpy` are missing, it silently continues without those features. This means the app can "start" but be half-broken.
- No `setup.sh`, no `Makefile`, no reproducible bootstrap.

### 🔴 C2: Silent Failures Everywhere
**Impact:** The app appears to work but returns empty data with no user feedback.
- `app.py` has **162 exception handlers** — almost all are bare `except Exception: print("[X] Error: %s" % e)` and return empty JSON arrays.
- A user sees blank pages, missing charts, or "no data" with zero indication of WHY.
- **No structured error responses** (no HTTP 500 with error messages, no UI-level error banners).

### 🔴 C3: No Authentication or Access Control
**Impact:** Any user with network access can see financial data, trigger LLM calls, modify knowledge base, and delete articles.
- No login, no session management, no `SECRET_KEY` set.
- Routes like `/api/knowledge/save`, `/api/backlog`, `/api/cms/articles` (CRUD) are completely open.
- Admin panel (`/admin`) has no authentication gate.

### 🔴 C4: Hardcoded Paths & Config Fragmentation
**Impact:** The app is essentially locked to one developer's machine.
- `/Users/nghialam/jarvis-hub/knowledge/jarvis.db` hardcoded in `app.py:1535`
- `db_path` defaults to `jarvis_hub.db` in root but config.yaml specifies `~/jarvis-hub/knowledge/jarvis.db` — two different databases used in different code paths.
- Three parallel database files exist: `jarvis_hub.db`, `jarvis.db`, `watchlist.db` — with duplicate schema definitions (`db.py` and `core/db.py`).
- `config.yaml` has `db_path: "~/jarvis-hub/..."` but the `~` expansion is inconsistent across code paths.

---

## 3. High-Priority Issues (Breaking Core Features)

### 🟠 H1: vnstock4 Import Chain Is Fragile
**Impact:** Market data endpoint often returns empty data.
- `core/market_service.py` imports `vnstock4_provider` inside a try/except
- `vnstock4_provider.py` imports `from vnstock import Market` inside a try/except
- If vnstock is missing or fails, the app silently falls through to Yahoo Finance
- The Yahoo Finance fallback has its own hardcoded URLs and CSV parsing logic
- No health check exposed for the data pipeline itself

### 🟠 H2: LLM Provider Config Has Two Conflicting Systems
**Impact:** LLM calls may silently use the wrong provider or fail.
- `config.yaml` has `llm.provider: "omlx"` with nested `omlx` and `ollama` sections
- `core/llm_client.py` also checks `os.environ["LLM_PROVIDER"]` env var
- `llm_call()` function merges both configs in a complex way
- `ollama_call()` and `ollama_parse_json()` explicitly override `os.environ["LLM_PROVIDER"]` to "ollama" — a dangerous side effect
- No validation that the configured provider actually works before first use

### 🟠 H3: Massive Dead Code & Backlog of Backup Files
**Impact:** Users and developers can't tell what's "the real" app.
- **14 backup copies** of `app.py` in root directory alone (`app.py.bak*`, `app.py.rebuild*`, etc.)
- **10+ fix scripts** scattered in root (`fix_app.py`, `fix_indent.py`, `fix_streaming.py`, etc.)
- **3 separate database files** with overlapping schemas
- `db.py` in root is a **duplicate** of `core/db.py`
- `market.py.bak`, `news.py.bak` — remnants from old architecture
- Empty folders: `knowledge/agents/`, `knowledge/companies/`, `knowledge/finance/`, `kb/`, `knowledge_base/`

### 🟠 H4: No Logging — Only print() Statements
**Impact:** Impossible to diagnose issues in production.
- `app.py` uses 51 `print()` statements scattered throughout
- No Python `logging` module configured
- No log rotation, no log levels, no structured logging
- `flask-error.log` and `flask.log` exist in `logs/` but nothing writes to them automatically

### 🟠 H5: Database Schema Drift Risk
**Impact:** Data loss or corruption during migration.
- 12 tables defined in `core/db.py`'s `init_db()`:
  - `knowledge`, `activity_log`, `daily_snapshots`, `watchlist`, `market_cache`, `market_evaluations`, `trading_alerts`, `market_intelligence`, `cms_articles`, `research_items`, `backlog_tasks`, `portfolio_transactions`
- No migration system (no Alembic, no `ALTER TABLE` logic)
- Running `init_db()` multiple times uses `IF NOT EXISTS` — old data may not match new schema
- `journal_mode=WAL` and `foreign_keys=ON` are set, which is good

---

## 4. Medium-Priority Issues (Degraded UX / Reliability)

### 🟡 M1: 84 Routes in a Single File
**Impact:** Unmaintainable. New features are likely to conflict with existing routes.
- `app.py` is ~2,500 lines with routes organized only by comment blocks
- Three route naming conventions overlap: `/api/*`, `/api/v1/*`, `/api/v2/*`
- No Blueprint pattern — everything is registered on the global `app` object
- Adding a new endpoint risks naming collisions (e.g., `/api/search` vs `/api/symbols/search`)

### 🟡 M2: No API Versioning Strategy
**Impact:** Breaking changes will silently break clients.
- Routes at `/api/*` (legacy), `/api/v1/*` (current), and `/api/v2/*` (new) all coexist
- No deprecation headers, no sunset dates for old endpoints
- `/api/health` exists but `/health` also exists (duplicate)

### 🟡 M3: Scheduler Configuration Is Inflexible
**Impact:** Background jobs cannot be easily configured.
- APScheduler triggers are embedded in `app.py` source code
- `config.yaml` has `schedule.morning_briefing` and `schedule.evening_briefing` but these are not wired to any actual scheduled tasks
- No way to enable/disable individual scheduled jobs without modifying code

### 🟡 M4: News Service Has No Error Resilience
**Impact:** A single broken RSS feed can corrupt the news feed.
- `core/news_service.py` fetches from 8 RSS sources using `feedparser`
- No per-feed timeout configuration
- No circuit breaker pattern — if CafeF is down, it blocks the entire news pipeline

### 🟡 M5: Knowledge Base Is Underpopulated
**Impact:** The `AI Intelligence` and `search` features have nothing to search.
- `kb/` folder is empty
- `knowledge/` has subfolders but all except `knowledge/` (the SQLite DB) are empty
- `seed_kb.py` exists but hasn't been run recently (last run data not present)

---

## 5. Low-Priority Issues (Cleanup / Polish)

### 🟢 L1: No Testing Infrastructure
- `tests/` directory exists with 4 files but no pytest configuration
- No CI/CD pipeline
- No test coverage measurement
- `test_app.py`, `test_integration_full.py`, `test_regression_full.py` are standalone scripts, not pytest tests

### 🟢 L2: No Deployment Configuration
- No Dockerfile, docker-compose, or Dockerfile reference
- `VERCEL_DEPLOYMENT_PLAN.md` exists but Vercel is not a good fit for a Python/SQLite app
- No systemd service file for Linux deployment
- `flask run` is not production-safe (no gunicorn/uwsgi configuration)

### 🟢 L3: Documentation Fragmentation
- `docs/` has 7 markdown files but they may not reflect current code
- `JARVIS_HUB_2.0_DESIGN.md` exists in root (this is the current file open)
- No `CHANGELOG.md`
- `AGENTS.md` describes the AI agent system but is outdated (v1.8.0)

### 🟢 L4: No Observability
- No metrics collection (Prometheus, StatsD)
- No request tracing
- No health endpoint with depth (currently `/api/health` just returns 200 OK)
- No alerting when data pipelines fail

### 🟢 L5: CSS/JS Unbundled
- Dashboard static files (`dashboard/static/css/`, `dashboard/static/js/`, `dashboard/static/charts/`) are likely served directly by Flask
- No build step, no asset pipeline
- Charts may rely on external CDN links (unspecified)

---

## 6. Recommended Backlog

### Phase 1: Stabilize (Week 1-2) — **Must Have**
| # | Task | Priority | Owner |
|---|------|----------|-------|
| 1.1 | Clean up backup files and dead code (remove all `app.py.bak*`, `fix_*.py`, etc.) | 🔴 Critical | Dev |
| 1.2 | Consolidate to a single database path (`core/db.py` schema only) | 🔴 Critical | Dev |
| 1.3 | Add `SECRET_KEY` to config and enable Flask session security | 🔴 Critical | Dev |
| 1.4 | Create `pip install -r requirements.txt` bootstrap script | 🔴 Critical | Dev |
| 1.5 | Add basic authentication to `/admin`, `/api/knowledge/save`, `/api/cms/*` | 🟠 High | Dev |
| 1.6 | Add structured error responses (HTTP status codes + user-friendly messages) | 🟠 High | Dev |

### Phase 2: Architecture (Week 3-4) — **Should Have**
| # | Task | Priority | Owner |
|---|------|----------|-------|
| 2.1 | Split `app.py` into Flask Blueprints (one per feature area) | 🟠 High | Dev |
| 2.2 | Add Python `logging` configuration with file rotation | 🟠 High | Dev |
| 2.3 | Add API versioning headers (Deprecation, Sunset) | 🟡 Medium | Dev |
| 2.4 | Create `core/data_pipeline.py` as a unified data health checker | 🟠 High | Dev |
| 2.5 | Add per-feed timeout to news service | 🟡 Medium | Dev |

### Phase 3: Reliability (Week 5-6) — **Should Have**
| # | Task | Priority | Owner |
|---|------|----------|-------|
| 3.1 | Add integration tests with pytest | 🟡 Medium | Dev |
| 3.2 | Add data freshness monitoring (alert if data is > X hours old) | 🟡 Medium | Dev |
| 3.3 | Add migration system (Alembic or manual migration scripts) | 🟡 Medium | Dev |
| 3.4 | Create systemd service template for deployment | 🟡 Medium | Dev |
| 3.5 | Seed knowledge base with initial content | 🟡 Medium | Dev |

### Phase 4: Polish (Week 7+) — **Nice to Have**
| # | Task | Priority | Owner |
|---|------|----------|-------|
| 4.1 | Create Dockerfile for containerized deployment | 🟢 Low | Dev |
| 4.2 | Add Prometheus metrics endpoint | 🟢 Low | Dev |
| 4.3 | Create CHANGELOG.md | 🟢 Low | Dev |
| 4.4 | Update `AGENTS.md` to current state | 🟢 Low | Dev |
| 4.5 | Frontend asset bundling (if using build tools) | 🟢 Low | Dev |

---

## 7. File Structure Health Score

| Category | Score | Notes |
|----------|-------|-------|
| **Code Quality** | 4/10 | 162 bare excepts, 51 print() calls, no logging module |
| **Architecture** | 5/10 | 84 routes in one file, but modular core modules are well-organized |
| **Config Management** | 3/10 | Hardcoded paths, duplicate DB configs, env var + yaml conflict |
| **Security** | 2/10 | No auth, no CSRF, no secret key, open API endpoints |
| **Testing** | 2/10 | 4 standalone test files, no pytest config, no CI |
| **Documentation** | 5/10 | Good intent (AGENTS.md, docs/*) but likely stale |
| **Data Integrity** | 6/10 | WAL mode + foreign keys are good, but no migrations |
| **Deployment** | 2/10 | No Dockerfile, no systemd, no deployment guide |
| **Overall** | **3.8/10** | Functionally rich but needs significant stabilization work |

---

## 8. User-Centric Usability Assessment

### If a new user tried to use this today:
1. **Can they install it?** ❌ No — no bootstrap script, dependencies not installed
2. **Can they start it?** ❌ Not reliably — silent import failures mean partial functionality
3. **Can they see data?** ⚠️ Maybe — if vnstock4 and LLM providers are running, but error messages are invisible
4. **Can they configure it?** ⚠️ Partially — config.yaml exists but paths are hardcoded in code
5. **Can they trust the data?** ⚠️ Unknown — no data freshness indicators
6. **Can they deploy it?** ❌ No — no deployment configuration

### If the current developer continues working:
1. **Can they find "the" app.py?** ❌ No — 14 backups, 10 fix scripts
2. **Can they debug issues?** ❌ No — only print() statements, no structured logging
3. **Can they add new features?** ⚠️ Difficult — 2,500-line file, no blueprints
4. **Can they refactor safely?** ❌ No — no test suite
