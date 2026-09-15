# Jarvis Hub 3.0 — Feature Preservation Audit
**Date:** 2026-08-24  
**Status:** Gap Analysis & Remediation Plan

---

## 1. Executive Summary

This document audits every v2.0 feature against the v3.0 design to ensure **zero feature loss** during the architectural migration. The v3.0 design covers the **backend architecture** but under-represents **frontend features**, **navigation structure**, **CMS capabilities**, and **specialized data tables**.

**Verdict:** The v3.0 **system design** is complete for backend, but **frontend pages, templates, breadcrumbs, sidebar navigation, and several data tables** need explicit inclusion.

---

## 2. Feature Preservation Matrix

### 2.1 Frontend Pages (Templates)

Every v2.0 template page must exist in v3.0.

| # | v2.0 Template | v3.0 Route | v3.0 Status | Action Required |
|---|--------------|------------|-------------|-----------------|
| 1 | `index.html` | `/` | ✅ Mentioned | None |
| 2 | `hub2.html` | `/hub2` | ✅ Mentioned | None |
| 3 | `market.html` | `/hub2/market` | ⚠️ Mentioned as blueprint | Add template preservation note |
| 4 | `news.html` | `/hub2/news` | ⚠️ Mentioned as blueprint | Add template preservation note |
| 5 | `company.html` | `/hub2/company` | ⚠️ Mentioned as blueprint | Add template preservation note |
| 6 | `research.html` | `/hub2/research` | ⚠️ Mentioned as blueprint | Add template preservation note |
| 7 | `screener.html` | `/hub2/screener` | ⚠️ Mentioned as blueprint | Add template preservation note |
| 8 | `market-intel.html` | `/hub2/market-intel` | ✅ Mentioned | None |
| 9 | `portfolio.html` | `/hub2/portfolio` | ✅ Mentioned | None |
| 10 | `ai_intelligence.html` | `/ai-intelligence` | ✅ Mentioned | None |
| 11 | `cms.html` | `/admin`, `/cms` | ✅ Mentioned | None |

**Decision:** All 11 templates are **preserved as-is** in v3.0. They are static HTML/JS/CSS files served from `dashboard/templates/` and `dashboard/static/`. No changes needed to templates — the API layer change is transparent to the frontend.

---

### 2.2 Sidebar Navigation (hub2.html)

The hub2.html template contains a sidebar navigation with 8 items. This is **critical UX** and must be preserved.

| # | Tab | Icon | Route | v2.0 Description | v3.0 Status |
|---|-----|------|-------|-----------------|-------------|
| 1 | 🏠 Hub Home | 🏠 | `/hub2` | Landing page with overview cards | ✅ Preserve |
| 2 | 📊 Market | 📊 | `/hub2/market` | Market Overview tab — charts, indices, OHLCV | ✅ Preserve |
| 3 | 📰 News | 📰 | `/hub2/news` | News Aggregator tab — RSS feed, categories | ✅ Preserve |
| 4 | 🏢 Company | 🏢 | `/hub2/company` | Company News tab — ticker search, events | ✅ Preserve |
| 5 | 📑 Research | 📑 | `/hub2/research` | Research Reports tab — broker PDFs, summaries | ✅ Preserve |
| 6 | 🔍 Screener | 🔍 | `/hub2/screener` | Screener & Alerts tab — watchlist, alerts | ✅ Preserve |
| 7 | 🧠 Market Intel | 🧠 | `/hub2/market-intel` | Market Intelligence — AI brief, sentiment | ✅ Preserve |
| 8 | 💼 Portfolio | 💼 | `/hub2/portfolio` | Portfolio — holdings, transactions, PnL | ✅ Preserve |

**Decision:** Sidebar navigation is **100% preserved**. It lives in `hub2.html` template, served by Flask. No changes needed.

---

### 2.3 Breadcrumb Navigation

hub2.html has a breadcrumb component (lines 13-19, 121-128):

```html
<nav class="breadcrumb" aria-label="Breadcrumb">
    <ol class="breadcrumb-list">
        <li class="breadcrumb-item">
            <a href="/hub2" class="breadcrumb-link">🏠 Hub Home</a>
        </li>
    </ol>
</nav>
```

