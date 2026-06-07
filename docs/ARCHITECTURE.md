# Jarvis Hub — Architecture & Design Doc

**Version:** v2.0 (2026-05-22)  
**Last Updated:** 2026-05-22

---

## 🏗️ Hệ thống tổng quan

Jarvis Hub là hệ thống **finance intelligence platform** bao gồm:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  RSS Sources │     │  Yahoo API   │     │  DXY/Oil     │
│  (Cafef, VNE)│     │  (stock data)│     │  external srcs│
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                     │                     │
       ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────┐
│                   Flask Web Server :8100              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────┐  │
│  │ News API │  │Market API│  │Search API│  │Eval │  │
│  └──────────┘  └──────────┘  └──────────┘  └─────┘  │
│                      │                               │
│              ┌───────▼────────┐                       │
│              │   Cache Layer   │ ◄── Thread-safe     │
│              │  (_cache dict)  │    with locks       │
│              └───────┬────────┘                       │
└──────────────────────┼───────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼             ▼
   ┌──────────┐  ┌────────┐  ┌──────────┐
   │SQLite DB │  │Ollama  │  │ Telegram │
   │(jarvis.db│  │LLM API │  │ Bot      │
   │ .db)     │  │:11434  │  │          │
   └──────────┘  └────────┘  └──────────┘
```

---

## 📦 Thành phần chính

### 1. Core Engine (`core/`)

| Module | Nhiệm vụ | Dependencies |
|--------|----------|-------------|
| `config.py` | Load YAML config, dot-notation access | PyYAML |
| `db.py` | SQLite với 3 bảng: knowledge_base, activity_log, watchlist | sqlite3 (stdlib) |
| `news.py` | RSS fetcher → sentiment analysis (2-layer Ollama) | feedparser, requests |
| `market.py` | Yahoo Finance API + TAI engine + LLM analysis wrapper | yfinance, requests |

### 2. Web Dashboard (`app.py`)

Flask web server cung cấp:
- **Homepage**: rendered template với cached articles + indices
- **REST API endpoints** (xem API Reference bên dưới)
- **Background cache refresh**: thread daemon tự refresh data

#### Cache Strategy
```python
_cache = {
    "articles": [],        # RSS news articles (20 newest)
    "indices": {},         # VN-Index, HNX, UPCOM + global indices
    "rates": {},           # Exchange rates USD/VND etc.
    "crypto": {},          # BTC, ETH, SOL data
    "dxy": None,           # Dollar Index
    "oil": None,           # Oil crude price
    "cache_time": 0        # Timestamp of last refresh
}
```

Refresh trigger conditions:
- **Morning**: cache\_time < 7:30 AM (market open)
- **Stale**: cache\_age > 12 hours
- **New day**:不同日
- **Initial load**: cache\_time == 0

### 3. CLI Tool (`cli.py`)

Click-based command line interface:
- `jarvis briefing` — generate + send daily news summary
- `jarvis analyze <SYMBOL>` — full analysis with LLM report  
- `jarvis watch add/list/remove` — manage watchlist
- `jarvis search <TERM>` — KB search / AI generate
- `jarvis quiz` — spaced repetition flashcard mode
- `jarvis log [-l 20]` — activity log viewer
- `jarvis history <DATE1> [DATE2]` — compare daily snapshots
- `jarvis doctor` — health check for all systems

### 4. Knowledge Base

SQLite database (jarvis.db) với FTS5 full-text search:
```sql
CREATE TABLE knowledge_base (
    id INTEGER PRIMARY KEY,
    term TEXT UNIQUE,         -- Keyword like "P/E ratio"
    content TEXT NOT NULL,    -- Definition/Explanation text
    tags TEXT,                -- Comma-separated: "stock,valuation,ratio"
    created_at TIMESTAMP,     -- Auto-set on create
    updated_at TIMESTAMP      -- Updated when regeneration happens
)

