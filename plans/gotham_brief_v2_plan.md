# Gotham Brief v2.0 — Refactor Plan

**Created**: Saturday, June 06, 2026  
**Status**: Phase 2a - Kanban Extraction (In Progress)  
**Owner**: Hermes Agent (Rex's personal assistant)

---

## 🎯 Objective

Transform `gotham_brief.py` (560-line monolith, sequential-only) into a modular, cron-safe intelligence briefing pipeline.

### Why This Matters
- Current v1.0 fires LLM prompts **sequentially** — total latency ≈ 180s for 2 prompts  
- No audit trail: when briefs fail in cron, there's no way to verify what happened
- Ollama auto-eviction kills silent runs (model unloads after ~15 min idle)
- File bloat makes incremental patches corrupt indentation across sessions

### Design Principles
1. **Simple is best** — single .py entry point for cron shims, but modular internals  
2. **Each module testable independently** with `unittest.mock`
3. **Graceful degradation prioritized** over "fail fast, fail everything"
4. **One feature at a time** — zero collateral risk, verify before next step

---

## 📐 Target Architecture (Modular Refactor)

### Module Structure
```
gotham/                           # New package for orchestration
├── __init__.py                   # Import-only: exposes shared config & constants
├── kanban.py                     # SQLite state machine (~200 lines)
├── health_check.py               # Ollama pre-flight checks (~80 lines)  
└── orchestrator.py               # Parallel LLM orchestration engine
gotham_brief.py                   # Main entry point (imports from gotham/, ~150 lines refactored)
```

### Module Dependencies
```
gotham/__init__.py     No deps (constants only)
      ↓
gotham/kanban.py         ← depends on __init__  
gotham/orchestrator.py   ← depends on kanban + health_check  
gotham_brief.py          ← imports all gotham modules
```

### Module Interfaces (API Contracts)

**`gotham/kanban.py`:**
```python
def init_kanban_db() -> None                 # Create gotham_runs table IF NOT EXISTS  
def update(run_id: str, **fields) -> None    # INSERT OR REPLACE filtered fields
def read(run_id: str) -> dict | None         # Return row as dict or None  
def list_recent(limit: int=10) -> list       # ORDER BY completed_at DESC (LIMIT N)
```

**`gotham/health_check.py`:**
```python  
def ollama_health(timeout: int = 10) -> dict   # {running, model_loaded, error}
def pull_model(timeout: int = 60) -> bool      # Initiate model pull, return success/fail
```

**`gotham/orchestrator.py`:**
```python
class ParallelLLMEngine:                       # Fire prompts concurrently via ThreadPoolExecutor  
    def __init__(self, pool_size=2, total_timeout=500)  
    def run(self, prompts_list, article_text) -> dict   # {prompt_name: analysis_text}
```

### Kanban Schema (`gotham_runs` table)
```sql
CREATE TABLE IF NOT EXISTS gotham_runs (
    run_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'IDLE',          -- IDLE → TRIAGE → PROCESSING → DELIVERED/FAILED
    mode TEXT,                                    -- morning|noon|afternoon|evening  
    date_str TEXT,                                -- "DD/MM/YYYY"  
    day_name TEXT,                                -- Monday...Sunday
    rss_count_main INTEGER DEFAULT -1,           -- Main articles fetched  
    rss_count_ent INTEGER DEFAULT -1,            -- ENT articles
    ent_sources_loaded INTEGER DEFAULT 0,        -- Working ENT feed sources
    prompts_fired INTEGER DEFAULT 0,             -- LLM prompts queued
    llm_success_count INTEGER DEFAULT 0,         -- Successful prompt results  
    llm_results TEXT,                             -- JSON {prompt_name: text}  
    telegram_sent INTEGER DEFAULT 0,             -- Chunks sent to Telegram
    telegram_msg_ids TEXT,                        -- JSON array of msg IDs 
    errors TEXT,                                  -- Error details  
    started_at TEXT,                               -- ISO8601 timestamp
    completed_at TEXT,                            -- ISO8601 timestamp
    duration_sec REAL                              -- Total pipeline duration
);
```

---

## 📅 Incremental Roadmap

### Phase 2a: Kanban Module Extraction [CURRENT]
Extract SQLite state machine into `gotham/kanban.py`, wire imports at top of `gotham_brief.py`.

**Steps:**
1. Create `gotham/__init__.py` with shared constants  
2. Build `gotham/kanban.py` from extracted kanban logic in current file
3. Replace inline kanban code in `gotham_brief.py` with `from gotham import kanban`
4. Verify: `python -m py_compile gotham_brief.py` → exit 0
5. Test: `python3 scripts/gotham_brief.py --test` → no crashes

**Target file size after:** ~100 lines (down from ~470 kanban + inline DB code)

---

### Phase 2b: Parallel LLM Orchestration [FUTURE]  
Extract and wire `concurrent.futures.ThreadPoolExecutor` engine to replace sequential loop.

**Steps:**
1. Implement `gotham/orchestrator.py` with `ParallelLLMEngine` class  
2. Wire orchestration into `run_pipeline()` replacing old for-loop
3. Add partial-failure handling (1/2 succeed → deliver brief with placeholder)

---

### Phase 2c: Health Check Pre-flight [FUTURE]
Add Ollama `/api/tags` pre-flight, graceful abort if model missing.

**Steps:**  
1. Implement `gotham/health_check.py` with health check functions
2. Wire into `run_pipeline()` sequence before LLM dispatch
3. Test: simulate model eviction → verify graceful failure path  

---

### Phase 3: Kanban Query Reports [FUTURE]
Add SQL query patterns for status reporting (latest failed run, daily summary, etc.)

---

## ✅ Testing Checklist (After Each Phase)

| Test | Command | Pass Criteria |
|------|---------|---------------|
| Syntax compile | `python -m py_compile gotham_brief.py` | Exit code 0, no errors |
| Module import | `python -c "from gotham import kanban; print('OK')"` | prints "OK" |
| DB init | `python3 scripts/gotham_brief.py --test` | No crashes, prints progress |
| Full pipeline dry-run | `python3 scripts/gotham_brief.py afternoon` | Brief delivered or gracefully fails |

---

## 📝 Session Notes & Decisions

- **2026-06-07**: Rex requested proper planning document + modular refactor approach over monolithic patch  
- Goal: persistent plan file stored alongside source code for cross-session consistency  
- Phase 2a (Kanban extraction) is the first implementation step once plan is approved  

---

*Last updated: Saturday, June 07, 2026*
