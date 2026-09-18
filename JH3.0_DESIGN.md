# Jarvis Hub 3.0 — System Design
**Version:** 3.0.0-draft  
**Date:** 2026-08-24 (Updated: 2026-09-18)  
**Status:** Implementation Progress — Phase 3 Partially Complete  
**Author:** Jarvis Hub Team

---

## 1. Vision & Scope

Jarvis Hub 3.0 is a complete architectural overhaul of the Vietnamese stock intelligence platform. It transforms the system from a **LLM-dependent monolith** into an **async-first, resilient intelligence engine** where:

- The system works **100% without LLM** — heuristics are the default, LLM is an optional quality upgrade
- LLM calls are **asynchronous and non-blocking** — users never wait for LLM
- LLM results are **cached and pre-computed** — once analyzed, always available
- LLM failures **never cascade** — circuit breakers degrade gracefully

### 1.1 What Changes in 3.0

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

### 1.2 Non-Goals (Out of Scope for 3.0)

- Mobile app (planned for 4.0)
- Real-time WebSocket streaming (planned for 3.1)
- Multi-user collaboration (planned for 3.1)
- WebSocket push notifications (planned for 3.1)
- Cloud-native deployment (Kubernetes, Terraform) — out of scope for 3.0

### 1.3 Frontend Preservation (v2.0 → v3.0)

> **CRITICAL:** All frontend components from v2.0 are **100% preserved** in v3.0. The v3.0 migration changes only the **backend API layer** — frontend code is untouched.

| Component | Location | v2.0 Count | v3.0 Status |
|-----------|----------|------------|-------------|
| HTML Templates | `dashboard/templates/` | 11 files | ✅ 100% preserved |
| Sidebar Navigation | `hub2.html` (lines 75-112) | 8 tabs | ✅ 100% preserved |
| Breadcrumb Navigation | `hub2.html` (lines 13-19, 121-128) | 1 component | ✅ 100% preserved |
| Static Assets | `dashboard/static/{css,js,charts}/` | 3 directories | ✅ 100% preserved |
| CMS Panel | `cms.html` | 1 file | ✅ 100% preserved |
| Chart.js Charts | Multiple templates | Charts embedded | ✅ 100% preserved |
| Dark Theme CSS | `dashboard/static/css/` | Styles | ✅ 100% preserved |

**Frontend templates (all preserved):**
- `index.html` → `/`
- `hub2.html` → `/hub2`
- `market.html` → `/hub2/market`
- `news.html` → `/hub2/news`
- `company.html` → `/hub2/company`
- `research.html` → `/hub2/research`
- `screener.html` → `/hub2/screener`
- `market-intel.html` → `/hub2/market-intel`
- `portfolio.html` → `/hub2/portfolio`
- `ai_intelligence.html` → `/ai-intelligence`
- `cms.html` → `/admin`, `/cms`

**Sidebar navigation (8 tabs, all preserved):**
- 🏠 Hub Home → `/hub2`
- 📊 Market → `/hub2/market`
- 📰 News → `/hub2/news`
- 🏢 Company → `/hub2/company`
- 📑 Research → `/hub2/research`
- 🔍 Screener → `/hub2/screener`
- 🧠 Market Intel → `/hub2/market-intel`
- 💼 Portfolio → `/hub2/portfolio`

**Breadcrumb navigation:**
- Located in `hub2.html` (lines 121-128)
- Component: `<nav class="breadcrumb">` with `breadcrumb-list` and `breadcrumb-item`
- Styling: CSS defined at lines 13-19
- Fully preserved — no changes needed

---

## 2. Architecture Overview

### 2.1 High-Level Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         User / Frontend                           │
│         (React SPA ←→ Flask API ←→ Charts + Real-time)             │
└─────────────────────┬──────────────────────────────────────────────┘
                      │ HTTP/REST (JSON)
                      ▼
┌────────────────────────────────────────────────────────────────────┐
│                     Flask Application Layer                       │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Auth Layer  │  │  API Layer   │  │  Admin Layer │           │
│  │  (Middleware)│  │  (Blueprints)│  │  (Middleware)│           │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │
│         │                  │                  │                   │
│         └──────────────────┼──────────────────┘                   │
│                            │                                      │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │ │
│  │  │ Market   │ │ News     │ │ LLM      │ │ Semantic │   │ │
│  │  │ Service  │ │ Service  │ │ Gateway  │ │ Layer    │   │ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘   │ │
│  │       │            │            │            │          │ │
│  │       └────────────┴────────────┼────────────┘          │ │
│  │                                │                         │ │
│  │  ┌─────────────────────────────┼─────────────────────┐  │ │
│  │  │           Async Task Queue   │                      │  │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │ │
│  │  │  │ Worker 1 │ │ Worker 2 │ │ Worker 3 │          │  │ │
│  │  │  └──────────┘ └──────────┘ └──────────┘          │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │     Event Bus (cron/API → SQLite audit trail)    │  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────────────────┐
│                     Data & External Layer                         │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │   SQLite DB  │  │  Redis Cache │  │  File Store  │           │
│  │  (Persistent)│  │  (Fast Read) │  │  (Attachments)│          │
│  └──────┬───────┘  └──────────────┘  └──────────────┘           │
│         │                                                         │
│         └──────────┬──────────────────────────────────┘          │
│                    │                                              │
│  ┌─────────────────┼─────────────────┬───────────────────┐      │
│  ▼                 ▼                 ▼                   ▼      │
│ ┌──────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐   │
│ │vnstock│  │Yahoo Finance │  │ RSS Feeds   │  │LLM API   │   │
│ │4 VN  │  │ Global Mkt   │  │(CafeF,etc)  │  │(omlx/    │   │
│ │Stock │  │ Data         │  │              │  │ ollama)  │   │
│ └──────┘  └──────────────┘  └──────────────┘  └──────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Layer Responsibilities

| Layer | Responsibility | Key Components |
|-------|---------------|----------------|
| **API Layer** | HTTP routing, request validation, response serialization | Flask Blueprints, Pydantic models |
| **Service Layer** | Business logic, orchestration, data transformation | Service classes, pipeline managers |
| **Gateway Layer** | External service abstraction, fallback handling | LLM Gateway, Market Data Gateway, News Gateway |
| **Data Layer** | Persistence, caching, storage | SQLite, Redis, File Store |
| **Async Layer** | Background task processing | Task queue, worker pool, scheduler |

---

## 3. Core Components

### 3.1 LLM Gateway (`core/llm_gateway.py`)

