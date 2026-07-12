# Jarvis Hub 2.0 — Architecture & Design Doc

**Version:** v2.0 | **Last Updated:** 2026-06-28

---

## System Overview

Jarvis Hub is a **local finance intelligence platform** consisting of:

```
┌───────────────┐    ┌──────────────────┐    ┌───────────────┐
│  Yahoo        │    │ vnstock4 (KBS/   │    │ Binance       │
│  Finance API  │    │  VCI sources)    │    │ Crypto API    │
│  VN indices,  │    │                  │    │ BTC/ETH/SOL   │
│  stocks, gold │    │                  │    │               │
└───────┬───────┘    └────────┬─────────┘    └───────┬───────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Jarvis Hub 2.0 — Flask Server (port 8100)       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌─────────┐  │
│  │ Web UI   │   │ REST     │   │ AI       │   │ Signal  │  │
│  │(Hub2/AI) │   │ API      │   │ Intel    │   │ Engine  │  │
│  └────┬─────┘   └────┬─────┘   └──────────┘   └─────────┘  │
│       └──────────┬────┘                                    │
│                  ▼                                          │
│          ┌───────────────┐                                  │
│          │ Cache Layer    │ ◄ TTL-based, circuit breaker     │
│          │ LLMResponseCache │ + per-key TTL eviction        │
│          └───────┬───────┘                                  │
└──────────────────┼──────────────────────────────────────────┘
                   │
         ┌─────────┼──────────────┐
         ▼         ▼              ▼
    ┌────────┐  ┌──────┐   ┌──────────┐
    │SQLite  │  │Ollama│   │Telegram  │
    │jarvis.db│ │:11434│   │ Bot      │
    │(38+ tbs)│ │Qwen3.6│  │ :1670013239│
    └────────┘  └──────┘   └──────────┘
```

---

## Architecture Layers

### Layer 1: Data Sources

| Source | Purpose | Endpoint / Method |
|--------|---------|-------------------|
| **Yahoo Finance** | VN indices, VN stocks, global indices, crypto, gold, oil, DXY | `v8/finance/chart/{symbol}` + `v7/download` CSV fallback |
| **vnstock4** | Primary VN stock OHLCV from KBS/VCI | `Market().equity(sym).ohlcv(start, end, resolution)` |
| **Binance** | Crypto prices (BTC, ETH, SOL) | `api/v3/ticker/24hr?symbol=BTCUSDT` |
| **Vietcombank** | USD/VND exchange rates | Web scraping HTML |
| **RSS Feeds** | News articles from Cafef, VnExpress, Reuters, etc. | `feedparser` parsing with deduplication |

### Layer 2: Core Engine (`core/`)

#### Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| **config.py** | YAML config loader with dot-notation access | `load_config()`, `get(key)`, `reload_config()` |
| **db.py** | SQLite database layer (38+ tables) | `Database()` class with thread-safe CRUD |
| **news.py** | RSS fetching + 2-layer sentiment analysis | `fetch_rss_feeds()`, `enrich_article()`, `heuristic_sentiment()`, `llm_sentiment()` |
| **market.py** | Stock/gold/crypto analysis + TA indicators | `analyze_stock()`, `fetch_gold_price()`, `fetch_crypto()` |
| **market_service.py** | Unified market data service with cache | `MarketService.analyze_stock()`, `_calculate_technical_indicators()`, `MarketCache` |
| **market_overview.py** | Hub 2.0 overview dashboard fetcher | `fetch_all_overview()`, `get_top_motions()`, `fetch_vn_indices()`, `fetch_global_indices()` |
| **vnstock4_provider.py** | vnstock4 wrapper for VN stock OHLCV | `fetch_daily_ohlcv(s, days, use_vci)` — applies x1000 multiplier |
| **news_engine.py** | Enhanced news engine (Hub 2.0) | `fetch_all_news()`, `_heuristic_sentiment()`, `save_news_to_db()` |
| **news_service.py** | News service with threading cache | `get_articles()`, `get_exchange_rates()`, `_NewsCache` |
| **llm_cache.py** | TTL + circuit breaker for LLM calls | `LLMResponseCache.get_or_call(circuit_threshold=3, recovery_window=60s)` |
| **ollama_client.py** | Ollama (mlx-lm) API client | `ollama_call(prompt)`, `ollama_parse_json(prompt)` |
| **research_crawler.py** | Brokerage report crawler (SSI, VCI, HCM, TCBS, VCBS) | `crawl_all_brokers()`, `store_reports()`, `generate_llm_summary()` |
| **tier_data_collector.py** | Tier 1: Raw data collection (NO LLM) | `run_collection()` → feeds `market_quotes` & `news_articles` tables |
| **tier_llm_analyst.py** | Tier 2: LLM analysis pipeline | `run_analysis()` → calls Ollama, cleans preamble, saves `analytical_reports` |

