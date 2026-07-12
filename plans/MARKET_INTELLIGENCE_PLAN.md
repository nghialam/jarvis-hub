# Market Intelligence Agent — Implementation Plan

> **Version:** 1.0  
> **Date:** 2026-07-07  
> **Status:** Planning  
> **Target:** Jarvis Hub v2.0

---

## Overview

This plan details the implementation of the **Market Intelligence Agent** — a 5-stage autonomous pipeline that operates on a 6-hour cycle to aggregate, analyze, and synthesize financial news into actionable market insights.

### Pipeline Stages

```
Stage 1: Ingestion   → RSS/web scrapers fetch last 6h of articles
Stage 2: Parsing     → HTML stripping, boilerplate removal, text cleaning
Stage 3: Analysis    → LLM generates summary + sentiment per article (Analyst Agent)
Stage 4: Synthesis   → LLM creates Market Brief from all summaries (Strategist Agent)
Stage 5: Delivery    → Persist to DB, trigger notifications (Telegram/dashboard)
```

---

## Phase 1: Database Schema (Day 1)

### Task 1.1: Add `market_intelligence` table to `db.py`

**File:** `core/db.py`  
**Location:** Inside `init_db()` method, after the `market_evaluation` table

**SQL Schema:**
```sql
CREATE TABLE IF NOT EXISTS market_intelligence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date        TEXT    NOT NULL,              -- ISO date of the 6-hour run
    run_period      TEXT    NOT NULL,              -- 'morning' | 'afternoon' | 'evening' | 'night'
    articles_json   TEXT    NOT NULL,              -- JSON array of article objects
    market_brief    TEXT    NOT NULL,              -- synthesized Market Brief text
    status          TEXT    DEFAULT 'Notification Ready',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_date, run_period)
);

CREATE INDEX IF NOT EXISTS idx_mi_run_date ON market_intelligence(run_date);
CREATE INDEX IF NOT EXISTS idx_mi_status ON market_intelligence(status);
```

**Implementation Notes:**
- Follow existing pattern: use `c.executescript()` inside `init_db()`
- Use `IF NOT EXISTS` for idempotent schema creation
- Add UNIQUE constraint on `(run_date, run_period)` to prevent duplicate runs per cycle

### Task 1.2: Add helper methods to `Database` class

**File:** `core/db.py`  
**Location:** After existing helper methods (after `search_knowledge`)

**Methods to add:**
```python
def save_market_intelligence(self, run_date, run_period, articles_json, market_brief, status="Notification Ready"):
    """Save a complete market intelligence run to DB."""

def get_latest_market_intelligence(self):
    """Get the most recent market intelligence run."""

def get_market_intelligence_history(self, limit=10, period=None):
    """List past runs with optional period filter."""

def get_market_intelligence_by_id(self, run_id):
    """Get specific run by ID."""

def delete_market_intelligence(self, run_id):
    """Delete a specific run."""

def get_sentiment_distribution(self):
    """Get Bullish/Bearish/Neutral counts across all articles."""
```

---

## Phase 2: Core Pipeline Modules (Days 1-3)

### Task 2.1: Create module structure

**Directory:** `core/market_intelligence/`  
**Files to create:**
```
core/market_intelligence/
├── __init__.py          # Package init, exports main pipeline function
├── ingestion.py         # Stage 1: RSS/web scraper for last 6h
├── parsing.py           # Stage 2: HTML stripping, text cleaning
├── analyst.py           # Stage 3: LLM Analyst (summary + sentiment)
├── synthesizer.py       # Stage 4: LLM Strategist (Market Brief)
└── delivery.py          # Stage 5: DB persistence + notification trigger
```

### Task 2.2: `ingestion.py` — Stage 1: Ingestion

**File:** `core/market_intelligence/ingestion.py`

**Purpose:** Fetch raw articles from RSS feeds and web scrapers for the last 6 hours.

**Key Components:**

1. **RSS Source Configuration** (reuse existing patterns):
   ```python
   MARKET_INTELLIGENCE_SOURCES = [
       {"name": "Cafef Thị trường", "url": "https://cafef.vn/thi-truong.rss", "lang": "vi"},
       {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "lang": "vi"},
       {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "lang": "vi"},
       {"name": "VnExpress Kinh tế", "url": "https://vnexpress.net/rss/kinh-te.rss", "lang": "vi"},
       {"name": "Vietstock", "url": "https://vietstock.com.vn/rss.htm", "lang": "vi"},
       {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "lang": "en"},
       {"name": "BBC Business", "url": "https://feeds.bbci.co.uk/news/business/rss.xml", "lang": "en"},
   ]
   ```