The unified LLM abstraction layer that replaces all direct LLM calls.

**Key features:**
- Multiple provider support (omlx, ollama, future providers)
- Circuit breaker pattern (fail fast, recover automatically)
- Result caching with TTL
- Heuristic fallback when LLM is unavailable
- Async task submission with status tracking

```python
# Conceptual API
gateway = LLMGateway(config, db)

# Synchronous call (with fallback)
result = gateway.call(prompt, timeout=30, use_fallback=True)

# Asynchronous call (non-blocking)
task_id = gateway.call_async(prompt, provider="omlx", timeout=120)

# Check task status
status = gateway.get_task_status(task_id)  # {"status": "running", "progress": 0.6}

# Get task result
result = gateway.get_task_result(task_id)  # Returns None if not ready
```

**Circuit Breaker States:**
```
CLOSED ──(3 failures)──> OPEN ──(30s timeout)──> HALF-OPEN
   ^                                               │
   │                                               │
   └──────────────(success)────────────────────────┘
```

- **CLOSED**: Normal operation, requests go through LLM
- **OPEN**: LLM failing, requests immediately use heuristic fallback
- **HALF-OPEN**: Testing if LLM recovered, single probe request

### 3.2 Async Task Queue (`core/async_queue.py`)

Thread-based task queue for non-blocking LLM execution.

**Key features:**
- 3 worker threads (configurable)
- Task status tracking (queued → running → completed/failed)
- Result persistence in SQLite
- Automatic cleanup of expired tasks
- Priority queue (important tasks first)

```python
queue = AsyncQueue(max_workers=3)

# Submit a task
task_id = queue.submit(
    fn=analyze_stock,
    args=("VCB",),
    priority="high",
    ttl_hours=24
)

# Check status
status = queue.get_status(task_id)

# Get result (returns None if not ready)
result = queue.get_result(task_id)
```

### 3.3 Fallback Engine (`core/fallback_engine.py`)

Heuristic alternatives for every LLM-dependent endpoint.

| LLM Feature | Heuristic Alternative | Quality |
|------------|----------------------|---------|
| Stock analysis (buy/hold/sell) | Technical indicators + fundamental ratios | Good |
| Market sentiment | Keyword scoring + volume analysis | Good |
| Article classification | Category-based routing + keyword matching | Good |
| Market brief synthesis | Aggregated sentiment + volume-weighted scoring | Good |
| News scoring | Recency + source priority + keyword weight | Good |
| Trend prediction | Moving average crossovers + momentum indicators | Good |

### 3.4 Market Data Gateway (`core/market_gateway.py`)

Unified interface to all market data sources with automatic fallback.

```python
gateway = MarketGateway(config, db)

# Get stock price — auto-selects best source
price = gateway.get_price("VCB", days=30)
# Falls back: vnstock4 → Yahoo Finance → CafeF

# Get indices — from Yahoo Finance
indices = gateway.get_indices(["^VNINDEX.VN", "^HNXINDEX"])

# Get sector performance
sector = gateway.get_sector_performance()

# Get OHLCV
ohlcv = gateway.get_ohlcv("VCB", period="week")
```

### 3.5 News Gateway (`core/news_gateway.py`)

RSS feed aggregation with heuristic enrichment.

```python
gateway = NewsGateway(config, db)

# Fetch articles — always works
articles = gateway.fetch_articles(limit=50, use_llm=False)

# Fetch with optional LLM enrichment
articles = gateway.fetch_articles(limit=50, use_llm=True)
# LLM runs async, returns immediately with heuristic data
# Result cached for 1 hour

# Get trending articles
trending = gateway.get_trending(hours=24)
```

### 3.6 Telegram Delivery Service (`core/market_intelligence/delivery.py`)

Sends market intelligence briefs via Telegram (v2.0 feature).

```python
class TelegramDeliveryService:
    """Send market intelligence brief via Telegram."""
    
    def __init__(self, config):
        self.telegram_token = config.telegram.token
        self.chat_id = config.telegram.target_chat_id
        self.openclaw_path = config.telegram.openclaw_path
    
    def send_brief(self, brief_text, run_id):
        """Send brief to Telegram target_chat_id."""
        ...
    
    def send_alert(self, alert_text):
        """Send real-time alert to Telegram."""
        ...
    
    def trigger_openclaw(self, command):
        """Execute openclaw command on target machine."""
        ...
```

### 3.7 Dashboard Update Service (`core/market_intelligence/delivery.py`)

Updates dashboard with latest intelligence brief (v2.0 feature).

```python
class DashboardUpdateService:
    """Update dashboard with latest intelligence brief."""
    
    def update_dashboard(self, run_id):
        """Update dashboard cache with latest brief from DB."""
        ...
    
    def get_latest_brief(self):
        """Get most recent brief for dashboard display."""
        ...
```

### 3.8 Research Crawler Service (`services/research_service.py`)

Scans broker websites for new research reports (v2.0 feature).

```python
class ResearchCrawlerService:
    """Scan broker websites for new research reports."""
    
    BROKERS = {
        "SSI": "https://www.ssi.com.vn/research",
        "VCI": "https://vcsc.com.vn/research",
        "HCM": "https://www.hcmsec.com.vn/research",
        "TCBS": "https://www.tcbs.com.vn/research",
        "VCBS": "https://www.vcbs.com.vn/research",
    }
    
    def scan_brokers(self):
        """Scan SSI, VCI, HCM, TCBS, VCBS for PDFs."""
        ...
    
    def download_pdf(self, report_id, url):
        """Download and store report PDF."""
        ...
    
    def parse_report(self, pdf_path):
        """Extract metadata and summary from PDF."""
        ...
    
    def generate_summary(self, report_id):
        """Generate LLM summary of report (async)."""
        ...
```

### 3.9 Alert Monitor Service (`workers/alert_monitor.py`)

Watches watchlist for alert conditions every 60s (v2.0 feature).

```python
class AlertMonitor:
    """Check watchlist alerts every 60 seconds."""
    
    def check_alerts(self):
        """Check if any watchlist alerts have been triggered."""
        active_alerts = self.get_active_alerts()
        for alert in active_alerts:
            if self.condition_met(alert):
                self.trigger_alert(alert)
    
    def condition_met(self, alert):
        """Check if alert condition is met (price, volume, etc)."""
        ...
    
    def trigger_alert(self, alert):
        """Send alert notification (Telegram, dashboard, email)."""
        ...
    
    def get_active_alerts(self):
        """Get all active alerts from database."""
        ...
```

