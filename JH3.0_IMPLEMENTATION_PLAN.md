# Jarvis Hub 3.0 — Implementation Plan
**Version:** 3.0.0-draft  
**Date:** 2026-08-24  
**Status:** In Progress — Phase 3 Partially Complete  
**Last Updated:** 2026-09-18  
**Estimated Duration:** 11-16 weeks (5 phases, ~28-40 story points)

---

## 1. Overview

This plan details the step-by-step implementation of Jarvis Hub 3.0, transforming the current v2.0 monolith into an async-first, resilient intelligence engine. Each phase is self-contained and deliverable.

### 1.1 Key Principles

1. **Non-destructive migration** — v2.0 continues to work during transition
2. **Feature flags** — New features enabled progressively via config
3. **Backward compatibility** — All v2.0 API routes continue to work
4. **Database forward-compatible** — v3.0 schema is additive only
5. **Progressive enhancement** — System degrades gracefully at every level

### 1.2 Technical Debt Inventory

| Item | Current State | Target State | Effort |
|------|--------------|--------------|--------|
| `app.py` | 2,500 lines, 84 routes | Split into blueprints | 2 weeks |
| `db.py` / `db.py` duplicate | 2 files, overlapping schema | Single `core/db.py` | 1 day |
| 14 backup files | `app.py.bak*`, `fix_*.py` | Clean repository | 1 day |
| 3 database files | `jarvis_hub.db`, `jarvis.db`, `watchlist.db` | Single `jarvis.db` | 1 day |
| No logging | 51 `print()` statements | Structured logging | 1 day |
| No auth | Open endpoints | RBAC middleware | 3 days |
| No tests | 4 standalone scripts | Pytest suite | 2 weeks |
| No deployment config | Manual setup | Docker + systemd | 1 week |
| Heuristic fallbacks | Exist but not wired | Wired by default | 1 week |
| Async LLM calls | Synchronous, blocking | Async queue | 2 weeks |

### 1.3 Architecture Patterns (Borrowed from ever-gauzy)

Two patterns from ever-gauzy are feasible to adopt for JH3.0. Both are **lightweight adaptations** — no heavy infrastructure.

#### Pattern 1: Event-Driven Data Pipeline

**Source:** ever-gauzy uses Jitsu event collection to log every data pipeline tick.

**JH3.0 adaptation:**
- **Event schema** (SQLite table `events`):
  - `id`, `name` (event type), `source` (cron job / API / manual), `status` (success/error/timeout),
    `payload` (JSON blob), `start_time`, `end_time`, `duration_ms`, `error_trace`, `created_at`
- **Event bus** (`core/events.py`): Async queue → background worker → SQLite insert.
  Same pattern as existing `core/async_queue.py` but with event log, not LLM tasks.
- **Pipeline events**: market snapshot, stock data pull, analysis tick, summary generation — each emits an `EVENT_TYPE` event.
- **Event viewer**: simple /admin/events page with filter (source, status, date range), sort, and duration chart.

**Why:** Full audit trail of data flow. See which cron failed, how long, what error. Critical for reliability.

**Not needed:** No Redis, no RabbitMQ, no Kafka. SQLite + async queue is sufficient for solo dev + <100 events/day.

#### Pattern 2: Semantic Layer for Analytics

**Source:** ever-gauzy uses Cube.js semantic layer for unified analytics queries.

**JH3.0 adaptation:**
- **Semantic view** (`core/semantic.py`): Python layer that:
  1. Takes raw data from multiple sources (vnstock, vnai, web APIs)
  2. Normalizes into unified schema
  3. Precomputes derived metrics (MA20, RSI, volume ratio, price change %, sector ranking)
  4. Exposes typed query methods: `get_stock_profile(ticker)`, `get_sector_snapshot(date)`, `get_top_movers(date)`

- **Table structure** (`aggregated_data`):
  - `ticker`, `date`, `close`, `open`, `high`, `low`, `volume`, `market_cap`
  - `ma5`, `ma10`, `ma20`, `ma50`, `rsi14`, `volume_ratio`, `price_change_pct`
  - `sector_rank`, `sector_avg_close_pct`, `is_uptrend` (boolean), `is_high_volume` (boolean)
- **Precompute scheduler** (`core/precompute.py`): runs daily after market close (16:00), batches all calculations in one pass.
- **Semantic views** on top of raw + aggregated tables for dashboard queries.

**Why:** DRY — computed columns calculated once, not per-request. Consistent numbers everywhere (all dashboards show same MA20). 10-50x faster on repeated queries.

