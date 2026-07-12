# Jarvis Hub 2.0 — Vietnamese Market Intelligence Portal

## Design Specification v2.0 — 2026-07-07

---

## 1. Overview

**Jarvis Hub 2.0** is a web-based portal that aggregates Vietnamese stock market data, designed for financial professionals who need daily market tracking, news aggregation, and broker research analysis to make investment decisions based on real-time data and professional insights.

### 1.0. Market Intelligence Agent (NEW — v2.0)

A new autonomous agent system operating on a **6-hour cycle** that:
- **Ingests** raw news from RSS feeds, web scrapers, and news APIs for the last 6 hours
- **Parses** and cleans article content (strips HTML, removes boilerplate)
- **Analyzes** each article with LLM: generates concise summaries (≤3 sentences), assigns sentiment (Bullish/Bearish/Neutral)
- **Synthesizes** all article summaries into a cohesive "Market Brief" identifying major themes and trends
- **Delivers** structured JSON output to the database, then triggers notifications (Telegram, dashboard)

See **Section 1.6** for full architecture and pipeline details.

### 1.6. Market Intelligence Agent Architecture (NEW)

```
┌─────────────────────────────────────────────────────────────────┐
│              MARKET INTELLIGENCE AGENT — 6-Hour Cycle            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ STAGE 1      │    │ STAGE 2      │    │ STAGE 3      │       │
│  │ INGESTION    │───▶│ PARSING      │───▶│ ANALYSIS     │       │
│  │              │    │              │    │ (Analyst)    │       │
│  │ • RSS feeds  │    │ • Strip HTML │    │ • Summarize  │       │
│  │ • Web scrapers│   │ • Remove     │    │   per article│       │
│  │ • News APIs  │    │   boilerplate│    │ • Sentiment  │       │
│  │ • Last 6h    │    │ • Clean text │    │   classify   │       │
│  └──────────────┘    └──────────────┘    └──────┬───────┘       │
│                                                  │              │
│                                          ┌───────▼───────┐      │
│                                          │ STAGE 4      │      │
│                                          │ SYNTHESIS    │      │
│                                          │ (Strategist) │      │
│                                          │              │      │
│                                          │ • Identify   │      │
│                                          │   major themes│     │
│                                          │ • Detect     │      │
│                                          │   trends     │      │
│                                          │ • Generate   │      │
│                                          │   Market Brief│     │
│                                          └───────┬───────┘      │
│                                                  │              │
│                                          ┌───────▼───────┐      │
│                                          │ STAGE 5      │      │
│                                          │ DELIVERY     │      │
│                                          │              │      │
│                                          │ • Save JSON  │      │
│                                          │   to DB      │      │
│                                          │ • Trigger    │      │
│                                          │   notifications│    │
│                                          │   (Telegram, │      │
│                                          │   dashboard) │      │
│                                          └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

#### 1.6.1. Stage Details

| Stage | Component | File | Description |
|---|---|---|---|
| **Ingestion** | `core/market_intelligence/ingestion.py` | Fetches raw articles from RSS feeds, web scrapers, news APIs for the last 6 hours |
| **Parsing** | `core/market_intelligence/parsing.py` | Strips HTML tags, removes boilerplate (ads, nav), cleans text for LLM consumption |
| **Analysis** | `core/market_intelligence/analyst.py` | LLM-powered: generates ≤3 sentence summary per article, classifies sentiment (Bullish/Bearish/Neutral) |
| **Synthesis** | `core/market_intelligence/synthesizer.py` | LLM-powered: aggregates all summaries into cohesive Market Brief with themes and trends |
| **Delivery** | `core/market_intelligence/delivery.py` | Persists structured JSON to DB, triggers notification service (Telegram/webhook) |

#### 1.6.2. Output Schema

```json
{
    "articles": [
        {
            "title": "String",
            "date": "String (ISO format)",
            "url": "String",
            "summary": "String (≤3 sentences)",
            "sentiment": "String (Bullish|Bearish|Neutral)"
        }
    ],
    "market_brief": "String (cohesive synthesis of all articles)",
    "status": "Notification Ready"
}
```

#### 1.6.3. Operational Constraints

- **Accuracy:** No hallucination — if article impact unclear, mark sentiment as "Neutral" with note
- **Format:** Valid parsable JSON output required
- **Tone:** Objective, professional, analytical — no biased or emotional language
- **Temporal Context:** Analysis based strictly on news from current 6-hour window
- **Deterministic:** Every article input must be processed and represented before Market Brief generation

#### 1.6.4. Trigger & Notification Flow

```
Pipeline Complete
    │
    ▼
JSON saved to DB (market_intelligence table)
    │
    ▼
status = "Notification Ready"
    │
    ├─▶ Telegram webhook → push summary to chat
    ├─▶ Dashboard API → update /api/market-intelligence endpoint
    └─▶ Activity log → record in activity_log table
```

#### 1.6.5. Scheduling

- **Frequency:** Every 6 hours (06:00, 12:00, 18:00, 00:00 SGT)
- **Implementation:** APScheduler cron job or Hermes Agent cron job
- **Grace period:** If pipeline fails, retry once after 5 minutes; log failure to activity_log

### 1.1. Objectives

- **Single-pane view:** Market data, news, and research reports in one unified interface.
- **Real-time updates:** Market data refreshes every 300s, news pulled hourly.
- **Flexible filtering:** By time period (week/month/quarter/year), by broker, by sector.
- **Lightweight & fast:** Responsive, desktop-optimized (financial professionals use desktop).

### 1.2. Target Users

- Financial analysts, portfolio managers, investment professionals.
- Time-sensitive: need latest information, no long load waits.
- Data-driven: prefer numbers, charts, comparisons over long descriptions.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Jarvis Hub 2.0 — Frontend                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────────────┐   │
│  │Market   │ │ News    │ │ Company │ │ Reports             │   │
│  │Overview │ │Aggregator│ │ News    │ │ Aggregator          │   │
│  │Tab      │ │ Tab     │ │ Tab     │ │ Tab                 │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────────────────┘   │
│  ┌─────────┐ ┌─────────────────────────────────────────────┐    │
│  │Screener │ │ Controls: Date Range | Broker | Sector      │    │
│  │& Alerts │ │ Filters: Week | Month | Quarter | Year      │    │
│  └─────────┘ └─────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Flask Backend   │
                    │   (jarvis-hub/)   │
                    │                   │
                    │  API Routes:      │
                    │  /api/market/     │
                    │  /api/news/       │
                    │  /api/company/    │
                    │  /api/reports/    │
                    └─────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
     ┌──────────────┐ ┌─────────────┐ ┌────────────┐
     │ Vietstock/   │ │ News APIs / │ │ Broker     │
     │ vnstock3     │ │ RSS Scrapers│ │ Websites   │
     │ (OHLCV data) │ │ (Reuters,   │ │ (SSI, VCI, │
     │              │ │  CNBC, ...) │ │  HCM, ...) │
     └──────────────┘ └─────────────┘ └────────────┘
                              │
                              ▼
     ┌─────────────────────────────────────────────┐
     │  mlx-lm (Apple Silicon native inference)    │
     │  • load() / generate() / stream_generate()  │
     │  • Relevance scoring, summarization         │
     │  • Entity extraction (tickers, companies)   │
     │  • Sentiment analysis (bullish/bearish)     │
     │  • Report summarization & consensus view    │
     └─────────────────────────────────────────────┘
```