### 3.10 Database Layer (`core/db.py`)

Enhanced SQLite layer with new tables for async LLM support.

**New tables (see §5.1):**
- `llm_tasks` — Task queue storage (design only)
- `llm_cache` — LLM result cache with TTL (design only)
- `circuit_breaker` — Circuit breaker state (design only)
- `events` — Event-driven pipeline audit trail (ever-gauzy Jitsu pattern) ✅
- `events_archive` — Archived events >90 days old ✅
- `aggregated_data` — Semantic layer placeholder (design)
- `v_market_indicators` — SQLite view: MA5/10/20/50/200 + volume_ratio ✅
- `v_market_rsi` — SQLite view: RSI14 ✅
- `aggregate_cache` — Key/value cache with TTL ✅
- `market_breadth` — Daily breadth snapshot ✅

**Existing tables (unchanged):**
- `knowledge`, `activity_log`, `daily_snapshots`, `watchlist`, `market_cache`
- `market_evaluations`, `trading_alerts`, `market_intelligence`
- `cms_articles`, `research_items`, `backlog_tasks`, `portfolio_transactions`

### 3.11 Event-Driven Pipeline (`core/events.py`)

Every data pipeline tick emits an event — not fire-and-forget cron. Borrowed from ever-gauzy's Jitsu event collection pattern, but implemented as lightweight Python + SQLite.

**Core types (implemented):**

```python
class EventType(str, Enum):
    # Data ingestion
    TICK_START = "tick_start"
    TICK_COMPLETE = "tick_complete"
    TICK_ERROR = "tick_error"
    RSS_FETCH = "rss_fetch"
    API_FETCH = "api_fetch"
    WEB_SCRAPING = "web_scraping"
    CRON_TRIGGER = "cron_trigger"
    MANUAL_TRIGGER = "manual_trigger"
    # Data processing
    DATA_PARSED = "data_parsed"
    DATA_STORED = "data_stored"
    DATA_VALIDATED = "data_validated"
    DATA_INVALID = "data_invalid"
    # Semantic layer
    METRIC_PRECOMPUTED = "metric_precomputed"
    VIEW_INVALIDATED = "view_invalidated"
    VIEW_REFRESHED = "view_refreshed"
    # Pipeline lifecycle
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"
    # Notifications
    ALERT_TRIGGERED = "alert_triggered"
    NOTIFICATION_SENT = "notification_sent"

class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"
```

**Event dataclass (implemented):**
```python
@dataclass
class Event:
    event_id: str          # uuid-based, e.g. "a1b2c3d4e5f6"
    type: EventType
    status: EventStatus
    source: str            # module/component that triggered it
    payload: dict          # structured JSON context
    timestamp: str         # ISO format
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None  # links related events together
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:        # serialise to JSON
    @classmethod
    def create(cls, event_type, source, payload=None, trace_id=None, metadata=None) -> "Event"
    @classmethod
    def from_row(cls, row) -> "Event"  # reconstruct from sqlite3.Row (index access)
```

**EventStore API (implemented):**
```python
store = EventStore(db_path=None)  # auto-detects from Flask config or defaults to data/jarvis.db

# Emit — create + insert in one call
event_id = store.emit(EventType.RSS_FETCH, "news_cron",
                      {"articles": 24, "sources": ["cafef"]})

# Manual create + insert
event = Event.create(EventType.PIPELINE_START, "market",
                     {"symbols": ["VIC", "VCB"]})
store.insert(event)

# Update event mid-lifecycle
store.update(event_id, status=EventStatus.COMPLETED,
             duration_ms=45.2, result={"count": 24})

# Query with filters
events = store.query(
    event_type=EventType.API_FETCH,
    source="cron",
    status=EventStatus.COMPLETED,
    start_time="2026-09-01",
    limit=100, offset=0,
)

# Trace — all events linked by trace_id
trace = store.get_trace(trace_id)  # ordered by timestamp ASC

# Failed events
errors = store.get_errors(limit=50, source="cron")

# Stats — aggregated metrics
stats = store.get_stats(hours=24)
# → {"type_counts": {...}, "status_counts": {...},
#    "avg_duration_ms": 35.2, "total_events": 42,
#    "top_errors": [...]}

# Archiving
store.archive(event_id)                  # single event
store.archive_old(days=30)               # bulk > 30 days, returns count
```
```

**EventStore API:**
```python
store = EventStore(db_path)

# Emit — create + insert in one call
event_id = store.emit(EventType.RSS_FETCH, "news_cron",
                      {"articles": 24, "sources": ["cafef"]})

# Manual create + insert
event = Event.create(EventType.PIPELINE_START, "market",
                     {"symbols": ["VIC", "VCB"]})
store.insert(event)

# Update event mid-lifecycle
store.update(event_id, status=EventStatus.COMPLETED,
             duration_ms=45.2, result={"count": 24})

# Query with filters
events = store.query(
    event_type=EventType.API_FETCH,
    source="cron",
    status=EventStatus.COMPLETED,
    start_time="2026-09-01",
    limit=100, offset=0,
)

# Trace — all events linked by trace_id
trace = store.get_trace(trace_id)  # ordered by timestamp ASC

# Failed events
errors = store.get_errors(limit=50, source="cron")

# Stats — aggregated metrics
stats = store.get_stats(hours=24)
# → {"type_counts": {...}, "status_counts": {...},
#    "avg_duration_ms": 35.2, "total_events": 42,
#    "top_errors": [...]}

# Archiving
store.archive(event_id)                  # single event
store.archive_old(days=30)               # bulk > 30 days, returns count
```

**Tables:**
```sql
CREATE TABLE events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL,
    payload TEXT,           -- JSON blob
    timestamp TEXT NOT NULL,
    duration_ms REAL,
    error TEXT,
    trace_id TEXT,
    metadata TEXT           -- JSON blob
);
-- Indexes: event_type, status, source, timestamp, trace_id, composite (event_type, source, timestamp)

CREATE TABLE events_archive (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    payload TEXT,
    timestamp TEXT NOT NULL,
    duration_ms REAL,
    error TEXT,
    trace_id TEXT,
    metadata TEXT,
    archived_at TEXT NOT NULL
);
```

**Event bus architecture:**
```
Cron/API Trigger → store.emit(event_type, source, payload, trace_id, metadata)
                   → Immediate SQLite INSERT
                   → Dashboard/API can query, filter, trace
                   → Auto-cleanup: store.archive_old(days=30)
