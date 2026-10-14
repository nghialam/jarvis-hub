# Jarvis Hub — Vietnamese Stock Market Intelligence Portal

A Flask-based local web dashboard for Vietnamese stock market intelligence, combining real-time market data, news aggregation, LLM-powered summarization, portfolio screening, and autonomous 6-hour Market Intelligence Agent. Now with **persistent semantic memory**, **performance optimizations**, and **resilient delivery**.

## Features

### Market Data & Analysis
- **Market Overview** — VN-Index, HNX-Index, VN30 with live charts (Chart.js)
- **Parallel Data Fetching** — All market sources fetched concurrently via ThreadPoolExecutor; dashboard load reduced from ~30s to ~3-6s
- **Crypto, Gold, Oil & FX Rates** — Live prices with cached fallback (dynamic TTL by market hours: shorter during trading, 4× longer after close)
- **Technical Analysis** — RSI, SMA, MACD, Bollinger Bands calculations for watchlist symbols

### News & Intelligence
- **News Aggregator** — RSS feeds from Cafef, VnExpress, Reuters, BBC, TechCrunch, Ars Technica; parallel fetch with ThreadPoolExecutor (5× faster)
- **Company News & Screens** — Scan Vietnamese listed companies for breaking news and signals
- **Broker Reports** — Aggregate research reports from SSI, VCI, HCM with consensus summaries
- **Market Intelligence Agent** — Autonomous 6-hour cycle pipeline: ingest → parse → LLM analyze → synthesize brief → deliver to DB + notifications

### 🧠 Persistent Memory System (NEW v4.0)
- PostgreSQL + pgvector for semantic memory storage
- Ollama `bge-m3` embeddings (1024 dimensions, local inference)
- **CRUD**: Create, Retrieve, Update, Delete memory conclusions and memdocs
- **Semantic search** with cosine similarity scoring (~0.74+ accuracy)
- **Session tracking** — group memories by peer for multi-session context
- Dashboard UI at `/hub2/memory` — stats panel, filtered lists, live search, add/edit modals

### 💬 Resilient Delivery
- **Telegram alerts** via Bot API + openclaw fallback
- **Circuit breaker** (5-failure threshold before opening)
- **Dead-letter queue** with exponential backoff (30s → 90s → 5min retries)
- **Admin alerting** — notifies `JARVIS_TELEGRAM_ADMIN_CHAT_ID` on retry exhaustion

### CMS & Knowledge Base
- **Article Management System** — Full CRUD for CMS articles via admin panel at `/cms`
- **Markdown rendering** with XSS sanitization (bleach + markdown libraries)
- **Soft-delete pattern** — draft → published → unpublished lifecycle
- **Knowledge base search** via semantic retrieval

## Reliability & Performance Optimizations (Oct 2026)

### Database & Memory
| Optimization | Impact |
|---|---|
| PostgreSQL connection pooling (5-20 pooled conns via `psycopg2.pool.SimpleConnectionPool`) | Zero connect latency overhead on memory queries |
| SQLite indexes: watchlist(symbol), trading_alerts(timestamp DESC), market_evaluations(date DESC) | O(log n) lookups vs table scans |
| PG indexes: memdocs(peer_id), sessions(peer_id, created_at DESC) | Sub-100ms search even at 5k+ records |

### Caching
| Setting | Trading Hours | Off-Hours |
|---|---|---|
| Market data cache | 300s (5 min) | 1200s (20 min, 4× longer) |
| RSS feeds | 300s | 1200s |
| LLM response cache | 300s base + hot-key promotion (≥50 hits → 4× TTL) | — |
| Max LRU eviction at count | 500 entries, oldest-first removal | — |

### Concurrency
| Module | Pattern | Speed |
|---|---|---|
| `market_overview.py` | ThreadPoolExecutor(max_workers=10), per-task timeout 5-15s | 3‑10× faster |
| `data_collector.py` | Parallel RSS + commodity fetches, first-wins fallback | ~3× faster |
| `news_service.py` | Parallel feed fetching with graceful failure per-source | — |