### 2.1. Components

| Component | Technology | Description |
|---|---|---|
| Frontend | HTML/CSS/JS + Chart.js | Lightweight SPA, responsive, professional dark theme |
| Backend | Flask (extends existing jarvis-hub) | REST API, SQLite cache, background threads |
| Data Layer | SQLite + vnstock3 / DNSE API | Historical data storage, OHLCV, news |
| Background Jobs | APScheduler / Threading | Auto-refresh market data 300s, news 60m |
| LLM Integration | mlx-lm (qwen3.6-35b-a3b-mlx-8bit) | News summarization, insights, relevance scoring, entity extraction |
| **Market Intelligence Agent** | **Python pipeline + LLM** | **6-hour cycle: ingest → parse → analyze → synthesize → deliver** |

---

## 3. UI Design — 5 Tabs

### 3.1. Tab 1: Market Overview

#### 3.1.1. Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [🔴] Market Overview       [Week] [Month] [Quarter] [Year]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ VN-Index     │  │ HNX-Index    │  │ VN30         │          │
│  │ 1,284.56 ▲0.8%│ │ 247.32 ▲0.3% │ │ 342.10 ▼0.2% │          │
│  │              │  │              │  │              │          │
│  │ [Chart: Line]│  │ [Chart: Line]│  │ [Chart: Line]│          │
│  │              │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Sector Heatmap                                            ││
│  │  ┌────┬────┬────┬────┬────┬────┬────┬────┐                ││
│  │  │Bank│Real│Tech│Auto│Food│Tele│Powe│Chem│                ││
│  │  │▲2.1%│▼0.5%│▲1.3%│▲0.8%│▼0.3%│▲1.0%│▲0.6%│▼1.2%│           ││
│  │  │    │    │    │    │    │    │    │    │                ││
│  │  └────┴────┴────┴────┴────┴────┴────┴────┘                ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │ Top Gainers          │  │ Top Losers           │             │
│  │ 1. HVN  ▲5.2%       │  │ 1. VNM  ▼3.1%        │             │
│  │ 2. VCX  ▲4.8%       │  │ 2. MWN  ▼2.7%        │             │
│  │ 3. GVR  ▲4.1%       │  │ 3. HPG  ▼2.3%        │             │
│  │ 4. FPT  ▲3.9%       │  │ 4. FPM  ▼2.1%        │             │
│  │ 5. MAB  ▲3.7%       │  │ 5. LCI  ▼1.8%        │             │
│  └──────────────────────┘  └──────────────────────┘             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Volume Analysis                                           ││
│  │  Exchange    │ Volume (B)  │ Value (Trillion VND)          ││
│  │  HOSE        │ 152.3       │ 45,200                        ││
│  │  HNX         │ 18.7        │ 3,100                         ││
│  │  UPCoM       │ 8.2         │ 890                           ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

#### 3.1.2. Data Fields

| Field | Source | Refresh |
|---|---|---|
| VN-Index, HNX-Index, VN30 | Vietstock / vnstock3 | 300s |
| Stock OHLCV prices | Vietstock / vnstock3 | 300s |
| Volume, trade value | Vietstock / vnstock3 | 300s |
| Top Gainers / Losers | Self-calculated from OHLCV | 300s |
| Sector performance | Grouped by industry code | 300s |
| Up/Down ratio | Count stocks by daily change | 300s |

#### 3.1.3. Time Periods

- **Week:** Period = -7 days, compare with previous week close
- **Month:** Period = -30 days, compare with previous month close
- **Quarter:** Period = -90 days, compare with previous quarter close
- **Year:** Period = -365 days (optional, in filter bar)

#### 3.1.4. Chart Configuration

- Default: Line chart with gradient fill
- Hover tooltip: date + value + daily change %
- Grid: light gray, minimal grid lines
- Colors: green (▲), red (▼)
- Time axis: auto-scale based on selected period

---

### 3.2. Tab 2: News Aggregator

#### 3.2.1. Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [📰] News Aggregator       [All] [Stocks] [Forex] [Crypto]    │
│                           [Week] [Month] [Quarter]             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ FEATURED / TOP STORIES                                     │ │
│  │                                                             │ │
│  │  VN-Index gains strongly as money flows into              │ │
│  │  banking and real estate sectors                           │ │
│  │  ── Reuters • 2h ago • Markets • ●●●○○○                    │ │
│  │  [Read more →]                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────┐             │
│  │ Top Stories          │  │ By Source            │             │
│  │                      │  │ ┌──────────────────┐ │             │
│  │ 1. Fed keeps rates   │  │ │ Reuters  ●●●●○○  │ │             │
│  │    unchanged at 5.5% │  │ │ CNBC   ●●●○○○  │ │             │
│  │    [2h ago]          │  │ │ Bloomberg●●●●●○  │ │             │
│  │                      │  │ │ VnExpress●●●○○○  │ │             │
│  │ 2. VN30 surpasses    │  │ │ Reddit   ●○○○○○  │ │             │
│  │    340 psychological │  │ │ Vietstock●●●●●○  │ │             │
│  │    level [4h ago]    │  │ └──────────────────┘ │             │
│  │                      │  │                      │             │
│  │ 3. Global gold prices│  │ Total: 142 articles  │             │
│  │    drop on strong USD│  │ Last updated: xx:xx  │             │
│  │    [6h ago]          │  │                      │             │
│  │                      │  └──────────────────────┘             │
│  │                      │                                      │
│  │ 4. ...               │                                      │
│  └──────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.2.2. News Sources