```

**Events API (api/events.py):**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/events` | Query with filters (type, status, source, trace_id, start, end, limit, offset) |
| GET | `/api/v1/events/stats` | Stats for N hours (hours param, default 24) |
| GET | `/api/v1/events/errors` | Failed events (limit, source params) |
| GET | `/api/v1/events/trace/<trace_id>` | Full event trace by trace_id |
| POST | `/api/v1/events/archive` | Archive events >N days (days param, default 30) |
| POST | `/api/v1/events/archive/<event_id>` | Archive single event |

**Why this matters:** Full audit trail of data flow. When a cron job fails, you can see exactly which tick failed, how long it took, what error occurred. Critical for reliability and debugging.

**Not needed:** No Redis, RabbitMQ, or Kafka. SQLite + existing async queue is sufficient for <100 events/day scale.

### 3.12 Semantic Layer (`core/semantic.py`)

Unified query abstraction that precomputes derived metrics so every dashboard shows the same numbers. Implemented as Python classes + SQLite views.

**Implemented components:**

```python
class MarketView:
    """SQLite views for precomputed technical indicators on price data."""

    def __init__(self, db_path: str): ...

    # SQL Views created:
    #   CREATE VIEW v_market_indicators  — MA5/10/20/50/200 + volume_ratio
    #   CREATE VIEW v_market_rsi         — RSI14 with full CTE chain

    # Query methods:
    def get_indicators(self, symbol, date_from, date_to=None, limit=None) -> List[Dict]
    def get_rsi(self, symbol, date_from, date_to=None, limit=None) -> List[Dict]
    def get_latest_for_symbols(self, symbols: List[str]) -> List[Dict]
    # Returns: date, symbol, close, ma5, ma10, ma20, ma50, ma200, volume_ratio

class AggregateCache:
    """Manages precomputed aggregate data for quick dashboard queries."""

    # Tables created:
    #   aggregate_cache (key/value with TTL)
    #   market_breadth (date/symbol/close/pct_change/volume/classification)

    def __init__(self, db_path: str): ...
    def init_db(self) -> None
    def get_cached(self, key: str) -> Optional[Dict]
    def set_cached(self, key: str, value: Dict, ttl_hours: int = 12) -> None
    def invalidate(self, key: str) -> None
    def refresh_all(self) -> Dict    # Runs full precompute: breadth + gainers/losers + sector rank
    def get_market_breadth(self, date: str) -> List[Dict]
```

**SQLite views (actual DDL):**
```sql
-- Moving averages + volume ratio
CREATE VIEW IF NOT EXISTS v_market_indicators AS
SELECT t.date, t.symbol, t.open, t.high, t.low, t.close, t.volume, t.adj_close,
       -- Moving averages (window functions)
       AVG(t2.close) OVER (...) AS ma5,
       AVG(t2.close) OVER (...) AS ma10,
       AVG(t2.close) OVER (...) AS ma20,
       AVG(t2.close) OVER (...) AS ma50,
       AVG(t2.close) OVER (...) AS ma200,
       -- Volume ratio (current vs 10-day avg)
       t.volume * 1.0 / NULLIF(AVG(t2.volume) OVER (...), 0) AS volume_ratio
FROM stock_data t
INNER JOIN stock_data t2 ON t2.symbol = t.symbol AND t2.date <= t.date
GROUP BY t.date, t.symbol;

-- RSI14 with full CTE chain
CREATE VIEW IF NOT EXISTS v_market_rsi AS
WITH price_changes AS (
    SELECT symbol, date, close,
           close - LAG(close) OVER (...) AS price_change
    FROM stock_data
),
gains_losses AS (...),
avg_gain_loss AS (...)
SELECT symbol, date, close, avg_gain, avg_loss,
       CASE WHEN avg_loss = 0 OR avg_loss IS NULL THEN 100.0
            ELSE 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
       END AS rsi14
FROM avg_gain_loss;
```

**Precompute scheduler (`core/precompute_scheduler.py`):**
- Uses APScheduler (in-process) for scheduling
- Daily at 06:00 SGT (23:00 UTC): full market precompute
- Hourly indicators snapshot during trading hours (00:00-09:00 UTC)
- Jobs: `daily_market`, `market_breadth`, `sector_ranking`, `indicators_snapshot`
- Integrates with EventStore for audit trail on each precompute tick

**Query methods:**
```python
from core.semantic import MarketView, AggregateCache

mv = MarketView(db_path)
ag = AggregateCache(db_path)

# Get indicators
indicators = mv.get_indicators("VIC", "2026-01-01", limit=10)
# → [{date, symbol, open, high, low, close, volume, adj_close,
#     ma5, ma10, ma20, ma50, ma200, volume_ratio}, ...]

# Get RSI
rsi = mv.get_rsi("VIC", "2026-01-01", limit=5)
# → [{date, symbol, close, rsi14}, ...]

# Latest snapshot for multiple symbols
latest = mv.get_latest_for_symbols(["VIC", "VCB", "HPG"])
# → [{date, symbol, close, ma5, ma10, ma20, ma50, ma200, volume_ratio}, ...]

# Full precompute run
results = ag.refresh_all()
# → {"advancers": [...], "losers": [...], "sector_rank": [...]}
```

**Singleton access:**
```python
from core.precompute_scheduler import get_precompute_scheduler
scheduler = get_precompute_scheduler(db_path, event_store)
# Automatically starts scheduler if not running
```

**Why this matters:**
- DRY: computed columns calculated once, not per-request
- Consistency: all dashboards show same MA20, RSI, volume ratio
- Performance: 10-50x faster on repeated queries (precomputed SQLite view)
- Maintainability: change MA20 formula in one place, all dashboards update

**Not needed:** No Cube.js server, no GraphQL. Python functions + SQLite views are lighter and more maintainable for solo dev.

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

### 5.3 Existing Tables (from v2.0 — all preserved)

