# Jarvis Hub 3.0 — Vietnamese Market Intelligence Platform

> **Version:** 3.0.0-draft  
> **Last Updated:** 2026-08-24  
> **Status:** Design & Implementation Planning

---

## 📋 Quick Links

| Document | Description |
|----------|-------------|
| [`JH3.0_DESIGN.md`](JH3.0_DESIGN.md) | **System Design** — Architecture, components, data model, config |
| [`JH3.0_IMPLEMENTATION_PLAN.md`](JH3.0_IMPLEMENTATION_PLAN.md) | **Implementation Plan** — Phases, tasks, timeline, dependencies |
| [`JARVIS_HUB_2.0_DESIGN.md`](JARVIS_HUB_2.0_DESIGN.md) | v2.0 Design (legacy, for reference) |
| [`AUDIT_BACKLOG_20260824.md`](AUDIT_BACKLOG_20260824.md) | v2.0 Audit & Backlog |
| [`LLM_DEPENDENCY_AUDIT_AND_ASYNC_DESIGN.md`](LLM_DEPENDENCY_AUDIT_AND_ASYNC_DESIGN.md) | LLM Dependency Analysis & Async Design |
| [`AGENTS.md`](AGENTS.md) | AI Agent Bootstrap Instructions |

---

## 🚀 What's New in 3.0

Jarvis Hub 3.0 is a complete architectural overhaul of the Vietnamese stock intelligence platform:

| Area | v2.0 (Current) | v3.0 (Design) |
|------|----------------|---------------|
| **LLM Dependency** | 8 hard dependencies, blocking | 0 hard dependencies, async queue |
| **Fallback Strategy** | Silent `except Exception` returns | Heuristic fallbacks enabled by default |
| **Architecture** | 84 routes in 1 file, no separation | Modular blueprints, layered separation |
| **Data Pipeline** | Synchronous, re-runs on every tick | Pre-compute + incremental re-analysis |
| **Logging** | 51 `print()` statements | Structured logging with rotation |
| **Config** | Hardcoded paths, 3 DB files | Single source of truth, env-aware |
| **Testing** | 4 standalone scripts | Pytest suite with CI |
| **Security** | No auth, no secrets | RBAC, secret management |
| **Deployment** | No configuration | Docker, systemd templates |

---

## 📖 Documentation Index

### v2.0 Audit (Current State)

| Document | Purpose |
|----------|---------|
| [`AUDIT_BACKLOG_20260824.md`](AUDIT_BACKLOG_20260824.md) | Full audit of v2.0 — critical issues, high-priority fixes, backlog |
| [`JARVIS_HUB_2.0_DESIGN.md`](JARVIS_HUB_2.0_DESIGN.md) | v2.0 design specification (legacy reference) |
| [`LLM_DEPENDENCY_AUDIT_AND_ASYNC_DESIGN.md`](LLM_DEPENDENCY_AUDIT_AND_ASYNC_DESIGN.md) | LLM dependency analysis — traces all 8 LLM call paths, designs async-first architecture |

**Key Findings:**
- **Score:** 3.8/10 — Functionally rich but operationally fragile
- **LLM Dependency:** 8 hard dependencies, 4 soft — system works ~60% without LLM
- **Code Quality:** 162 bare excepts, 51 print() calls, no logging module
- **Security:** No auth, no CSRF, no secret key, open API endpoints
- **Architecture:** 84 routes in one file, no blueprints

### v3.0 System Design

| Document | Purpose |
|----------|---------|
| [`JH3.0_DESIGN.md`](JH3.0_DESIGN.md) | **System Design** — Complete architecture, components, data model, config, security, deployment |
| `JH3.0_REVIEW_NOTES.md` | *(Planned — post-design review)* |

**Key Design Decisions:**
1. **LLM is always optional** — heuristics are the default, LLM is an upgrade
2. **Async-first** — LLM calls run in background threads, never block HTTP
3. **Circuit breaker** — LLM failures don't cascade, immediate fallback to heuristics
4. **Pre-compute** — LLM results cached and refreshed on schedule, not on request
5. **Modular** — Clean separation with Flask Blueprints (one per feature)
6. **Secure** — Auth, RBAC, secret management
7. **Observable** — Structured logging, health checks, metrics
8. **Deployable** — Docker, systemd, bootstrap script

### v3.0 Implementation Plan

| Document | Purpose |
|----------|---------|
| [`JH3.0_IMPLEMENTATION_PLAN.md`](JH3.0_IMPLEMENTATION_PLAN.md) | **Implementation Plan** — 5 phases, 50+ tasks, timeline, dependencies, success metrics |

**Phases:**

| Phase | Title | Duration | Est. Points |
|-------|-------|----------|-------------|
| **1** | Foundation — Stabilize & Clean | Week 1-2 | 5-7 |
| **2** | Async Queue — Non-Blocking LLM | Week 3-4 | 5-7 |
| **3** | Architecture — Modular & Clean | Week 5-6 | 7-10 |
| **4** | Security & Reliability | Week 7-8 | 5-7 |
| **5** | Testing & Deployment | Week 9-14 | 7-10 |
| **Total** | | **10-14 weeks** | **~35 points** |

### Reference Documentation

