# Jarvis Hub Dashboard API Specification

> Local Flask Dashboard v2 | Port 8100 | `jarvis-hub/app_clean.py`

Base URL: `http://localhost:8100`

---

## 1. Web UI

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/` | GET | Home index page (renders `dashboard/templates/index.html`) | HTML |

---

## 2. Health & Status

### GET /api/health
Health check with system status overview.

**Response:**
```json
{
    "status": "ok",
    "timestamp": "YYYY-MM-DD HH:MM",
    "omlx": "online" | "offline" | "error: ...",
    "db_path": "/path/to/jarvis.db",
    "indices": { "VN-Index": { "price": 1798.61, "change_pct": -0.28, ... } },
    "rates": { "USD": { "cash": 261.0, "transfer": 261.3, "sell": 264.1 }},
    "crypto": { "BTC", "ETH", "SOL" data },
    "gold": null | { price, change_pct, ... },
    "oil": null | { price, change_pct, historical_closes, ... },
    "dxy": null | { value, change_pct },
    "cache_age_seconds": 60
}
```

---

## 3. Knowledge Base

### GET /api/search
Search knowledge base by keyword.

**Parameters:**
- `q` (required): Search query string
- `limit` (optional, default 20): Max results to return

**Response:**
```json
{
    "results": [[5, { "id": 34, "term": "...", "content": "...", "tags": "...", "updated_at": "..." }]],
    "query": "test",
    "total": 10
}
```

---

## 4. Stock Analysis

### GET /api/analyze
Single stock analysis with technical indicators.

**Parameters:**
- `symbol` (required): Stock symbol (e.g., `VCB`)

**Response:**
```json
{
    "symbol": "VCB",
    "price": 61.9,
    "change_pct": 0.0,
    "bollinger_lower": 60.28,
    "bollinger_upper": 65.22,
    "historical_closes": [59.2, 59.3, ...],
    "volatility": 1.2,
    "vwap": 61.5,
    ...
}
```

---

## 5. Activity Log

### GET /api/activities
Return recent system activities.

**Parameters:**
- No parameters (hardcoded limit)

**Response:**
```json
{
    "count": 20,
    "activities": [
        { "command": "...", "args": "...", "status": "ok", ... }
    ]
}
```

---

## 6. Watchlist Management

### GET /api/watchlist
Get watchlist symbols.

**Response:**
```json
{ "symbols": ["VCB", "VNM", "VIC"] }
```

### POST /api/watchlist/add
Add symbol to watchlist.

**Body (JSON):**
```json
{ "symbol": "VCB", "name": "Vietcombank" }  // name optional
```

**Response:** `"success": true`, `"added": symbol`

### POST /api/watchlist/remove
Remove symbol from watchlist.

**Body (JSON):**
```json
{ "symbol": "VCB" }
```

**Response:** `"success": true`, `"removed": symbol`

---

## 7. Daily Snapshots (News Briefings)

### GET /api/snapshots
Return last 5 daily briefing snapshots.

**Response:**
```json
{
    "count": 1,
    "snapshots": [
        {
            "date": "2026-05-20",
            "preview": "...truncated content...",
            "article_count": 15,
            "full_content": "..."
        }
    ]
}
```

### GET /api/daily-snapshot/<date>
Get snapshot for specific date.

**Parameters:**
- `:date` (URL segment): `YYYY-MM-DD` format

**Response:**
```json
{
    "status": "ok",
    "data": {
        "id": 1,
        "date": "2026-05-20",
        "short_summary": "...",
        "briefing_content": "..."  // Full news content with images
    }
}
```

---

## 8. Articles (RSS Feed)

### GET /api/articles
Fetch live RSS articles.

**Parameters:**
- `category` (optional): Filter by category (e.g., `vn`, `finance`)

**Response:**
```json
{
    "articles": [ ... ],
    "count": 30
}
```

---

## 9. Market Evaluation (LLM Powered)

### GET /api/market-evaluation
Get latest market evaluation.

**Response:**
```json
{
    "status": "ok" | "pending",
    "date": "YYYY-MM-DD",
    "evaluation": "...full LLM analysis..."
}
```
If pending: `"message": "Chua co danh gia."`

### POST /api/market-evaluation/generate
Trigger fresh LLM evaluation with live market data.

**Body (JSON):** Optional `{"force": true}` for forced recalculation.

**Flow:**
1. Fetch latest articles via `get_articles(limit=20)`
2. Fetch market indices (`fetch_market_indices()`)
3. Fetch crypto (`BTC`, `ETH`, `SOL`), gold, DXY, oil
4. Send prompt to Ollama model (qwen3.6:35b-mlx)
5. Cache result in DB

### GET /api/market-evaluation/history
Return historical evaluations.

**Response:**
```json
{
    "status": "ok",
    "evaluations": [ { "date": "...", "evaluation": "..." ... } ]
}
```

---

## 10. Trading Signals

### GET /api/signals
Unified signal feed (merged from `signals_log` + `trading_alerts`).

**Parameters:**
- `signal` (optional): Filter by type (`BUY`, `SELL`, etc.)
- `severity` (optional): Filter by severity (`HIGH`, `MEDIUM`)
- `symbol` (optional): Filter by symbol
- `unread` (optional): Only unread signals (`true`/`false`)

**Response:**
```json
{
    "signals": [
        {
            "id": 1,
            "symbol": "VCB",
            "source": "TRADING_BOT" | "AUTO_SCAN" | null,
            "signal_type": "BUY",
            "severity": "...",
            "price": 98.5,
            "details": "...",
            "detected_at": "...",
            "delivered": true | false
        }
    ],
    "source_counts": { "signals_log": 10, "trading_alerts": 5 },
    "total": 15
}
```

### GET /api/signals/latest
Most recent signals for grid view.

**Parameters:**
- `limit` (optional, default 20, max 100): Number of signals to return

**Response:** Same as `/api/signals` but simplified.

### GET /api/signals/symbol/:symbol
All signals for specific symbol.

```json
{
    "symbol": "VCB",
    "signals": [ { ... } ]
}
```

### POST /api/signals/add
Manually create a tracking signal.

**Body (JSON):** Required fields: `symbol`, `signal` (type), `strength` (float)
Optional: `price`, `timestamp`.

### POST /api/signals/mark-delivered: Mark signal as already delivered/visible to user.

**Body:** `"id": 1234` (integer or null for batch update).

---

## 11. Alert Feed (Trading Bot)

### GET /api/alert-feed
Get trading alerts sorted by importance.

**Parameters:**
- `signal` (optional): Filter by signal type (`BUY`, `SELL`)
- `severity` (optional): Filter by severity (`HIGH`, `MEDIUM`)

### POST /api/signal/feed/clear
Clear all alert feed as read/processed.

**Body:** `"unread_only": true | false`

---

## 12. Auto-Scan (Trading Bot)

### GET /api/auto-scan
Trigger automated scan of watchlist for trading signals.

**Response:**
```json
{
    "scanned": 5,          // Symbols scanned
    "alerts_found": 2,     // New alerts detected
    "details": {
        "{...}": {         // Per-symbol results
            "price": 98.5,
            "change_pct": -0.28,
            "rsi": 35.1,
            "signal": ...
        }
    },
    "success": true
}
```