```sql
-- Sector performance (v2.0 Tab 1 — Market Overview)
CREATE TABLE IF NOT EXISTS sector_performance (
    id INTEGER PRIMARY KEY,
    sector TEXT NOT NULL,
    change_pct REAL,
    volume REAL,
    market_cap REAL,
    top_gainer TEXT,
    top_loser TEXT,
    recorded_at TEXT
);

-- Entity mentions (v2.0 Tab 3 — Company News)
CREATE TABLE IF NOT EXISTS entity_mentions (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,  -- ticker | company | index
    entity_name TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    context TEXT,
    created_at TEXT,
    FOREIGN KEY(article_id) REFERENCES cms_articles(id)
);

-- Report summaries (v2.0 Tab 4 — Research Reports)
CREATE TABLE IF NOT EXISTS report_summaries (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL,
    summary_text TEXT,
    key_points TEXT,
    generated_by TEXT,
    generated_at TEXT,
    FOREIGN KEY(report_id) REFERENCES research_items(id)
);

-- Broker overview (v2.0 Tab 4 — Research Reports)
CREATE TABLE IF NOT EXISTS broker_overview (
    id INTEGER PRIMARY KEY,
    broker TEXT NOT NULL,
    index_target REAL,
    top_picks TEXT,
    market_outlook TEXT,
    published_at TEXT,
    UNIQUE(broker, published_at)
);

-- Market Quotes (v2.0 Tab 1 — Market Overview)
CREATE TABLE IF NOT EXISTS market_quotes (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT,
    price REAL,
    change_pct REAL,
    volume REAL,
    market_cap REAL,
    high REAL,
    low REAL,
    open REAL,
    previous_close REAL,
    last_updated TEXT
);

-- Daily OHLCV (v2.0 Tab 1 — Market Overview)
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    UNIQUE(symbol, date)
);

-- News Articles (v2.0 Tab 2 — News Aggregator)
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT,
    category TEXT,
    published_at TEXT,
    content TEXT,
    summary TEXT,
    sentiment TEXT,
    score REAL,
    created_at TEXT
);

-- Alerts (v2.0 Tab 5 — Screener & Alerts)
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    alert_type TEXT,
    condition TEXT,
    threshold REAL,
    status TEXT DEFAULT 'active',
    triggered_at TEXT,
    created_at TEXT,
    FOREIGN KEY(symbol) REFERENCES watchlist(symbol)
);
```

---

## 4. Application Architecture

### 4.1 Flask Blueprint Structure

```
app.py (entry point only — registers blueprints)
│
├── api/
│   ├── __init__.py          # Blueprint registration
│   ├── market.py            # /api/v1/market/* — indices, OHLCV, quotes, chart, sector
│   ├── news.py              # /api/v1/news/* — articles, trending, score, categories
│   ├── stocks.py            # /api/v1/stocks/* — analyze, quotes, symbols/search
│   ├── screener.py          # /api/v1/screener/* — signals, alert-feed, watchlist
│   ├── research.py          # /api/v1/research/* — reports, stats, crawl, download
│   ├── portfolio.py         # /api/v1/portfolio/* — holdings, transactions, pnl
│   ├── cms.py               # /api/v1/cms/* — articles CRUD
│   ├── intelligence.py      # /api/v1/intelligence/* — pipeline, ai-daily
│   ├── llm.py               # /api/v1/llm/* — tasks, health
│   ├── auth.py              # /api/v1/auth/* — login, logout, me
│   └── main.py              # /api/v1/main/* — health, overview, logs
│
├── services/                       # Business logic
│   ├── __init__.py
│   ├── market_service.py
│   ├── news_service.py
│   ├── portfolio_service.py
│   └── research_service.py         # Research crawler + report management

│
│   ├── screener.py          # /api/v1/screener/* — signals, alert-feed, watchlist
│   │   ├── GET  /signals                          -- Get all signals
│   │   ├── GET  /signals/latest                   -- Latest signals
│   │   ├── GET  /signals/symbol/<symbol>          -- Signal for symbol
│   │   ├── POST /signals                          -- Add signal
│   │   ├── POST /signals/mark-delivered           -- Mark delivered
│   │   ├── GET  /alert-feed                       -- Get alert feed
│   │   ├── GET  /alert-feed/auto-scan             -- Auto-scan watchlist
│   │   ├── POST /alert-feed/clear                 -- Clear alerts
│   │   ├── GET  /watchlist                        -- Get watchlist
│   │   ├── POST /watchlist                        -- Add to watchlist
│   │   └── DELETE /watchlist/<symbol>             -- Remove from watchlist
│   ├── research.py          # /api/v1/research/* — reports, stats, crawl, download
│   │   ├── GET  /reports                          -- List reports
│   │   ├── GET  /stats                            -- Report statistics
│   │   ├── POST /crawl                            -- Trigger crawl
│   │   └── GET  /reports/<id>/download            -- Download PDF
│   ├── portfolio.py         # /api/v1/portfolio/* — holdings, transactions, pnl
│   │   ├── GET  /holdings                         -- Portfolio holdings
│   │   ├── GET  /transactions                     -- Transaction history
│   │   ├── GET  /pnl-summary                      -- Profit/loss summary
│   │   ├── POST /add-txn                          -- Add transaction
│   │   └── DELETE /txn/<id>                       -- Delete transaction
│   ├── cms.py               # /api/v1/cms/* — articles CRUD
│   │   ├── GET  /articles                         -- List articles
│   │   ├── GET  /articles/<id>                    -- Article detail
│   │   ├── PUT  /articles/<id>                    -- Update article
│   │   ├── POST /articles                         -- Create article
│   │   └── DELETE /articles/<id>                  -- Delete article
│   ├── intelligence.py    # /api/v1/intelligence/* — pipeline, ai-daily
│   │   ├── POST /pipeline/run                     -- Run intelligence pipeline
│   │   ├── GET  /pipeline/latest                  -- Latest brief
│   │   ├── GET  /pipeline/history                 -- Run history
│   │   ├── GET  /pipeline/<id>                    -- Specific run detail
│   │   ├── GET  /pipeline/sentiment-dist          -- Sentiment distribution
│   │   ├── DELETE /pipeline/<id>                  -- Delete run
│   │   ├── GET  /ai-daily                         -- AI intelligence feed
│   │   └── GET  /ai-daily/<run_id>                -- Specific run
│   ├── llm.py             # /api/v1/llm/* — task management
│   │   ├── POST /tasks                            -- Submit async LLM task
│   │   ├── GET  /tasks/<id>/status                -- Task status
│   │   ├── GET  /tasks/<id>/result                -- Task result
│   │   └── GET  /health                           -- LLM provider health
│   ├── auth.py            # /api/v1/auth/* — authentication
│   │   ├── POST /login                            -- User login
│   │   ├── POST /logout                           -- User logout
│   │   └── GET  /me                               -- Current user info
│   └── main.py          # /api/v1/main/* — health & overview
│       ├── GET  /health                           -- System health
│       ├── GET  /overview                         -- Dashboard overview
│       ├── GET  /overview/indices                 -- Market indices
│       ├── GET  /overview/crypto                  -- Cryptocurrency
│       ├── GET  /overview/gold                    -- Gold/commodities
│       ├── GET  /overview/motions                 -- Top movers
│       ├── GET  /overview/chart                   -- OHLCV chart
│       └── GET  /logs                             -- System logs
│
```