| Source | Type | Coverage | Refresh |
|---|---|---|---|
| **Reuters Vietnam** | RSS API | Global + VN macro | 30m |
| **CNBC** | RSS / Web scrape | Global markets | 30m |
| **Bloomberg** | Web scrape | Global + Asia | 30m |
| **VnExpress International** | RSS | VN economy + business | 30m |
| **Reddit r/stocks r/investing** | Reddit API | Sentiment, breaking news | 1h |
| **Vietstock.vn** | Web scrape | VN market-specific | 30m |
| **CafeF.vn** | Web scrape | VN stock news | 30m |

#### 3.2.3. Data Fields

| Field | Description |
|---|---|
| headline | Article headline |
| source | Source (Reuters, CNBC, ...) |
| published_at | Publication time |
| category | Global Macro, VN Market, Forex, Crypto, Commodities |
| sentiment | AI-assigned: Bullish/Bearish/Neutral (from LLM) |
| relevance_score | 1-5 stars (importance vs noise) |
| snippet | 2-3 sentence summary |
| url | Link to original article |
| tags | Keywords: [Fed, CPI, VN-Index, Bank, ...] |

#### 3.2.4. Sorting & Filtering

- Default: **Relevance score** (descending), last 7 days
- Sort alternatives: chronological, by source, by sentiment
- Filter by: category (dropdown), source (multi-select), date range
- Featured articles: top 3 by relevance + recency (auto-selected)

---

### 3.3. Tab 3: Company News

#### 3.3.1. Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [🏢] Company News          [Search ticker...]  [Week] [Month] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ LIVE TICKER BAR                                            │ │
│  │ [HVH ▲2.3%] [GVR ▲1.8%] [VNM ▼1.2%] [FPT ▲0.5%] ...    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  EVENTS / KEY NEWS (High-impact company news)              │ │
│  │                                                             │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │ │
│  │  │ ACB          │  │ VHM          │  │ FPT          │     │
│  │  │ ↑ Dividend   │  │ ↓ Buyback    │  │ ↑ Earnings   │     │
│  │  │ 15,000đ/sh   │  │ 2M shares    │  │ Q2 revenue   │     │
│  │  │ 2h ago       │  │ 5h ago       │  │ ↑18% YoY     │     │
│  │  │ [Detail →]   │  │ [Detail →]   │  │ [Detail →]   │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  DETAILED FEED (All company news)                          │ │
│  │                                                             │ │
│  │  [Filter: Ticker __| Type __| Source __| Date __]          │ │
│  │                                                             │ │
│  │  ┌───────────────────────────────────────────────────────┐ │ │
│  │  │ 📊 MBB — MBBank publishes Q2 2026 financial report   │ │ │
│  │  │    Net profit +12% YoY to 12.3T VND ...              │ │ │
│  │  │    Vietstock • 3h ago • Earnings • ●●●●○○             │ │ │
│  │  └───────────────────────────────────────────────────────┘ │ │
│  │  ┌───────────────────────────────────────────────────────┐ │ │
│  │  │ 📊 VCB — VietinBank announces 2027 strategic plan    │ │ │
│  │  │    Target ROE 18%, NIM expansion to 4.2% ...          │ │ │
│  │  │    CafeF • 5h ago • Strategy • ●●●●○○                 │ │ │
│  │  └───────────────────────────────────────────────────────┘ │ │
│  │  ...                                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.3.2. News Event Types

| Type | Icon | Description |
|---|---|---|
| Earnings | 📊 | Quarterly/annual financial reports |
| Dividend | 💰 | Dividend policy |
| Buyback | 🔄 | Share buyback |
| IPO | 🆕 | Initial public offering |
| Strategy | 🎯 | New business strategy |
| Regulation | ⚖️ | Regulatory changes impacting the company |
| Merger | 🔗 | M&A, acquisitions |
| Alert | 🚨 | Risk alerts, board meetings |

#### 3.3.3. News Sources

| Source | Coverage |
|---|---|
| Vietstock.vn | Ticker-specific news, earnings, dividends |
| CafeF.vn | Detailed company analysis, financial data |
| Yahoo Finance VN | International coverage of VN stocks |
| Business24.vn | Corporate news, IPO tracking |
| Internal scraper | Custom rules per ticker |

#### 3.3.4. Data Fields

| Field | Description |
|---|---|
| ticker | Stock symbol (HVH, GVR, VNM, ...) |
| company_name | Company name |
| event_type | Earnings, Dividend, Buyback, ... |
| headline | Headline |
| snippet | Summary |
| impact_score | 1-5 (price impact potential) |
| published_at | Publication time |
| source | News source |
| url | Link |
| related_tickers | Related tickers |

---

### 3.4. Tab 4: Research Reports

#### 3.4.1. Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [📈] Research Reports     [SSI] [VCI] [HCM] [TCBS] [VCBS]    │
│                        [Week] [Month] [Quarter] [Year]         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  BROKER SUMMARY (Quick overview)                          │ │
│  │                                                             │ │
│  │  SSI:  VN-Index targets 1,310 | Overweight Bank, Real Estate│
│  │  VCI:  Bullish on Tech, Energy | Target index 1,320         │
│  │  HCM:  Caution on Q3 | Favor Value plays                    │
│  │  TCBS: Positive on consumer stocks | Target 1,295           │
│  │  VCBS: Neutral, wait for clarity on rate cuts               │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  DETAILED REPORTS                                           │ │
│  │                                                             │ │
│  │  [Filter: Broker __| Date __| Sector __| Rating __]        │ │
│  │                                                             │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  │ 📄 SSI       │  │ 📄 VCI       │  │ 📄 HCM       │     │
│  │  │ Weekly Chart │  │ Sector Mix   │  │ Macro View   │     │
│  │  │ 21 Jun 2026  │  │ 20 Jun 2026  │  │ 19 Jun 2026  │     │
│  │  │                                              │     │
│  │  │ Index Target:│  │ Top Picks:   │  │ Market:      │     │
│  │  │ 1,310 (UB)   │  │ FPT, GSC,   │  │ Neutral      │     │
│  │  │ Top Picks:   │  │     POI     │  │ 300-day:     │     │
│  │  │ HVN, CTG,    │  │              │  │ 1,250        │     │
│  │  │     VCB      │  │              │  │              │     │
│  │  │              │  │              │  │              │     │
│  │  │ [Download →] │  │ [Download →] │  │ [Download →] │     │
│  │  └──────────────┘  └──────────────┘  └──────────────┘     │
│  │                                                             │
│  │  ┌──────────────┐  ┌──────────────┐                        │
│  │  │ 📄 TCBS      │  │ 📄 VCBS      │                        │
│  │  │ Consumer     │  │ Month-end    │                        │
│  │  │ Focus        │  │ Review       │                        │
│  │  │ 18 Jun 2026  │  │ 17 Jun 2026  │                        │
│  │  │              │  │              │                        │
│  │  │ Top Picks:   │  │ Market:      │                        │
│  │  │ FPT, VIC,    │  │ Accumulate   │                        │
│  │  │     DGC      │  │ 300-day:     │                        │
│  │  │              │  │ 1,280        │                        │
│  │  │ [Download →] │  │ [Download →] │                        │
│  │  └──────────────┘  └──────────────┘                        │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.4.2. Report Data Fields

