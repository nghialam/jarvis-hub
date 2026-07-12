# 📋 JARVIS HUB 2.0 — CLI Command Reference

**Version:** v2.0 | **Updated:** 2026-06-28

---

## Quick Start

```bash
cd ~/jarvis-hub

# Start Flask dashboard
python app.py                          # → http://localhost:8100

# Run brief CLI commands (no server needed)
python cli.py <command> [options]
```

---

## Commands

### 1. `jarvis briefing` — Daily News Briefing

Generate and display a daily news summary with sentiment analysis, market indices, and exchange rates.

```bash
python cli.py briefing                  # Default: morning type
python cli.py briefing --type morning   # Morning briefing
python cli.py briefing --type evening   # Evening briefing
```

**Output:**
- RSS articles from configured sources (Cafef, VnExpress, Reuters) with heuristic + LLM sentiment
- VN-Index + top global indices
- USD/VND exchange rate from Vietcombank
- Sentiment distribution (tích cực / tiêu cực / trung lập)
- Briefing saved to `daily_snapshots` table

---

### 2. `jarvis analyze <SYMBOL>` — Deep Analysis

Run a full analysis on a stock, gold, or crypto symbol including:
- Current price, change %, volume, P/E, EPS, market cap
- Technical indicators: SMA_20/50, RSI_14, MACD line/signal/histogram
- AI-generated report via Ollama LLM

```bash
python cli.py analyze VNM              # Vietnam Dairy
python cli.py analyze BTC              # Bitcoin
python cli.py analyze XAUUSD          # Gold
python cli.py analyze BTC --verbose    # Include full technical details
```

**Supported symbols:**
- VN stocks: `VIC`, `VCB`, `FPT`, `HPG`... (auto-appends `.VN`)
- Gold: `XAUUSD`, `XAU/USD`, `XAUUSD=X`
- Crypto: `BTC`, `ETH`, `SOL`

---

### 3. `jarvis watch` — Watchlist Management

Manage your list of tracked symbols.

#### Add to watchlist
```bash
python cli.py watch add VNM           # Adds with auto-fetched name
python cli.py watch add VNM -n "Vinamilk"   # With custom name
```

#### List watchlist (with live prices)
```bash
python cli.py watch list
```
Shows: symbol, name, current price, % change for each entry.

#### Remove from watchlist
```bash
python cli.py watch remove VNM
```

---

### 4. `jarvis search <TERM>` — Knowledge Base Search

Search the financial term dictionary with relevance scoring.

```bash
python cli.py search "P/E ratio"
python cli.py search RSI
python cli.py search Bollinger bands
```

**Output:** Returns matching terms with tags, content snippets, and score ranking.

**Auto-generate (if no results found):**
System will use LLM to generate a definition, then prompt you:
> Save this to knowledge base? (y/n) → `y` saves it permanently.

---

### 5. `jarvis quiz` — Spaced Repetition Quiz

Test your financial knowledge with flashcard-style questions.

```bash
python cli.py quiz
```

**Flow:**
1. Randomly selects 5 terms from the knowledge base
2. Shows a hint (first ~150 chars of content)
3. You guess or press Enter to reveal the answer
4. Rate your recall: `rat_tot` (excellent) | `kha` (good) | `can_hoc_lai` (needs review)

---

### 6. `jarvis log [-l N]` — Activity Log Viewer

View system activity logs (commands run, errors, durations).

```bash
python cli.py log                        # Last 20 entries
python cli.py log -l 50                # Last 50 entries
python cli.py log --last 100           # Also works (same as -l)
```

**Output format:**
```
✅ 2026-06-28 10:30:05 analyze VNM | Market Cap: 78.9T VND | Time: 4523ms
⚠️ 2026-06-28 09:15:22 briefing | 23 articles fetched, sentiment: tích_cực
❌ 2026-06-27 14:00:00 analyze XYZ | Could not fetch data for XYZ
```

---

### 7. `jarvis history <DATE1> [DATE2]` — Daily Snapshot Diff

Compare two daily briefing snapshots, showing what changed between days.

```bash
python cli.py history                  # Show available dates only
python cli.py history 2026-05-20      # Line-by-line diff for one date
python cli.py history 2026-05-20 2026-05-21  # Diff between two dates
```

**Output:** Lines marked with `+` (added/changed in later date) and `-` (removed/changed). Shows news headline changes, index movements, sentiment shifts.

---

### 8. `jarvis doctor` — System Health Check

Comprehensive health check for all system components.

```bash
python cli.py doctor
```

**Checks:**
- ✅ Config file loading & Ollama/Ollama endpoint
- ✅ Database connectivity (jarvis.db) + KB entry count
- ✅ RSS source reachability (with priority-prioritized status per feed)
- ✅ Model availability

---

## Cron Scripts (Terminal Execution)

### Tier 1: Raw Data Collection
```bash
python core/tier_data_collector.py              # Run for today
python core/tier_data_collector.py --date 2026-06-27  # Override date
```
Feeds VN stocks, indices, crypto, commodities, and news headlines into `market_quotes` & `news_articles`.

### Tier 2: LLM Analysis Pipeline
```bash
python core/tier_llm_analyst.py                         # Run full analysis (calls Ollama)
python core/tier_llm_analyst.py --dry-run               # Generate prompt only, no API call
```
Reads from `market_quotes`/`news_articles`, generates analysis via Qwen3.6, cleans preamble leaks, saves to `analytical_reports`.

### Research Crawl
```bash
# Via API (from Flask):
curl -X POST http://localhost:8100/api/v1/research/crawl

# Directly:
python core/research_crawler.py  # crawl_all_brokers() → store_reports()
```

---

## Configuration (`config.yaml`)

Edit `~/jarvis-hub/config.yaml` to customize:

```yaml
system:
  name: "Jarvis Hub"
  timezone: "Asia/Saigon"

telegram:
  target_chat_id: "1670013239"       # Telegram delivery channel

ollama:
  url: "http://localhost:11434"     # Ollama endpoint
  model: "qwen3.6:35b-a3b-mxfp8" # Default LLM model
  api_key: ""                       # If needed

feed:
  sources:                          # RSS sources (name, URL, category, priority)
    - name: "Cafef Doanh nghiệp"
      url: "https://cafef.vn/doanh-nghiep.rss"
      category: "vn-stock"
      priority: 1                    # Lower = higher priority

exchange_rates_source: "vietcombank"

schedule:
  morning_briefing: "06:18"         # GMT+7
  evening_briefing: "23:00"
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `JARVIS_CONFIG` | `~/jarvis-hub/config.yaml` | Override config file path |
| OLLAMA_URL (in code) | `http://localhost:11434` | Ollama API endpoint |

---

*Last updated: 2026-06-28 — reflects actual CLI commands in cli.py.*