### 4.2 API Route Mapping (v3.0)

| Old Route | New Route | Blueprint | Notes |
|-----------|-----------|-----------|-------|
| `/` | `/` | main | Index page |
| `/dashboard` | `/dashboard` | main | Dashboard redirect |
| `/hub2` | `/hub2` | main | Hub2 UI |
| `/api/analyze?symbol=X` | `/api/v1/stocks/analyze?symbol=X` | stocks | Returns heuristic + queues LLM |
| `/api/market-evaluation/generate` | `/api/v1/market/evaluate` | market | Returns heuristic + queues LLM |
| `/api/market-intelligence/run` | `/api/v1/intelligence/pipeline/run` | intelligence | Returns task_id |
| `/api/v1/market/auto-refresh/trigger` | `/api/v1/market/refresh` | market | Data sync only, LLM async |
| `/api/v1/news/score` | `/api/v1/news/score` | news | Heuristic scoring, LLM optional |
| `/api/v2/ai-intelligence/daily-list` | `/api/v1/intelligence/ai-daily` | intelligence | Cached feed, LLM async |
| `/api/v2/ai-finance/run/<run_id>` | `/api/v1/finance/report/<run_id>` | intelligence | Task-based |
| `/api/health` | `/api/v1/health` | main | Health check |
| `/api/llm/health` | `/api/v1/llm/health` | llm | LLM provider health |
| `/api/llm/task/<id>/status` | `/api/v1/llm/tasks/<id>/status` | llm | Task status |
| `/api/llm/task/<id>/result` | `/api/v1/llm/tasks/<id>/result` | llm | Task result |

### 4.3 Request Flow Examples

#### Example 1: Analyze a Stock (Async LLM)

```
1. User → GET /api/v1/stocks/analyze?symbol=VCB
2. Stocks Blueprint → MarketService.get_price("VCB")
3. MarketService → MarketGateway.get_price("VCB")
4. MarketGateway → vnstock4 (2s) → Price data
5. Stocks Blueprint → FallbackEngine.heuristic_analysis(price, fundamentals)
6. Stocks Blueprint → AsyncQueue.submit(fn=llm_gateway.call, args=(prompt,))
7. Stocks Blueprint → Return: {
     "symbol": "VCB",
     "price": {...},
     "analysis": "Heuristic: bullish (P/E=15 < 20, price > MA50)",
     "llm_status": "queued",
     "task_id": "abc123"
   }
8. User receives response in <200ms ✅
9. Backend: Worker thread calls LLM (15s)
10. LLM result cached in llm_cache table
11. Frontend polls /api/v1/llm/tasks/abc123/status → "completed"
12. Frontend fetches /api/v1/llm/tasks/abc123/result → LLM analysis
13. Frontend replaces heuristic with LLM analysis
```

#### Example 2: Market Intelligence Pipeline (Async)

```
1. User → POST /api/v1/intelligence/pipeline/run
2. Intelligence Blueprint → IntelligenceService.run_pipeline()
3. IntelligenceService → MarketGateway.fetch_articles()
4. MarketGateway → RSS feeds (10s) → Articles data
5. IntelligenceService → Queue full pipeline as async task
6. IntelligenceService → Return: {"task_id": "def456", "status": "queued"}
7. User receives response in <100ms ✅
8. Backend:
   - Worker 1: Article analysis (20 articles × 3s each, 4 parallel = 15s)
   - Worker 2: Synthesis (1 article × 30s = 30s)
   - Worker 3: Delivery (Telegram notification = 5s)
9. Pipeline completes in ~50s total (vs 30+ min synchronous)
10. Result stored in market_intelligence table
11. Frontend polls /api/v1/llm/tasks/def456/status → "completed"
12. Frontend fetches /api/v1/intelligence/latest → Full brief
```

#### Example 3: LLM Down (Graceful Degradation)

```
1. User → GET /api/v1/stocks/analyze?symbol=VCB
2. Stocks Blueprint → FallbackEngine.heuristic_analysis()
3. Stocks Blueprint → AsyncQueue.submit(fn=llm_gateway.call, ...)
4. LLM Gateway → Circuit breaker OPEN → Skip LLM call
5. LLM Gateway → Return heuristic_fallback(prompt)
6. Stocks Blueprint → Return: {
     "symbol": "VCB",
     "price": {...},
     "analysis": "Heuristic: bullish (P/E=15 < 20, price > MA50)",
     "llm_status": "unavailable",
     "llm_note": "LLM provider currently unavailable. Showing heuristic analysis."
   }
7. User receives response with clear status ✅
```

---

## 5. Data Model

### 5.1 Database Schema (SQLite)

#### New Tables

```sql
-- LLM Task Queue
CREATE TABLE IF NOT EXISTS llm_tasks (
    task_id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    fn_name TEXT NOT NULL,           -- Which function to call
    args_json TEXT,                  -- JSON args for the function
    provider TEXT DEFAULT 'omlx',
    timeout INTEGER DEFAULT 30,
    priority TEXT DEFAULT 'normal',  -- low | normal | high
    status TEXT DEFAULT 'queued',    -- queued | running | completed | failed | expired
    result TEXT,                     -- JSON result
    error TEXT,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    expire_at TEXT                   -- Auto-prune old tasks
);

-- LLM Result Cache (prompt → result mapping)
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    result TEXT NOT NULL,
    provider TEXT,
    cached_at TEXT,
    expires_at TEXT                  -- TTL-based expiry
);

-- Circuit Breaker State
CREATE TABLE IF NOT EXISTS circuit_breaker (
    provider TEXT PRIMARY KEY,
    state TEXT DEFAULT 'closed',     -- closed | open | half-open
    failure_count INTEGER DEFAULT 0,
    last_failure_at TEXT,
    last_reset_at TEXT,
    threshold INTEGER DEFAULT 3,     -- Failures before opening
    reset_timeout INTEGER DEFAULT 30 -- Seconds before half-open
);

-- Event Pipeline (borrowed from ever-gauzy's Jitsu pattern)
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,              -- Event type: market_snapshot, stock_pull, analysis_tick, etc.
    source TEXT NOT NULL,            -- cron | api | manual
    status TEXT NOT NULL,            -- success | error | timeout
    payload TEXT,                    -- JSON blob with context
    start_time TEXT,
    end_time TEXT,
    duration_ms REAL,
    error_trace TEXT,
    created_at TEXT
);

-- Aggregated Data (semantic layer — precomputed metrics)
CREATE TABLE IF NOT EXISTS aggregated_data (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL,
    open REAL,
    high REAL,
    low REAL,
    volume REAL,
    market_cap REAL,
    ma5 REAL,
    ma10 REAL,
    ma20 REAL,
    ma50 REAL,
    ma200 REAL,
    rsi14 REAL,
    volume_ratio REAL,
    price_change_pct REAL,
    price_change_5d REAL,
    price_change_20d REAL,
    sector_rank INTEGER,
    sector_avg_close_pct REAL,
    is_uptrend BOOLEAN,
    is_high_volume BOOLEAN,
    is_breakout BOOLEAN,
    UNIQUE(ticker, date)
);

-- Event archive (for old events > 90 days)
CREATE TABLE IF NOT EXISTS events_archive (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT,
    start_time TEXT,
    end_time TEXT,
    duration_ms REAL,
    error_trace TEXT,
    archived_at TEXT
);
```