| Field | Description |
|---|---|
| broker | SSI, VCI, HCM, TCBS, VCBS |
| report_type | Weekly Chart, Sector Mix, Macro View, Stock Recommendation, Earnings Forecast |
| title | Report title |
| published_at | Publication date |
| index_target | Target index (VN-Index) |
| top_picks | Recommended stocks list |
| sector_weight | Overweight / Neutral / Underweight by sector |
| market_outlook | Bullish / Neutral / Bearish outlook |
| file_url | PDF link or stored file path |
| summary | Auto-generated summary (LLM) |
| key_tickers | Most mentioned tickers |

#### 3.4.3. Report Collection Strategy

| Method | Implementation |
|---|---|
| **RSS feeds** | SSI, VCI have RSS on official websites |
| **Web scraping** | Custom scraper for HCM, TCBS, VCBS (no RSS) |
| **Manual upload** | Admin upload PDFs via dashboard |
| **Newsletter parsing** | Parse email newsletters (if available) |
| **API integrations** | If brokers provide API (rare) |

#### 3.4.4. Filtering & Sorting

- **By broker:** Checkbox multi-select (SSI, VCI, HCM, TCBS, VCBS)
- **By time:** Week / Month / Quarter / Year buttons
- **By report type:** Dropdown (Chart, Macro, Sector, Stock Pick)
- **By sector:** Dropdown (Bank, Real Estate, Tech, Energy, ...)
- **By rating:** Overweight / Neutral / Underweight

---

### 3.5. Tab 5: Screener & Alerts

#### 3.5.1. Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  [⚙️] Screener & Alerts          [Watchlist] [Alerts] [Config] │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  WATCHLIST                                                  │ │
│  │                                                             │ │
│  │  Ticker  │ Price  │ Δ%    │ Vol     │ Alert Status         │
│  │ HVN      │ 68.5k  │ ▲2.3%│ 12.1M   │ ● Target: 75k       │
│  │ CTG      │ 34.2k  │ ▲0.8%│ 25.3M   │ ● Buy zone: 32-35k  │
│  │ FPT      │ 112k   │ ▲1.1%│ 5.7M    │ ○ None                │
│  │ VNM      │ 78.3k  │ ▼1.5%│ 8.2M    │ ● Stop: 75k          │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  ACTIVE ALERTS                                              │ │
│  │                                                             │ │
│  │  🔔 HVN crossed above 68k  —  2h ago                       │ │
│  │  🔔 VNM dropped below 80k  —  5h ago                       │ │
│  │  🔔 CTG volume spike (3x avg) —  1h ago                    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  CREATE ALERT                                               │ │
│  │                                                             │ │
│  │  Ticker: [____]  Condition: [Price > / < / Volume >]       │ │
│  │  Value: [______]  Notify: [Telegram] [Email] [On-screen]  │ │
│  │  [Create Alert]                                              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow Architecture

### 4.1. Market Data Pipeline

```
┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│ Vietstock/   │    │ vnstock3 /    │    │ DNSE API     │
│ API / RSS    │───▶│ Web Scrapers  │───▶│ (optional)   │
│ (live ticks) │    │               │    │              │
└──────────────┘    └───────────────┘    └──────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│  Data Transformer (Python)                         │
│  - Normalize data format                           │
│  - Calculate derived fields (change%, volume avg)  │
│  - Assign sector classifications                   │
└────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│  SQLite Cache (jarvis.db extensions)               │
│  - market_quotes table                             │
│  - daily_ohlcv table                               │
│  - sector_performance table                        │
└────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│  Flask API Endpoints                               │
│  GET /api/market/quotes                            │
│  GET /api/market/ohlcv?period=week                 │
│  GET /api/market/sectors                           │
│  GET /api/market/top-movers                        │
└────────────────────────────────────────────────────┘
```