2. **`fetch_articles(hours_back=6)` function:**
   - Use `feedparser` (already a dependency via `news_engine.py`)
   - Fetch from all sources in parallel using `ThreadPoolExecutor`
   - Filter articles by publication date (last 6 hours)
   - Deduplicate by URL and content hash (simhash or simple MD5 of title+snippet)
   - Return list of raw article dicts: `{"title", "date", "content", "url", "source", "lang"}`

3. **`deduplicate(articles)` function:**
   - First pass: exact URL match
   - Second pass: content similarity (Jaccard similarity on title words > 0.8)
   - Keep the article with the most complete content

**Dependencies:** `feedparser`, `requests`, `concurrent.futures`, `datetime`

### Task 2.3: `parsing.py` — Stage 2: Parsing

**File:** `core/market_intelligence/parsing.py`

**Purpose:** Clean raw article content for LLM consumption.

**Key Components:**

1. **`clean_article(article)` function:**
   - Strip HTML tags (use `BeautifulSoup` or regex)
   - Remove boilerplate: navigation links, ads, footers, "Read more" buttons
   - Normalize whitespace and encoding
   - Truncate content to max 3000 characters (LLM context limit)
   - Return cleaned article dict

2. **`extract_text_from_html(html)` function:**
   - Use `BeautifulSoup` with `html.parser`
   - Remove `<script>`, `<style>`, `<nav>`, `<footer>`, `.ad-`, `.sidebar` elements
   - Extract main content area (heuristic: longest text block or `<article>` tag)

3. **`normalize_text(text)` function:**
   - Handle Vietnamese encoding issues
   - Normalize whitespace (multiple spaces → single space)
   - Ensure UTF-8 encoding

**Dependencies:** `beautifulsoup4`, `re`

### Task 2.4: `analyst.py` — Stage 3: Analysis (Analyst Agent)

**File:** `core/market_intelligence/analyst.py`

**Purpose:** LLM-powered analysis of each article: generate summary + classify sentiment.

**Key Components:**

1. **`analyze_article(article)` function:**
   - Takes cleaned article dict
   - Constructs prompt for Analyst Agent (see prompt template below)
    - Calls `ollama_client.ollama_parse_json()` for structured JSON output
   - Returns: `{"title", "date", "url", "summary", "sentiment"}`

2. **`analyze_articles(articles)` function:**
   - Parallel processing using `ThreadPoolExecutor` (max 4 concurrent)
   - Error handling: if LLM fails for one article, mark as `{summary: "LLM analysis unavailable", sentiment: "Neutral"}`
   - Returns list of analyzed articles

3. **Analyst Agent Prompt Template:**
   ```
   You are a Lead Market Intelligence Agent analyzing financial news.

   Title: {title}
   Date: {date}
   URL: {url}
   Content: {content[:3000]}

   Return ONLY valid JSON (no markdown, no explanation):
   {
       "title": "{title}",
       "date": "{date}",
       "url": "{url}",
       "summary": "Concise summary in 1-3 sentences. Professional tone.",
       "sentiment": "Bullish" | "Bearish" | "Neutral"
   }

   Rules:
   - If impact is unclear, mark sentiment as "Neutral" with note "Insufficient information to determine sentiment."
   - Maintain strict factual accuracy — do not hallucinate data.
   - Summary must be ≤3 sentences.
   ```

**Dependencies:** `core.ollama_client`, `json`, `concurrent.futures`

### Task 2.5: `synthesizer.py` — Stage 4: Synthesis (Strategist Agent)

**File:** `core/market_intelligence/synthesizer.py`

**Purpose:** Aggregate all article summaries into a cohesive Market Brief.

**Key Components:**

1. **`synthesize_market_brief(analyzed_articles)` function:**
   - Takes list of analyzed articles from Stage 3
   - Constructs prompt for Strategist Agent (see prompt template below)
   - Calls `ollama_client.ollama_call()` for narrative output
   - Returns: Market Brief string (5-10 sentences)

2. **Strategist Agent Prompt Template:**
   ```
   You are the Lead Market Intelligence Agent. Synthesize the following
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
   ```

**Dependencies:** `core.ollama_client`

### Task 2.6: `delivery.py` — Stage 5: Delivery

**File:** `core/market_intelligence/delivery.py`

**Purpose:** Persist results to DB and trigger notifications.

**Key Components:**

1. **`save_to_db(run_date, run_period, articles_json, market_brief)` function:**
   - Uses `core.db.Database.save_market_intelligence()`
   - Returns run_id on success