### Signal & Alert Monitoring
| Before | After |
|---|---|
| Tight `time.sleep(10)` polling loops | APScheduler / threading.Timer with 5-min intervals (`AUTO_SCAN_INTERVAL`) |
| Thread-blocking synchronous scans | Non-blocking event-driven scheduling with graceful SIGTERM/SIGINT shutdown |

## Architecture

```
┌─────────────────────── frontend (HTML/CSS/JS + Chart.js) ─────────────────────────┐
│  Tabs: Market Overview | News Aggregator | Company News | Reports | Screener | CMS | Memory
└────────────────────────────────────────────┬───────────────────────────────────────┘
                                             │ Flask REST API
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
             vnstock3 / DNSE          News RSS + Web         Broker Websites
             (OHLCV market data)    Parallel fetcher        (SSI, VCI, HCM)
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
           PostgreSQL (pgvector)      SQLite DB              LLM Pipeline
          jarvis_hub_memory          (jarvis.db ~44 tables)    Qwen3.8 27B
             + Ollama bge-m3           CMS article data    (mlx-lm / omlx)
            semantic memory store                                                   
                    ┌──────────────────────────┐
                    ▼                          ▼                         
               Telegram              Cron Scheduler
             Bot API + DLQ           APScheduler + Hermes Agent
          Dead-letter queue,           
          circuit breaker,             
          exponential backoff          
```

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML/CSS/JS + Chart.js (dark theme, responsive SPA) |
| Backend | Flask (REST API, PostgreSQL + SQLite caching) |
| Memory | PostgreSQL + pgvector vector search; Ollama `bge-m3` embeddings |
| Data | vnstock4 / VNstock MCP / DNSE API (OHLCV), RSS feeders for news |
| LLM | Qwen3.8-27B via mlx-lm (Apple Silicon native) or omlx provider |
| Database | **PostgreSQL** (`jarvis_hub_memory`, pgvector, connection pooled 5-20) + **SQLite** (`jarvis.db`, ~44 tables, indexed) |
| Scheduling | APScheduler cron + threading.Timer event-driven signal monitoring |
| Delivery | Telegram Bot API (circuit breaker + dead-letter queue with backoff) + cms article management |

## Quick Start

### Prerequisites

- macOS with Apple Silicon (for mlx-lm inference) — Mac Mini M4 Pro recommended
- Python 3.10+
- Ollama running locally (`http://localhost:11434`) with `qwen3.8:27b-mxfp8` or `bge-m3` loaded
- PostgreSQL (v14+) with `pgvector` extension installed and running on port 5432

### Installation

```bash
git clone https://github.com/nghialam/jarvis-hub.git
cd jarvis-hub

# Venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# PostgreSQL setup (pgvector)
createdb jarvis_hub_memory
psql jarvis_hub_memory -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Migrate SQLite indexes (jarvis.db)
python scripts/apply_indexes.py

# Start the server
python app.py --port 8100
```

Dashboard available at: http://localhost:8100/hub2
Memory dashboard:    http://localhost:8100/hub2/memory
CMS admin panel:     http://localhost:8100/cms

### Config

Edit `config.yaml`:

```yaml
system:
  name: "Jarvis Hub"
  timezone: "Asia/Saigon"

telegram:
  target_chat_id: "YOUR_CHAT_ID"
  admin_chat_id: "ADMIN_CHAT_ID"       # for death-alert routing
  openclaw_path: "/opt/homebrew/bin/openclaw"

ollama:
  url: "http://localhost:11434"
  # Embedding model for persistent memory
  embedding_model: "bge-m3"
  # LLM for market analysis
  model: "qwen3.8:27b-mxfp8"

# Memory system — PostgreSQL connection (used by core/local_memory_plugin)
pg_memory:
  host: "127.0.0.1"
  port: 5432
  dbname: "jarvis_hub_memory"
  user: "nghialam"
  pool_min: 5
  pool_max: 20

feed:
  sources:
    - name: "Cafef Doanh nghiệp"
      url: "https://cafef.vn/doanh-nghiep.rss"
      category: "vn-stock"
```

