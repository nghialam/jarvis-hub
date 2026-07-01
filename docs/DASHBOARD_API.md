# Jarvis Hub 2.0 — Dashboard REST API Reference

**Version:** v2.0 | **Last Updated:** 2026-06-28

---

## Base URL

```
http://localhost:8100
```

All routes are defined in `app.py`. JSON responses use standard keys. Health check confirms server status and data freshness.

---

## Authentication

No authentication required — intended for single-user local access only.

---

## Route Groups

### 1. Health & System (no prefix)

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | GET | Health check returning status, timestamp, db connection state, ollama health, and key data levels — with TTL-based health level (ok/degraded/error based on cache age) |
| `GET /health` | GET | Alias endpoint for system diagnostics; returns cache age in seconds alongside Ollama status (healthy/unhealthy/unreachable), current market data snapshot, and flask/db connection indicators |

**Health response:**
```json
{
  "status": "ok",
  "timestamp": "2026-06-28 14:35",
  "ollama": "healthy",
  "db": "connected",
  "cache_age_seconds": 23,
  "vn_indices": {"VN-Index": {"price": 1283.5}},
  "global_indices": {},
  "rates": {},
  "crypto": {},
  "gold": null,
  "dxy": null,
  "oil": null
}
```

---

### 2. Legacy API Routes (`/api/*`)

These routes support the original dashboard interface and are backwards-compatible with v1 clients.

#### Knowledge Base Search
| Route | Method | Description |
|-------|--------|-------------|
| `/api/search?q=<term>&limit=20` | GET | Search knowledge base with relevance scoring (exact match, positional ordering, word count) |

**Response:** `{"results": [...], "query": "...", "total": N}`

#### Symbol Analysis
| Route | Method | Description |
|-------|--------|-------------|
| `/api/analyze?symbol=VIC` | GET | Deep analysis: price data + TA indicators (RSI, SMA, MACD, Bollinger) + LLM report |

**Response:** Price info (`price`, `change_pct`, `pe_ratio`, `eps`, `market_cap`), technical dict (`rsi`, `sma_20`, `support_level`, `resistance_level`, `bollinger_upper/lower`, `macd_histogram`, `momentum`, `signals` [list]), and `llm_report` string.

#### Activity Logs
| Route | Method | Description |
|-------|--------|-------------|
| `/api/activities?limit=20` | GET | Recent system activities from activity_log table: command, args, status, duration_ms |

#### Watchlist Management
| Route | Method | Description |
|-------|--------|-------------|
| `/api/watchlist` | GET | Return list of watchlist symbols with names and added dates |
| `/api/watchlist/add` | POST | Add symbol: `{symbol: "VIC", name: "Vingroup"}` |
| `/api/watchlist/remove` | POST | Remove symbol: `{symbol: "VIC"}` |

#### Daily Briefings & Snapshots
| Route | Method | Description |
|-------|--------|-------------|
| `/api/snapshots` | GET | Last N daily briefing snapshots with preview (first 300 chars) and article counts |
| `/api/daily-snapshot/<date>` | GET | Full content snapshot for a specific date (e.g. `2026-05-20`) |

#### Web Pages
| Route | Method | Description |
|-------|--------|-------------|
| `/hub2` | GET | Hub 2.0 Market Intelligence Portal — main dashboard page with tabs for Overview, Analysis, Market Evaluation, News Feed, Knowledge Base, Watchlist, Signals |

#### News Feed
| Route | Method | Description |
|-------|--------|-------------|
| `/api/articles?category=vn-stock` | GET | Aggregated RSS articles filtered by category; returns title, summary_raw, sentiment_class (TRUNG_LAP/TÍCH_CỰC/TIÊU_CỰC), published date, source URL |

#### Health Check
| Route | Method | Description |
|-------|--------|-------------|
| `/api/health` | GET | Alternative health endpoint — returns db connection state, market data levels, and overall system status; used as fallback when `/health` is unavailable |

#### Market Data (DB-backed)
| Route | Method | Description |
|-------|--------|-------------|
| `/api/indices` | GET | Return VN + global indices directly from database — returns `{vn_indices:{...}, global_indices:{...}, source:"DB", updated_at:"..."}`; used as fast fallback when overview fetch is unavailable |

#### Market Evaluation
| Route | Method | Description |
|-------|--------|-------------|
| `/api/market-evaluation` | GET | Most recent evaluation with status (ok/pending), evaluation text, summary preview |
| `/api/market-evaluation/generate` | POST | Force LLM to generate fresh evaluation from current market data — returns evaluation + summary |
| `/api/market-evaluation/history` | GET | All historical evaluations chronologically ordered |