2. **`notify_telegram(market_brief, sentiment_dist)` function:**
   - Format brief for Telegram (markdown-friendly)
   - Send via existing Telegram integration (openclaw or direct API)
   - Include sentiment distribution summary

3. **`update_dashboard(run_id)` function:**
   - Log activity in `activity_log` table
   - Update any dashboard cache if applicable

4. **`trigger_notifications(run_id, market_brief, articles)` function:**
   - Call `notify_telegram()`
   - Call `update_dashboard()`
   - Return notification status

**Dependencies:** `core.db`, `core.config`, `requests` (for Telegram API)

---

## Phase 3: Pipeline Orchestrator (Day 3-4)

### Task 3.1: Create main pipeline function

**File:** `core/market_intelligence/__init__.py`

**Purpose:** Orchestrate the full 5-stage pipeline.

**Key Components:**

```python
def run_pipeline():
    """Execute the complete Market Intelligence pipeline."""
    import logging
    log = logging.getLogger(__name__)
    
    start_time = datetime.utcnow()
    period = determine_period()  # morning/afternoon/evening/night
    
    try:
        # Stage 1: Ingestion
        log.info("[MI] Stage 1: Ingesting articles...")
        raw_articles = ingestion.fetch_articles(hours_back=6)
        log.info(f"[MI] Ingested {len(raw_articles)} articles")
        
        if not raw_articles:
            log.warning("[MI] No articles found in last 6 hours")
            return {"status": "no_articles", "article_count": 0}
        
        # Stage 2: Parsing
        log.info("[MI] Stage 2: Parsing and cleaning articles...")
        cleaned_articles = [parsing.clean_article(a) for a in raw_articles]
        
        # Stage 3: Analysis
        log.info("[MI] Stage 3: Analyzing articles with LLM...")
        analyzed_articles = analyst.analyze_articles(cleaned_articles)
        
        # Stage 4: Synthesis
        log.info("[MI] Stage 4: Synthesizing Market Brief...")
        market_brief = synthesizer.synthesize_market_brief(analyzed_articles)
        
        # Stage 5: Delivery
        log.info("[MI] Stage 5: Delivering to DB and notifications...")
        articles_json = json.dumps(analyzed_articles, ensure_ascii=False)
        run_id = delivery.save_to_db(
            run_date=datetime.utcnow().strftime("%Y-%m-%d"),
            run_period=period,
            articles_json=articles_json,
            market_brief=market_brief
        )
        
        # Trigger notifications
        sentiment_dist = delivery.get_sentiment_distribution()  # quick count
        delivery.trigger_notifications(run_id, market_brief, analyzed_articles)
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        log.info(f"[MI] Pipeline complete in {elapsed:.1f}s — Run ID: {run_id}")
        
        return {
            "status": "complete",
            "run_id": run_id,
            "article_count": len(analyzed_articles),
            "period": period,
            "elapsed_seconds": elapsed
        }
    
    except Exception as e:
        log.error(f"[MI] Pipeline failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
```

**Dependencies:** All stage modules, `logging`, `datetime`, `json`

---

## Phase 4: API Endpoints (Day 4-5)

### Task 4.1: Add Market Intelligence endpoints to Flask app

**File:** `app.py` (or `flask_dashboard.py`)

**Endpoints to add:**

```python
@app.route('/api/market-intelligence/run', methods=['POST'])
def mi_run():
    """Trigger a new 6-hour cycle pipeline run."""
    result = market_intelligence.run_pipeline()
    return jsonify(result)

@app.route('/api/market-intelligence/latest')
def mi_latest():
    """Get the most recent Market Brief + articles."""
    db = Database()
    data = db.get_latest_market_intelligence()
    return jsonify(data)

@app.route('/api/market-intelligence/history')
def mi_history():
    """List past intelligence runs with filters."""
    limit = request.args.get('limit', 10, type=int)
    period = request.args.get('period', None)
    db = Database()
    data = db.get_market_intelligence_history(limit=limit, period=period)
    return jsonify(data)

@app.route('/api/market-intelligence/<int:run_id>')
def mi_by_id(run_id):
    """Get specific run detail."""
    db = Database()
    data = db.get_market_intelligence_by_id(run_id)
    if not data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)

@app.route('/api/market-intelligence/sentiment-dist')
def mi_sentiment_dist():
    """Get sentiment distribution summary."""
    db = Database()
    data = db.get_sentiment_distribution()
    return jsonify(data)

@app.route('/api/market-intelligence/<int:run_id>', methods=['DELETE'])
def mi_delete(run_id):
    """Delete a specific run."""
    db = Database()
    db.delete_market_intelligence(run_id)
    return jsonify({"status": "deleted", "run_id": run_id})
```

---

