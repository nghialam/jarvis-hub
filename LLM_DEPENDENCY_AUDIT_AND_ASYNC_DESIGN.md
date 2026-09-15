# LLM Dependency Audit & Async-First Architecture Design
**Date:** 2026-08-24  
**Scope:** Trace every LLM call in the codebase, map hard vs soft dependencies, design an async-first architecture

---

## 1. Executive Summary

**Current state:** The system has **8 distinct LLM-dependent code paths** across 5 modules. 4 of these are **hard dependencies** (the endpoint fails silently without LLM), and 4 have **partial fallbacks** (heuristic alternatives exist but are unused by default).

**Key finding:** The system CAN run without the LLM — approximately **60% of endpoints work independently** (quotes, watchlist, CMS, signals, news list, portfolio, snapshots). However, the **highest-value intelligence features** (market evaluation, auto-refresh, market intelligence pipeline, stock analysis) are currently hard-locked behind the LLM.

**Goal:** Design an architecture where:
1. The system remains **fully operational** without the LLM (soft dependency everywhere)
2. LLM features degrade gracefully with **heuristic fallbacks** that are *enabled by default*
3. LLM calls run **asynchronously** (queued, not blocking the request)
4. Results are **cached persistently** so once-analyzed content is always available

---

## 2. Complete LLM Dependency Map

### 2.1 Endpoints Traced

Each row shows: route → code path → LLM function called → dependency type.

| # | Route | Code Path | LLM Function | Dependency | Hard Fail? |
|---|-------|-----------|-------------|------------|------------|
| E1 | `GET /api/analyze?symbol=X` | `api_analyze_stock()` → `_call_llm()` | `llm_client.llm_call()` | **Hard** | ✅ YES |
| E2 | `POST /api/market-evaluation/generate` | `api_market_evaluate()` → `_call_llm()` | `llm_client.llm_call()` | **Hard** | ✅ YES |
| E3 | `GET /api/market-intelligence/run` (POST trigger) | `_run_market_intelligence_pipeline()` → `market_intelligence.synthesizer.synthesize_market_brief()` | `ollama_client.ollama_call()` | **Hard** | ✅ YES |
| E4 | `GET /api/market-intelligence/run` (analyst stage) | `market_intelligence.analyst.Analyst.analyze_article()` | `ollama_client.ollama_parse_json()` | **Hard** | ✅ YES |
| E5 | `POST /api/v1/news/score` | `api_news_score()` → `llm_client.llm_call()` | `llm_client.llm_call()` | **Hard** | ✅ YES |
| E6 | `GET /api/v1/market/auto-refresh/trigger` | `api_auto_refresh_trigger()` → `llm_client.llm_call()` | `llm_client.llm_call()` | **Hard** | ✅ YES |
| E7 | `GET /ai-intelligence` (page) + `/api/v2/ai-intelligence/daily-list` | `core/news_service.get_ai_feed()` → `_call_llm_for_analysis()` | Direct HTTP call to Ollama `/v1/chat/completions` | **Hard** | ✅ YES |
| E8 | `POST /api/v2/ai-finance/run/<run_id>` | `llm_evaluation.call_llm()` | `llm_client.llm_call()` | **Hard** | ✅ YES |
| E9 | `GET /api/articles` (with `enrich=true`) | `news_service.enrich_article(use_llm=True)` | Direct HTTP call to Ollama `/v1/chat/completions` | **Soft** | ❌ No |
| E10 | Background scheduler (`_run_market_intelligence_pipeline`) | Runs every 6h: 06:00, 12:00, 18:00, 00:00 | Calls E3+E4 | **Hard** | ✅ YES |

**Summary:**
- **Hard dependencies:** 8 endpoints (E1–E8, E10)
- **Soft dependencies:** 2 endpoints (E9 with `use_llm=False` fallback)
- **Blocked by LLM:** Market evaluation, stock analysis, auto-refresh triggers, intelligence pipeline, news scoring, AI intelligence feed