### Layer 3: Database (`jarvis.db` — 38 tables)

#### Core Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **knowledge** (+ FTS) | 42 | Financial term dictionary with full-text search |
| **activity_log** | 1 | System command and CLI run logs |
| **watchlist** | 14 | User watchlist symbols |
| **watchlist_symbols** | 29 | Extended watchlist |
| **portfolio_watchlist** | 4 | Portfolio watchlist with sector tagging |

#### Market Data Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **market_quotes** | 24 | Live/last prices for tracked tickers (VN stocks, indices, crypto, commodities) |
| **market_overview** | 8 | Pre-computed overview data for fast dashboard load |
| **daily_ohlcv** | 20 | Daily OHLCV time-series per ticker |
| **price_history** | 20 | Price history records |
| **meta** | 11 | Metadata/cache entries |

#### News & Intelligence Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **news_articles** | 48 | Aggregated news headlines with category/sentiment |
| **news_enhanced** | 64 | Enhanced news with sentiment scores and importance |
| **news_enrichment** | 0 | LLM-scored news results (pending enrichment pipeline) |
| **entity_mentions** | 0 | Ticker/company mentions in articles |

#### AI / Intelligence Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **analytical_reports** | 12 | Tier 2 LLM analysis results with confidence scores |
| **articles_images** | 0 | Images associated with news articles |
| **recommendations** | 1 | AI-generated recommendations from runs |
| **run_chains** | 14 | AI intelligence pipeline run metadata |

#### Signal & Alert Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **signals_log** | 6 | Trading bot signal records |
| **trading_alerts** | 9 | Auto-scan trading alerts with RSI/MACD signals |
| **alerts** | 0 | User-configured price/volume alerts (empty) |

#### Memory & Evaluation Tables
| Table | Rows | Purpose |
|-------|------|---------|
| **memories** (+ FTS) | 28 | Persistent memory entries with full-text search |
| **memories_archive** | 0 | Archived memories |
| **market_evaluations** | 15 | Daily market evaluation reports (LLM-generated) |
| **market_evaluation** | 0 | Older evaluation table (legacy, empty) |
| **daily_snapshots** | 2 | Daily briefing snapshots |

---

## Data Flow

```
User Request (Web/CLI/Cron)
         │
         ▼
  ┌──────────┐     ┌──────────────┐
  │ Flask    │────▶│ Cache Check   │ Hits → return cached
  │ Route    │     │ (TTL: 1-24h)  │ Misses → fetch fresh
  └────┬─────┘     └──────┬───────┘
       │                   ▼
       │          ┌────────────────┐
       │          │ Data Source    │
       │          │ Yahoo/vnstock4/Binance/rates/rss/news/LM
       │          └────────┬───────┘
       │                   ▼
       │          ┌────────────────┐     ┌──────────┐
       │          │ TA Engine      │────▶│ Market   │
       │          │ RSI, SMA20,    │     │ DB       │
       │          │ MACD, BBands   │     └──────────┘
       │          └────────────────┘
       │                   │
       │              ┌────▼─────┐
       │              │ Ollama   │ ◄─ Tier 2 analysis (streaming mode)
       │              │ LLM      │     ── Qwen3.6:35b-a3b-mxfp8
       │              └──────────┘
       │                   │
       ▼                   ▼
  ┌──────────┐     ┌──────────────┐
  │ Response │ ◀──│ JSON to user │
  └──────────┘     └──────────────┘
```

---

## Cache Strategy

**LLMCache (`llm_cache.py`)**:
- TTL: 300 seconds (5 minutes) default per-key
- Circuit breaker: opens after 3 consecutive failures, recovers after 60s half-open probe
- Max size: 500 entries with LRU eviction
- Thread-safe with `threading.Lock()`

**MarketCache (`market_service.py`)**:
| Category | TTL |
|----------|-----|
| Stock prices | 300s (5 min) |
| Crypto prices | 60s (1 min) |
| Gold | 300s |
| DXY | 300s |
| Oil | 300s |
| FX rates | 60s |
| Indices | 300s |

**NewsCache (`news_service.py`)**:
| Category | TTL |
|----------|-----|
| Articles | 180s (3 min) |
| Exchange rates | 60s (1 min) |

---

## Database Schema

WAL journal mode, busy timeout 5 seconds, foreign keys enabled.
All datetime stored as ISO strings.

### Key Relationships

```
knowledge ──FTS──▶ knowledge_fts (FULL TEXT INDEX)
memories ──FTS──▶ memories_fts (FULL TEXT INDEX)

run_chains ──1:N──▶ articles ──1:N──▶ articles_images
run_chains ──1:N──▶ recommendations

market_quotes (live prices, refreshed by Tier 1 cron / manual API calls)
└─ feeds ──▶ analytical_reports (LLM analysis per run)

signals_log ←── AI signals from bot/auto-scan
trading_alerts ←── auto_scan endpoint RSI/MACD-based alerts

market_evaluations ←── stored LLM-generated market assessments
daily_snapshots ←── daily briefing content saved by CLI/app
```