#### Enhanced Existing Tables

```sql
-- Add LLM enrichment flag to market_evaluations
ALTER TABLE market_evaluations 
    ADD COLUMN heuristic_eval TEXT,    -- Always available
    ADD COLUMN llm_eval TEXT;          -- Populated when LLM completes

-- Add task reference to market_intelligence
ALTER TABLE market_intelligence 
    ADD COLUMN llm_task_id TEXT;       -- Links to llm_tasks

-- Add last_refreshed to all data tables
ALTER TABLE market_cache 
    ADD COLUMN last_refreshed TEXT;
```

### 5.2 Key Relationships

```
market_intelligence
    │
    ├── llm_task_id → llm_tasks (one pipeline = one task)
    │
    └── [articles] → news_articles (aggregated into brief)

llm_tasks
    │
    ├── result → llm_cache (on completion)
    │
    └── provider → circuit_breaker (monitoring)

portfolio_transactions
    │
    └── symbol → watchlist (cross-reference)
```

---

## 6. Configuration

### 6.1 config.yaml Structure

```yaml
system:
  name: "Jarvis Hub 3.0"
  timezone: "Asia/Saigon"
  version: "3.0.0"

# Database
database:
  primary: "~/jarvis-hub/data/jarvis.db"
  wal_mode: true
  journal_size: "100MB"

# LLM Configuration
llm:
  default_provider: "omlx"
  enabled: true                   # Set to false to disable all LLM
  fallback:
    enabled: true                 # Heuristic fallback enabled by default
    timeout_ms: 5000              # Max wait for LLM before fallback
  omlx:
    base_url: "http://localhost:8000/v1"
    model: "Qwen3.6-35B-A3B-MLX-8bit"
    api_key: ""
    timeout: 120
  ollama:
    url: "http://localhost:11434"
    model: "qwen3.6:35b-a3b-mxfp8"
    api_key: ""
    timeout: 60
  circuit_breaker:
    failure_threshold: 3          # Open after 3 failures
    reset_timeout: 30             # Half-open after 30s
    half_open_max_calls: 1        # 1 probe before closing

# Async Task Queue
queue:
  max_workers: 3
  task_timeout: 300               # Max seconds per task
  cleanup_interval: 3600          # Clean expired tasks every hour
  ttl_hours: 24                   # Default task TTL

# Market Data
market:
  data_source_priority:          # Fallback order
    - vnstock4
    - yahoo_finance
    - cafe_f
  cache_ttl_minutes: 300         # 5 minutes
  refresh_interval_minutes: 30   # Background refresh

# News
news:
  feed_sources:                   # From existing config
    - name: "Cafef Doanh nghiệp"
      url: "https://cafef.vn/doanh-nghiep.rss"
      category: "vn-stock"
      priority: 1
    - name: "VnExpress Kinh doanh"
      url: "https://vnexpress.net/rss/kinh-doanh.rss"
      category: "vn-business"
      priority: 2
    # ... (rest of existing sources)
  enrichment:
    heuristic: true               # Always enabled
    llm: true                     # Enabled when LLM available
    cache_ttl_minutes: 60         # Cache enrichment for 1 hour

# Scheduler
scheduler:
  morning_briefing: "06:18"
  evening_briefing: "23:00"
  market_intelligence:           # New: async pipeline schedule
    enabled: true
    interval_hours: 6            # 06:00, 12:00, 18:00, 00:00
    pre_compute: true            # Pre-compute LLM results
  auto_refresh:                  # New: async data refresh
    enabled: true
    interval_minutes: 30
  llm_health_check:              # New: monitor LLM health
    enabled: true
    interval_minutes: 5

# Logging
logging:
  level: "INFO"                   # DEBUG | INFO | WARNING | ERROR
  file: "~/jarvis-hub/logs/jarvis.log"
  max_bytes: 10485760             # 10 MB
  backup_count: 5                 # Keep 5 rotated files
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Security
security:
  secret_key: "${SECRET_KEY}"     # Env var or config
  admin_password: "${ADMIN_PASSWORD}"  # Env var or config
  jwt_expiry_hours: 24
  max_login_attempts: 5
  lockout_minutes: 15
```

### 6.2 Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SECRET_KEY` | Flask session secret | Random if not set |
| `ADMIN_PASSWORD` | Admin panel password | Required |
| `LLM_PROVIDER` | Override LLM provider | `omlx` from config |
| `DATABASE_URL` | Override database path | `~/jarvis-hub/data/jarvis.db` |
| `DEBUG` | Enable debug mode | `false` |
| `LOG_LEVEL` | Override log level | `INFO` |

---

## 7. Security

### 7.1 Authentication & Authorization

```python
# Middleware pattern
@app.before_request
def require_auth():
    if request.path.startswith('/api/public/'):
        return  # No auth needed
    if request.path.startswith('/api/admin/'):
        return require_admin()  # Admin only
    return require_login()  # Login required

# RBAC roles
ROLES = {
    "admin": ["read", "write", "admin"],
    "analyst": ["read", "write"],
    "viewer": ["read"],
}
```

### 7.2 Data Protection