#### Signal Tracking & Trading Alerts
| Route | Method | Description |
|-------|--------|-------------|
| `/api/signals?signal=BUY&severity=HIGH&symbol=VIC&unread=false` | GET | Unified signal feed merged from signals_log + trading_alerts; supports filtering by type, severity, symbol, and read status; returns deduplicated latest signal per symbol (non-neutral signals take precedence) |
| `/api/signals/latest?limit=20` | GET | Latest N signals for grid overview without filtering |
| `/api/signals/symbol/<symbol>` | GET | All signals for a specific symbol (full history) |
| `/api/signals/add` | POST | Manually create signal: `{symbol: "VIC", signal: "BUY", strength: 7, price: 228000}` |
| `/api/signals/mark-delivered` | POST | Mark signal as delivered for tracking: `{id: 123}` |

#### Auto-Scan & Alert Feed
| Route | Method | Description |
|-------|--------|-------------|
| `/api/alert-feed?signal=BUY&severity=HIGH&symbol=VIC` | GET | Get trading alerts with filters from trading_alerts table; parses JSON alert_data field containing price, change_pct, rsi_14, sma_20, macd_histogram, signal_reason |
| `/api/alert-feed/auto-scan` | GET | Trigger auto-scan: loops through watchlist, applies RSI/MACD/change thresholds (RSI ≤ 30→BUY, ≥ 70→SELL, price < SMA20×0.95→SELL, sharp drop -5%→SELL, rally +5%→BUY; 80%+ multi-indicator confluence = STRONG signal); generates alerts avoiding duplicate per symbol per 6 hours |
| `/api/alert-feed/clear` | POST | Mark all trading_alerts as read (`status='read'`) |

**Aliases:**
| Route | Method | Points to |
|-------|--------|-----------|
| `/api/signal/feed/clear` | POST | Alias for `alert-feed/clear` |
| `/api/auto-scan` | GET | Alias for `alert-feed/auto-scan` |

#### System Logs (Consolidated)
| Route | Method | Description |
|-------|--------|-------------|
| `/logs` | GET | Aggregated logs from 3 tables: activity_log, signals_log, trading_alerts — returns `{activity_logs:{}, signal_logs:{}, trading_alerts:{}}` each with count, column names (for spreadsheet import), and data array |

---

### 3. Hub 2.0 API (`/api/v1/*`)

These routes power the Hub 2.0 dashboard in `hub2.html`.

#### Overview Data
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/overview` | GET | Full market overview: VN indices (`vn_indices`), global indices (`global_indices`), crypto (BTC/ETH/SOL), gold, oil, DXY, plus `top_motions` (gainers/losers from vnstock4/Yahoo). Returns `{status:"ok", data:{updated_at: "...", ...}}` |
| `/api/v1/overview/indices` | GET | Indices as arrays with name/symbol fields for easier frontend rendering |
| `/api/v1/overview/crypto` | GET | Crypto prices array |
| `/api/v1/overview/gold` | GET | Gold price + metadata |

#### Top Motions & Charting
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/overview/motions?limit=10&symbols=VIC,VCB,FPT` | GET | Top movers from VN-30 (or custom symbols list); returns gainers + losers sorted by change_pct; top 5 stocks per sector in sector aggregation |
| `/api/v1/overview/chart?symbol=VIC` | GET | Candlestick chart data: timestamps, open/high/low/close/volume arrays (last 5 days / 30m interval) |

#### News with Filters
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/news?category=all&sentiment=all&limit=50&days=7` | GET | Enhanced news from news_enhanced table (or falls back to RSS fetch). Filterable by category, sentiment; returns full articles with importance scores when LLM-scoring is enabled |
| `/api/v1/news/trending` | GET | High-importance trending articles only (`is_trending=1`) |
| `/api/v1/news/score` | POST | Trigger LLM scoring of news: assigns 1-10 importance with reasoning per article; saves to DB via `update_news_importance()` if available |

#### Company Lookups
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/companies?q=VIC` | GET | Search portfolio_watchlist by symbol or name (fuzzy, case-insensitive, top 50) → `[{symbol:"VIC", name:"Vingroup"}]` |
| `/api/v1/companies/<symbol>/news` | GET | News articles affecting a specific company; filters by affected_symbols LIKE %SYM% OR title LIKE %SYM%, last 30 days, ordered by importance DESC |