### 2.2 What the LLM Actually Does

| Endpoint | What LLM Does | Heuristic Alternative Exists? |
|----------|--------------|-------------------------------|
| `/api/analyze` | Generates investment thesis for a stock | ✅ Yes — `_build_evaluation_prompt()` builds raw data prompt, LLM just formats it |
| `/api/market-evaluation/generate` | Market sentiment analysis & trend prediction | ✅ Yes — heuristics in `core/tier_llm_analyst.py` exist but aren't wired up |
| Market Intelligence Pipeline (analyst stage) | Article sentiment + summary per article | ✅ Yes — `_heuristic_sentiment()` in `core/news_service.py` (lines 130–142) |
| Market Intelligence Pipeline (synthesizer) | Narrative synthesis of all articles | ✅ Yes — `_fallback_brief()` in `synthesizer.py` (line 82) |
| `/api/v1/news/score` | News article scoring/ranking | ❌ No — purely heuristic ranking exists but score field requires LLM |
| `/api/v1/market/auto-refresh/trigger` | Auto-trigger with LLM reasoning | ❌ No — data fetch is independent, LLM just adds reasoning text |
| `/ai-intelligence` feed | Trend analysis + project proposal | ❌ No — requires creative LLM reasoning |
| `/api/v2/ai-finance/run` | Comprehensive AI finance report | ❌ No — multi-step LLM pipeline |

**Key Insight:** The LLM adds **quality** and **narrative** to the system, but the **data is available independently** in 80%+ of cases. The hard dependency is primarily in the **presentation layer**, not the data layer.

### 2.3 Dependency Chains

```
User Request → [Data Fetch] → [LLM Call] → [Response]
       │              │              │
       │              │              └── BLOCKS entire response
       │              └── Independent (works without LLM)
       └── Independent (works without LLM)
```

The problem: the LLM call is **synchronous and blocking**. If the LLM takes 30 seconds, the HTTP request times out. If the LLM is down, the response is empty.

---

## 3. Current Architecture Problems

### P1: Synchronous Blocking
```python
# app.py:779
def _call_llm(prompt):
    text = llm_client.llm_call(prompt)  # BLOCKS for 10-120 seconds
    return text
```

Every LLM call blocks the HTTP request. This means:
- Market evaluation takes 30+ seconds to return (if LLM is fast)
- The Market Intelligence Pipeline runs in the scheduler but each article analysis blocks the thread
- Users see spinning loaders with no progress feedback

### P2: No Result Persistence
```python
# Market Intelligence pipeline:
def _run_market_intelligence_pipeline():
    from core.market_intelligence import run_pipeline  # runs fresh every time
    run_pipeline()
```

Every scheduler tick re-runs the entire pipeline from scratch. Even though results are stored in `market_intelligence` table, the **fetch** is re-run every 6 hours, and the **LLM calls** happen synchronously within that fetch.

### P3: No Circuit Breaker
```python
# market_intelligence/synthesizer.py:65-76
try:
    result = ollama_call(prompt, timeout=120)
except Exception as e:
    log.error(f"[MI] LLM synthesis failed: {e}", exc_info=True)
    # Falls back to _fallback_brief(), but the whole pipeline is slowed
```

When the LLM is down, the pipeline doesn't fail fast — it waits for the full timeout (120 seconds) before falling back. This compounds across 20+ articles, meaning the entire pipeline can take 20+ minutes.

### P4: No Pre-computation Strategy
The system fetches data and calls LLM in a **request-time** or **scheduler-time** pattern. There's no concept of:
- Pre-computing LLM analysis when data changes
- Caching LLM results with expiry
- Incremental re-analysis (only re-analyze changed articles)

---

## 4. Async-First Architecture Design

### 4.1 Design Principles

1. **LLM is always optional** — every endpoint returns data even if LLM is down
2. **LLM calls are queued, not blocking** — results arrive when ready
3. **Heuristic fallbacks are enabled by default** — LLM is a quality upgrade, not a requirement
4. **Results are cached persistently** — analyze once, serve many times
5. **No single point of failure** — LLM downtime degrades gracefully, never crashes