### 4.2. News Pipeline

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Reuters RSS  │ │ CNBC RSS     │ │ VnExpress RSS│
│ VnExpress    │ │ Reddit API   │ │ Vietstock    │
│ CafeF        │ │ Bloomberg    │ │ Yahoo Finance│
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌────────────────────────────────────────────────┐
│  News Ingestor (Python)                        │
│  1. Fetch new articles from all sources        │
│  2. Deduplicate (simhash + fuzzy match)        │
│  3. Classify: category, source, sentiment      │
│  4. Score relevance (LLM-assisted)             │
│  5. Extract entities (tickers, companies)      │
└────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────┐
│  SQLite Cache                                  │
│  - news_articles table                         │
│  - news_categories table                       │
│  - entity_mentions table (ticker↔article)      │
└────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────┐
│  Flask API Endpoints                           │
│  GET /api/news/articles                        │
│  GET /api/news/featured                        │
│  GET /api/news/by-ticker?ticker=HVH            │
│  GET /api/news/sentiment?period=week           │
└────────────────────────────────────────────────┘
```

### 4.3. Research Report Pipeline

```
┌─────────────────────────────────────────────────┐
│  Report Sources                                  │
│  • SSI: ssi.com.vn/research                      │
│  • VCI: vci.com.vn/research                      │
│  • HCM: hcmsec.com.vn/research                   │
│  • TCBS: tcbs.com.vn/research                    │
│  • VCBS: vcbsecurities.com/research              │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│  Report Crawler (Python)                               │
│  1. Scan broker websites for new PDF/HTML reports      │
│  2. Extract metadata: title, date, broker, type        │
│  3. Download & store PDF                               │
│  4. LLM summarize key points                           │
│  5. Extract target prices, top picks, sector views     │
│  6. Index in SQLite                                    │
└────────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│  SQLite Cache                                          │
│  - research_reports table                              │
│  - broker_overview table (current consensus)           │
│  - report_summaries table (LLM-generated)              │
└────────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────┐
│  Flask API Endpoints                                   │
│  GET /api/reports/list                                 │
│  GET /api/reports/by-broker?broker=SSI                 │
│  GET /api/reports/by-period?period=week                │
│  GET /api/reports/consensus                            │
│  GET /api/reports/<id>/summary                         │
│  GET /api/reports/<id>/download                        │
└────────────────────────────────────────────────────────┘
```

### 4.4. Market Intelligence Pipeline (NEW — v2.0)

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ RSS feeds      │ │ Web scrapers   │ │ News APIs     │
│ (Cafef,        │ │ (Vietstock,    │ │ (Reuters,     │
│  VnExpress,    │ │  BBC, etc.)    │ │  CNBC, etc.) │
│  Reuters)      │ │               │ │                │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌────────────────────────────────────────────────┐
│  STAGE 1: INGESTION (ingestion.py)              │
│     • Fetch articles from last 6 hours          │
│     • Deduplicate by URL/content hash           │
│     • Store raw articles temporarily            │
└──────────────────────┬─────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────┐
│  STAGE 2: PARSING (parsing.py)                  │
│     • Strip HTML tags                           │
│     • Remove boilerplate (ads, nav, footers)    │
│     • Clean text for LLM consumption            │
└──────────────────────┬─────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────┐
│  STAGE 3: ANALYSIS — Analyst Agent (analyst.py)│
│     • For each article:                          │
│       - Generate ≤3 sentence summary             │
│       - Classify sentiment (Bullish/Bearish/Neutral)│
│     • Output: structured JSON per article        │
└──────────────────────┬─────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────┐
│  STAGE 4: SYNTHESIS — Strategist Agent           │
│            (synthesizer.py)                        │
│     • Aggregate all article summaries             │
│     • Identify major themes & trends              │
│     • Generate cohesive Market Brief              │
└──────────────────────┬─────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────┐
│  STAGE 5: DELIVERY (delivery.py)                 │
│     • Save structured JSON to DB                  │
│     • Set status = "Notification Ready"           │
│     • Trigger notifications (Telegram, dashboard)│
└────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────┐
│  Flask API Endpoints                              │
│  POST /api/market-intelligence/run                │
│  GET    /api/market-intelligence/latest           │
│  GET    /api/market-intelligence/history          │
│  GET    /api/market-intelligence/sentiment-dist   │
└────────────────────────────────────────────────┘
```

---

## 5. Database Schema

### 5.1. market_quotes

```sql
CREATE TABLE market_quotes (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    exchange TEXT CHECK(exchange IN ('HOSE','HNX','UPCoM')),
    current_price REAL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    prev_close REAL,
    volume REAL,
    value REAL,
    change REAL,
    change_pct REAL,
    pe_ratio REAL,
    pb_ratio REAL,
    market_cap REAL,
    sector TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2. daily_ohlcv

```sql
CREATE TABLE daily_ohlcv (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    close_price REAL,
    volume REAL,
    value REAL,
    UNIQUE(ticker, date)
);
```

### 5.3. news_articles

```sql
CREATE TABLE news_articles (
    id INTEGER PRIMARY KEY,
    headline TEXT NOT NULL,
    snippet TEXT,
    content TEXT,
    source TEXT NOT NULL,
    url TEXT,
    category TEXT CHECK(category IN ('Global Macro','VN Market','Forex',
        'Crypto','Commodities','Earnings','Dividend','IPO','Strategy',
        'Regulation','M&A','Alert')),
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment TEXT CHECK(sentiment IN ('Bullish','Bearish','Neutral')),
    relevance_score INTEGER CHECK(relevance_score BETWEEN 1 AND 5),
    is_featured BOOLEAN DEFAULT 0,
    lang TEXT DEFAULT 'en'
);
```

### 5.4. entity_mentions

```sql
CREATE TABLE entity_mentions (
    id INTEGER PRIMARY KEY,
    article_id INTEGER,
    ticker TEXT,
    company_name TEXT,
    mention_type TEXT CHECK(mention_type IN ('direct','indirect','sector')),
    FOREIGN KEY(article_id) REFERENCES news_articles(id)
);
```

### 5.5. research_reports

```sql
CREATE TABLE research_reports (
    id INTEGER PRIMARY KEY,
    broker TEXT NOT NULL CHECK(broker IN ('SSI','VCI','HCM','TCBS','VCBS')),
    title TEXT NOT NULL,
    report_type TEXT CHECK(report_type IN ('Weekly Chart','Sector Mix',
        'Macro View','Stock Recommendation','Earnings Forecast')),
    published_at DATE,
    file_url TEXT,
    local_file_path TEXT,
    index_target REAL,
    market_outlook TEXT CHECK(market_outlook IN ('Bullish','Neutral','Bearish')),
    key_tickers TEXT,
    summary TEXT,
    sector_weights TEXT,
    downloaded BOOLEAN DEFAULT 0,
    summary_generated BOOLEAN DEFAULT 0
);
```

### 5.6. alerts

```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    ticker TEXT NOT NULL,
    condition TEXT CHECK(condition IN ('price_above','price_below',
        'volume_spike','price_change_pct')),
    threshold REAL,
    active BOOLEAN DEFAULT 1,
    notification_channels TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at TIMESTAMP
);
```

### 5.7. market_intelligence (NEW — v2.0)

```sql
CREATE TABLE IF NOT EXISTS market_intelligence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date        TEXT    NOT NULL,             -- ISO date of the 6-hour run
    run_period      TEXT    NOT NULL,             -- 'morning' | 'afternoon' | 'evening' | 'night'
    articles_json   TEXT    NOT NULL,             -- JSON array of article objects
    market_brief    TEXT    NOT NULL,             -- synthesized Market Brief text
    status          TEXT    DEFAULT 'Notification Ready',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_date, run_period)
);

-- Article JSON structure:
-- [
--   {
--     "title": "String",
--     "date": "String (ISO format)",
--     "url": "String",
--     "summary": "String (≤3 sentences)",
--     "sentiment": "String (Bullish|Bearish|Neutral)"
--   }
-- ]

CREATE INDEX IF NOT EXISTS idx_mi_run_date ON market_intelligence(run_date);
CREATE INDEX IF NOT EXISTS idx_mi_status ON market_intelligence(status);
```

---

## 6. API Design

### 6.1. Market API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/market/quotes` | Current quotes for all tracked stocks |
| GET | `/api/v1/market/quotes/{ticker}` | Single stock quote + details |
| GET | `/api/v1/market/ohlcv` | OHLCV data with period filter |
| GET | `/api/v1/market/sectors` | Sector performance rankings |
| GET | `/api/v1/market/top-movers` | Top gainers/losers |
| GET | `/api/v1/market/indexes` | VN-Index, HNX-Index, VN30 |
| GET | `/api/v1/market/heatmap` | Sector heatmap data |