---

## API Endpoints (Summary)

### Legacy Routes (`/api/*`)
| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Dashboard homepage (`index.html`) |
| `/hub2` | GET | Hub 2.0 dashboard (`hub2.html`) |
| `/api/search?q=TERM` | GET | Search knowledge base |
| `/api/analyze?symbol=X` | GET | Analyze stock/gold/crypto with TA + LLM report |
| `/api/activities?limit=50` | GET | Recent activity logs |
| `/api/watchlist` | GET | Get watchlist symbols |
| `/api/watchlist/add` | POST | Add symbol to watchlist |
| `/api/watchlist/remove` | POST | Remove symbol from watchlist |
| `/api/snapshots` | GET | Last 5 daily briefing snapshots |
| `/api/daily-snapshot/<date>` | GET | Full snapshot for date |
| `/api/articles?category=VN` | GET | RSS articles (DB-backed or live fetch) |
| `/api/market-evaluation` | GET | Most recent market evaluation |
| `/api/market-evaluation/generate` | POST | Force LLM to generate new evaluation |
| `/api/market-evaluation/history` | GET | Historical evaluations |
| `/api/health` | GET | Health check (ollama status, cache age, data levels) |
| `/api/indices` | GET | VN + global indices from DB |
| `/api/signals?signal=BUY&symbol=X` | GET | Unified signal feed (signals_log + trading_alerts) |
| `/api/signals/latest?limit=20` | GET | Latest N signals for grid view |
| `/api/signals/symbol/X` | GET | All signals for symbol X |
| `/api/signals/add` | POST | Manually create a tracking signal |
| `/api/signals/mark-delivered` | POST | Mark signal as delivered |
| `/api/alert-feed?signal=BUY&severity=HIGH` | GET | Trading alerts with filters |
| `/api/alert-feed/auto-scan` | GET | Trigger auto-scan of watchlist |
| `/api/alert-feed/clear` | POST | Mark all alerts as read |
| `/api/signal/feed/clear` | POST | Alias for alert-feed/clear |
| `/api/auto-scan` | GET | Alias for alert-feed/auto-scan |
| `/logs` | GET | System logs (activity + signals + trading_alerts combined) |