CSS styling (lines 13-19):
```css
.breadcrumb { margin-bottom: 24px; }
.breadcrumb-list { list-style: none; display: flex; flex-wrap: wrap; ... }
.breadcrumb-link { color: var(--text-secondary); text-decoration: none; ... }
.breadcrumb-separator { color: var(--text-muted); font-size: 12px; }
.breadcrumb-current { color: var(--text-primary); font-size: 14px; font-weight: 500; }
```

**Decision:** Breadcrumb component is **100% preserved** in `hub2.html` template. It is a pure frontend component (HTML + CSS) — no backend change needed. The v3.0 design **must document this as preserved**.

---

### 2.4 CMS (Content Management System)

The CMS has 2 components: the **panel UI** and the **API endpoints**.

#### CMS Panel UI

| Route | Template | Purpose | v3.0 Status |
|-------|----------|---------|-------------|
| `/admin` | `cms.html` | Admin panel → CMS | ✅ Mentioned |
| `/cms` | `cms.html` | CMS panel | ✅ Mentioned |

CMS features from `cms.html`:
- Sidebar with filters
- Article list view
- Article create/edit form
- Rich text editor with Markdown support
- Table support via custom renderer
- User management (placeholder)

#### CMS API Endpoints

| Method | Route | v2.0 Function | v3.0 Status |
|--------|-------|--------------|-------------|
| GET | `/api/cms/articles` | List all articles | ✅ Migrate to `api/cms.py` |
| GET | `/api/cms/articles/<id>` | Get article detail | ✅ Migrate to `api/cms.py` |
| PUT | `/api/cms/articles/<id>` | Update article | ✅ Migrate to `api/cms.py` |
| POST | `/api/cms/articles` | Create article | ✅ Migrate to `api/cms.py` |
| DELETE | `/api/cms/articles/<id>` | Delete article | ✅ Migrate to `api/cms.py` |

CMS `cms_articles` table (from `core/db.py`):
```sql
CREATE TABLE IF NOT EXISTS cms_articles (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    category TEXT,
    tags TEXT,
    status TEXT DEFAULT 'draft',  -- draft | published | archived
    author TEXT,
    published_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    is_featured INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0
);
```

**Decision:** CMS is **100% preserved**. All 5 CRUD endpoints migrate to `api/cms.py`. The `cms_articles` table is already in the v3.0 schema.

---

### 2.5 Market Overview Tab (tab-1)

This is the **primary dashboard** with charts, indices, and OHLCV data.

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| VN-Index, HNX-Index, VN30 | Data feed (300s) | ✅ Covered in `MarketGateway` | Document explicit preservation |
| OHLCV data with period filter | `GET /api/v1/market/ohlcv` | ⚠️ Covered by `/api/v1/overview/chart` | Document explicit preservation |
| Top Gainers / Losers | Self-calculated from OHLCV | ⚠️ Covered by `/api/v1/overview/motions` | Document explicit preservation |
| Sector performance | `sector_performance` table | ❌ **NOT in v3.0 schema** | **ADD TABLE** |
| Stock OHLCV prices | Vietstock/vnstock3 (300s) | ✅ Covered by `MarketGateway` | Document explicit preservation |

**Missing from v3.0 schema:**
```sql
-- ADD to v3.0 schema
CREATE TABLE IF NOT EXISTS sector_performance (
    id INTEGER PRIMARY KEY,
    sector TEXT NOT NULL,
    change_pct REAL,
    volume REAL,
    market_cap REAL,
    top_gainer TEXT,
    top_loser TEXT,
    recorded_at TEXT
);
```

**Decision:** Sector performance table **must be added** to v3.0 schema. All other Market Overview features are covered.

---

