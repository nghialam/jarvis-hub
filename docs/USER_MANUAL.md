# 📘 JARVIS HUB 2.0 — User Manual

**Version:** v2.0 | **Updated:** 2026-06-28

---

## What Is Jarvis Hub?

Jarvis Hub is a **local financial intelligence platform** for Vietnamese and global markets. It runs entirely on your machine — no external data leaves, no cloud dependencies beyond the Ollama LLM inference engine.

**Key capabilities:**

- **Real-time market data** — VN stocks (via vnstock4), global indices, crypto, gold, oil
- **Technical analysis** — RSI, SMA20/50, MACD, Bollinger Bands, momentum
- **LLM-powered reports** — Qwen3.6 analyzes data and generates BUY/SELL/HOLD recommendations with confidence scores
- **News aggregation** — RSS feeds from Cafef, VnExpress, Reuters with sentiment analysis (heuristic + LLM)
- **Watchlist & alerts** — Track symbols, get RSI/MACD-based trading signals
- **Knowledge base** — Financial term dictionary with FTS5 full-text search

---

## Dashboard Overview

Open `http://localhost:8100/hub2` to see the main dashboard. It has these tabs:

### 📊 Overview Tab — Market Intelligence Portal

Shows live data from 7+ sources simultaneously:

| Section | Data Points |
|---------|-------------|
| **VN Indices** | VN-Index, HOSE Cap — price, change %, 1W/1M/1Q changes |
| **Global Indices** | S&P 500, Dow Jones, NASDAQ, Nikkei 225, Hang Seng, KOSPI, DAX, FTSE 100 |
| **Crypto** | BTC, ETH, SOL — price, % change (from Binance/Yahoo) |
| **Gold & Oil** | Gold ($/oz), WTI Oil ($/barrel) |
| **DXY** | US Dollar Index |
| **Exchange Rates** | USD/VND transfer/sell from Vietcombank |
| **Top Motions** | VN-30 stocks ranked: top gainers and losers |

**How to use:**
1. Open the tab → data auto-fetches (parallel fetch via ThreadPoolExecutor)
2. Wait ~5-15s for all sources to complete
3. View candlestick charts from Yahoo Finance 5d/30m intervals
4. Click **Auto Refresh** button to force a fresh data pull

### 💡 Analysis Tab — Deep Symbol Analysis

Enter any symbol to get:

| Section | Details |
|---------|---------|
| **Market Data** | Price, change%, percentage, P/E, EPS, Market Cap |
| **Technical Indicators** | SMA20/50, RSI14, MACD line/signal/histogram, Bollinger Bands, Momentum (10-day ROC), Support & Resistance levels |
| **Signal Analysis** | RSI oversold (<30) → buy opportunity; RSI overbought (>70) → reversal warning |
| **LLM Report** | AI-generated: trends across 3 timeframes (short/mid/long), support/resistance, recommendations with confidence score (%), risk level, stop-loss suggestions, investment catalysts (bullish/bearish) |

**Examples:**
- Vietnamese stock: `HVN` → auto-appends `.VN`, fetches vnstock4 data
- Global stock: `AAPL` → Yahoo Finance chart + CSV fallback
- Crypto: `BTC` → Binance API + Yahoo
- Gold: `XAUUSD` → special gold fetcher

### 📰 News Feed Tab — AI-Scored Headlines

Shows aggregated news from configured RSS sources with:
- **Title & source** (Cafef, VnExpress, Reuters, TechCrunch, etc.)
- **Category & sector tag** (banking, real estate, tech, energy, FMCG, etc.)
- **Sentiment classification** — 🟢 tích cực / 🔴 tiêu cực / 🟡 trung lập
  - Layer 1: Heuristic keyword scoring (always runs)
  - Layer 2: Ollama LLM analysis (top 15 articles only)
- **Importance score** — LLM scores importance 1-10 for VN market impact
- **Filters** — Filter by category, sentiment, or recency

### 💾 Market Evaluation Tab

Auto-generates a daily market assessment covering:
- Overall trend (bullish/bearish/neutral) + confidence (1-100)
- Deep dive per category: VN stocks, crypto, gold, oil/DX
- Risk opportunities (2-3 each)
- Short-term recommendations with stop-loss levels

**Generate new assessment:** Click "Generate" button → triggers LLM call on fresh market data.

### ⭐ Watchlist Tab

Your portfolio of tracked symbols showing:
- Current price + % change
- Add/remove symbols easily
- Auto-scan generates trading signals based on RSI/MACD thresholds

### 📊 Signals Tab

Trading signals from two sources merged and deduplicated:
- **TRADING_BOT** — Automated signal engine
- **AUTO_SCAN** — Watchlist-based alerts

Filter by:
- Signal type (BUY/SELL/HOLD/STOP_LOSS/TAKE_PROFIT)
- Severity (LOW/MEDIUM/HIGH/CRITICAL)
- Symbol
- Read/unread status

### 🧠 AI Intelligence Tab

Shows past runs of the AI intelligence pipeline:
- Run dates, article counts, chain summaries
- Full run details: articles listed, recommendations extracted
- Pipeline health indicator + daily average stats

---

## Knowledge Base (Term Dictionary)

Search financial terms by keyword:

1. Type term in search input: "P/E ratio" or "RSI" or "Moving Average"
2. Press Enter or click 🔍 SEARCH
3. Results shown with tags, content preview, and relevance score ranking
4. **AI-generated fallback:** If no exact match, LLM generates a definition → you can choose to save it

**Term format:** Each entry has `term`, `content` (definition with examples), and `tags` for filtering.

