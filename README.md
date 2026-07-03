# Jarvis Hub — Vietnamese Stock Market Intelligence Portal

A Flask-based local web dashboard for Vietnamese stock market intelligence, combining real-time market data, news aggregation, LLM-powered summarization, and portfolio screening.

## Features

- **Market Overview** — VN-Index, HNX-Index, VN30 with live charts (Chart.js)
- **News Aggregator** — RSS feeds from Cafef, VnExpress, Reuters, BBC, TechCrunch, Ars Technica; LLM summarization & relevance scoring
- **Company News & Screens** — Scan Vietnamese listed companies for breaking news and signals
- **Broker Reports** — Aggregate research reports from SSI, VCI, HCM with consensus summaries
- **Portfolio Screening & Alerts** — Technical indicator calculations, watchlist management, alert system
- **Knowledge Base Search** — Semantic search across stored knowledge base (SQLite)
- **Telegram Delivery** — Automated daily briefings: market info, news aggregation, stock recommendations delivered to Telegram DM

## Architecture

```
┌─────────────────────── frontend (HTML/CSS/JS + Chart.js) ─────────────────────────┐
│  Tabs: Market Overview | News Aggregator | Company News | Reports | Screener     │
└────────────────────────────────────────────┬───────────────────────────────────────┘
                                             │ Flask REST API
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
             vnstock3 / DNSE          News RSS Feeders         Broker Websites
             (OHLCV market data)    (Reuters, BBC, Cafef,    (SSI, VCI, HCM
                                   VnExpress, TechCrunch)      research reports)
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
                SQLite DB             LLM Pipeline                  Telegram
              (knowledge base)     (Qwen3.6 via mlx-lm)         (daily briefings, alerts)
```

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML/CSS/JS + Chart.js (dark theme, responsive SPA) |
| Backend | Flask (REST API, SQLite cache, background refresh threads) |
| Data | vnstock3 / DNSE API (OHLCV), RSS feeders for news |
| LLM | mlx-lm — Qwen3.6-35B-A3B-MLX-8bit (Apple Silicon native) |
| Database | SQLite (`jarvis.db`, ~43 tables in Hub 2.0) |
| Scheduling | APScheduler / threading background tasks |

## Quick Start

### Prerequisites

- macOS with Apple Silicon (for mlx-lm inference) — runs on Mac Mini M4 Pro recommended
- Python 3.10+
- Ollama running with `Qwen3.6-35B-A3B-MLX-8bit` loaded

### Installation

```bash
git clone https://github.com/nghialam/jarvis-hub.git
cd jarvis-hub
pip install -r requirements.txt  # if applicable, or pip install flask vnstock3 requests apscheduler
python app.py --port 8100
```

Dashboard available at: http://localhost:8100

### Config

Edit `config.yaml`:

```yaml
system:
  name: "Jarvis Hub"
  timezone: "Asia/Saigon"

telegram:
  target_chat_id: "YOUR_CHAT_ID"
  openclaw_path: "/opt/homebrew/bin/openclaw"

omlx:
  url: "http://localhost:11434"
  model: "Qwen3.6-35B-A3B-MLX-8bit"

feed:
  sources:
    - name: "Cafef Doanh nghiệp"
      url: "https://cafef.vn/doanh-nghiep.rss"
      category: "vn-stock"
```

## Cron Jobs

Integrated scheduled tasks (via Hermes Agent):

| Job | Schedule | Description |
|-----|----------|-------------|
| Daily News Aggregation | Weekdays 06:00 SGT | Scans RSS feeds, aggregates & summarizes Vietnamese market news |
| Daily Market Information | Weekdays 06:00 SGT | Fetches VN indices, exchange rates, crypto, gold, oil data |
| Daily Stock Recommendations | Weekdays 07:00 SGT | Screens stocks, generates buy/sell recommendations |

## Project Structure

```
jarvis-hub/
├── app.py                  # Flask dashboard application (v3)
├── cli.py                  # CLI interface
├── config.yaml             # Configuration
├── core/                   # Core modules
│   ├── cache_manager.py    # LLM & data caching
│   ├── config.py           # Config loader
│   ├── data_collector.py   # Data scraping & collection
│   ├── db.py / db_hub2.py  # Database layer (SQLite)
│   ├── llm_cache.py        # LLM result cache
│   ├── market.py           # Market data (Yahoo Finance, exchange rates)
│   ├── market_overview.py  # VN index aggregation
│   └── ...                 # Signal analysis, evaluation modules
├── dashboard/              # Frontend (templates + static assets)
├── daily/                  # Daily briefing outputs
├── backups/                # DB & config backups
└── .bak/                   # Safety backup directory
```

## Deployment

### Vercel + Cloudflare Tunnel

For remote access:
- Frontend served via Vercel CDN
- Backend proxies route to local Mac Mini via Cloudflare tunnel (port 8100)
- Graceful degradation when Mac is offline
- RSS cron runs daily on Vercel at 06:25 UTC (1:25 PM SGT)

## Tech Notes

- All vnstock prices are in "nghàn đồng" (thousands of VND) — multiply by 1000 for actual VND values
- Yahoo Finance VN stocks require `.VN` suffix (e.g., `VIC.VN`)
- Local ML inference via Ollama on Apple Silicon native (MLX runtime)

---

**Built with ❤️ on Mac Mini M4 Pro** for efficient local AI-powered market analysis.