### 2.6 News Aggregator Tab (tab-2)

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| RSS feed fetching | Multiple sources (Cafef, VnExpress, Reuters, etc.) | ✅ Covered by `NewsGateway` | None |
| Heuristic sentiment | Keyword-based scoring | ✅ Covered by `FallbackEngine` | None |
| Article categorization | News categories (stock, forex, crypto) | ✅ Covered by `NewsGateway` | None |
| AI-powered news scoring | LLM relevance scoring | ✅ Covered by async queue | None |
| News articles table | `news_articles` | ⚠️ Covered by `cms_articles` + knowledge | **Clarify distinction** |
| News trending | `/api/v1/news/trending` | ✅ Covered | None |

**Note:** v2.0 has a `news_articles` table but v3.0 uses `cms_articles` instead. These serve different purposes:
- `cms_articles` = Admin-created, editorial content
- `news_articles` = Auto-fetched RSS feed articles

**Decision:** The RSS feed articles are stored in `activity_log` (current implementation) and `cms_articles` (CMS admin). The distinction should be documented in v3.0.

---

### 2.7 Company News Tab (tab-3)

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Ticker search | Search articles by symbol | ✅ Covered by `/api/v1/companies/<symbol>/news` | None |
| Events feed | High-impact company news | ✅ Covered by news pipeline | None |
| Entity mentions | Link tickers to articles | ⚠️ `entity_mentions` table **not in v3.0 schema** | **ADD TABLE** |
| News event types | Dividend, board meeting, risk alert | ✅ Covered by `news_categories` (implicit) | Document explicit preservation |
| Company news sources | Cafef, Vietstock, etc. | ✅ Covered by `NewsGateway` | None |

**Missing from v3.0 schema:**
```sql
-- ADD to v3.0 schema
CREATE TABLE IF NOT EXISTS entity_mentions (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,  -- ticker | company | index
    entity_name TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    context TEXT,
    created_at TEXT,
    FOREIGN KEY(article_id) REFERENCES cms_articles(id)
);
```

**Decision:** Entity mentions table **must be added** to v3.0 schema for the Company News tab to function.

---

### 2.8 Research Reports Tab (tab-4)

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Broker PDF scanning | SSI, VCI, HCM, TCBS, VCBS | ⚠️ Covered by `research_items` + crawler | Document crawler migration |
| PDF download | `/api/v1/reports/{id}/download` | ❌ **NOT in v3.0 design** | **ADD ENDPOINT** |
| Report summaries | LLM-generated summaries | ⚠️ Covered by async queue | Document |
| `report_summaries` table | LLM-generated content | ❌ **NOT in v3.0 schema** | **ADD TABLE** |
| `broker_overview` table | Current consensus | ❌ **NOT in v3.0 schema** | **ADD TABLE** |
| `research_reports` table | Research report metadata | ⚠️ Covered by `research_items` | Clarify mapping |

**Missing from v3.0 schema:**
```sql
-- ADD to v3.0 schema
CREATE TABLE IF NOT EXISTS report_summaries (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL,
    summary_text TEXT,
    key_points TEXT,
    generated_by TEXT,
    generated_at TEXT,
    FOREIGN KEY(report_id) REFERENCES research_items(id)
);

CREATE TABLE IF NOT EXISTS broker_overview (
    id INTEGER PRIMARY KEY,
    broker TEXT NOT NULL,
    index_target REAL,
    top_picks TEXT,
    market_outlook TEXT,
    published_at TEXT,
    UNIQUE(broker, published_at)
);
```

**Missing from v3.0 API:**
```
GET /api/v1/reports/{id}/download  -- Download PDF
```

**Decision:** Report summaries, broker overview tables, and PDF download endpoint **must be added** to v3.0.

---

### 2.9 Screener & Alerts Tab (tab-5)

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Watchlist | CRUD (add/remove) | ✅ Covered by `watchlist` table | None |
| Alerts | CRUD (create/update/delete) | ✅ Covered by `trading_alerts` | Document migration |
| Signal system | Get, latest, for symbol, add, mark-delivered | ⚠️ Not explicitly listed in v3.0 blueprint | **ADD TO BLUEPRINT** |
| Auto-scan | Scan watchlist for signals | ⚠️ Not explicitly listed | **ADD TO BLUEPRINT** |
| Alert feed | Real-time alert notifications | ⚠️ Covered by `trading_alerts` | Document |
| Config | Screener filter settings | ⚠️ Implicit in config | Document |