- Database path not hardcoded — always from config/env
- No secrets in code — all from env vars or config
- API rate limiting: 100 requests/minute per IP
- Input validation: All API parameters validated with Pydantic
- SQL injection: Parameterized queries only (sqlite3)
- XSS: Template escaping (Jinja2 default)

---

## 8. Logging & Monitoring

### 8.1 Structured Logging

```python
import logging

# app.py setup
logging.basicConfig(
    level=config.logging.level,
    handlers=[
        logging.FileHandler(config.logging.file),
        logging.StreamHandler()
    ],
    format=config.logging.format
)

# Usage throughout
logger = logging.getLogger(__name__)
logger.info("Stock analysis started for %s", symbol)
logger.warning("LLM call failed: %s", error)
logger.error("Database connection lost: %s", error)
```

### 8.2 Health Check Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /api/v1/health` | `{"status": "ok", "version": "3.0.0", "uptime": "1d2h"}` |
| `GET /api/v1/health/db` | `{"status": "ok", "tables": 15, "size_mb": 2.5}` |
| `GET /api/v1/health/llm` | `{"omlx": "healthy", "ollama": "unhealthy"}` |
| `GET /api/v1/health/queue` | `{"queued": 3, "running": 1, "completed": 42}` |
| `GET /api/v1/health/cache` | `{"hits": 150, "misses": 30, "hit_rate": 0.83}` |

---

## 9. Deployment

### 9.1 Docker (Phase 4)

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SECRET_KEY=changeme
ENV ADMIN_PASSWORD=changeme
ENV LLM_PROVIDER=omlx

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

### 9.2 systemd Service

```ini
# /etc/systemd/system/jarvis-hub.service
[Unit]
Description=Jarvis Hub 3.0
After=network.target

[Service]
Type=simple
User=nghialam
WorkingDirectory=/opt/jarvis-hub
Environment=SECRET_KEY=${SECRET_KEY}
Environment=ADMIN_PASSWORD=${ADMIN_PASSWORD}
Environment=LLM_PROVIDER=omlx
ExecStart=/opt/jarvis-hub/venv/bin/python -m gunicorn --bind 0.0.0.0:5000 --workers 4 app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 9.3 Quick Start Script

```bash
#!/bin/bash
# jarvis-hub setup

set -e

echo "🚀 Jarvis Hub 3.0 Setup"

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Initialize database
python -m core.db init
echo "✅ Database initialized"

# Start
python app.py
echo "✅ Jarvis Hub started at http://localhost:5000"
```

---

## 10. Migration Strategy (v2.0 → v3.0)

### 10.1 Data Migration

```python
# scripts/migrate_v2_to_v3.py
def migrate():
    """Migrate v2.0 database to v3.0 schema."""
    db = Database(config.database.primary)
    
    # Add new tables
    db.execute("""
        CREATE TABLE IF NOT EXISTS llm_tasks (
            task_id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            fn_name TEXT NOT NULL,
            args_json TEXT,
            provider TEXT DEFAULT 'omlx',
            timeout INTEGER DEFAULT 30,
            priority TEXT DEFAULT 'normal',
            status TEXT DEFAULT 'queued',
            result TEXT,
            error TEXT,
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            expire_at TEXT
        )
    """)
    
    # Add columns to existing tables
    db.execute("ALTER TABLE market_evaluations ADD COLUMN heuristic_eval TEXT")
    db.execute("ALTER TABLE market_evaluations ADD COLUMN llm_eval TEXT")
    db.execute("ALTER TABLE market_intelligence ADD COLUMN llm_task_id TEXT")
    
    # Create fallback data (run heuristic analysis on existing records)
    db.execute("""
        UPDATE market_evaluations 
        SET heuristic_eval = ? 
        WHERE heuristic_eval IS NULL
    """, (generate_heuristic_eval(),))
    
    print("✅ Migration complete")
```

### 10.2 Backward Compatibility

- All v2.0 API routes continue to work (with alias redirects)
- `/api/analyze?symbol=X` → `/api/v1/stocks/analyze?symbol=X` (automatic redirect)
- Frontend can work with either v2 or v3 API endpoints
- Database is forward-compatible (v3 can read v2 data)

### 10.3 Rollback Plan

- Keep v2.0 codebase as backup (`app.py.bak.v3-rollback`)
- Database migrations are additive (never destructive)
- Configuration file is separate from code
- All data preserved in SQLite (no external dependencies for migration)

---

## 11. Risk Assessment & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SQLite write contention | Low | Medium | WAL mode, connection pooling, lock_timeout |
| Thread safety in queue | Medium | High | Use queue.Queue (thread-safe), SQLite WAL |
| Memory leaks in workers | Low | Medium | Daemon threads, periodic worker reset |
| Cache bloat | Medium | Low | TTL-based expiry, periodic cleanup |
| Frontend breaking during migration | Medium | High | Backward compatibility layer, gradual rollout |
| LLM provider downtime | High | Low | Circuit breaker + heuristic fallback |
| Security breach | Low | Critical | RBAC, input validation, rate limiting |

---

## 12. Success Metrics

| Metric | Current (v2.0) | Target (v3.0) |
|--------|----------------|---------------|
| API response time (analyze) | 15-30s (LLM blocking) | <200ms (heuristic) + async LLM |
| LLM failure rate | System hangs | Circuit breaker → immediate fallback |
| Heuristic fallback usage | 0% (not wired) | 100% of endpoints |
| System uptime without LLM | ~60% (partial data) | 100% (full operation) |
| Database file count | 3 (duplicate schemas) | 1 (consolidated) |
| Code complexity | 84 routes in 1 file | Modular blueprints |
| Test coverage | 0% automated | >60% critical paths |
| Deployment time | Manual, undocumented | <5 minutes (Docker/script) |

---

## 13. Summary

Jarvis Hub 3.0 is a complete architectural overhaul that transforms the system from a **LLM-dependent monolith** into a **resilient, async-first intelligence engine**. The key changes:

1. **LLM is always optional** — heuristics are the default, LLM is an upgrade
2. **Async-first** — LLM calls run in background threads
3. **Circuit breaker** — LLM failures don't cascade
4. **Pre-compute** — LLM results cached and refreshed on schedule
5. **Modular** — Clean separation of concerns with blueprints
6. **Secure** — Auth, RBAC, secret management
7. **Observable** — Structured logging, health checks, metrics
8. **Deployable** — Docker, systemd, bootstrap script

This design ensures the system remains fully operational regardless of LLM availability, while providing a seamless upgrade path to richer intelligence when LLM is available.