**Not needed:** No Cube.js server, no GraphQL. Python functions + SQLite views are lighter and more maintainable for a single developer.

### ✅ Pattern Evaluation Results

Pattern 1 (Event-Driven Pipeline) — ✅ **Áp dụng được**
- Lightweight adaptation: SQLite + async queue, không cần Redis/RabbitMQ/Kafka
- Full audit trail cho mọi data pipeline tick (cron/API/manual)
- Event viewer page với filter, duration chart, error drill-down
- Đánh giá: ✅ Fits solo dev constraints, <100 events/day, SQLite sufficient

Pattern 2 (Semantic Layer) — ✅ **Áp dụng được**
- Python functions + SQLite views thay vì Cube.js server
- Precompute daily: MA5/10/20/50/200, RSI14, volume ratio, sector ranking
- UNIQUE: No external server dependency, 10-50x faster repeated queries
- Đánh giá: ✅ Eliminates DRY violations, consistent dashboard numbers, zero new infra

#### Phase 3 Addition

These patterns are added to Phase 3 (Architecture):

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 3.12 | Event pipeline | `core/events.py`, `events` table, event viewer page | 2d | 3.8 | ✅ Complete |
| 3.13 | Semantic layer | `core/semantic.py`, aggregated_data table, precompute scheduler | 3d | 3.8 | ✅ Complete |

#### Scope — What We Do NOT Adopt