Environment variables (optional overrides):
- `FLASK_SECRET_KEY` — Flask session encryption key
- `JARVIS_TELEGRAM_CHAT_ID` — Telegram destination channel/group
- `JARVIS_TELEGRAM_ADMIN_CHAT_ID` — Admin alert destination for DLQ exhaustion
- `JARVIS_BOT_TOKEN` — Telegram Bot API token (used as fallback transport)
- `AUTO_SCAN_INTERVAL` — Signal monitor scan interval in seconds (default: 300 = 5 min)

## Cron Jobs

Integrated scheduled tasks (via Hermes Agent + APScheduler):

| Job | Schedule | Description |
|-----|----------|-------------|
| Daily News Aggregation | Weekdays 06:00 SGT | Scans RSS feeds, aggregates & summarizes Vietnamese market news |
| Daily Market Information | Weekdays 06:30 SGT | Fetches VN indices, exchange rates, crypto, gold, oil data (parallel) |
| Daily Stock Recommendations | Weekdays 09:30 SGT | Screens stocks, generates buy/sell recommendations |
| Monthly Fundamental Screening | 1st Mon 07:00 SGT | Full fundamental screening across VN-listed companies |
| **Market Intelligence Agent** (NEW) | Every 6h (06:00, 12:00, 18:00, 00:00) | Full pipeline: ingest → parse → LLM analyze → synthesize Market Brief → deliver to DB + notifications |
| **Precompute Scheduler** (NEW v4.0) | Every 5 min | Queues LLM tasks for trending analysis; runs after each data refresh cycle |

## Project Structure

```
jarvis-hub/
├── app.py                  # Flask dashboard application v4.0 (updated Oct 2026)
├── cli.py                  # CLI interface
├── config.yaml             # Configuration
├── README.md               # This file
├── core/                   # Core modules
│   ├── cache_manager.py    # Dynamic TTL + LRU hot-key caching
│   ├── config.py           # Config loader
│   ├── context.py          # Shared DB/context injector for blueprints
│   ├── data_collector.py   # Parallel RSS/commodity fetcher with fallback
│   ├── db.py               # SQLite database layer (~44 tables)
│   ├── llm_cache.py        # LLM response cache with LRU eviction
│   ├── market_overview.py  # Parallel Yahoo Finance index & ticker fetching
│   ├── news_service.py     # Parallel RSS feed fetching
│   ├── telegram_delivery.py# Telegram delivery with dead-letter queue + circuit breaker
│   ├── local_memory_plugin/         # Persistent memory: PostgreSQL + pgvector + Ollama
│   │   ├── __init__.py
│   │   ├── config.py             # Config schema & PG defaults
│   │   ├── embedding_client.py   # bge-m3 embedder via Ollama /api/embed
│   │   ├── memory_manager.py     # CRUD + semantic search (connection pooled)
│   │   ├── plugin_adapter.py     # Flask Blueprint integration + routes
│   │   └── vector_store.py       # pgvector operations + similarity search
│   └── market_intelligence/  # Market Intelligence Agent pipeline
│         ├── ingestion.py     # Stage 1: RSS/web scraper for last 6h
│         ├── parsing.py       # Stage 2: HTML stripping, text cleaning
│         ├── analyst.py       # Stage 3: LLM Analyst (summary + sentiment)
│         ├── synthesizer.py   # Stage 4: LLM Strategist (Market Brief)
│         └── delivery.py      # Stage 5: DB persistence + notification trigger
├── api/                    # Flask blueprints (v1/v2, CMS, memory)
│   ├── __init__.py         # Blueprint registration (collision-tolerant)
│   ├── news.py             # News aggregation routes
│   ├── market.py           # Market overview & technical analysis routes
│   └── portfolio.py        # Portfolio/stock screen routes
├── core/precompute_scheduler.py  # Auto LLM task queue for trending analysis
├── services/ai_signal_monitor.py   # Event-driven signal scanning (APScheduler / Timer)
├── workers/alert_monitor.py        # Event-driven alert monitoring loop
├── dashboard/              # Frontend (templates + static assets)
│   ├── templates/hub2.html    # Main dashboard
│   ├── templates/memory.html  # Memory management UI
│   └── templates/cms.html     # CMS admin panel
├── daily/                  # Daily briefing outputs
├── backups/                # DB & config backups
├── scripts/
│   ├── migrate_indexes.sql    # PostgreSQL + SQLite index creation SQL
│   ├── apply_indexes.py       # Auto-executor with backup + verification
│   └── jhrs-regression-tests.py  # Automated regression tests for all API routes
└── .bak/                   # Safety backup directory (Golden Rule: never delete without backup)
```