### Hub 2.0 API (`/api/v1/*`)
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v1/overview` | GET | Full market overview (indices, crypto, gold, oil, DXY + top motions) |
| `/api/v1/overview/indices` | GET | VN + global indices as arrays |
| `/api/v1/overview/crypto` | GET | Crypto prices |
| `/api/v1/overview/gold` | GET | Gold price |
| `/api/v1/overview/motions?limit=10` | GET | Top gainers/losers |
| `/api/v1/overview/chart?symbol=X` | GET | Chart data for symbol |
| `/api/v1/news?category=all&sentiment=all&limit=50&days=7` | GET | Enhanced news with filters |
| `/api/v1/news/trending` | GET | High-importance trending news |
| `/api/v1/news/score` | POST | Score news articles using LLM |
| `/api/v1/companies?q=VIC` | GET | Search companies by symbol/name |
| `/api/v1/companies/VIC/news` | GET | News for specific company |
| `/api/v1/research?broker=SSI&period=1m` | GET | Brokerage reports with filters |
| `/api/v1/research/stats` | GET | Report stats per broker |
| `/api/v1/research/crawl` | POST | Trigger research crawl (SSI, VCI, HCM, TCBS, VCBS) |
| `/api/v1/watchlist/portfolio` | GET | Portfolio watchlist |
| `/api/v1/watchlist/portfolio/add` | POST | Add to portfolio watchlist |
| `/api/v1/watchlist/portfolio/remove` | POST | Remove from portfolio watchlist |
| `/api/v1/market/heatmap` | GET | Sector performance heatmap data |
| `/api/v1/market/auto-refresh/trigger` | POST | Manual data refresh |

### AI Intelligence API (`/api/v2/*`)
| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v2/ai-intelligence/daily-list` | GET | List of run dates with article counts |
| `/api/v2/ai-finance/run/<run_id>` | GET | Run detail: articles, recommendations, metadata |
| `/api/v2/ai-finance/health` | GET | Pipeline health + last run status |

### Health Endpoint (`/health`)
Returns: `status`, `timestamp`, `flask`, `db`, `ollama` (healthy/unhealthy/unreachable)

---

## Cron Jobs (7 active, Hermes Agent)

All jobs run on `qwen3.6:35b-a3b-mxfp8` via Ollama (`localhost:11434`), deliver to Telegram chat `1670013239`.

| Job | Schedule | Purpose |
|-----|----------|---------|
| **Daily News & Strategy Briefing** | Every day 06:00 GMT+7 | Market data + VN/global news → investment recommendations |
| **Jarvis Auto-Update Pipeline** | Mon–Fri 08:45 | System health, code analysis, auto-maintenance |
| **Memory Compact** | Sundays 09:00 | Weekly hindsight recall synthesis + pattern detection |
| **Daily Memory Update** | Every day 23:00 | Auto-retain durable facts into Hindsight memory store |
| **Backlog Sync** | Every day 22:00 | Update BACKLOG.md with new items, re-prioritize |
| **Auto-Improvement Engine** | Every day 01:00 | Detect recurring patterns, promote to SKILL.md best practices |
| **Memory Regression Test** | Every day 02:00 | Validate Hindsight + Builtin memory systems |

---

## Security & Privacy

- **No external data transmission** — all analysis runs locally via Ollama
- **API keys stored** in `config.yaml` (never committed to git)
- **SQLite database** — single file, easy backup at `~/jarvis-hub/knowledge/jarvis.db`
- **No authentication required** — intended for single-user local use only
- **Rate limiting** — Yahoo Finance API calls throttled; vnstock4 has per-symbol retries

---

## Performance Characteristics

| Component | Strategy |
|-----------|----------|
| Cache | Thread-safe TTL dict with per-key expiration + circuit breaker |
| LLM | Prompt hashing + TTL cache (300s) to avoid redundant Ollama API calls |
| Database | SQLite with FTS5 for fast full-text search on knowledge base and memories |
| Parallelism | `ThreadPoolExecutor` for concurrent RSS fetches, index fetches, overview data |
| Pagination | CLI `log` command defaults to 20 entries; API limits capped at 100-200 |
| VN Stock Price Conversion | vnstock4 returns "nghìn đồng" — x1000 multiplier applied everywhere (vn stock + TA) |

---

## File Structure

```
jarvis-hub/
├── app.py                    # Flask web server (main entry point, port 8100)
├── cli.py                    # CLI tool via Click (briefing, analyze, watch, search, quiz, log, history, doctor)
├── config.yaml               # Configuration: Ollama/Ollama, feeds, schedule, db_path
├── vnstock4_provider.py      # vnstock4 OHLCV wrapper with VND multiplier
├── seed_kb.py                # Seed knowledge base entries
├── core/                     # Core engine package
│   ├── __init__.py
│   ├── config.py              # YAML config loader (dot-notation access)
│   ├── db.py                  # SQLite database layer (38+ tables, thread-safe CRUD)
│   ├── news.py               # RSS fetching + 2-layer sentiment analysis
│   ├── market.py             # Stock/gold/crypto analysis + TA indicators
│   ├── market_service.py     # Unified market service with MarketCache + circuit breaker
│   ├── market_overview.py    # Hub 2.0 overview dashboard fetcher (VN+global+crypto+gold)
│   ├── vnstock4_provider.py  # vnstock4 wrapper for VN stocks
│   ├── news_engine.py        # Enhanced news engine for Hub 2.0
│   ├── news_service.py       # News service with threading cache
│   ├── llm_cache.py          # TTL + circuit breaker for LLM responses
│   ├── ollama_client.py        # Ollama (mlx-lm) API client
│   ├── research_crawler.py   # Brokerage report crawler (SSI, VCI, HCM, TCBS, VCBS)
│   ├── tier_data_collector.py# Tier 1: Raw data collection (feeds market_quotes/news_articles)
│   └── tier_llm_analyst.py   # Tier 2: LLM analysis pipeline with preamble cleanup
├── dashboard/
│   ├── templates/
│   │   ├── index.html        # Legacy dashboard
│   │   ├── hub2.html          # Hub 2.0 Market Intelligence Portal
│   │   └── ai_intelligence.html # AI Intelligence Dashboard
│   ├── static/css/style.css
│   └── static/js/app.js
├── docs/                     # Documentation (you're here)
├── scripts/                   # Helper scripts for cron jobs, analysis, maintenance
│   ├── gotham_brief.py        # Gotham brief generator
│   ├── jarviz_llm_full.py     # LLM full analysis runner
│   └── trading_bot/           # Trading bot module (signals, watchlist, signals engine)
├── knowledge/                # Data directory
│   └── jarvis.db             # SQLite database (38+ tables)
├── memory/                   # Daily memory files (2026-06-16 to 2026-06-26)
├── daily/                    # Daily briefing snapshots
├── tests/                    # Test suite
└── .plans/                   # Architecture plans, migration docs
```

---

*Last updated: 2026-06-28 — reflects actual codebase as of today.*