---

## Using Via CLI

The command-line interface mirrors dashboard functionality:

```bash
cd ~/jarvis-hub

# Daily briefing with sentiment analysis + market indices + FX rates
python cli.py briefing --type morning

# Deep stock analysis with TA indicators + LLM report
python cli.py analyze VIC

# Watchlist management
python cli.py watch add HPG              # Add with auto-name
python cli.py watch list                 # View live prices
python cli.py watch remove HPG           # Remove from watch

# Search financial terms
python cli.py search "moving average"   # Returns matches + AI fallback

# Quiz mode (spaced repetition)
python cli.py quiz                     # Tests knowledge randomly

# System health check
python cli.py doctor                   # Checks config, DB, Ollama, RSS feeds

# View history & compare days
python cli.py log                      # Activity logs
python cli.py history 2026-06-01 2026-06-02   # Diff between two briefings
```

---

## Scheduling Automated Tasks (Cron Jobs)

Jarvis Hub runs automatically via Hermes Agent cron jobs:

### Daily News & Strategy Briefing (Primary Automation)
- **Schedule:** Every day at 06:00 GMT+7
- **Source:** RSS feeds (`https://cafef.vn/doanh-nghiep.rss`, `https://vnexpress.net/rss/kinh-doanh.rss`)
- **Output:** Telegram message with market data + sentiment + investment recommendations

### Other Automated Jobs
| Job | Schedule | Purpose |
|-----|----------|---------|
| Jarvis Auto-Update Pipeline | Mon-Fri 08:45 | System health, code analysis, maintenance |
| Memory Compact | Sundays 09:00 | Weekly hindsight recall synthesis |
| Daily Memory Update | Every day 23:00 | Auto-retain durable facts into Hindsight |
| Backlog Sync | Every day 22:00 | BACKLOG.md updates & re-prioritization |
| Auto-Improvement Engine | Every day 01:00 | Pattern detection → SKILL.md promotion |
| Memory Regression Test | Every day 02:00 | Validate memory systems |

**Managing cron jobs:**
```bash
hermes cron job list                              # View all active jobs
hermes cron job pause <job_id>                    # Suspend a job
hermes cron job resume <job_id>                   # Resume a paused job
hermes cron job remove <job_id>                   # Delete a job
hermes cron job run <job_id>                      # Force execution now (debugging)
```

---

## How LLM Analysis Works

1. **Tier 1: Raw Data Collection** — Fetches live prices, news headlines, macro data → saves to `jarvis.db`
2. **Tier 2: LLM Pipeline** — Reads compiled data from DB → builds prompt → calls Ollama with Qwen3.6 → cleans reasoning preamble leaks → saves analysis report

### Prompt Structure
- Market overview (VN stocks + macro indicators)
- Sector momentum & hot stock analysis
- Macro factors (US indices, gold/oil impact, crypto sentiment)
- News impact summary for VN market
- Short-term forecast + actionable recommendations

### Output Format
- Markdown with headers (#### sections), bullet points, no numbered lists
- Includes: confidence %, risk level, stop-loss suggestion, catalysts

---

## Configuration (`config.yaml`)

All settings in `~/jarvis-hub/config.yaml`:

| Section | Key | Purpose |
|---------|-----|----------|
| `system` | timezone | Defaults to Asia/Saigon (GMT+7) |
| `telegram` | target_chat_id | Telegram delivery channel (1670013239) |
| `omlx` | url | Ollama endpoint — default: http://localhost:11434 |
| `omlx` | model | LLM model name — default: Qwen3.6-35B-A3B-MLX-8bit |
| `feed.sources[].priority` | 1 / 2 / 3 / 4 | Lower number = higher priority in news feed display |
| `exchange_rates_source` | vietcombank/sacombank | Which bank's rates to use |
| `schedule.morning_briefing` | "06:18" | Morning briefing time (GMT+7) |

---

## Data Sources Summary

| Source | Covers | Primary / Fallback |
|--------|--------|---------------------|
| **Yahoo Finance** | VN stocks, global indices, gold, oil, DXY, crypto | Chart API v8 + CSV download v7 fallback |
| **vnstock4** | VN stock OHLCV data (KBS/VCI sources) | Primary for VN stocks; applies x1000 VND multiplier |
| **Binance API** | BTC, ETH, SOL prices | Primary for crypto |
| **Vietcombank** | USD/VND exchange rates | Web-scraped HTML parser |
| **RSS Feeds** | News from Cafef, VnExpress, Reuters, etc. | feedparser with deduplication & sentiment scoring |

---

## Troubleshooting

### Dashboard won't load / blank screen
- Wait 30 seconds for initial data refresh (not a bug)
- Manually trigger: `POST /api/v1/market/auto-refresh/trigger`
- Check Ollama is running: `curl localhost:11434/api/tags`

### LLM analysis not producing results
- Ensure Ollama is reachable; check `jarvis doctor` output
- Verify model exists in Ollama: models list should include your configured model
- Circuit breaker may be open after too many failures — wait 60s for recovery window

### Port 8100 already occupied
```bash
lsof -t -i :8100 | xargs kill -9
python app.py
```

### Knowledge base searching returns nothing
- Use broader keywords or try different search terms
- Try generating a definition: when no results found, AI can generate one on-the-fly

### Data seems stale
- Default cache TTL is 5 minutes for stocks/crypto, 3 min for news
- Force refresh via API endpoint or restart Flask server

---

*Last updated: 2026-06-28 — reflects all features available in the current v2.0 release.*