## Phase 5: Scheduling & Integration (Day 5-6)

### Task 5.1: Add APScheduler job

**File:** `app.py` or separate scheduler module

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# Run every 6 hours: 06:00, 12:00, 18:00, 00:00 SGT
scheduler.add_job(
    func=market_intelligence.run_pipeline,
    trigger="cron",
    hour=[6, 12, 18, 0],
    minute=0,
    timezone="Asia/Saigon",
    id="market_intelligence_pipeline",
    replace_existing=True
)

scheduler.start()
```

### Task 5.2: Add CLI command

**File:** `cli.py`

```python
@cli.command("market-intelligence")
@click.option("--run", is_flag=True, help="Run pipeline immediately")
def market_intelligence(run):
    """Market Intelligence Agent — 6-hour cycle pipeline."""
    if run:
        result = market_intelligence.run_pipeline()
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo("Market Intelligence Agent ready. Use --run to execute.")
```

---

## Phase 6: Testing & Validation (Day 6-7)

### Task 6.1: Unit tests

**File:** `tests/test_market_intelligence.py`

Test each stage independently:
- `test_ingestion_fetches_articles()` — mock RSS responses
- `test_parsing_strips_html()` — verify HTML removal
- `test_analyst_sentiment_classification()` — mock LLM responses
- `test_synthesizer_brief_generation()` — mock LLM responses
- `test_delivery_db_save()` — mock DB methods

### Task 6.2: Integration test

**File:** `tests/test_market_intelligence_integration.py`

Test full pipeline with real RSS feeds (read-only, no DB writes):
- Fetch real articles from Cafef/VnExpress
- Verify parsing produces clean text
- Mock LLM calls for analysis/synthesis
- Verify JSON structure matches schema

### Task 6.3: Manual validation

1. Run pipeline manually via CLI: `python cli.py market-intelligence --run`
2. Check DB for saved records
3. Verify Telegram notification received (if configured)
4. Validate JSON output matches expected schema

---

## Dependencies Checklist

| Package | Status | Notes |
|---------|--------|-------|
| `feedparser` | ✅ Already installed | Via `news_engine.py` |
| `beautifulsoup4` | ⚠️ Check | Used for HTML parsing |
| `requests` | ✅ Already installed | HTTP requests |
| `apscheduler` | ✅ Already installed | Background scheduling |
| `core/ollama_client` | ✅ Exists | LLM inference |
| `core/db` | ✅ Exists | Database layer |
| `core/config` | ✅ Exists | Config loader |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM API unavailable | High | Fallback to heuristic sentiment (reuse `news_engine.py` patterns) |
| RSS feeds blocked/rate-limited | Medium | Add delays between requests, retry with backoff |
| Article content too long for LLM | Medium | Truncate to 3000 chars, summarize first if needed |
| DB schema migration fails | Low | Use `IF NOT EXISTS`, test in dev DB first |
| Telegram delivery fails | Low | Log error, continue pipeline (non-critical) |

---

## Implementation Order (Recommended)

1. **Day 1:** Database schema + helper methods (`db.py`)
2. **Day 1-2:** Ingestion module (`ingestion.py`)
3. **Day 2:** Parsing module (`parsing.py`)
4. **Day 2-3:** Analyst module (`analyst.py`) — requires LLM access
5. **Day 3:** Synthesizer module (`synthesizer.py`) — requires LLM access
6. **Day 3:** Delivery module (`delivery.py`)
7. **Day 4:** Pipeline orchestrator (`__init__.py`)
8. **Day 4-5:** API endpoints in Flask app
9. **Day 5-6:** Scheduling + CLI integration
10. **Day 6-7:** Testing + validation

---

## Success Criteria

- [ ] All 5 pipeline stages implemented and tested individually
- [ ] Full pipeline runs end-to-end successfully with real RSS data
- [ ] JSON output matches documented schema exactly
- [ ] Database records created with correct structure
- [ ] API endpoints return expected responses
- [ ] APScheduler job runs every 6 hours automatically
- [ ] CLI command `python cli.py market-intelligence --run` works
- [ ] Telegram notifications delivered (if configured)
- [ ] LLM fallback works when Ollama is unavailable
- [ ] All unit tests pass

---

## Notes

- Reuse existing RSS source patterns from `news_engine.py` and `news_service.py`
- Reuse heuristic sentiment patterns from `news_engine.py` as LLM fallback
- Follow existing code style: snake_case, docstrings, lazy imports
- Use `ollama_client.ollama_parse_json()` for structured LLM outputs
- Use `ollama_client.ollama_call()` for narrative LLM outputs
- All datetime stored as ISO strings per existing convention