- ❌ Monorepo / pnpm workspaces (we're Python, not Node.js)
- ❌ NestJS / Angular (we use Flask + Jinja + vanilla JS)
- ❌ Electron desktop bundling (we're a web dashboard)
- ❌ Microservices decomposition (solo dev, single deploy target)
- ❌ Redis, OpenSearch, MinIO (SQLite handles all for our scale)
- ❌ Cube.js server / Jitsu (Python implementations are lighter and more maintainable for solo dev)

### 1.4 Design Principles

1. **Event-driven over polling** — Cron jobs emit events, not fire-and-forget
2. **Semantic over raw** — Precompute derived metrics, expose unified views
3. **Non-destructive migration** — v2.0 continues to work during transition
4. **Feature flags** — New features enabled progressively via config
5. **Backward compatibility** — All v2.0 API routes continue to work
6. **Database forward-compatible** — v3.0 schema is additive only
7. **Progressive enhancement** — System degrades gracefully at every level

## 2. Implementation Phases

### Phase 1: Foundation — Stabilize & Clean (Week 1-2)

**Goal:** System works 100% without LLM. Clean repository. Single database. Structured logging.

#### Story Points: 5-7

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 1.1 | Clean repository | Remove all backup files, fix scripts, duplicate code | 0.5d | — |
| 1.2 | Consolidate database | Merge `db.py` + `core/db.py`, use single `jarvis.db` | 1d | 1.1 |
| 1.3 | Configure structured logging | Replace `print()` with `logging` module, add rotation | 1d | — |
| 1.4 | Fix config loading | Centralize `config.yaml` parsing, remove hardcoded paths | 1d | 1.2 |
| 1.5 | Bootstrap install script | `setup.sh` with venv, pip install, DB init | 0.5d | — |
| 1.6 | Add `llm_tasks` + `llm_cache` + `circuit_breaker` tables | New DB schema for async LLM | 0.5d | 1.2 |
| 1.7 | Add v2.0 compatibility tables | `sector_performance`, `entity_mentions`, `report_summaries`, `broker_overview` | 0.5d | 1.2 |
| 1.8 | Create `core/fallback_engine.py` | Heuristic alternatives for all 8 LLM endpoints | 2d | — |
| 1.9 | Wire heuristic fallback into `/api/analyze` | Return heuristic immediately, optionally queue LLM | 1d | 1.8 |
| 1.10 | Wire heuristic fallback into `/api/market-eval/generate` | Return heuristic immediately, optionally queue LLM | 1d | 1.8 |
| 1.11 | Wire heuristic fallback into Market Intelligence pipeline | `analyst.py` + `synthesizer.py` use heuristics by default | 1d | 1.8 |
| 1.12 | Add `LLM_AVAILABLE` health check | `/api/v1/health/llm` endpoint | 0.5d | — |
| 1.13 | Add `TelegramDeliveryService` | Send briefs via Telegram (v2.0 feature) | 1d | — |
| 1.14 | Add `DashboardUpdateService` | Update dashboard with latest brief (v2.0 feature) | 1d | — |

**Deliverable:** System fully operational without LLM. All intelligence features return data via heuristics. All v2.0 database tables preserved. Telegram + Dashboard delivery services active.

**Acceptance Criteria:**
- [ ] `python setup.sh` installs and initializes everything
- [ ] System starts with `python app.py` even if LLM is down
- [ ] All 8 LLM-dependent endpoints return data when LLM is down
- [ ] Single database file (`jarvis.db`) with 16 tables (12 original + 4 new)
- [ ] No `print()` statements in production code
- [ ] Log file rotates at 10MB, keeps 5 files

---

### Phase 2: Async Queue — Non-Blocking LLM (Week 3-4)

**Goal:** LLM calls run in background threads. Users never wait for LLM.

#### Story Points: 5-7

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 2.1 | Create `core/async_queue.py` | Thread-based task queue with 3 workers | 2d | 1.6 |
| 2.2 | Create `core/llm_gateway.py` | Unified LLM gateway with circuit breaker | 2d | 1.6, 2.1 |
| 2.3 | Add `/api/v1/llm/tasks` endpoints | Submit, status, result polling | 1d | 2.1, 2.2 |
| 2.4 | Modify `/api/analyze` for async | Submit task, return `task_id`, frontend polls | 1d | 2.3 |
| 2.5 | Modify `/api/market-eval/generate` for async | Same pattern as 2.4 | 1d | 2.3 |
| 2.6 | Modify Market Intelligence pipeline for async | Queue entire pipeline, return `task_id` | 1d | 2.1, 2.3 |
| 2.7 | Modify `/api/v1/news/score` for async | Queue scoring per article | 0.5d | 2.3 |
| 2.8 | Modify `/api/v1/market/auto-refresh` | Data sync sync, LLM reasoning async | 0.5d | 2.3 |
| 2.9 | Modify `/ai-intelligence` feed for async | Cache previous, queue new if stale | 1d | 2.3 |
| 2.10 | Frontend: Task status polling | Poll `/api/v1/llm/tasks/<id>/status`, show progress | 2d | 2.3 |
| 2.11 | Frontend: Result display | When LLM ready, replace heuristic with LLM | 1d | 2.10 |
| 2.12 | Background scheduler: pre-compute LLM | Queue LLM tasks on data refresh, not on request | 1d | 2.1, 2.2 |

**Deliverable:** LLM never blocks an HTTP request. All intelligence features return immediately.

**Acceptance Criteria:**
- [ ] `/api/analyze` returns in <200ms (heuristic + task_id)
- [ ] `/api/market-eval/generate` returns in <200ms (heuristic + task_id)
- [ ] Market Intelligence pipeline returns `task_id` immediately
- [ ] Frontend shows "LLM analysis in progress" badge
- [ ] Frontend auto-updates when LLM result is ready
- [ ] Scheduler pre-computes LLM results every 6 hours
- [ ] No HTTP request blocked by LLM

---

### Phase 3: Architecture — Modular & Clean (Week 5-6)

**Goal:** Split `app.py` into blueprints. Clean codebase. Proper separation of concerns.

#### Story Points: 9-14

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 3.1 | Create `api/` blueprint structure | Market, News, Stocks, Screener, Research, Portfolio, CMS, Intelligence, LLM, Auth, Main | 1d | — |
| 3.2 | Migrate `/api/market/*` routes | Market indices, signals, heatmap, auto-refresh | 1d | 3.1 |
| 3.3 | Migrate `/api/news/*` routes | Articles, trending, news scoring | 1d | 3.1 |
| 3.4 | Migrate `/api/stocks/*` routes | Analyze, quotes, symbols, watchlist | 1d | 3.1 |
| 3.5 | Migrate `/api/screener/*` routes | Signals, alert-feed, watchlist (v2.0 feature) | 1d | 3.1 |
| 3.6 | Migrate `/api/research/*` routes | Reports, stats, crawl, PDF download (v2.0 feature) | 1d | 3.1 |
| 3.7 | Migrate `/api/portfolio/*` routes | Holdings, transactions, PnL | 1d | 3.1 |
| 3.8 | Migrate `/api/cms/*` routes | Articles CRUD | 1d | 3.1 |
| 3.9 | Migrate `/api/intelligence/*` routes | Market intelligence, AI intelligence, pipeline | 2d | 3.1 |
| 3.10 | Migrate `/api/llm/*` routes | Task management, health | 1d | 3.1 |
| 3.11 | Migrate `/api/main/*` routes | Health, overview, logs | 1d | 3.1 |
| 3.12 | Add event-driven pipeline | `core/events.py`, `events` table, event viewer — audit trail for all data pipeline ticks | 2d | 2.12 |
| 3.13 | Add semantic layer | `core/semantic.py`, `aggregated_data` table, precompute scheduler — unified query abstraction for computed metrics | 3d | 2.12 |
| 3.14 | Create `services/` layer | MarketService, NewsService, PortfolioService, ResearchService | 1d | — |
| 3.15 | Create `gateways/` layer | MarketGateway, NewsGateway (LLMGateway in 2.2) | 1d | 3.14 |
| 3.16 | Create `workers/` layer | Scheduler, AlertMonitor | 0.5d | — |
| 3.17 | Update entry point `app.py` | Register blueprints, middleware, config | 0.5d | 3.1-3.16 |
| 3.18 | API route redirect layer | Old v2.0 routes → new v3.0 routes (backward compat) | 0.5d | 3.1-3.16 |

**Deliverable:** Clean, modular architecture. All routes organized in blueprints. Event pipeline + semantic layer implemented. All v2.0 features preserved. Backward compatible.

**Acceptance Criteria:**
- [x] `app.py` <200 lines (entry point only) ✅
- [x] All routes organized in blueprints under `api/` (11 blueprints) ✅
- [x] Event pipeline with audit trail ✅
- [x] Semantic layer with precomputed indicators ✅
- [ ] Service layer separates business logic from routing (partial)
- [ ] Gateway layer abstracts external data sources (partial)
- [x] All v2.0 routes still work (redirect to v3.0) ✅
- [x] No duplicate route definitions ✅

---

### Phase 4: Security & Reliability (Week 7-8)

**Goal:** Authentication, RBAC, input validation, rate limiting, observability.

#### Story Points: 5-7

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 4.1 | Add Flask authentication | Session-based auth with JWT | 1d | — |
| 4.2 | Implement RBAC middleware | Admin, Analyst, Viewer roles | 1d | 4.1 |
| 4.3 | Add `/api/auth/*` routes | Login, logout, register, change password | 1d | 4.1 |
| 4.4 | Protect admin endpoints | `/admin`, `/api/cms/*`, `/api/knowledge/save` require admin | 0.5d | 4.2 |
| 4.5 | Add input validation | Pydantic models for all API endpoints | 2d | 3.1-3.7 |
| 4.6 | Add rate limiting | 100 req/min per IP for API endpoints | 0.5d | — |
| 4.7 | Add secret management | Env vars for all secrets, no hardcoded passwords | 0.5d | 1.4 |
| 4.8 | Add health check endpoints | `/api/v1/health`, `/api/v1/health/db`, `/api/v1/health/llm`, `/api/v1/health/queue` | 0.5d | 1.11 |
| 4.9 | Add metrics collection | Request count, error rate, LLM success rate, cache hit rate | 1d | 1.3 |
| 4.10 | Configure production logging | File rotation, structured format, log levels | 0.5d | 1.3 |

**Deliverable:** Secure, observable system. Admin endpoints protected. API rate limited.

**Acceptance Criteria:**
- [ ] Admin panel requires login + admin role
- [ ] CMS endpoints require login
- [ ] API rate limited to 100 req/min per IP
- [ ] All API parameters validated
- [ ] No secrets in code or config file
- [ ] Health check endpoints return detailed status
- [ ] Metrics available via `/api/v1/metrics`

---

### Phase 5: Testing & Deployment (Week 9-14)

**Goal:** Pytest suite, Docker deployment, systemd service, documentation.

#### Story Points: 7-10

| # | Task | Description | Est. | Dependencies |
|---|------|-------------|------|--------------|
| 5.1 | Create `pytest` configuration | `pytest.ini`, conftest.py, fixtures | 0.5d | — |
| 5.2 | Write unit tests for `core/` | DB, LLM Gateway, Async Queue, Fallback Engine | 2d | 1-3 |
| 5.3 | Write unit tests for `api/` | All blueprint routes | 2d | 3.1-3.7 |
| 5.4 | Write integration tests | Full API flows, async task lifecycle | 2d | 2.1-2.11 |
| 5.5 | Create `Dockerfile` | Python 3.12, gunicorn, production config | 0.5d | 3.11 |
| 5.6 | Create `docker-compose.yml` | App + Redis + (optional) PostgreSQL | 0.5d | 5.5 |
| 5.7 | Create systemd service template | `jarvis-hub.service` | 0.5d | 5.5 |
| 5.8 | Update `requirements.txt` | All new dependencies | 0.5d | 1-4 |
| 5.9 | Update `README.md` | Setup, configuration, deployment | 1d | 1.5, 5.7 |
| 5.10 | Update `docs/` | Architecture, API reference, deployment guide | 1d | 3-4 |
| 5.11 | Create migration script | `scripts/migrate_v2_to_v3.py` | 1d | 1.6, 5.2 |
| 5.12 | End-to-end testing | Full system test with LLM up and down | 1d | 5.3-5.4 |

**Deliverable:** Production-ready deployment with tests, Docker, and documentation.

**Acceptance Criteria:**
- [ ] >60% test coverage on critical paths
- [ ] All tests pass in CI
- [ ] `docker-compose up` runs the full system
- [ ] systemd service starts/stops/restarts correctly
- [ ] Migration script works (v2.0 → v3.0)
- [ ] README covers setup, config, deployment
- [ ] E2E tests pass with LLM up and down

---

## 3. Task Dependencies & Timeline

```
Phase 1: Foundation (Week 1-2)
  ├── 1.1 Clean repository ──────────────────────┐
  ├── 1.2 Consolidate database ──────────────────┤
  ├── 1.3 Structured logging ────────────────────┼──► All phases
  ├── 1.4 Config loading ────────────────────────┤
  ├── 1.5 Bootstrap script ──────────────────────┤
  ├── 1.6 New DB tables ─────────────────────────┼──► Phase 2
  ├── 1.7 Fallback engine ───────────────────────┼──► Phase 2
  ├── 1.8-1.10 Wire heuristics ──────────────────┼──► Phase 2
  └── 1.11 LLM health check ─────────────────────┴──► Phase 2

Phase 2: Async Queue (Week 3-4)
  ├── 2.1 Async queue ───────────────────────────┼──► Phase 2, 5
  ├── 2.2 LLM gateway ───────────────────────────┼──► Phase 2, 5
  ├── 2.3 LLM task endpoints ────────────────────┼──► Phase 2
  ├── 2.4-2.9 Modify endpoints for async ────────┼──► Phase 3
  ├── 2.10 Frontend task polling ────────────────┼──► Phase 3
  ├── 2.11 Frontend result display ──────────────┼──► Phase 3
  └── 2.12 Pre-compute scheduler ────────────────┴──► Phase 3

Phase 3: Architecture (Week 5-6)
  ├── 3.1 Blueprint structure ───────────────────┼──► Phase 4
  ├── 3.2-3.7 Migrate routes ────────────────────┼──► Phase 4
  ├── 3.12 Event pipeline ───────────────────────┼──► Phase 4 (audit)
  ├── 3.13 Semantic layer ───────────────────────┼──► Phase 4 (analytics)
  ├── 3.14 Services layer ───────────────────────┼──► Phase 4
  ├── 3.15 Gateways layer ───────────────────────┼──► Phase 4
  ├── 3.16 Workers layer ────────────────────────┼──► Phase 4
  ├── 3.17 Entry point ──────────────────────────┼──► Phase 4
  └── 3.18 Route redirect layer ─────────────────┴──► Phase 4

Phase 4: Security (Week 7-8)
  ├── 4.1 Authentication ────────────────────────┼──► Phase 5
  ├── 4.2 RBAC middleware ───────────────────────┼──► Phase 5
  ├── 4.3 Auth routes ───────────────────────────┼──► Phase 5
  ├── 4.4 Protect admin endpoints ───────────────┼──► Phase 5
  ├── 4.5 Input validation ──────────────────────┼──► Phase 5
  ├── 4.6 Rate limiting ─────────────────────────┼──► Phase 5
  ├── 4.7 Secret management ─────────────────────┼──► Phase 5
  ├── 4.8 Health checks ─────────────────────────┼──► Phase 5
  ├── 4.9 Metrics ───────────────────────────────┼──► Phase 5
  └── 4.10 Production logging ───────────────────┴──► Phase 5

Phase 5: Testing & Deployment (Week 9-14)
  ├── 5.1 pytest configuration ──────────────────┐
  ├── 5.2 Unit tests core ───────────────────────┼──► Phase 5
  ├── 5.3 Unit tests api ────────────────────────┼──► Phase 5
  ├── 5.4 Integration tests ─────────────────────┼──► Phase 5
  ├── 5.5 Dockerfile ────────────────────────────┼──► Phase 5
  ├── 5.6 docker-compose ────────────────────────┼──► Phase 5
  ├── 5.7 systemd service ───────────────────────┼──► Phase 5
  ├── 5.8 requirements.txt ──────────────────────┼──► Phase 5
  ├── 5.9 README.md ─────────────────────────────┼──► Phase 5
  ├── 5.10 docs/ ────────────────────────────────┼──► Phase 5
  ├── 5.11 Migration script ─────────────────────┼──► Phase 5
  └── 5.12 E2E testing ──────────────────────────┴──► Phase 5
```

---

## 4. Dependency Chain

```
Phase 1 (Foundation)
  └── Phase 2 (Async Queue)
        └── Phase 3 (Architecture)
              └── Phase 4 (Security)
                    └── Phase 5 (Testing & Deployment)
```

**Critical Path:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5

**Parallel Workstreams:**
- Phase 1.1 (cleanup) can run in parallel with Phase 1.2-1.11
- Phase 5.1 (pytest config) can start after Phase 3.1 (blueprints)
- Phase 5.5-5.7 (deployment) can start after Phase 3.11 (entry point)

---

## 5. Technical Decisions

### 5.1 Async Implementation

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Thread queue (stdlib)** | No new dependencies, simple | Limited scalability | ✅ **Phase 2** |
| **RQ (Redis-backed)** | Scalable, distributed | Requires Redis, new dep | Phase 3+ if needed |
| **Celery** | Most powerful | Heavy, complex | Not needed yet |

**Decision:** Start with thread queue (stdlib). Migrate to RQ if scaling requires it.

### 5.2 Database Choice

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **SQLite** | No external dep, simple, WAL | Limited concurrency | ✅ **Primary** |
| **PostgreSQL** | Scalable, concurrent | External dep, complex | Phase 4+ if needed |
| **Redis** | Fast, in-memory | Not persistent | Cache only |

**Decision:** SQLite for primary storage (current). Redis for cache (optional, Phase 2+). PostgreSQL if scaling requires it.

### 5.3 Authentication

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Session-based** | Simple, Flask-native | Stateful | ✅ **Phase 4** |
| **JWT** | Stateless, scalable | Token management | If Phase 5 needs it |
| **OAuth2** | Social login | Complex, overkill | Not in scope |

**Decision:** Session-based auth with JWT if scaling requires it.

### 5.4 Caching

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **In-memory dict** | Fast, simple | Not persistent, per-process | ✅ **Phase 2** |
| **Redis** | Persistent, shared | External dep | Phase 3+ if needed |
| **SQLite** | Persistent, no dep | Slower | ✅ **llm_cache table** |

**Decision:** SQLite for LLM result cache (in `llm_cache` table). In-memory dict for hot data. Redis if scaling requires it.

---

## 6. Risk Mitigation

### 6.1 Known Risks

| Risk | Mitigation |
|------|------------|
| SQLite write contention under concurrent workers | WAL mode, `check_same_thread=False`, `timeout=30` |
| Memory leaks in worker threads | Daemon threads, periodic worker reset, task timeout |
| Frontend breaking during migration | Backward compatibility layer, gradual rollout |
| LLM provider downtime | Circuit breaker + heuristic fallback (already designed) |
| Security breach | RBAC, input validation, rate limiting (Phase 4) |
| Test coverage gaps | Start tests early (Phase 2+), >60% target |

### 6.2 Rollback Plan

1. Keep v2.0 codebase as backup (`app.py.bak.v3-rollback`)
2. Database migrations are additive (never destructive)
3. Configuration file is separate from code
4. All data preserved in SQLite (no external dependencies for migration)
5. Feature flags allow gradual rollout (`llm.enabled`, `async.enabled`)

---

## 7. Success Criteria

### 7.1 Technical Metrics

| Metric | Current (v2.0) | Target (v3.0) | Measurement |
|--------|----------------|---------------|-------------|
| API response time (analyze) | 15-30s (blocking) | <200ms (heuristic) + async LLM | `/api/analyze?symbol=VCB` |
| LLM failure impact | System hangs | Immediate fallback to heuristic | `/api/analyze?symbol=VCB` with LLM down |
| Heuristic fallback usage | 0% | 100% of endpoints | All endpoints return data without LLM |
| System uptime without LLM | ~60% | 100% | Monitor `/api/v1/health/llm` |
| Event audit trail | None | All pipeline ticks logged | `events` table query |
| Semantic consistency | Duplicated across dashboards | Single precomputed source | Compare dashboard outputs |
| Database file count | 3 | 1 | `ls *.db` |
| Code complexity | 84 routes in 1 file | Modular blueprints | `wc -l app.py` < 200 |
| Test coverage | 0% | >60% | `pytest --cov` |
| Deployment time | Manual | <5 minutes | `docker-compose up` |

### 7.2 User Experience Metrics

| Metric | Current (v2.0) | Target (v3.0) |
|--------|----------------|---------------|
| First page load | 2-5s | <1s |
| Stock analysis | 15-30s (spinning) | Instant (heuristic) + LLM in background |
| Market intelligence | 30+ min (synchronous) | Instant (`task_id`) + progress updates |
| LLM down experience | Blank page / timeout | Data + clear message: "LLM unavailable, showing heuristic analysis" |
| News feed | 5-10s (synchronous LLM) | Instant (RSS) + LLM enrichment in background |
| Admin panel | No auth | Login required, RBAC |

### 7.3 Non-Functional Requirements

| Requirement | Target |
|------------|--------|
| **Reliability** | 99.9% uptime (without LLM) |
| **Performance** | <200ms API response (data layer) |
| **Security** | RBAC, input validation, rate limiting |
| **Observability** | Structured logging, health checks, metrics |
| **Maintainability** | >60% test coverage, modular architecture |
| **Deployability** | Docker, systemd, bootstrap script |
| **Scalability** | 3 worker threads (upgradeable to RQ/Celery) |

---

## 8. Configuration Changes

### 8.1 config.yaml Additions

```yaml
# New sections for v3.0
database:
  primary: "~/jarvis-hub/data/jarvis.db"
  wal_mode: true
  journal_size: "100MB"

queue:
  max_workers: 3
  task_timeout: 300
  cleanup_interval: 3600
  ttl_hours: 24

llm:
  fallback:
    enabled: true
    timeout_ms: 5000

  circuit_breaker:
    failure_threshold: 3
    reset_timeout: 30
    half_open_max_calls: 1

news:
  enrichment:
    heuristic: true
    llm: true
    cache_ttl_minutes: 60

scheduler:
  market_intelligence:
    enabled: true
    interval_hours: 6
    pre_compute: true
  auto_refresh:
    enabled: true
    interval_minutes: 30
  llm_health_check:
    enabled: true
    interval_minutes: 5

security:
  secret_key: "${SECRET_KEY}"
  admin_password: "${ADMIN_PASSWORD}"
  jwt_expiry_hours: 24
  max_login_attempts: 5
  lockout_minutes: 15

logging:
  level: "INFO"
  file: "~/jarvis-hub/logs/jarvis.log"
  max_bytes: 10485760
  backup_count: 5
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

### 8.2 requirements.txt Additions

```
# Existing (unchanged)
flask==3.1.0
apscheduler==3.10.4
feedparser==6.0.11
numpy==2.2.0
requests==2.32.3

# New (v3.0)
redis==5.2.0              # Cache + async queue (optional, Phase 2+)
rq==1.16.0                # Task queue (if migrating from thread queue)
pydantic==2.10.0          # Input validation
pydantic-settings==2.7.0  # Config validation
gunicorn==23.0.0          # Production WSGI server
pytest==8.3.0             # Testing
pytest-cov==6.0.0         # Test coverage
```

---

## 9. File Structure Changes

### 9.1 New Structure (v3.0)

```
jarvis-hub/
├── app.py                          # Entry point (<200 lines)
├── config.yaml                     # Configuration
├── requirements.txt                # Dependencies
├── setup.sh                        # Bootstrap script
├── Dockerfile                      # Container deployment
├── docker-compose.yml              # Docker orchestration
│
├── api/                            # Flask Blueprints
│   ├── __init__.py                 # Blueprint registration
│   ├── market.py                   # /api/v1/market/*
│   ├── news.py                     # /api/v1/news/*
│   ├── stocks.py                   # /api/v1/stocks/*
│   ├── portfolio.py                # /api/v1/portfolio/*
│   ├── cms.py                      # /api/v1/cms/*
│   ├── intelligence.py             # /api/v1/intelligence/*
│   ├── llm.py                      # /api/v1/llm/*
│   └── auth.py                     # /api/v1/auth/*
│
├── services/                       # Business logic
│   ├── __init__.py
│   ├── market_service.py
│   ├── news_service.py
│   ├── portfolio_service.py
│   └── intelligence_service.py
│
├── gateways/                       # External service abstraction
│   ├── __init__.py
│   ├── llm_gateway.py              # LLM abstraction
│   ├── market_gateway.py           # Market data abstraction
│   └── news_gateway.py             # News abstraction
│
├── workers/                        # Background tasks
│   ├── __init__.py
│   ├── async_queue.py              # Task queue
│   ├── scheduler.py                # Background scheduler
│   └── health_monitor.py           # Circuit breaker monitoring
│
├── core/                           # Existing (unchanged, augmented)
│   ├── db.py                       # Enhanced with new tables
│   ├── llm_client.py               # Unchanged
│   ├── ollama_client.py            # Unchanged
│   ├── news_service.py             # Enhanced with async
│   ├── market_service.py           # Enhanced with async
│   ├── data_collector.py           # Unchanged
│   ├── fallback_engine.py          # NEW
│   └── market_intelligence/        # Enhanced with heuristics
│       ├── __init__.py
│       ├── analyst.py
│       ├── delivery.py
│       ├── ingestion.py
│       ├── parsing.py
│       └── synthesizer.py
│
├── templates/                      # Flask templates (unchanged)
├── static/                         # Static assets (unchanged)
├── data/                           # Single database
│   └── jarvis.db
├── logs/                           # Log files
├── scripts/                        # Migration scripts
├── tests/                          # Pytest suite
└── docs/                           # Documentation
```

### 9.2 Files Removed (v3.0)

| File | Reason |
|------|--------|
| `app.py.bak*` (14 copies) | Backup files, replace with git history |
| `fix_*.py` (10+ files) | Fix scripts, replaced by proper code |
| `db.py` (root) | Duplicate of `core/db.py`, merged |
| `market.py.bak*` | Backup file |
| `news.py.bak*` | Backup file |
| `gotham_brief*.py` | Legacy code, replaced by market intelligence pipeline |
| `hotfix_jarvis.py` | Temporary fix, replaced by proper fix |
| `test_*.py` (standalone scripts) | Migrated to pytest suite |
| `jarvis_hub.db` | Merged into `data/jarvis.db` |
| `watchlist.db` | Merged into `data/jarvis.db` |

---

## 10. Migration Checklist (v2.0 → v3.0)

### Pre-Migration

- [ ] Back up all data files (`jarvis_hub.db`, `jarvis.db`, `watchlist.db`)
- [ ] Document current API routes (done in `AUDIT_BACKLOG_20260824.md`)
- [ ] Document current codebase structure (done in `AUDIT_BACKLOG_20260824.md`)
- [ ] Ensure git commit is clean before starting migration

### During Migration

- [ ] Run Phase 1 tasks (foundation)
- [ ] Test: system works without LLM
- [ ] Test: all endpoints return data
- [ ] Test: single database file
- [ ] Run Phase 2 tasks (async queue)
- [ ] Test: LLM never blocks HTTP request
- [ ] Test: async task status polling works
- [ ] Test: frontend displays task progress
- [ ] Run Phase 3 tasks (architecture)
- [ ] Test: all routes work (old and new)
- [ ] Test: backward compatibility redirects work
- [ ] Run Phase 4 tasks (security)
- [ ] Test: admin panel requires login
- [ ] Test: API rate limiting works
- [ ] Test: input validation works
- [ ] Run Phase 5 tasks (testing & deployment)
- [ ] Test: all pytest tests pass
- [ ] Test: Docker compose works
- [ ] Test: systemd service works
- [ ] Test: migration script works

### Post-Migration

- [ ] Update `README.md` with new setup instructions
- [ ] Update `AGENTS.md` with new codebase structure
- [ ] Archive v2.0 codebase (`git tag v2.0-final`)
- [ ] Deploy v3.0 to production
- [ ] Monitor for 48 hours
- [ ] Collect feedback from users
- [ ] Archive any remaining v2.0 files

---

## 11. Glossary

| Term | Definition |
|------|------------|
| **Async Queue** | Thread-based task queue for non-blocking LLM execution |
| **Circuit Breaker** | Pattern that fails fast when LLM is down, preventing cascading timeouts |
| **Fallback Engine** | Heuristic alternatives for all LLM-dependent endpoints |
| **LLM Gateway** | Unified LLM abstraction layer with caching, fallback, and async support |
| **Heuristic** | Non-LLM analysis method (keyword matching, technical indicators, etc.) |
| **Pre-compute** | Running LLM analysis in background on schedule, not on request |
| **Blueprint** | Flask module for organizing routes by feature |
| **WAL Mode** | SQLite Write-Ahead Logging for concurrent access |
| **TTL** | Time-To-Live for cache entries |
| **RBAC** | Role-Based Access Control |

---

## 12. Appendix

### A. API Route Mapping (v2.0 → v3.0)

See `JH3.0_DESIGN.md` §4.3 for full mapping table.

### B. Database Schema (v3.0)

See `JH3.0_DESIGN.md` §5.1 for full schema.

### C. Configuration (v3.0)

See `JH3.0_DESIGN.md` §6 for full config structure.

### D. Risk Assessment

See `JH3.0_DESIGN.md` §11 for risk assessment.

### E. Success Metrics

See `JH3.0_DESIGN.md` §12 for success metrics.