## Deployment

### Vercel + Cloudflare Tunnel

For remote access:
- Frontend served via Vercel CDN
- Backend proxies route to local Mac Mini via Cloudflare tunnel (port 8100)
- Graceful degradation when Mac is offline
- RSS cron runs daily on Vercel at 06:25 UTC (1:25 PM SGT)

### Systemd Service (Linux/Docker)

Create `/etc/systemd/system/jarvis-hub.service`:
```ini
[Unit]
Description=Jarvis Hub Flask Dashboard
After=network.target postgresql.service

[Service]
Type=simple
User=nghialam
WorkingDirectory=/opt/jarvis-hub
ExecStart=/opt/jarvis-hub/venv/bin/python3 app.py --port 8100
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Tech Notes

- **vnstock prices**: All prices returned in "nghìn đồng" (thousands of VND) — multiply by 1000 for actual VND values. Raw price < 1000 is a red flag.
- **Yahoo Finance VN stocks**: Require `.VN` suffix (e.g., `VIC.VN`) — auto-appended if missing
- **Local ML inference**: Ollama on Apple Silicon (MLX runtime) or omlx provider for Qwen3.8 27B
- **PostgreSQL pgvector**: Cosine similarity via `<=>` operator; use `ivfflat` index when memdocs >10k for fast recall
- **Circuit breaker default**: Telegram delivery failures → opens at 5 consecutive failures → half-open after 60s cooldown
- **Dead-letter queue**: Retries with exponential backoff (30s, 90s, 300s); admin alerted on all-retry exhaustion per `(chat_id, delivery_type)` session

## Reliability Features Summary (Oct 2026)

| Feature | Detail |
|---------|--------|
| **DB Connection Pooling** | PostgreSQL `SimpleConnectionPool(min=5, max=20)` — zero connect overhead |
| **Dynamic Cache TTL** | 4× longer when VN market is closed (off-hours reduce DB cache misses) |
| **SQLite Indexes** | 8+ new indexes on watchlist, alerts, evaluations, research_items, briefings |
| **PG Indexes** | 5+ new indexes on memdocs, sessions for sub-100ms memory queries |
| **Parallel Market Data** | ThreadPoolExecutor with per-call timeout — dashboard ~10× faster |
| **Signal Monitor** | Event-driven scheduling (5-min intervals via APScheduler/Timer), no tight polling |
| **Telegram DLQ** | Dead-letter queue, retry backoff, admin alert on exhaustion — much more reliable delivery |
| **CMS System** | Full article CRUD with markdown rendering, soft-delete, category filtering |
| **Persistent Memory** | pgvector semantic retrieval + LLM-powered conclusions — full CRUD via API and UI |

---

**Built with ❤️ on Mac Mini M4 Pro (64 GB)** for efficient local AI-powered market analysis.  
Version: **v4.0.0** — Oct 14, 2026
