# 🚀 Jarvis Hub 2.0 — Quick Start Guide

**Version:** v2.0 | **Last Updated:** 2026-06-28

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python 3.10+** | System Python or virtualenv |
| **Ollama** | Running on `localhost:11434` with model `qwen3.6:35b-a3b-mxfp8` |
| **vnstock4** | For VN stock data (KBS/VCI sources, prices in nghìn đồng) |
| **Dependencies** | flask, feedparser, requests, numpy, bs4, click, pyyaml |

---

## Installation

### Step 1: Clone and initialize
```bash
cd ~
git clone <repo-url> jarvis-hub          # Or place code locally
cd jarvis-hub
```

### Step 2: Install dependencies
```bash
pip install -r requirements.txt   # flask, feedparser, requests, numpy, bs4, click, pyyaml
pip install vnstock               # VN stock data provider (from hermes-agent venv or system pip)
```

### Step 3: Configure Ollama/Ollama
Make sure Ollama is running and the model is pulled:
```bash
ollama serve &                    # Start locally if not running
ollama pull qwen3.6:35b-a3b-mxfp8   # Or your preferred model
```

### Step 4: Configure Jarvis Hub
Edit `config.yaml`:
```yaml
# Required settings:
ollama:
  url: "http://localhost:11434"
  model: "qwen3.6:35b-a3b-mxfp8"

feed:
  sources:                        # Your news sources (Cafef, VnExpress, Reuters...)

db_path: "~/jarvis-hub/knowledge/jarvis.db"   # Auto-created if missing
```

### Step 5: Initialize the database
The database auto-creates on first Flask start. Or run manually:
```bash
# Via CLI (auto-triggers via app import)
python cli.py doctor
```

---

## First Run

### Start the Dashboard (recommended)
```bash
cd ~/jarvis-hub
python app.py
```
Output:
```
[CFG] Loaded configuration OK
[DB] Connected OK at /Users/nghialam/jarvis-hub/knowledge/jarvis.db
[REFRESH] Done — 7 sources loaded
[APP] Starting Jarvis Hub Flask server on port 8100...
 * Running on http://0.0.0.0:8100
```

Open in browser: **http://localhost:8100**

### Quick CLI tests
```bash
# Test knowledge base search
python cli.py search RSI

# Analyze a stock
python cli.py analyze VIC

# View system health
python cli.py doctor

# Generate a briefing
python cli.py briefing
```

---

## Dashboard Tabs

When you open `http://localhost:8100/hub2`, you'll see:

| Tab | What it shows | Data source |
|-----|--------------|-------------|
| **Overview** | VN-Index, global indices, crypto, gold, oil, DXY | Live Yahoo + vnstock4 fetch |
| **Analysis** | Enter symbol → TA indicators + LLM report | Yahoo/vnstock4 + Ollama |
| **Market Evaluation** | Auto-generated market assessment (bullish/bearish/neutral) | Ollama LLM on fresh data |
| **News feed** | Headlines with sentiment classification | RSS feeds → `news_articles` DB table |
| **Knowledge Base** | Search financial terms + AI-generated definitions | SQLite knowledge table |
| **Watchlist** | Your tracked symbols with live prices | Watchlist table + yahoo/vnstock4 data |
| **Signals** | Trading signals (RSI, MACD, auto-scan) | signals_log + trading_alerts tables |

---

## Scheduling Cron Jobs (Hermes Agent)

Jarvis Hub integrates with Hermes Agent for automated daily tasks:

```bash
# See all scheduled jobs
hermes cron job list

# To add a new briefings cron job:
hermes cron job create \
  --schedule "0 6 * * *" \          # Every day at 06:00 GMT+7
  --name "Jarvis-Hub Briefing" \
  --prompt "Run jarvis briefing and deliver to Telegram."
```

**Active Cron Jobs:**
| Job | Schedule | Purpose |
|-----|----------|---------|
| Daily News & Strategy | 06:00 daily | Market data + news → investment recommendations |
| Auto-Update Pipeline | Mon-Fri 08:45 | System health check + auto-maintenance |
| Memory Compact | Sundays 09:00 | Weekly hindsight recall synthesis |
| Daily Memory Update | 23:00 daily | Durable facts retention |
| Backlog Sync | 22:00 daily | BACKLOG.md updates |
| Auto-Improvement | 01:00 daily | Pattern detection → SKILL.md promotion |
| Memory Regression Test | 02:00 daily | Validate memory systems |

---

## Troubleshooting Quick Fixes

| Issue | Solution |
|-------|----------|
| Dashboard shows blank/black screen | Wait 30s for initial data refresh — or use manual API call `POST /api/v1/market/auto-refresh/trigger` |
| Ollama "unhealthy" in health check | Run `ollama serve &` and verify `curl localhost:11434/api/tags` returns models |
| Stock analysis fails for VN stocks | Ensure vnstock4 is installed: `pip install vnstock` or use hermes-agent venv at `/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages` |
| News RSS feeds return empty | Check internet connection; some Vietnamese feeds may be temporarily unavailable |
| Port 8100 already in use | `lsof -t -i :8100 | xargs kill -9`, then restart |
| Knowledge base search returns nothing | Use broader keyword or generate via LLM when no match found |

---

## Key Data Sources & Price Scaling

- **vnstock4** returns VN stock prices in **"nghìn đồng"** (thousands of VND)
  → All price fields are automatically multiplied by **1000** before display/analysis
  - Correct: VIC ≈ 228,000 VND (raw = 228.0)
  - Wrong: VIC ≈ 228 VND (missing ×1000 multiplier)

- **Yahoo Finance** for VN APIs requires `.VN` suffix: `VIC.VN`, not `VIC`

- **Binance API** for crypto: `BTCUSDT`, `ETHUSDT`, `SOLUSDT` endpoints

---

## Next Steps

1. ✅ Add symbols to your watchlist
2. ✅ Configure more RSS sources in `config.yaml`
3. ✅ Run Tier 1/2 manually via CLI scripts in `core/`
4. ✅ Set up cron jobs for automated daily briefings
5. ✅ Explore AI Intelligence tab for run history and deep analysis

---

*Last updated: 2026-06-28 — based on actual v2.0 codebase.*