CREATE VIRTUAL TABLE knowledge_fts 
USING fts5(term, content, tags);
```

### 5. LLM Cache (`llm_cache.py`)

Decorator pattern cho Ollama calls:
- Same prompt → same hash → return cached result (avoid redundant API calls)
- TTL-based expiration for time-sensitive content

---

## 🔌 API Reference

### GET `/` — Dashboard Homepage
Returns: rendered index.html with articles, indices, rates

### GET `/api/search?q=TERM&generate=true|false`
Search knowledge base. Returns JSON:
```json
{
  "query": "P/E ratio",
  "count": 2,
  "results": [
    {
      "score": 0.95,
      "term": "P/E Ratio",
      "content": "Price-to-Earnings ratio is...",
      "tags": "stock,valuation,ratio",
      "updated_at": "2026-05-21 03:51:24"
    }
  ]
}
```

### GET `/api/analyze?symbol=VNM`
Full stock/gold/crypto analysis. Returns JSON:
```json
{
  "data": {
    "symbol": "VNM",
    "name": "Vietnam Dairy",
    "price": 57500,
    "change_pct": 1.23,
    "volume": 12000000,
    "pe_ratio": 24.5,
    "eps": 2346,
    "market_cap": "78.9T",
    "technical": {
      "SMA_20": 57200,
      "SMA_50": 56800,
      "RSI_14": 62.3,
      "MACD": {"macd": 120, "signal": 100, "histogram": 20}
    },
    "technical_summary": "SMA_20: 57200 (ABOVE)\n...",
    "llm_report": "# Phân tích VNM\\n\n## Xu hướng..."
  },
  "error": null
}
```

### GET `/api/activities?limit=50`
Returns activity logs.

### GET `/api/watchlist`
Watchlist with current prices.

### GET `/api/market-evaluation`
Fresh data fetch → generate daily evaluation report via LLM.

### GET `/api/snapshots`
Returns list of daily briefing snapshot dates + preview content.

### GET `/api/health`
Health check: Ollama status, cache age, indices, rates etc.

---

## 🔄 Data Flow

```
1. REQUEST  → Flask route (/api/analyze?symbol=VNM)
2. CHECK    → Is cache fresh? (should_refresh())
3. FETCH   → Yahoo API / exchange rate API (parallel threads)
4. ENGINE  → Calculate TA indicators (SMA, RSI, MACD)
5. LLM     → If no cached report: call Ollama with enhanced prompt
6. CACHE   → Store response in llm_cache for future same-symbol requests
7. RESPONSE → JSON back to frontend or CLI output
```

---

## 🗄️ Database Schema (SQLite)

### knowledge\_base + knowledge\_fts
Full-text search over financial terms. Created by `seed_kb.py` and enriched by scripts in `scripts/`.

### activity\_log
Audit trail for all Jarvis operations:
| Field | Description |
|-------|-------------|
| timestamp | ISO 8601 datetime |
| command | Command name (briefing, analyze, search) |
| args | Arguments passed |
| status | ok / error / warn |
| summary | Human-readable description |
| duration_ms | Execution time in milliseconds |

### watchlist
| Field | Description |
|-------|-------------|
| symbol | Ticker (VNM, FRT, BTC...) |
| name | Display name (optional) |

---

## 🧠 Sentiment Analysis Pipeline

```
RSS Feed → fetch_rss_feeds() → [article with title, content, link]
                                    │
                          enrich_article(article)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              LAYER 1         LAYER 2           OUTPUT
         Quick keyword       Deep LLM          Final sentiment:
         based scoring        analysis          TÍCH CỰC /
         (fast, local)       via Ollama        TIÊU CỰC / TRUNG LẬP
                                    │
                           Sentiment score (0-100)
```

---

## 📐 Technical Indicators Engine (`core/market.py`)

| Indicator | Formula | Signal |
|-----------|---------|--------|
| SMA\_20/50/200 | Simple Moving Average | Price > SMA = bullish |
| RSI\_14 | Relative Strength Index | <30 oversold, >70 overbought |
| MACD | 12-EMA - 26-EMA, signal=9-EMA | crossover = golden/death cross |
| Bollinger Bands | SMA20 ± 2\*σ | Price near bands = reversal zone |

---

## 🔐 Security & Constraints

1. **No external API keys** — all data sources are free (Yahoo, Vietnamcombank public rates)
2. **Local LLM only** — Ollama runs locally, no cloud model calls
3. **SQLite local DB** — single file, no network dependency for storage
4. **Rate limiting awareness** — Yahoo Finance has soft limits, implemented with timeout/error handling

---

## 🔮 Future Extensions (TODO)

- [ ] Telegram bot integration (auto-send briefings + alerts)
- [ ] More crypto support (BNB, DOGE, ADA...)  
- [ ] Portfolio tracker module
- [ ] Alerts: price threshold notifications
- [ ] Export reports as PDF
- [ ] Multi-language support (English/Vietnamese toggle)

---

*Cập nhật lần cuối: 2026-05-22*