**Missing from v3.0 API blueprint:**
```
GET  /api/v1/signals              -- Get all signals
GET  /api/v1/signals/latest       -- Latest signals
GET  /api/v1/signals/symbol/<sym> -- Signal for symbol
POST /api/v1/signals              -- Add signal
POST /api/v1/signals/mark-delivered -- Mark delivered

GET  /api/v1/alert-feed           -- Get alert feed
GET  /api/v1/alert-feed/auto-scan -- Auto-scan
POST /api/v1/alert-feed/clear     -- Clear alerts
```

**Decision:** Signal system and alert-feed endpoints **must be added** to v3.0 `api/stremer.py` blueprint.

---

### 2.10 Market Intelligence Tab

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Pipeline run | POST /api/market-intelligence/run | ✅ Covered | None |
| Latest brief | GET /api/market-intelligence/latest | ✅ Covered | None |
| History | GET /api/market-intelligence/history | ✅ Covered | None |
| Sentiment dist | GET /api/market-intelligence/sentiment-dist | ✅ Covered | None |
| Delete run | DELETE /api/market-intelligence/<id> | ✅ Covered | None |
| 6-stage pipeline | Ingest → Parse → Analyze → Synthesize → Deliver | ✅ Covered | None |
| 5 pipeline modules | ingestion, parsing, analyst, synthesizer, delivery | ✅ Covered | None |
| Telegram delivery | Notification trigger | ❌ **NOT in v3.0 design** | **ADD MODULE** |
| Dashboard update | Update dashboard with latest brief | ❌ **NOT in v3.0 design** | **ADD MODULE** |

**Missing from v3.0:**
- Telegram delivery service (notification trigger)
- Dashboard update service

**Decision:** Telegram delivery and dashboard update **must be added** as modules in `core/market_intelligence/delivery.py`.

---

### 2.11 Portfolio Tab

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Holdings | Portfolio holdings list | ✅ Covered by `portfolio_transactions` | None |
| Transactions | Add/remove transactions | ✅ Covered by `portfolio_transactions` | None |
| PnL summary | Profit/loss calculation | ✅ Covered by `/api/v1/portfolio/pnl-summary` | None |

**Decision:** Portfolio is **100% covered**.

---

### 2.12 AI Intelligence Feed

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| AI trend analysis | LLM-powered news analysis | ✅ Covered by async queue | None |
| Project proposal | LLM project suggestion | ✅ Covered by async queue | None |
| Feed endpoint | GET /api/v2/ai-intelligence/daily-list | ✅ Covered | None |
| Feed template | ai_intelligence.html | ✅ Mentioned | None |

**Decision:** AI Intelligence feed is **100% covered**.

---

### 2.13 Admin Panel

| Feature | v2.0 Definition | v3.0 Status | Action Required |
|---------|----------------|-------------|-----------------|
| Admin panel UI | `/admin` → `cms.html` | ✅ Covered | None |
| CMS management | Create/edit/delete articles | ✅ Covered | None |
| Protection | Login required | ✅ Covered in Phase 4 | None |

**Decision:** Admin panel is **100% covered**.

---

## 3. Database Table Gap Analysis

### 3.1 Tables Present in v2.0 but Missing from v3.0

| # | Table | Purpose | Priority | Action |
|---|-------|---------|----------|--------|
| 1 | `sector_performance` | Sector performance data | 🔴 High | Add to schema |
| 2 | `entity_mentions` | Link tickers to articles | 🔴 High | Add to schema |
| 3 | `report_summaries` | LLM-generated report summaries | 🔴 High | Add to schema |
| 4 | `broker_overview` | Broker consensus data | 🟡 Medium | Add to schema |

### 3.2 Tables Present in v2.0 and Mapped in v3.0