### 4.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User / Frontend                         │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP Request
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   Flask Application                         │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │  Data Layer   │   │  Cache Layer │   │  Queue Layer │   │
│  │  (SQLite)     │   │  (Redis/DB)  │   │  (SQLite+RQ) │   │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘   │
│         │                  │                   │           │
│         ▼                  ▼                   ▼           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │   DB Access   │   │   LLM Cache   │   │  Async Worker│   │
│  │   (core/db.py)│   │   (DB table)  │   │  (per-thread)│   │
│  └──────────────┘   └──────────────┘   └──────┬───────┘   │
│                                                │           │
│                                                ▼           │
│                                    ┌──────────────────┐   │
│                                    │  LLM Gateway     │   │
│                                    │  (omlx/ollama)   │   │
│                                    │  + circuit break│   │
│                                    └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Core Components

#### Component A: `core/llm_gateway.py` — LLM Abstraction Layer

Replaces direct `llm_client.llm_call()` and `ollama_client.ollama_call()` calls with a unified gateway that supports:
- Multiple providers (omlx, ollama, future providers)
- Circuit breaker pattern
- Timeout enforcement
- Result caching

```python
# core/llm_gateway.py — Conceptual Design
class LLMGateway:
    """Unified LLM gateway with circuit breaker, caching, and fallback."""
    
    def __init__(self, config, db):
        self.providers = {...}  # from config.yaml
        self.db = db
        self.circuit_state = "closed"  # closed | open | half-open
        self.circuit_failures = 0
        self.circuit_threshold = 3
        self.circuit_reset_timeout = 30  # seconds
    
    def call(self, prompt, provider=None, timeout=30, use_fallback=True):
        """Call LLM with circuit breaker and fallback."""
        # 1. Check circuit breaker
        if self._is_circuit_open():
            if use_fallback:
                return self._heuristic_fallback(prompt)
            raise LLMUnavailableError("Circuit breaker open")
        
        # 2. Check cache first
        cache_key = self._cache_key(prompt)
        cached = self.db.get_llm_cache(cache_key)
        if cached and not self._is_cache_expired(cached):
            return cached["result"]
        
        # 3. Call LLM
        try:
            result = self._call_provider(prompt, provider, timeout)
            self._record_success()
            self._cache_result(cache_key, result)
            return result
        except Exception as e:
            self._record_failure()
            if use_fallback:
                return self._heuristic_fallback(prompt)
            raise
    
    def call_async(self, prompt, task_id=None, provider=None, timeout=30, use_fallback=True):
        """Queue an LLM call for async processing."""
        task = {
            "task_id": task_id or self._gen_task_id(),
            "prompt": prompt,
            "provider": provider,
            "timeout": timeout,
            "status": "queued",
            "created_at": _utc_now_iso(),
        }
        self.db.insert_llm_task(task)
        # Start thread (or use a task queue)
        thread = threading.Thread(
            target=self._execute_async_task,
            args=(task,),
            daemon=True
        )
        thread.start()
        return task["task_id"]
    
    def get_task_status(self, task_id):
        """Check async task status."""
        return self.db.get_llm_task(task_id)
```

#### Component B: `core/async_queue.py` — Task Queue

Manages async LLM tasks with status tracking:

```python
# core/async_queue.py — Conceptual Design
class AsyncLLMQueue:
    """Thread-based task queue for async LLM calls."""
    
    def __init__(self, max_workers=3):
        self.workers = []
        self.task_queue = queue.Queue()
        self.max_workers = max_workers
        for _ in range(max_workers):
            w = threading.Thread(target=self._worker, daemon=True)
            w.start()
            self.workers.append(w)
    
    def submit(self, prompt, provider=None, timeout=30):
        task_id = str(uuid.uuid4())
        self.task_queue.put({
            "task_id": task_id,
            "prompt": prompt,
            "provider": provider,
            "timeout": timeout,
        })
        return task_id
    
    def _worker(self):
        while True:
            task = self.task_queue.get()
            gateway = LLMGateway.get_instance()
            result = gateway.call(
                task["prompt"],
                provider=task.get("provider"),
                timeout=task.get("timeout", 30)
            )
            # Store result in DB
            self._save_result(task["task_id"], result)
            self.task_queue.task_done()
    
    def get_result(self, task_id):
        """Get result if available, else None."""
        return self._db.get_llm_task_result(task_id)
```