### 6.2. News API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/news/articles` | List articles with filters |
| GET | `/api/v1/news/featured` | Top featured articles |
| GET | `/api/v1/news/by-ticker` | News for specific ticker |
| GET | `/api/v1/news/sentiment` | Sentiment summary by period |
| GET | `/api/v1/news/sources` | News source breakdown |
| GET | `/api/v1/news/categories` | Category distribution |

### 6.3. Reports API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/reports/list` | List all reports with filters |
| GET | `/api/v1/reports/by-broker` | Reports from specific broker |
| GET | `/api/v1/reports/by-period` | Reports by time period |
| GET | `/api/v1/reports/consensus` | Broker consensus summary |
| GET | `/api/v1/reports/{id}` | Report detail |
| GET | `/api/v1/reports/{id}/summary` | LLM-generated summary |
| GET | `/api/v1/reports/{id}/download` | Download PDF |

### 6.4. Screener/Alerts API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/watchlist` | User's watchlist |
| POST | `/api/v1/watchlist` | Add stock to watchlist |
| DELETE | `/api/v1/watchlist/{ticker}` | Remove from watchlist |
| GET | `/api/v1/alerts` | Active alerts |
| POST | `/api/v1/alerts` | Create new alert |
| PATCH | `/api/v1/alerts/{id}` | Update alert |
| DELETE | `/api/v1/alerts/{id}` | Delete alert |

### 6.5. Market Intelligence API (NEW — v2.0)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/market-intelligence/run` | Trigger a new 6-hour cycle pipeline run |
| GET | `/api/v1/market-intelligence/latest` | Get the most recent Market Brief + articles |
| GET | `/api/v1/market-intelligence/history` | List past intelligence runs with filters |
| GET | `/api/v1/market-intelligence/{id}` | Get specific run detail (articles + brief) |
| GET | `/api/v1/market-intelligence/sentiment-dist` | Sentiment distribution summary (Bullish/Bearish/Neutral counts) |
| DELETE | `/api/v1/market-intelligence/{id}` | Delete a specific run (cleanup) |

**POST /api/v1/market-intelligence/run Response:**
```json
{
     "status": "started",
     "run_id": 42,
     "message": "Pipeline started — will complete in ~2-5 minutes"
}
```

**GET /api/v1/market-intelligence/latest Response:**
```json
{
     "id": 42,
     "run_date": "2026-07-07",
     "run_period": "morning",
     "articles": [
         {
             "title": "...",
             "date": "2026-07-07T08:30:00",
             "url": "...",
             "summary": "...",
             "sentiment": "Bullish"
         }
     ],
     "market_brief": "...",
     "status": "Notification Ready",
     "created_at": "2026-07-07T09:15:00"
}
```

---

## 7. Frontend Architecture