| v2.0 Table | v3.0 Table | Notes |
|------------|------------|-------|
| `market_quotes` | `market_cache` | Merged into general cache |
| `daily_ohlcv` | `market_cache` + data gateway | OHLCV stored in market_cache with period filter |
| `news_articles` | `cms_articles` + activity_log | Distinguished: CMS vs RSS articles |
| `research_reports` | `research_items` | Renamed |
| `alerts` | `trading_alerts` | Renamed |
| `market_intelligence` | `market_intelligence` | Same name |
| `knowledge` | `knowledge` | Same name |
| `activity_log` | `activity_log` | Same name |
| `daily_snapshots` | `daily_snapshots` | Same name |
| `watchlist` | `watchlist` | Same name |
| `backlog_tasks` | `backlog_tasks` | Same name |
| `portfolio_transactions` | `portfolio_transactions` | Same name |
| `cms_articles` | `cms_articles` | Same name |

### 3.3 Tables Added in v3.0 (New)

| # | Table | Purpose |
|---|-------|---------|
| 1 | `llm_tasks` | Async LLM task queue |
| 2 | `llm_cache` | LLM result cache with TTL |
| 3 | `circuit_breaker` | Circuit breaker state |

---

## 4. API Endpoint Gap Analysis

### 4.1 v2.0 Endpoints Not Explicitly Listed in v3.0

| Method | v2.0 Route | v3.0 Blueprint | Status |
|--------|-----------|----------------|--------|
| GET | `/api/v1/market/ohlcv` | `api/market.py` | ✅ Covered (general API) |
| GET | `/api/v1/market/indexes` | `api/market.py` | ✅ Covered |
| GET | `/api/v1/market/sector` | `api/market.py` | ⚠️ Need sector_performance table |
| GET | `/api/v1/reports/{id}/download` | `api/research.py` | ❌ **MISSING** |
| GET | `/api/v1/signals` | `api/screener.py` | ⚠️ Need explicit listing |
| GET | `/api/v1/signals/latest` | `api/screener.py` | ⚠️ Need explicit listing |
| GET | `/api/v1/signals/symbol/<sym>` | `api/screener.py` | ⚠️ Need explicit listing |
| POST | `/api/v1/signals` | `api/screener.py` | ⚠️ Need explicit listing |
| POST | `/api/v1/signals/mark-delivered` | `api/screener.py` | ⚠️ Need explicit listing |
| GET | `/api/v1/alert-feed` | `api/screener.py` | ⚠️ Need explicit listing |
| GET | `/api/v1/alert-feed/auto-scan` | `api/screener.py` | ⚠️ Need explicit listing |
| POST | `/api/v1/alert-feed/clear` | `api/screener.py` | ⚠️ Need explicit listing |

### 4.2 Services Not Listed in v3.0

| Service | Purpose | Priority | Action |
|---------|---------|----------|--------|
| Telegram delivery | Notification trigger | 🔴 High | Add to `delivery.py` |
| Dashboard update | Update dashboard with latest brief | 🔴 High | Add to `delivery.py` |
| Alert monitor | Watchlist alert checking (60s) | 🟡 Medium | Add to `workers/health_monitor.py` |
| Report crawler | Scan broker websites for PDFs | 🟡 Medium | Add to `services/research_service.py` |

---

## 5. Frontend Structure Gap Analysis

### 5.1 What's Preserved (No Action Needed)

| Component | Location | Status |
|-----------|----------|--------|
| Sidebar navigation | `hub2.html` lines 75-112 | ✅ 100% preserved |
| Breadcrumb navigation | `hub2.html` lines 13-19, 121-128 | ✅ 100% preserved |
| Chart.js charts | `hub2.html`, `market.html` | ✅ 100% preserved |
| Dark theme CSS | `dashboard/static/css/` | ✅ 100% preserved |
| All 11 templates | `dashboard/templates/` | ✅ 100% preserved |
| Static assets | `dashboard/static/js/`, `dashboard/static/charts/` | ✅ 100% preserved |

### 5.2 What Needs Documentation in v3.0

The v3.0 design **must** explicitly state:

> **Frontend pages, templates, sidebar navigation, and breadcrumb components are 100% preserved from v2.0.** They are static HTML/CSS/JS files served from `dashboard/templates/` and `dashboard/static/`. The v3.0 migration changes only the **backend API layer** — frontend code is untouched.