| Document | Purpose |
|----------|---------|
| [`AGENTS.md`](AGENTS.md) | AI Agent Bootstrap Instructions (Skill Router) |
| `BACKLOG.md` | Project backlog |
| `BUGLOG_20260524.md` | Bug log |
| `DASHBOARD_API.md` | Dashboard API reference |
| `EXECUTION_PLAN.md` | Execution plan |
| `MIGRATION_REPORT.md` | Migration report |
| `REVIEW_REPORT_20260709.md` | Review report |

### Docs Directory

| File | Purpose |
|------|---------|
| `docs/ARCHITECTURE.md` | Architecture reference |
| `docs/COMMANDS.md` | CLI commands |
| `docs/DASHBOARD_API.md` | Dashboard API reference |
| `docs/FAQ.md` | FAQ |
| `docs/QUICKSTART.md` | Quick start guide |
| `docs/USER_MANUAL.md` | User manual |
| `docs/VERCEL_DEPLOYMENT_PLAN.md` | Vercel deployment plan (legacy) |

---

## 🏗️ Project Structure (v3.0 Target)

```
jarvis-hub/
├── app.py                          # Entry point (<200 lines)
├── config.yaml                     # Configuration
├── requirements.txt                # Dependencies
├── setup.sh                        # Bootstrap script (v3.0)
├── Dockerfile                      # Container deployment (v3.0)
├── docker-compose.yml              # Docker orchestration (v3.0)
│
├── api/                            # Flask Blueprints (v3.0)
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
├── services/                       # Business logic (v3.0)
│   ├── __init__.py
│   ├── market_service.py
│   ├── news_service.py
│   ├── portfolio_service.py
│   └── intelligence_service.py
│
├── gateways/                       # External service abstraction (v3.0)
│   ├── __init__.py
│   ├── llm_gateway.py              # LLM abstraction
│   ├── market_gateway.py           # Market data abstraction
│   └── news_gateway.py             # News abstraction
│
├── workers/                        # Background tasks (v3.0)
│   ├── __init__.py
│   ├── async_queue.py              # Task queue
│   ├── scheduler.py                # Background scheduler
│   └── health_monitor.py           # Circuit breaker monitoring
│
├── core/                           # Core modules (augmented)
│   ├── db.py                       # Database layer (enhanced)
│   ├── llm_client.py               # LLM provider interface (unchanged)
│   ├── ollama_client.py            # Ollama interface (unchanged)
│   ├── news_service.py             # News aggregation (enhanced)
│   ├── market_service.py           # Market data (enhanced)
│   ├── data_collector.py           # Data collection (unchanged)
│   ├── fallback_engine.py          # Heuristic fallbacks (NEW)
│   └── market_intelligence/        # Intelligence pipeline (enhanced)
│       ├── __init__.py
│       ├── analyst.py
│       ├── delivery.py
│       ├── ingestion.py
│       ├── parsing.py
│       └── synthesizer.py
│
├── templates/                      # Flask templates (unchanged)
├── static/                         # Static assets (unchanged)
├── data/                           # Single database (v3.0)
│   └── jarvis.db
├── logs/                           # Log files
├── scripts/                        # Migration scripts
├── tests/                          # Pytest suite (v3.0)
└── docs/                           # Documentation
```

---

## 📊 Status

| Phase | Status | Target Date |
|-------|--------|-------------|
| Design | ✅ Complete | 2026-08-24 |
| Implementation | 📋 Planning | TBD |
| Testing | 📋 Planning | TBD |
| Deployment | 📋 Planning | TBD |

---

## 🔄 Migration Path (v2.0 → v3.0)

### Pre-Migration
1. Back up all data files (`jarvis_hub.db`, `jarvis.db`, `watchlist.db`)
2. Document current API routes (done in `AUDIT_BACKLOG_20260824.md`)
3. Document current codebase structure (done in `AUDIT_BACKLOG_20260824.md`)
4. Ensure git commit is clean before starting migration

### During Migration
1. **Phase 1:** Foundation & cleanup — system works without LLM
2. **Phase 2:** Async queue — LLM never blocks HTTP
3. **Phase 3:** Architecture — modular, clean codebase
4. **Phase 4:** Security — auth, RBAC, validation
5. **Phase 5:** Testing & deployment — Docker, systemd, docs

### Post-Migration
1. Update `README.md` with new setup instructions
2. Update `AGENTS.md` with new codebase structure
3. Archive v2.0 codebase (`git tag v2.0-final`)
4. Deploy v3.0 to production
5. Monitor for 48 hours
6. Collect feedback from users
7. Archive any remaining v2.0 files

---

## 📝 Glossary

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

## 🎯 Key Metrics

| Metric | v2.0 (Current) | v3.0 (Target) |
|--------|----------------|---------------|
| API response time (analyze) | 15-30s (blocking) | <200ms (heuristic) + async LLM |
| LLM failure impact | System hangs | Immediate fallback to heuristic |
| Heuristic fallback usage | 0% | 100% of endpoints |
| System uptime without LLM | ~60% | 100% |
| Database file count | 3 | 1 |
| Code complexity | 84 routes in 1 file | Modular blueprints |
| Test coverage | 0% | >60% |
| Deployment time | Manual | <5 minutes |