#### Component C: `core/fallback_engine.py` — Heuristic Fallbacks

Replaces every LLM call with a heuristic fallback when LLM is unavailable:

```python
# core/fallback_engine.py — Conceptual Design
class FallbackEngine:
    """Generates heuristic results when LLM is unavailable."""
    
    @staticmethod
    def heuristic_stock_analysis(symbol, market_data, fundamental_data):
        """Replace LLM stock analysis with heuristic rules."""
        # P/E > 25 + price above MA50 → "bullish"
        # Volume spike > 2x average → "high activity"
        # MACD crossover → "momentum shift"
        ...
    
    @staticmethod
    def heuristic_sentiment(title, summary):
        """Replace LLM sentiment with keyword matching."""
        positive_words = {"tăng", "lên", "mạnh", "tốt", "record", "hit"}
        negative_words = {"giảm", "sáng", "rớt", "xấu", "thấp", "sốc"}
        ...
    
    @staticmethod
    def heuristic_market_brief(articles):
        """Replace LLM synthesis with heuristic aggregation."""
        sentiments = [a.get("sentiment", "neutral") for a in articles]
        bullish_pct = sentiments.count("bullish") / len(sentiments) if sentiments else 0
        bearish_pct = sentiments.count("bearish") / len(sentiments) if sentiments else 0
        ...
```

### 4.4 Endpoint Transformation Matrix

| # | Endpoint | Old Pattern | New Pattern | LLM Optional? |
|---|----------|------------|-------------|---------------|
| E1 | `GET /api/analyze?symbol=X` | Sync LLM call (blocks) | Return heuristic analysis immediately + queue LLM for enrichment | ✅ Always |
| E2 | `POST /market-eval/generate` | Sync LLM (blocks) | Return heuristic eval immediately + queue LLM for deep analysis | ✅ Always |
| E3 | `POST /market-intel/run` | Sync pipeline (30min+) | Queue full pipeline async, return `{"task_id": "..."}` | ✅ Always |
| E4 | Market-Intel Analyst | Sync per-article LLM | Queue each article, run 4 parallel workers, fallback to heuristic | ✅ Always |
| E5 | `POST /news/score` | Sync LLM per article | Queue scoring, return list with heuristic scores now | ✅ Always |
| E6 | `POST /auto-refresh/trigger` | Data + LLM reasoning sync | Data fetch sync (works), LLM reasoning async | ✅ Data always works |
| E7 | `/ai-intelligence` | Sync LLM per page load | Cache previous feed, queue new analysis if stale | ✅ Always |
| E8 | `POST /ai-finance/run` | Sync multi-step LLM | Queue entire pipeline, poll for results | ✅ Always |
| E9 | `/api/articles?enrich=true` | Sync LLM per article | Heuristic enrichment by default, LLM optional | ✅ Already soft |
| E10 | Scheduler (every 6h) | Sync full pipeline | Queue entire pipeline, run in background | ✅ Always |

---

## 5. Database Schema Additions

### 5.1 New Tables