---

## 6. Remediation Plan

### 6.1 Database Schema Additions

**File:** `core/db.py` — `init_db()` method

Add these 4 tables:

```sql
CREATE TABLE IF NOT EXISTS sector_performance (
    id INTEGER PRIMARY KEY,
    sector TEXT NOT NULL,
    change_pct REAL,
    volume REAL,
    market_cap REAL,
    top_gainer TEXT,
    top_loser TEXT,
    recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id INTEGER PRIMARY KEY,
    article_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    context TEXT,
    created_at TEXT,
    FOREIGN KEY(article_id) REFERENCES cms_articles(id)
);

CREATE TABLE IF NOT EXISTS report_summaries (
    id INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL,
    summary_text TEXT,
    key_points TEXT,
    generated_by TEXT,
    generated_at TEXT,
    FOREIGN KEY(report_id) REFERENCES research_items(id)
);

CREATE TABLE IF NOT EXISTS broker_overview (
    id INTEGER PRIMARY KEY,
    broker TEXT NOT NULL,
    index_target REAL,
    top_picks TEXT,
    market_outlook TEXT,
    published_at TEXT,
    UNIQUE(broker, published_at)
);
```

### 6.2 API Blueprint Additions

**File:** `api/screener.py` — Add these routes:

```python
# Signal system
@blueprint.get("/api/v1/signals")
@blueprint.get("/api/v1/signals/latest")
@blueprint.get("/api/v1/signals/symbol/<symbol>")
@blueprint.post("/api/v1/signals")
@blueprint.post("/api/v1/signals/mark-delivered")

# Alert feed
@blueprint.get("/api/v1/alert-feed")
@blueprint.get("/api/v1/alert-feed/auto-scan")
@blueprint.post("/api/v1/alert-feed/clear")
```

**File:** `api/research.py` — Add these routes:

```python
@blueprint.get("/api/v1/reports/<int:report_id>/download")
def download_report(report_id):
    """Download research report PDF."""
```

### 6.3 Service Additions

**File:** `core/market_intelligence/delivery.py` — Add:

```python
class TelegramDeliveryService:
    """Send market intelligence brief via Telegram."""
    
    def send_brief(self, brief_text, run_id):
        """Send brief to Telegram target_chat_id."""
        ...

class DashboardUpdateService:
    """Update dashboard with latest intelligence brief."""
    
    def update_dashboard(self, run_id):
        """Update dashboard with latest brief from DB."""
        ...
```

**File:** `services/research_service.py` — Add:

```python
class ResearchCrawlerService:
    """Scan broker websites for new research reports."""
    
    def scan_brokers(self):
        """Scan SSI, VCI, HCM, TCBS, VCBS for PDFs."""
        ...
    
    def download_pdf(self, report_id):
        """Download and store report PDF."""
        ...
```

**File:** `workers/health_monitor.py` — Add:

```python
class AlertMonitor:
    """Check watchlist alerts every 60 seconds."""
    
    def check_alerts(self):
        """Check if any watchlist alerts have been triggered."""
        ...
```

### 6.4 v3.0 Design Document Updates

The following sections of `JH3.0_DESIGN.md` need to be updated:

| Section | Current | Required Update |
|---------|---------|----------------|
| §4.3 API Route Mapping | Missing signals/alert-feed | Add signal routes + alert-feed routes |
| §5.1 Database Schema | Missing 4 tables | Add `sector_performance`, `entity_mentions`, `report_summaries`, `broker_overview` |
| §4.1 Architecture Diagram | Missing delivery services | Add Telegram/Dashboard delivery to diagram |
| §4.2 Layer Responsibilities | Missing research/alert services | Add `ResearchService`, `AlertMonitor` |
| §10. Success Metrics | Missing frontend metrics | Add template count, route count |

---

## 7. Final Feature Coverage Score