### 7.1. Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Framework | Vanilla JS + HTML5 | No build step, loads fast |
| Styling | Custom CSS (dark theme) | Professional look, no heavy framework |
| Charts | Chart.js | Lightweight, supports line/bar/heatmap |
| Icons | SVG inline | No external dependency |
| State | JavaScript objects | Simple, no Redux needed |
| Routing | Hash-based (#market, #news) | SPA feel, no server config |

### 7.2. Design System

#### Colors (Dark Theme)

```
--bg-primary:    #1a1a2e
--bg-secondary:  #16213e
--bg-card:       #0f3460
--text-primary:  #e8e8e8
--text-secondary:#a0a0b0
--accent-green:  #00d4aa   (▲ positive)
--accent-red:    #ff4757   (▼ negative)
--accent-blue:   #4a90d9   (brand)
--accent-gold:   #ffd700   (highlights)
--border:        #2a2a4a
```

#### Typography

```
Font: Inter (Google Fonts) or system stack: -apple-system, BlinkMacSystemFont
Header: 18px, bold
Body: 14px, regular
Small: 12px, regular
Monospace (numbers): SF Mono, Consolas
```

#### Component Library

```
- Card: background #0f3460, border-radius 8px, padding 16px
- Table: header bg #16213e, row hover bg #1a1a3e
- Badge: small rounded pill (sector, rating, sentiment)
- Button: primary #4a90d9, secondary #2a2a4a border
- Input: dark bg, light text, blue focus ring
- Tabs: active = blue bottom border, inactive = gray text
```

---

## 8. Background Services

### 8.1. Market Data Refresher

```python
# Scheduled every 300 seconds (5 minutes)
def refresh_market_data():
    """Fetch and update market quotes from Vietstock/vnstock3"""
    quotes = fetch_quotes_from_vietstock()
    normalize_and_store(quotes)
    update_sector_performance()
    update_top_movers()
```

### 8.2. News Fetcher

```python
# Scheduled every 60 minutes
def fetch_news():
    """Pull new articles from all configured sources"""
    sources = get_news_sources()
    for source in sources:
        articles = fetch_from_source(source)
        for article in articles:
            if not exists_in_db(article.url):
                classify_article(article)
                score_relevance(article)
                extract_entities(article)
                store_in_db(article)
    update_featured_articles()
```

### 8.3. Report Crawler

```python
# Scheduled every 12 hours
def crawl_reports():
    """Scan broker websites for new research reports"""
    brokers = get_broker_sources()
    for broker in brokers:
        new_reports = scan_for_new(broker)
        for report in new_reports:
            download_pdf(report)
            extract_metadata(report)
            if not report.summary:
                generate_summary_with_llm(report)
            store_in_db(report)
```

### 8.4. Alert Monitor

```python
# Scheduled every 60 seconds
def check_alerts():
    """Check if any watchlist alerts have been triggered"""
    active_alerts = get_active_alerts()
    current_prices = get_current_prices()
    for alert in active_alerts:
        if check_condition(alert, current_prices[alert.ticker]):
            trigger_notification(alert)
            mark_alert_triggered(alert)
```

### 8.5. Market Intelligence Agent (NEW — v2.0)

```python
# Scheduled every 6 hours (06:00, 12:00, 18:00, 00:00 SGT)
def run_market_intelligence_pipeline():
    """Execute the full 5-stage Market Intelligence pipeline."""
    period = determine_period()  # 'morning' | 'afternoon' | 'evening' | 'night'
    
    # Stage 1: Ingestion
    raw_articles = ingest_from_sources(hours_back=6)
    
    # Stage 2: Parsing
    cleaned_articles = parse_and_clean(raw_articles)
    
    # Stage 3: Analysis (Analyst Agent)
    analyzed_articles = []
    for article in cleaned_articles:
        result = analyst_agent.analyze(article)  # summary + sentiment
        analyzed_articles.append(result)
    
    # Stage 4: Synthesis (Strategist Agent)
    market_brief = synthesizer_agent.synthesize(analyzed_articles)
    
    # Stage 5: Delivery
    run_id = delivery_service.save_to_db(
        run_date=datetime.now().isoformat(),
        run_period=period,
        articles_json=json.dumps(analyzed_articles),
        market_brief=market_brief,
        status="Notification Ready"
    )
    
    # Trigger notifications
    delivery_service.notify_telegram(run_id)
    delivery_service.update_dashboard(run_id)
    
    return {"run_id": run_id, "status": "complete"}
```

---

## 9. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

- [ ] Extend jarvis-hub Flask app with new routes
- [ ] Create database schema (market_quotes, daily_ohlcv)
- [ ] Build data fetcher for Vietstock/vnstock3 OHLCV
- [ ] Build basic Flask API endpoints (market/quotes, market/ohlcv)
- [ ] Create basic HTML template with tab navigation
- [ ] Implement Market Overview tab with charts (Chart.js)

### Phase 2: News Aggregator (Weeks 3-4)

- [ ] Build news ingestion pipeline (RSS + scrapers)
- [ ] Create news_articles and entity_mentions tables
- [ ] Build news API endpoints
- [ ] Implement News Aggregator tab with featured articles
- [ ] Implement category/source/sentiment filters
- [ ] LLM integration for relevance scoring

### Phase 3: Company News (Weeks 5-6)

- [ ] Build company-specific news scraper
- [ ] Create entity_mentions linking news to tickers
- [ ] Implement Company News tab with ticker search
- [ ] Build event classification (earnings, dividend, etc.)
- [ ] Impact scoring system
- [ ] Live ticker bar component

### Phase 4: Research Reports (Weeks 7-8)

- [ ] Build broker website crawlers (SSI, VCI, HCM, TCBS, VCBS)
- [ ] Create research_reports database schema
- [ ] Implement report download and storage
- [ ] LLM summary generation for each report
- [ ] Implement Research Reports tab with filters
- [ ] Broker consensus summary feature

### Phase 5: Screener & Alerts (Weeks 9-10)

- [ ] Create alerts and watchlist database tables
- [ ] Build alert creation UI
- [ ] Implement alert monitoring service
- [ ] Telegram notification integration
- [ ] Screener with custom filters
- [ ] User preference storage (SQLite-based, no auth)

### Phase 6: Polish & Deploy (Weeks 11-12)

- [ ] Performance optimization (caching, lazy loading)
- [ ] Dark theme refinement
- [ ] Responsive design tweaks
- [ ] Error handling and loading states
- [ ] Documentation
- [ ] Deploy to production (replace 1.0 on port 8100)

### Phase 7: Market Intelligence Agent (Weeks 13-14 — NEW v2.0)

- [ ] Create `core/market_intelligence/` module with 5 stage files
- [ ] Stage 1: Ingestion — RSS/web scraper for last 6 hours of news
- [ ] Stage 2: Parsing — HTML stripping, boilerplate removal, text cleaning
- [ ] Stage 3: Analysis — LLM Analyst Agent (summary + sentiment per article)
- [ ] Stage 4: Synthesis — LLM Strategist Agent (Market Brief from all summaries)
- [ ] Stage 5: Delivery — DB persistence + notification trigger (Telegram/dashboard)
- [ ] Create `market_intelligence` database table with schema
- [ ] Add API endpoints: POST /run, GET /latest, GET /history, GET /sentiment-dist
- [ ] Configure APScheduler cron job (every 6 hours: 06:00, 12:00, 18:00, 00:00 SGT)
- [ ] Add Market Intelligence tab to frontend dashboard
- [ ] Test full pipeline end-to-end with real news data

---

## 10. LLM Integration — mlx-lm (qwen3.6-35b-a3b-mlx-8bit)

### 10.1. Inference Architecture

```
Flask App
  │
  ├── News Scorer ────► mlx-lm relevance scoring
  │                     (seeded=True, cached model)
  │
  ├── Sentiment Analyzer ──► mlx-lm sentiment classification
  │
  ├── Entity Extractor ──► mlx-lm ticker/company extraction
  │
  ├── Report Summarizer ──► mlx-lm report key points
  │
  └── Consensus Builder ──► mlx-lm broker comparison
```

**No Ollama server needed** — mlx-lm runs directly in Python process,
calling model via API functions (no HTTP).

### 10.2. Model Loading

```python
# Singleton pattern — load model ONCE at app startup
_model = None
_tokenizer = None

def get_model():
    """Load model once, reuse across all requests"""
    global _model, _tokenizer
    if _model is None:
        from mlx_lm import load, generate, stream_generate
        _model, _tokenizer = load("unsloth/qwen3.6:35b-a3b-mxfp8")
    return _model, _tokenizer
```

**Model available:** `unsloth/qwen3.6:35b-a3b-mxfp8` (35B params, 8-bit quantized, ~21 GB)
- Architecture: Qwen3.5-35B-A3B (Mixture of Experts — 35B total, ~3B active per token)
- Format: MLX safetensors from HF Hub
- Quantization: 8-bit (better than 4-bit for accuracy, still fits 64 GB RAM)
- Already pulled and running stably in current chat session

### 10.3. Text Generation API

```python
from mlx_lm import load, generate, stream_generate

model, tokenizer = get_model()

# Simple generation (blocking)
result = generate(
    model, tokenizer,
    prompt=prompt_text,
    max_tokens=1024,
    temp=0.7,
    top_p=0.9,
    seed=42,  # Reproducible results
    verbose=False
)

# Streaming generation (non-blocking)
for token in stream_generate(model, tokenizer, prompt=prompt_text, max_tokens=512):
    print(token, end="", flush=True)
```

### 10.4. Chat Template (System Prompt)

```python
def chat_completion(messages, max_tokens=1024):
    """
    messages: [{"role": "system", "content": "..."},
               {"role": "user", "content": "..."}]
    """
    model, tokenizer = get_model()

    # Apply chat template
    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True
    )

    # Generate
    response = generate(
        model, tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        temp=0.5,  # Lower temp for consistent output
        top_p=0.9,
        seed=42
    )

    return response
```

### 10.5. Use Cases in Jarvis Hub 2.0

#### A. News Relevance Scoring

```python
def score_article_relevance(headline: str, snippet: str) -> int:
    """Score 1-5 based on financial relevance"""
    prompt = f"""You are a financial news analyst. Score the relevance
of this article for Vietnamese stock market professionals (1-5):

Headline: {headline}
Snippet: {snippet}

Score only the number (1-5), nothing else.
A 5 means critical market-moving news.
A 1 means noise/irrelevant.
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=10)
    return int(result.strip())
```

#### B. Sentiment Analysis

```python
def classify_sentiment(text: str) -> str:
    """Classify: Bullish, Bearish, or Neutral"""
    prompt = f"""Classify the market sentiment of this news:
{text}

Return ONLY one word: Bullish, Bearish, or Neutral.
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=20)
    return result.strip()
```

#### C. Entity Extraction (Tickers & Companies)

```python
def extract_entities(text: str) -> dict:
    """Extract tickers, companies, and their mentions"""
    prompt = f"""Extract all Vietnamese stock tickers and company names
from this text. Return JSON format:

{{
  "tickers": ["HVH", "GVR", "VNM"],
  "companies": ["Vinhomes", "Bien Hoa Steel", "Vinamilk"],
  "mentioned_context": {{
    "HVH": "real estate sector",
    "GVR": "aviation"
  }}
}}

Text: {text}
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=512)
    return json.loads(result)
```

#### D. Report Summarization

```python
def summarize_report(text: str, report_type: str) -> dict:
    """Summarize research report into key points"""
    prompt = f"""Summarize this {report_type} report. Extract:
1. Market outlook (Bullish/Neutral/Bearish)
2. Index target price
3. Top stock picks
4. Sector weightings

Return JSON:
{{
  "outlook": "Bullish",
  "index_target": 1310,
  "top_picks": ["HVH", "CTG", "FPT"],
  "sector_weights": {{
    "Bank": "Overweight",
    "Real Estate": "Overweight",
    "Tech": "Neutral"
  }}
}}

Report: {text[:4000]}
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=1024)
    return json.loads(result)
```

#### E. Broker Consensus Builder

```python
def build_consensus(reports: list) -> dict:
     """Compare all broker reports and build consensus view"""
    report_texts = "\n\n---\n\n".join([
        f"[{r['broker']}]\n{r['summary']}" for r in reports
     ])

    prompt = f"""Compare these broker reports for Vietnam stock market:

{report_texts}

Build a consensus summary:
1. Average index target
2. Most common top picks
3. Sector consensus (Overweight/Neutral/Underweight)
4. Key disagreements between brokers

Return JSON.
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=2048)
    return json.loads(result)
```

#### F. Market Intelligence — Analyst Agent (NEW — v2.0)

```python
def analyze_article(title: str, date: str, content: str, url: str) -> dict:
     """Generate summary + sentiment for a single article."""
    prompt = f"""You are a Lead Market Intelligence Agent. Analyze this financial news article.

Title: {title}
Date: {date}
URL: {url}
Content: {content[:3000]}

Return ONLY valid JSON (no markdown, no explanation):
{{
   "title": "{title}",
   "date": "{date}",
   "url": "{url}",
   "summary": "Concise summary in 1-3 sentences. Professional tone.",
   "sentiment": "Bullish" | "Bearish" | "Neutral"
}}

Rules:
- If impact is unclear, mark sentiment as "Neutral" with note "Insufficient information to determine sentiment."
- Maintain strict factual accuracy — do not hallucinate data.
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=512)
    return json.loads(result)
```

#### G. Market Intelligence — Strategist Agent (NEW — v2.0)

```python
def synthesize_market_brief(analyzed_articles: list) -> str:
     """Aggregate all article summaries into a cohesive Market Brief."""
    summaries = "\n\n---\n\n".join([
        f"[{a['sentiment']}] {a['title']}: {a['summary']}"
        for a in analyzed_articles
    ])

    prompt = f"""You are the Lead Market Intelligence Agent. Synthesize the following
analyzed article summaries into a cohesive Market Brief for the past 6 hours.

Identify:
1. Major themes and trends across all articles
2. Conflicting reports or divergent signals
3. Overall market status assessment
4. Strategic outlook for the upcoming period

Articles:
{summaries}

Return ONLY the Market Brief text (5-10 sentences, professional tone).
Do NOT include JSON — just the narrative brief.
"""
    result = chat_completion([{"role": "user", "content": prompt}], max_tokens=1024)
    return result.strip()
```

---

## 11. Deployment

### 11.1. Environment

| Component | Current | New (Hub 2.0) |
|---|---|---|
| Flask app | jarvis-hub/ (port 8100) | jarvis-hub/ (port 8100) — **replace 1.0** |
| Database | jarvis.db | jarvis.db (upgrade — keep DB, add new tables) |
| ollama/mlx-lm | qwen3.6-35b-a3b-mlx-8bit loaded | qwen3.6-35b-a3b-mlx-8bit (shared) |
| vnstock3 | installed | installed (shared) |
| Background jobs | APScheduler | APScheduler (extended) |

### 11.2. Directory Structure

```
jarvis-hub/
├── app.py                    # Main Flask application (Hub 2.0 — replaces 1.0)
├── config.py                 # Configuration
├── db/
│   └── jarvis.db            # SQLite database (upgrade — add new tables)
├── core/
│   ├── market/              # Market data handlers
│   │   ├── fetcher.py       # Vietstock/vnstock3 fetcher
│   │   ├── normalizer.py    # Data normalization
│   │   └── transformers.py  # Derived calculations
│   ├── news/                # News pipeline
│   │   ├── fetcher.py       # Multi-source news fetcher
│   │   ├── classifier.py    # Category/sentiment classification
│   │   ├── scorer.py        # Relevance scoring (LLM)
│   │   └── entities.py      # Entity extraction
│   ├── reports/             # Research report pipeline
│   │   ├── crawler.py       # Broker website crawler
│   │   ├── downloader.py    # PDF download
│   │   └── summarizer.py    # LLM summarization
│   └── alerts/              # Alert system
│       ├── monitor.py       # Alert checking
│        └── notifier.py            # Telegram/email notifications
│        └── market_intelligence/    # Market Intelligence Agent (NEW — v2.0)
│              ├── ingestion.py       # Stage 1: RSS/web scraper for last 6h
│              ├── parsing.py         # Stage 2: HTML stripping, text cleaning
│              ├── analyst.py         # Stage 3: LLM Analyst (summary + sentiment)
│              ├── synthesizer.py     # Stage 4: LLM Strategist (Market Brief)
│              └── delivery.py        # Stage 5: DB persistence + notification trigger
