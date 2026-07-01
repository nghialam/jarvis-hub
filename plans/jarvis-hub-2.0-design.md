# Jarvis Hub 2.0 — Vietnamese Market Intelligence Portal

> **Version:** v1.0 Draft  
> **Status:** Design → Implementation Ready  
> **Date Created:** 2026-06-21  
> **Target Platform:** Flask microservice on port 8100, macOS Mac Mini M4 Pro (64 GB)  
> **Root Cause Addressed:** Existing dashboard lacks usability, data freshness, and straightforward recommendations. Needs unified portal for daily professional use.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Overall Architecture](#2-overall-architecture)
3. [Dashboard Layout (9 Tabs → Unified Layout)](#3-dashboard-layout-9-tabs--unified-layout)
4. [API Layer Design](#4-api-layer-design)
5. [Backend Pipeline](#5-backend-pipeline)
6. [Database Schema (Extending jarvis.db)](#6-database-schema-extending-jarvisdb)
7. [Crawl Logic for Brokerage Reports](#7-crawl-logic-for-brokerage-reports)
8. [Integration With Existing Jarvis Hub](#8-integration-with-existing-jarvis-hub)
9. [Frontend Tech Stack](#9-frontend-tech-stack)
10. [Estimated Timeline](#10-estimated-timeline)
11. [Data Sources — Proposed Expansion](#11-data-sources--proposed-expansion)
12. [Key Design Principles](#12-key-design-principles)

---

## 1. Overview

**Objective:** Web-based information portal for financial professionals, updated daily, displaying a full market overview + news + brokerage reports.

**4 Primary Use Cases:**

1. **Market Overview** — Comprehensive information on stock market and asset classes across 1-week, 1-month, 1-quarter timeframes
2. **News Aggregator** — Curated news related to asset markets
3. **Company Focus** — Important news about listed companies
4. **Research Hub** — Analysis reports from SSI, VCI, HCM, TCBS, VCBS with filtering by week/month/quarter/year

**Target Audience:** Financial professionals using the dashboard daily for information updates and investment decisions.

---

## 2. Overall Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIETMARKET PORTAL (port 8100)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ Overview │  │  News    │  │  Companies│  │ Brokerage     │  │
│  │(Dashboard)│ │(Aggregator)│ │(Company  │  │ Research Hub  │  │
│  │          │  │          │  │  Focus)  │  │               │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬────────┘  │
│       │              │              │               │            │
│       └──────────────┴──────────────┴───────────────┘            │
│                            │                                     │
│                    ┌───────▼───────┐                             │
│                    │   API Layer   │                             │
│                    │   Flask Routes│                             │
│                    └───────┬───────┘                             │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         │                  │                  │                 │
│  ┌──────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐          │
│  │Data Fetcher │  │ News Engine  │  │ Research     │          │
│  │(Yahoo/TCInv)│  │(RSS+LLM)     │  │ Report Crawler│          │
│  └──────┬──────┘  └───────┬──────┘  └───────┬──────┘          │
│         │                 │                  │                  │
│  ┌──────▼─────────────────▼──────────────────▼──────┐          │
│  │              jarvis.db (SQLite)                   │          │
│  │  + market_overview, brokerage_reports new tables  │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Component Details

- **Frontend:** Flask + Jinja2 templates + Chart.js/lightweight-charts + Tailwind CSS
- **Backend:** Flask routes (extend app.py), Python modules (extend core/)
- **Database:** SQLite (jarvis.db) — 4 new tables
- **Data Sources:** Yahoo Finance, TCInvest, Vietstock, RSS feeds, Brokerage websites
- **LLM:** Ollama qwen3.6:35b-mlx for sentiment scoring, importance ranking, report summarization
- **Scheduler:** Hermes cron jobs for daily data refresh + report crawling

---

## 3. Dashboard Layout (9 Tabs → Unified Layout)

### Tab 1: OVERVIEW — "Mission Control"

```
┌──────────────────────────────────────────────────────────────────────┐
│  📊 VIETMARKET PORTAL                    🔍 Search   ⚡ Live    🕐 08:30│
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐           │
│  │  👑 VN-INDEX    │ │  🇺🇸 S&P 500   │ │  🇯🇵 NIKKEI    │           │
│  │  1,487.32  ▲2.1%│ │  6,382.10  ▲0.8%│ │  39,245  ▼0.3%│           │
│  │  W: +3.2% M: -1% Q: +8.7%        │ │  W: +1.1% M:+5%│           │
│  └────────────────┘ └────────────────┘ └────────────────┘           │
│                                                                      │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐           │
│  │  💵 USD/VND     │ │  🥇 GOLD       │ │  🛢️ OIL (WTI)  │           │
│  │  25,875  ▼0.1% │ │  $3,245  ▲1.2% │ │  $71.40  ▼0.5%│           │
│  │  W: -0.2%       │ │  W: +2.1%      │ │  W: -1.3%      │           │
│  └────────────────┘ └────────────────┘ └────────────────┘           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  📈 VN-INDEX 1Q/1M/1W CHART (interactive, toggle timeframe) │   │
│  │  ┌────────────────────────────────────────────────────────┐ │   │
│  │  │  [Chart: OHLC candlestick + volume bars]               │ │   │
│  │  │  ── SMA20 ── SMA50 - - - SMA200 (dashed)              │ │   │
│  │  └────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  🔥 TOP MOTIONS                                                │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │   │
│  │  │ HDB  │ │ VCX  │ │ PWM  │ │ GVR  │ │ FPT  │              │   │
│  │  │ ▲8.5%│ │ ▲7.2%│ │ ▲6.8%│ │ ▲5.9%│ │ ▲5.1%│              │   │
│  │  │ Vol: │ │ Vol: │ │ Vol: │ │ Vol: │ │ Vol: │              │   │
│  │  │ 12.1M│ │ 8.3M │ │ 5.7M │ │ 4.2M │ │ 3.8M │              │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  🌏 ASSETS BY SIGN                                         │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │   │
│  │  │ BTC  $67K │ │ ETH  $3.5K│ │ SOL  $178 │ │ DXY  104 │       │   │
│  │  │ ▲2.3% W  │ │ ▼1.1% W  │ │ ▲5.7% W  │ │ ▼0.3% W │       │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- One-glance KPI cards per asset class (VN stocks, global indices, FX, commodities, crypto)
- 3 timeframe toggle (1W / 1M / 1Q) for VN-Index + top 3 VN stocks chart
- Auto-refresh every 30s (WebSocket fallback planned for v2)
- Color-coded: green = up, red = down (VN convention)

---

### Tab 2: NEWS HUB — "News Hub"

```
┌──────────────────────────────────────────────────────────────────────┐
│  📰 MARKET NEWS              🔍 Search news   🕐 Today  📅 7D ▼ │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [FILTER BAR]                                                        │
│  All ▸ Market ▸ Stocks ▸ Macro ▸ Global ▸ Crypto ▸ Real Estate ▸ Banking│
│  [📅 Dropdown: Today | 7 Days | 30 Days | Quarter | Year]           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  🟢 HIGHLIGHTS (AI-ranked by importance)                    │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 🔴 HIGH IMPACT  │ 10:42  │  Vietcombank 0% interest... │   │   │
│  │  │ DB: 47  FB: 23  Comments: 156                          │   │   │
│  │  │ [Source: CafeF] [VN-Stock] [🟢 Positive]               │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 🟡 MEDIUM IMPACT  │ 09:15  │  TCBS increases capital...   │   │   │
│  │  │ DB: 12  FB: 8  Comments: 43                            │   │   │
│  │  │ [Source: VnExpress] [Banking] [🟡 Neutral]            │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 🔴 HIGH IMPACT  │ 08:30  │  SSI reports Q2 earnings...   │   │   │
│  │  │ DB: 31  FB: 19  Comments: 87                           │   │   │
│  │  │ [Source: CafeF] [Brokerage] [🟢 Positive]               │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  🌍 GLOBAL NEWS                                                │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                   │   │
│  │  │ Fed  │ │China│ │EU   │ │Oil  │ │Trade│                   │   │
│  │  │ cut  │ │stim│ │rate│ │supply│ │war │                     │   │
│  │  │...  │ │... │ │... │ │... │ │... │                       │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **AI-ranked articles:** LLM rates impact level (HIGH/MEDIUM/LOW) based on content
- **Filter:** by category (Market/Stocks/Macro/Global/Crypto), timeframe (Today/7D/30D/Quarter/Year)
- **Sentiment badge:** 🟢 Positive / 🔴 Negative / 🟡 Neutral (from heuristic + LLM)
- **Engagement metrics:** downvotes, bookmark count (localStorage)
- **Progressive disclosure:** 2-line preview, click to expand full

---

### Tab 3: COMPANIES — "Company Focus"

```
┌──────────────────────────────────────────────────────────────────────┐
│  🏢 COMPANY NEWS              🔍 Search company   📅 30D ▼    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [SEARCH BAR: "FPT", "VNM", "VCB"...]  [Sector filter ▼]           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  COMPANY NEWSFEED (sortable by relevance/date)        │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ FPT  │ Tech Sector  │  2h ago  │  🟢 Positive          │   │   │
│  │  │ FPT signs AI deal with Microsoft...                    │   │   │
│  │  │ [CafeF] [VN-Stock] [Volume: 2.1M shares]               │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ VNM  │ FMCG Sector  │  5h ago  │  🔴 Negative          │   │   │
│  │  │ VNM lowers export price for pork to China...             │   │   │
│  │  │ [VnExpress] [FMCG] [Volume: 890K shares]               │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ HPG  │ Steel Sector  │  8h ago  │  🟢 Positive          │   │   │
│  │  │ HPG upgraded credit rating by Fitch...                  │   │   │
│  │  │ [CafeF] [Steel] [Volume: 5.3M shares]                  │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  👑 WATCHLIST (auto-populated from DB)                         │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │   │
│  │  │ FPT  │ VNM  │ VCB  │ HDB  │ SSI  │              │   │
│  │  │ 12news│ 8news │ 15news│ 6news │ 9news │              │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Full-text search:** search by symbol, company name, keyword in title/content
- **Sector filter:** Banking, Real Estate, Tech, FMCG, Steel, Brokerage...
- **Per-article metadata:** sentiment, volume, source, time
- **Watchlist sidebar:** shows new article count per symbol in watchlist

---

### Tab 4: RESEARCH — "Research Hub"

```
┌──────────────────────────────────────────────────────────────────────┐
│  📊 RESEARCH REPORTS              🔍 Search report                │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [FILTER BAR]                                                        │
│  All ▸ SSI ▸ VCI ▸ HCM ▸ TCBS ▸ VCBS                               │
│  [📅 Dropdown: Today | 7D | 30D | Q1 2026 | 2026 | 2025]           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  LATEST REPORTS                                                │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 📄 SSI  │ 21/06/2026  │  VN-Index Outlook Q3/2026      │   │   │
│  │  │  Q3/2026 trend analysis: target 1,550 points...        │   │   │
│  │  │  Rating: 5/5 Stars  │  Download PDF  │  Read Summary   │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 📄 VCI  │ 20/06/2026  │  Banking Sector Review         │   │   │
│  │  │  Banking sector outlook Q3: ACB, VPB stand out...   │   │   │
│  │  │  Rating: 4/5 Stars  │  Download PDF  │  Read Summary   │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  │                                                                │   │
│  │  ┌────────────────────────────────────────────────────────┐   │   │
│  │  │ 📄 HCM  │ 19/06/2026  │  Tech Stocks Pick Q2           │   │   │
│  │  │  Tech top picks: FPT, GVR, VRC...                      │   │   │
│  │  │  Rating: 4/5 Stars  │  Download PDF  │  Read Summary   │   │   │
│  │  └────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  REPORT STATS BY COMPANY                                       │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │   │
│  │  │ SSI  │ VCI  │ HCM  │ TCBS │ VCBS │              │   │
│  │  │ 45rt │ 38rt │ 32rt │ 28rt │ 25rt │              │   │
│  │  │ Q3'26│ Q3'26│ Q2'26│ Q2'26│ Q2'26│              │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**Key Features:**
- **Filter:** by brokerage (SSI/VCI/HCM/TCBS/VCBS), timeframe (Today/7D/30D/Q/Y)
- **Each report:** title, date, brief summary, rating (LLM-generated quality score), download link (PDF)
- **Stats sidebar:** report count per company, per quarter
- **Click on report → modal** with full preview (if text extraction from PDF available)

---

## 4. API Layer Design

```
GET  /api/v1/overview/indices        → VN-Index, global indices, rates
GET  /api/v1/overview/chart?sym=VN-INDEX&range=1w|1m|1q  → OHLC data
GET  /api/v1/overview/top-motions    → Top gainers/losers W/M/Q
GET  /api/v1/overview/crypto         → BTC, ETH, SOL prices
GET  /api/v1/overview/gold           → Gold price

GET  /api/v1/news/list?category=all&timeframe=7d&sentiment=all  → Articles
GET  /api/v1/news/article/{id}       → Full article details
GET  /api/v1/news/trending           → Trending topics (LLM-generated)

GET  /api/v1/companies/search?q=FPT  → Company search
GET  /api/v1/companies/{symbol}/news?days=30  → News for symbol
GET  /api/v1/companies/{symbol}/overview  → Stock overview + key metrics

GET  /api/v1/research/list?broker=ssi&period=1m  → Report list
GET  /api/v1/research/{report_id}   → Report details
GET  /api/v1/research/download/{id} → PDF download link
GET  /api/v1/research/stats         → Stats per brokerage

POST /api/v1/webhooks/news           → Ingest new article
POST /api/v1/webhooks/research       → Ingest new report
```

---

## 5. Backend Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    DAILY SCHEDULE                             │
│                                                              │
│  06:00  ──► Market Data Refresh (all indices, rates, crypto) │
│  06:15  ──► News RSS Fetch (all sources)                     │
│  06:20  ──► LLM Sentiment + Importance Scoring               │
│  06:30  ──► Store to jarvis.db                               │
│  08:00  ──► Brokerage Report Crawl (SSI/VCI/HCM/TCBS/VCBS)   │
│  12:00  ──► Mid-day News Refresh                             │
│  15:00  ──► Market Close Data + Top Motions                  │
│  18:00  ──► Evening News Refresh                             │
│                                                              │
│  LIVE (every 30s) ──► WebSocket push for price updates       │
└──────────────────────────────────────────────────────────────┘
```

### Brokerage Reports — Data Sources

| Broker | Website | Path |
|--------|---------|------|
| SSI | ssi.com.vn | Research/Analysis Reports |
| VCI | vci.com.vn | Research & Analysis |
| HCM | hsc.com.vn | Research Reports |
| TCBS | tcbs.com.vn | Research & Insights |
| VCBS | vcbroker.com.vn | Research |

### Crawl Strategy
- **Cron job `research_crawler.py`** runs 2x/day (08:00, 18:00)
- Parse HTML pages → extract report titles, dates, PDF links
- LLM summary: 2-3 line summary per report
- Store: `brokerage_reports` table in jarvis.db

---

## 6. Database Schema (Extending jarvis.db)

### Existing Tables (already present)

| Table | Cols | Purpose |
|-------|------|---------|
| knowledge | 6 | Financial terms FTS5 search |
| activity_log | 7 | System command log |
| daily_snapshots | 5 | Daily briefing content |
| watchlist | 4 | User watchlist |
| market_cache | 5 | Cached market data |
| market_evaluations | 5 | Past market evaluations |
| trading_alerts | 8 | Trading signals |
| memories | 8 | Persistent memory entries |
| meta | 2 | System key-value config |
| watchlist_symbols | 18 | Multi-asset watchlist |
| signals_log | 10 | Signal detection log |
| price_history | 9 | OHLC price data |
| articles | 11 | RSS articles |
| recommendations | 8 | LLM recommendations |
| run_chains | 12 | Pipeline run metadata |

### New Tables (to add)

```sql
-- Market overview (pre-computed for fast dashboard load)
CREATE TABLE IF NOT EXISTS market_overview (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    name TEXT,
    asset_type VARCHAR(20),        -- index, stock, crypto, commodity, fx
    price REAL,
    change_pct REAL,
    market_cap REAL,
    volume REAL,
    week_change REAL,              -- % change 1 week
    month_change REAL,             -- % change 1 month
    quarter_change REAL,           -- % change 1 quarter
    chart_data TEXT,               -- JSON array of OHLC data points
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- News with enhanced metadata
CREATE TABLE IF NOT EXISTS news_enhanced (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER,             -- FK to articles.id (reuse)
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,                   -- Full content (if scraped)
    url TEXT NOT NULL,
    source TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP,
    category TEXT,                  -- market, stocks, macro, global, crypto, real_estate, banking
    sentiment TEXT,                 -- positive, negative, neutral
    sentiment_score REAL,           -- -1.0 to +1.0
    importance REAL,                -- LLM-ranked importance (0-10)
    affected_symbols TEXT,          -- JSON: ["FPT", "VNM", ...]
    is_trending BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Brokerage reports
CREATE TABLE IF NOT EXISTS brokerage_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker VARCHAR(10) NOT NULL,    -- SSI, VCI, HCM, TCBS, VCBS
    title TEXT NOT NULL,
    summary TEXT,                   -- LLM-generated brief (2-3 lines)
    full_text TEXT,                 -- Extracted text from PDF (optional)
    pdf_url TEXT,                   -- Direct PDF download link
    report_date DATE NOT NULL,
    crawled_at TIMESTAMP,
    rating INTEGER,                 -- Quality rating 1-5
    target_index TEXT,              -- e.g., "VN-Index", "KOSPI"
    sector_focus TEXT,              -- e.g., "Banking", "Tech"
    source_url TEXT,                -- Source page URL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio watchlist (enhanced user watchlist)
CREATE TABLE IF NOT EXISTS portfolio_watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    name TEXT,
    sector TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked TIMESTAMP,
    UNIQUE(symbol)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_overview_date ON market_overview(date DESC);
CREATE INDEX IF NOT EXISTS idx_market_overview_symbol ON market_overview(symbol);
CREATE INDEX IF NOT EXISTS idx_news_enhanced_category ON news_enhanced(category);
CREATE INDEX IF NOT EXISTS idx_news_enhanced_importance ON news_enhanced(importance DESC);
CREATE INDEX IF NOT EXISTS idx_news_enhanced_published ON news_enhanced(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_brokerage_reports_broker ON brokerage_reports(broker);
CREATE INDEX IF NOT EXISTS idx_brokerage_reports_date ON brokerage_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_brokerage_reports_broker_date ON brokerage_reports(broker, report_date DESC);
```

---

## 7. Crawl Logic for Brokerage Reports

```python
# research_crawler.py

BROKERS = {
    "SSI": {
        "url": "https://ssi.com.vn/research/reports/",
        "parser": "ssi_report_parser",
        "selectors": {
            "title": "h3.report-title",
            "date": "span.report-date",
            "pdf": "a.pdf-download[href$='.pdf']",
        }
    },
    "VCI": {
        "url": "https://vci.com.vn/research/",
        "parser": "vci_report_parser",
        "selectors": {
            "title": "div.report-item h4",
            "date": "div.report-item .date",
            "pdf": "a.download-link",
        }
    },
    "HCM": {
        "url": "https://hsc.com.vn/research-reports/",
        "parser": "hcm_report_parser",
    },
    "TCBS": {
        "url": "https://tcbs.com.vn/research/",
        "parser": "tcbs_report_parser",
    },
    "VCBS": {
        "url": "https://vcbroker.com.vn/research/",
        "parser": "vcbroker_report_parser",
    },
}


def crawl_all_brokers():
    """Crawl all brokerages for new reports."""
    results = []
    for broker, config in BROKERS.items():
        reports = crawl_broker(broker, config)
        results.extend(reports)
    store_reports(results)
    return results


def crawl_broker(broker, config):
    ...
```

---

## 8. Integration With Existing Jarvis Hub

**Extend (don't replace):**
- `app.py`: Add new Flask route groups (`/overview/`, `/news/`, `/companies/`, `/research/`)
- `core/`: Add `market_overview.py`, `news_engine.py`, `research_crawler.py`
- `jarvis.db`: Add 4 new tables (see Section 6)
- Keep existing Telegram delivery, cron jobs, and CLI all working

**Migration strategy:**
1. Add new DB tables (backward compatible — no impact on existing)
2. Add new API routes (versioned `/api/v1/`)
3. Add new frontend tab templates
4. Deploy and verify — existing users unaffected

---

## 9. Frontend Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Template Engine** | Jinja2 (existing) | No learning curve, Flask native |
| **Charting** | Chart.js + lightweight-charts | Candlestick + volume + SMA/EMA overlays |
| **CSS** | Tailwind CSS (CDN) | Fast styling, responsive |
| **JS** | Vanilla JS + Fetch API | No React/Vue — keep it simple |
| **Search** | SQLite FTS5 (existing) | Full-text search articles + reports |
| **Real-time** | SSE (Server-Sent Events) | Fallback if WebSocket unavailable |

---

## 10. Estimated Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **Phase 1: Foundation** | 2 days | New DB tables, data fetcher extensions, basic API routes |
| **Phase 2: Overview Dashboard** | 2 days | Tab 1 UI, chart integration, live data refresh |
| **Phase 3: News Hub** | 2 days | Tab 2 UI, RSS integration, LLM importance scoring |
| **Phase 4: Company Focus** | 1 day | Tab 3 UI, search + sector filter |
| **Phase 5: Research Hub** | 2 days | Tab 4 UI, brokerage crawler, PDF handling |
| **Phase 6: Polish & Testing** | 1 day | UI polish, error handling, performance tuning |

**Total: ~10 days**

---

## 11. Data Sources — Proposed Expansion

### VN Stock News (increased from 3 → 10 sources)

| Source | URL | Category |
|--------|-----|----------|
| CafeF Businesses | cafef.vn/doanh-nghiep.rss | vn-stock |
| CafeF Market | cafef.vn/thi-truong.rss | vn-market |
| VnExpress Business | vnexpress.net/rss/kinh-doanh.rss | vn-business |
| VnExpress Economy | vnexpress.net/rss/kinh-te.rss | vn-economy |
| Vietnamnet Economy | vietnamnet.vn/cong-nghe.rss | vn-economy |
| Bachkhoahoangha | bachkhoahoangha.com.vn/rss | vn-stock |
| Vietstock | vietstock.com.vn/rss | vn-market |
| Reuters Business | feeds.reuters.com/reuters/businessNews | global-business |
| BBC Business | feeds.bbci.co.uk/news/business/rss.xml | global-economy |
| Bloomberg Markets | feeds.bloomberg.com/markets/news.rss | global-markets |

### Brokerage Research Sites

| Broker | URL | Format |
|--------|-----|--------|
| SSI | ssi.com.vn/research/reports/ | HTML list + PDF links |
| VCI | vci.com.vn/research/ | HTML list + PDF links |
| HCM | hsc.com.vn/research-reports/ | HTML list + PDF links |
| TCBS | tcbs.com.vn/research/ | HTML list + PDF links |
| VCBS | vcbroker.com.vn/research/ | HTML list + PDF links |

### Market Data Sources (existing)

| Source | What | Backend Function |
|--------|------|-----------------|
| Yahoo Finance | VN-Index, global indices, crypto, gold | market.py: `_fetch_yahoo_price()` |
| TCInvest API | VN equity prices | vn_market.py (existing) |
| Vietcombank FX | USD/VND rate | news_service.py: `get_exchange_rates()` |
| Vietstock | VN stock data (fallback) | gotham_brief.py scan pipeline |

---

## 12. Key Design Principles

1. **One-glance readability** — Financial professionals need to see the full picture in <5 seconds
2. **Progressive disclosure** — Overview → detail on click per section
3. **Data freshness indicators** — Clearly show update time per card
4. **Mobile responsive** — Usable on iPad/phone while mobile
5. **Keyboard shortcuts** — `1-9` for tabs, `/` for search, `r` for refresh
6. **Dark mode toggle** — Professionals often work with low screen brightness
7. **LocalStorage persistence** — Watchlist, filters, last viewed tab saved locally
8. **Graceful degradation** — When data source is down → show cached data + "STALE" badge
9. **LLM as enhancement, not dependency** — Dashboard usable even when Ollama is down
10. **Backward compatible** — Existing Telegram delivery + cron jobs continue working

---

## Decision Points For Rex

1. **Start building now?** — If approved, I'll break into phases and code incrementally
2. **Brokerage reports crawl** — SSI/VCI/HCM/TCBS/VCBS websites may change HTML layout. Need fallback mechanism when parser breaks
3. **Charting library** — Chart.js is fine for basic charts, but lightweight-charts (TradingView) is stronger for candlestick. Which does Rex prefer?
4. **Scope** — Want to add any other features? (e.g., portfolio tracker, personal watchlist with alerts, comparison view)

---

## Cross-Links

| Document | File | Purpose |
|----------|------|---------|
| Backlog | jarvis-hub/BACKLOG.md | Existing priorities |
| AGENTS.md | jarvis-hub/AGENTS.md | System architecture constraints |
| MEMORY.md | jarvis-hub/MEMORY.md | Project conventions & bug fixes |
| Data Architecture | Plans/ (future) | Detailed pipeline schedule |
| Operational Blueprint | Plans/ (future) | Deployment + monitoring config |

---

*Document created: 2026-06-21 by Jarvis Hub 2.0 Design Sprint*