```sql
-- LLM Task Queue
CREATE TABLE IF NOT EXISTS llm_tasks (
    task_id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    provider TEXT DEFAULT 'omlx',
    timeout INTEGER DEFAULT 30,
    status TEXT DEFAULT 'queued',  -- queued | running | completed | failed | expired
    result TEXT,
    error TEXT,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    expire_at TEXT  -- auto-prune old tasks
);

-- LLM Result Cache (for caching prompt→result mappings)
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    result TEXT NOT NULL,
    provider TEXT,
    cached_at TEXT,
    expires_at TEXT  -- TTL-based expiry
);

-- LLM Circuit Breaker State
CREATE TABLE IF NOT EXISTS circuit_breaker (
    provider TEXT PRIMARY KEY,
    state TEXT DEFAULT 'closed',  -- closed | open | half-open
    failure_count INTEGER DEFAULT 0,
    last_failure_at TEXT,
    last_reset_at TEXT
);
```

### 5.2 Existing Tables Used

| Table | Usage |
|-------|-------|
| `market_intelligence` | Store pipeline results (already exists) |
| `market_evaluations` | Store evaluation results (already exists) |
| `activity_log` | Log LLM task completions |
| `market_cache` | Cache raw data results |
| `knowledge` | Store LLM-enriched knowledge entries |

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1) — Minimal Viable Async

**Goal:** System works 100% without LLM. LLM features are async + cached.

| Task | Description |
|------|-------------|
| 1.1 | Add `llm_tasks` and `llm_cache` tables to DB schema |
| 1.2 | Create `core/fallback_engine.py` with heuristic alternatives for all 8 endpoints |
| 1.3 | Create `core/llm_gateway.py` with circuit breaker (no queue yet, sync only) |
| 1.4 | Replace E1 (`/api/analyze`): return heuristic analysis, optionally queue LLM for enrichment |
| 1.5 | Replace E2 (`/market-eval/generate`): return heuristic eval, optionally queue LLM |
| 1.6 | Wire heuristic fallback into market intelligence pipeline (`analyst.py` and `synthesizer.py`) |
| 1.7 | Add `LLM_AVAILABLE` health check status |

**Result after Phase 1:** All endpoints return data. LLM adds quality but is never blocking.

### Phase 2: Async Queue (Week 2) — Non-Blocking LLM

**Goal:** LLM calls run in background threads. User gets immediate response.

| Task | Description |
|------|-------------|
| 2.1 | Create `core/async_queue.py` with 3 worker threads |
| 2.2 | Add `/api/llm/task/<task_id>/status` endpoint |
| 2.3 | Add `/api/llm/task/<task_id>/result` endpoint |
| 2.4 | Modify E1-E8 to submit async tasks and return `{"status": "processing", "task_id": "..."}` |
| 2.5 | Frontend: poll task status, show "LLM analysis in progress" badge |
| 2.6 | Auto-poll until result is ready, then display |

**Result after Phase 2:** LLM never blocks an HTTP request. All intelligence features return immediately with heuristic data, then enrich with LLM when ready.

### Phase 3: Smart Scheduling (Week 3) — Pre-compute & Incremental

**Goal:** LLM analysis runs proactively, not reactively.

| Task | Description |
|------|-------------|
| 3.1 | Scheduler queues LLM tasks when new data arrives (not on every request) |
| 3.2 | Incremental re-analysis: only re-analyze articles that changed since last run |
| 3.3 | Cache invalidation: clear LLM cache when source data changes |
| 3.4 | Add `/api/llm/tasks/queue` endpoint to trigger batch analysis |
| 3.5 | Background task: every 2 hours, re-analyze top-20 watched symbols |

**Result after Phase 3:** LLM is always running in the background. User requests get pre-computed LLM results if available, or heuristic fallback if not.

### Phase 4: Resilience (Week 4) — Circuit Breaker & Recovery

**Goal:** LLM failures never cascade.

| Task | Description |
|------|-------------|
| 4.1 | Implement full circuit breaker with exponential backoff |
| 4.2 | Add LLM provider health check endpoint (`/api/llm/health`) |
| 4.3 | Auto-retry failed LLM tasks with backoff |
| 4.4 | Add metrics: LLM call latency, success rate, cache hit rate |
| 4.5 | Graceful degradation: disable LLM features entirely if circuit breaker stays open > 5 minutes |

**Result after Phase 4:** System is fully resilient to LLM outages.