#### Research Hub (Brokerage Reports)
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/research?broker=SSI&period=1m&limit=20` | GET | Brokerage reports from SSI/VCI/HCM/TCBS/VCBS; `broker=all` for all brokers, `period` filters by date range (e.g. 1w, 1m, 3m) |
| `/api/v1/research/stats` | GET | Stats per broker: count of reports, breakdown by report_type (Weekly Chart, Sector Mix, Macro View, Stock Recommendation, Earnings Forecast), date distribution |
| `/api/v1/research/crawl` | POST | Trigger crawler for all 5 brokers: SSI, VCI, HCM, TCBS, VCBS; returns total found, saved count, brokers crawled, timestamp |

#### Portfolio Watchlist
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/watchlist/portfolio` | GET | Portfolio watchlist with sector tagging: `[{symbol:"VIC", name:"Vingroup", sector:"Real Estate", added_at:"..."}]` |
| `/api/v1/watchlist/portfolio/add` | POST | Add to portfolio: `{symbol:"VIC", name:"Vingroup", sector:"Real Estate"}` |
| `/api/v1/watchlist/portfolio/remove` | POST | Remove from portfolio: `{symbol:"VIC"}` |

#### Sector Heatmap
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/market/heatmap` | GET | Sector performance heatmap: aggregates gainers/losers by sector name, computes avg change per sector, returns top 5 stocks per sector. Useful for visualizing sector rotation and relative strength |

**Response:** `{"sectors":[{"name":"Real Estate","avg_change":3.45,"gainers":5,"losers":2,"total":7,"stocks":[{}]}]}`

#### Auto-Refresh
| Route | Method | Description |
|-------|--------|-------------|
| `/api/v1/market/auto-refresh/trigger` | POST | Force manual data refresh — triggers `_refresh_data()` which fetches indices, crypto, gold, oil, DXY, FX rates, and news in parallel; returns cache_age=0 to signal freshness |

---

### 4. AI Intelligence API (`/api/v2/*`)

Powered by the run_chains pipeline for deep market analysis.

| Route | Method | Description |
|-------|--------|-------------|
| `/api/v2/ai-intelligence/daily-list` | GET | List of all run dates with article counts + summaries: `[{run_id, date, article_count, total_articles, total_sources, chain_1_summary, status}]`; limited to 30 most recent runs |
| `/api/v2/ai-finance/run/<run_id>` | GET | Full run detail: run metadata, all articles (up to 200), all recommendations (up to 100); returns `article_count` and `recommendation_count` for quick status checks |
| `/api/v2/ai-finance/health` | GET | Pipeline health check: last run date, total runs saved count, daily average articles; useful for monitoring if the pipeline is running regularly |

---

## Response Formats

### Standard Success Response
```json
{
  "status": "ok",
  "data": { ... },
  "count": 42
}
```

### Error Response
```json
{
  "status": "error",
  "error": "Descriptive error message"
}
```
With HTTP status 500 for server errors, 502 for data fetch failures (Yahoo/vnstock4 unavailable), 503 for config/DB issues, 400 for bad input.

### Pagination & Limits
- Most list endpoints accept `limit` parameter (default 20-50, hard cap ~100)
- Results sorted by `DESC` date/timestamp unless otherwise specified
- Deduplication applied: latest entry per symbol wins for non-neutral signals; RSS articles deduplicated by URL

### Filtering Support
- Boolean filters encoded as string: `"true"`/`"false"` for read/unread, active/inactive
- Symbol filters: always uppercase, trimmed, length ≥ 2 required
- Category/sentiment filters: case-insensitive matching (e.g., `vn-stock` = `VN-STOCK`)

---

## Rate Limits & Performance

- Yahoo Finance: ~8s timeout per call; parallel fetch via ThreadPoolExecutor with concurrency limits (3 for VN indexes, 5 for global, 8 for full overview)
- Ollama LLM: 600s timeout for streaming analysis calls; circuit breaker prevents hammering after 3 consecutive failures
- Cache TTL: Varies by type (stocks 300s, crypto/FX 60s, news 180s, evaluations/evaluations 24h)

---

## Version History

| Date | Changes |
|------|---------|
| 2026-06-28 | Updated to v2.0: added Hub 2.0 API (`/api/v1/*`), AI Intelligence API (`/api/v2/*`), auto-scan alert system, sector heatmap endpoint, consolidated logs endpoint |
| 2026-05-20 | Original legacy routes established: `/api/*` endpoints for dashboard v1 compatibility |

---

*Last updated: 2026-06-28 — all routes verified against app.py source code.*