| Category | v2.0 Features | v3.0 Covered | Gap |
|----------|--------------|--------------|-----|
| **Frontend Templates** | 11 | 11 | 0% ✅ |
| **Sidebar Navigation** | 8 tabs | 8 tabs | 0% ✅ |
| **Breadcrumb** | 1 component | 1 component | 0% ✅ |
| **CMS** | 5 CRUD routes | 5 routes | 0% ✅ |
| **Market Overview** | 5 features | 4 of 5 | 1 table missing |
| **News Aggregator** | 6 features | 6 of 6 | 0% ✅ |
| **Company News** | 5 features | 4 of 5 | 1 table missing |
| **Research Reports** | 6 features | 4 of 6 | 2 tables + 1 route missing |
| **Screener & Alerts** | 6 features | 4 of 6 | 2 routes + 1 table missing |
| **Market Intelligence** | 8 features | 6 of 8 | 2 services missing |
| **Portfolio** | 3 features | 3 of 3 | 0% ✅ |
| **AI Intelligence** | 4 features | 4 of 4 | 0% ✅ |
| **Background Services** | 5 | 3 of 5 | 2 services missing |
| **Security** | 0 | All planned | Phase 4 ✅ |

**Overall Coverage: 57/65 features = 88%**

**Remediation needed:**
- 4 database tables to add
- 10 API routes to explicitly list
- 4 services to add
- v3.0 design document to update with frontend preservation note

---

## 8. Updated v3.0 Blueprint Map (Complete)

```
api/
├── __init__.py
├── market.py             # /api/v1/market/*
│   ├── GET  /ohlcv
│   ├── GET  /indexes
│   ├── GET  /sector
│   ├── GET  /quotes
│   └── GET  /chart
├── news.py               # /api/v1/news/*
│   ├── GET  /articles
│   ├── GET  /trending
│   ├── POST /score
│   └── GET  /categories
├── stocks.py             # /api/v1/stocks/*
│   ├── GET  /analyze
│   ├── GET  /quotes
│   ├── GET  /symbols/search
│   └── GET  /signals
├── screener.py           # /api/v1/screener/*
│   ├── GET  /signals
│   ├── GET  /signals/latest
│   ├── GET  /signals/symbol/<sym>
│   ├── POST /signals
│   ├── POST /signals/mark-delivered
│   ├── GET  /alert-feed
│   ├── GET  /alert-feed/auto-scan
│   ├── POST /alert-feed/clear
│   ├── GET  /watchlist
│   ├── POST /watchlist
│   └── DELETE /watchlist/<sym>
├── research.py           # /api/v1/research/*
│   ├── GET  /reports
│   ├── GET  /stats
│   ├── POST /crawl
│   └── GET  /reports/<id>/download
├── portfolio.py          # /api/v1/portfolio/*
│   ├── GET  /holdings
│   ├── GET  /transactions
│   ├── GET  /pnl-summary
│   ├── POST /add-txn
│   └── DELETE /txn/<id>
├── cms.py                # /api/v1/cms/*
│   ├── GET  /articles
│   ├── GET  /articles/<id>
│   ├── PUT  /articles/<id>
│   ├── POST /articles
│   └── DELETE /articles/<id>
├── intelligence.py       # /api/v1/intelligence/*
│   ├── POST /pipeline/run
│   ├── GET  /pipeline/latest
│   ├── GET  /pipeline/history
│   ├── GET  /pipeline/<id>
│   ├── GET  /pipeline/sentiment-dist
│   ├── DELETE /pipeline/<id>
│   ├── GET  /ai-daily
│   └── GET  /ai-daily/<run_id>
├── llm.py                # /api/v1/llm/*
│   ├── POST /tasks
│   ├── GET  /tasks/<id>/status
│   ├── GET  /tasks/<id>/result
│   └── GET  /health
├── auth.py               # /api/v1/auth/*
│   ├── POST /login
│   ├── POST /logout
│   └── GET  /me
└── main.py               # /api/v1/main/*
    ├── GET  /health
    ├── GET  /overview
    ├── GET  /overview/indices
    ├── GET  /overview/crypto
    ├── GET  /overview/gold
    ├── GET  /overview/motions
    └── GET  /logs
```