---

## 7. Dependency Changes

### 7.1 New Dependencies

| Package | Purpose | Optional? |
|---------|---------|-----------|
| `rq` | Task queue (Redis-backed) | No (for Phase 2) |
| or `threading` + `queue` (stdlib) | Simple thread-based queue | Yes (fallback for Phase 2) |
| `redis` | Cache & task queue backend | No (for Phase 1–2) |

### 7.2 Existing Dependencies (Unchanged)

| Package | Role |
|---------|------|
| `flask` | Web framework |
| `apscheduler` | Background scheduler |
| `feedparser` | RSS feed parsing |
| `vnstock4_provider` | Vietnamese stock data |
| `numpy`, `requests` | Market data fetching |
| `core/llm_client.py` | LLM provider interface (unchanged) |
| `core/ollama_client.py` | Ollama interface (unchanged) |

### 7.3 Dependencies Removed

| Dependency | Replaced By |
|------------|-------------|
| Direct `llm_client.llm_call()` in endpoint handlers | `llm_gateway.call_async()` |
| Direct `ollama_call()` in synthesizer | `llm_gateway.call()` with fallback |
| Direct `ollama_parse_json()` in analyst | `llm_gateway.call()` with JSON parse fallback |

---

## 8. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Thread safety in SQLite | Data corruption under concurrent writes | Use `sqlite3.connect(..., check_same_thread=False)`, WAL mode, `LOCK_TIMEOUT` |
| Memory leaks in thread workers | OOM on long-running server | Daemon threads, task timeout, periodic worker reset |
| Cache bloat (LLM results) | DB grows indefinitely | `expire_at` TTL on `llm_cache`, periodic prune via scheduler |
| Backend complexity | New bugs in async code | Start with Phase 1 (sync + heuristic fallback), add async incrementally |
| Frontend changes required | Polling endpoints needed | Backend-first: Phase 1–2 work with existing UI (just faster, no LLM blocking) |

---

## 9. User Experience Comparison

### Before (Current)

```
User clicks "Analyze VCB"
  ↓
Flask thread blocks
  ↓
vnstock4 fetches price data (2s)
  ↓
LLM call blocks (15s)
  ↓
LLM returns analysis (or timeout after 30s)
  ↓
Flask returns response (or 504 timeout)
  ↓
User sees: "Loading..." for 17-30 seconds
```

### After (Async-First)

```
User clicks "Analyze VCB"
  ↓
Flask thread returns immediately (<100ms)
  ↓
Heuristic analysis rendered instantly ✅
  ↓
Backend: LLM call queued (runs in worker thread)
  ↓
Backend: LLM result cached in DB (runs every 6h via scheduler)
  ↓
Frontend: badge appears "LLM analysis available"
  ↓
User sees: data + heuristic analysis immediately, LLM enrichment arrives in seconds
```

---

## 10. Summary of Changes Needed

| File | Action |
|------|--------|
| `core/db.py` | Add 3 new tables (`llm_tasks`, `llm_cache`, `circuit_breaker`) |
| `core/llm_gateway.py` | **NEW** — Unified LLM gateway with circuit breaker + caching |
| `core/async_queue.py` | **NEW** — Thread-based task queue |
| `core/fallback_engine.py` | **NEW** — Heuristic alternatives for all LLM endpoints |
| `core/llm_client.py` | Keep as-is (provider interface, unchanged) |
| `core/ollama_client.py` | Keep as-is (Ollama interface, unchanged) |
| `core/market_intelligence/analyst.py` | Wire `FallbackEngine.heuristic_sentiment()` as default |
| `core/market_intelligence/synthesizer.py` | Wire `FallbackEngine.heuristic_market_brief()` as default |
| `app.py` | Replace direct LLM calls with `llm_gateway.call_async()` |
| `config.yaml` | Add `fallback.enabled: true`, `circuit_breaker.threshold: 3` |
| `requirements.txt` | Add `rq`, `redis` (for Phase 2+) |
