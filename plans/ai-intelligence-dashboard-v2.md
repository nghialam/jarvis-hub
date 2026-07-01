# AI Intelligence Dashboard v2 — Full Pipeline + Recommendations Timeline

**Date:** 2026-06-10  
**Status:** Planning (P1 feature, per BACKLOG.md)  
**Goal:** Replace the current "AI Intelligence" tab with a proper web page where Rex can see every data point Cron crawled in chronological order, plus all LLM recommendations — fully filterable and interactive.

---

## 0. Current State Audit

### What Happens Now (Cron → Telegram)
```
┌──────────┐   ┌──────────────┐   ┌─────────────────────┐   ┌──────────┐
│ RSS/API  │→ │ LLM Chain 1:  │ → │ LLM Chain 2:         │ → │ Telegram │
│ Fetcher  │   │ Synthesis    │   │ Recommendations      │   │ x3 msg   │
│          │   │              │   │                        │   │          │
│ - CafeF  │   │ News summary   │   │ Actionable recs      │   │ Delivered│
│ - VnEx   │   │ Trends,        │   │ Tech Lab proposals   │   │ to Rex   │
│ - DDG AI │   │ Sentiment      │   │                      │   │          │
│ - Stocks │   │ Bull/Bear      │   │ (sequential ~90s ea) │   │          │
└──────────┘   └──────────────┘   └─────────────────────┘   └──────────┘
```

### What Gets Saved NOW
- **`daily_snapshots` table**: One row/date — contains the FULL briefing as monolithic `briefing_content` TEXT blob (HTML with article links) + a string summary
- **NO per-article storage**: Every individual article's title, URL, sentiment, category is lost before LLM chains run
- **NO LLM output persistence**: Chain 1/2/3 outputs go to Telegram, never save to DB

### What Rex Sees Now (app.py tabs)
1. **Dashboard** — market indices, headlines grid, crypto/commodities
2. **Analyze** — search single stock via `core/market.py`
3. **History** — daily snapshots as full-text blobs from `daily_snapshots.summary`
4. **AI Intelligence** (`/ai-intelligence`) — loads from `_fresh_cache.get("_briefings")`, which is populated per-cycle in `app_refresh_loop()` and falls back to a simple article fetch

### The Problem
- Per-article data = ephemeral (only in memory for 5-minute cache window)
- Recommendations = lost entirely (Telegram only)
- No chronological ordering across days
- No filtering by sentiment, category, or recommendation type

---

## 1. New Architecture Overview

```
┌──────────────────┐     ┌──────────────────────────────┐     ┌─────────────────┐
│  Cron Pipeline   │────>│  New DB Schema + Save Logic  │────>│  New API Layer  │
│  (gotham_brief)  │     │  jarvis.db                   │     │  app.py         │
│                  │     │                              │     │                 │
│  Phase 1: Fetch  │     │  articles: ALL crawled data  │     │  /api/v2/...   │     │  AI Intelligence tab
│  Phase 2: LLM    │     │  run_chains: LLM output      │     │                 │     │  (full-page, not tab)
│  Phase 3: Save   │     │  recommendations: per-source │     │  Real-time      │     │
└──────────────────┘     │  scores: run-level meta      │     │  dashboard      │     │
                         │                           │     │                 │     │
                         └───────────────────────────┘     └─────────────────┘
```

### Core Idea
- **Keep existing `daily_snapshots` table intact** — the monolithic blob remains for backward compatibility
- **Add new tables**: `articles`, `recommendations`, `run_chains` (for LLM chain metadata)
- **Add new API endpoints** under `/api/v2/...` — don't touch existing endpoints
- **Replace the "AI Intelligence" tab** with a full-page UI in `app.py`

---

## 2. New DB Schema (`core/db.py`)

### Table: `articles`
Stores EVERY article crawled from RSS/API before LLM chains see them.

```sql
CREATE TABLE IF NOT EXISTS articles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,           -- links to run_chains.run_id
    published_date    TEXT,                        -- when source published it
    title             TEXT    NOT NULL,
    summary_raw       TEXT,                        -- raw text before LLM
    category          TEXT    DEFAULT 'general',   -- vn-stock, vn-business, ai-tech, etc.
    sentiment         TEXT    DEFAULT 'TRUNG_LẬP', -- TÍCH_CỰC, TIÊU_CỰC, TRUNG_LẬP
    sentiment_score   REAL DEFAULT 0,              -- bull_count - bear_count (heuristic)
    url               TEXT,                        -- source link
    has_image         INTEGER DEFAULT 0,           -- whether it has embed image
    order_in_run      INTEGER,                     -- position in cron crawl (0-indexed)
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_articles_run_id ON articles(run_id);
CREATE INDEX idx_articles_sentiment ON articles(sentiment);
CREATE INDEX idx_articles_category ON articles(category);
```

### Table: `articles_images`
Stores each article's embedded image.

```sql
CREATE TABLE IF NOT EXISTS articles_images (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id    INTEGER NOT NULL REFERENCES articles(id),
    image_url     TEXT    NOT NULL,               -- full URL to the cached/inline image
    caption       TEXT DEFAULT '',                 -- alt text or caption if exists
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_arts_img_article ON articles_images(article_id);
```

### Table: `recommendations`
Stores LLM Chain 2 output, decomposed into **per-article** actionable recommendations.

```sql
CREATE TABLE IF NOT EXISTS recommendations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,           -- which run produced this rec
    article_id        INTEGER REFERENCES articles(id), -- links back to source article (NULL if general)
    type              TEXT    NOT NULL,           -- ACTIONABLE_RECOMMENDATION | TECH_LAB_PROPOSAL
    source_topic      TEXT DEFAULT '',             -- what the recommendation is ABOUT (short label)
    heading           TEXT    NOT NULL,            -- bold title line of the rec
    detail_markdown   TEXT,                        -- full markdown body text
    confidence_hint   TEXT                         -- e.g. "HIGH", "MEDIUM" from LLM output
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recs_run_id ON recommendations(run_id);
CREATE INDEX idx_recs_type ON recommendations(type);
```

### Table: `run_chains`
Run-level metadata for each cron execution.

```sql
CREATE TABLE IF NOT EXISTS run_chains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    UNIQUE NOT NULL,       -- same as daily_snapshots.date or UUID
    pipeline_date   TEXT NOT NULL,                 -- e.g. "2026-06-10"
    llm_chain_1_summary   TEXT,                    -- Chain 1: Global synthesis + trends
    llm_chain_3_summary   TEXT,                    -- Chain 3: Tech Lab
    total_articles  INTEGER DEFAULT 0,             # articles saved for this run
    total_sources   INTEGER DEFAULT 0,             # unique sources (CafeF, etc.)
    status          TEXT DEFAULT 'complete',         # complete | partial | failed
    error_log       TEXT,                          -- any errors during pipeline
    chain_started_at   TIMESTAMP,                    -- when first LLM call started
    chain_completed_at TIMESTAMP,                    -- when last LLM completed
    duration_sec    REAL                            -- total pipeline time
);

CREATE INDEX idx_runs_date ON run_chains(pipeline_date DESC);
```

### Migration Notes
- All new tables are `IF NOT EXISTS` + `PRAGMA_foreign_keys=ON`, safe to run on existing DB
- Existing app.py `daily_snapshots` table is **not modified** — backward compatible
- New `_articles_img.json` sidecar file for images: save to `knowledge/images/<date>/<index>.jpg`, track in DB for cleanup

---

## 3. Cron Pipeline Changes (`core/news.py`)

### Current Flow (what exists NOW):
```python
# In news.py get_articles():
1. fetch all RSS feeds → list of article dicts
2. for each: enrich with sentiment via LLM + heuristic scoring
3. return enriched articles list
4. app.py saves summary into daily_snapshots.briefing_content
5. NOTHING else saved — per-article data lost after Telegram send
```

### New Flow (after changes):
```python
# In news.py get_articles() + new helper:
1. fetch all RSS feeds → list of article dicts (same as now)
2. for each: enrich with sentiment + heuristics (same as now)
3. **NEW**: extract images from articles → save to knowledge/images/<date>/<n>.jpg
4. **NEW**: call save_articles_to_db(run_id, enriched_articles) — bulk INSERT
5. app.py still saves daily_snapshots summary (unchanged)
6. LLM chains still run same way, outputs now ALSO saved via new API endpoints
7. On DB commit success: return True to signal pipeline OK
```

### Specific Code Changes in `news.py`:

**A. Add `save_article_images(directory, article_html)` helper:**
```python
def extract_and_save_images(html_content: str, base_dir: Path) -> list[str]:
    """Extract image URLs from article HTML, download + save locally."""
    urls = re.findall(r'<img[^>]+src="([^"]+)"', html_content)
    saved = []
    for img_url in urls[:1]:  # first image per article (main one)
        try:
            r = requests.get(img_url, timeout=10)
            if r.status_code == 200:
                fname = f"{len(saved)}.jpg"
                path = base_dir / fname
                path.write_bytes(r.content)
                saved.append(str(path))
        except:
            pass
    return saved
```

**B. Add `save_articles_to_db()` function:**
```python
def save_articles_to_db(db_path, run_id, articles):
    """Save all fetched + enriched articles to DB."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    for i, art in enumerate(articles):
        # Insert article row
        c.execute("""INSERT INTO articles 
            (run_id, title, summary_raw, category, sentiment, 
             sentiment_score, url, has_image, order_in_run)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, art.get('title',''), art.get('summary_raw',''),
             art.get('category','general'), art.get('sentiment','TRUNG_LẬP'),
             art.get('score', 0), art.get('href',''), 
             1 if art.get('has_image') else 0, i))
        
        art_id = c.lastrowid
        
        # Save images if any
        if art.get('image_urls'):
            for img in art['image_urls']:
                c.execute("""INSERT INTO articles_images 
                    (article_id, image_url) VALUES (?, ?)""",
                    (art_id, img))
    
    conn.commit()
    return len(articles)  # return count for run_chains update
```

**C. Update `get_enriched_articles()` to also call save:**
- Add optional `save_to_db=True` parameter
- When called from cron context → pass `run_id` and `db_path`

---

## 4. New API Endpoints (`app.py`)

### Endpoint: `/api/v2/ai-intelligence/daily-list`
Returns list of all run dates with article counts + summary.

```json
[
    {
        "run_id": "2026-06-10",
        "date": "2026-06-10",
        "article_count": 35,
        "source_count": 7,
        "chain_1_summary": "...first 200 chars of synthesis...",
        "recommendation_count": 12,
        "status": "complete"
    },
    {
        "run_id": "2026-06-09",
        ...
    }
]
```

### Endpoint: `/api/v2/ai-finance/run/<date>`
Returns ALL data for one specific day — articles, recommendations, and metadata.

```json
{
    "run_id": "2026-06-10",
    "pipeline_date": "2026-06-10 06:00:00",
    "total_articles": 35,
    "sources": ["CafeF Doanh nghiệp", "VnExpress KM", ...],
    "status": "complete",
    "articles": [
        {
            "id": 1,
            "title": "EVN miền Bắc lập đỉnh lợi nhuận...",
            "summary_raw": "...first 300 chars...",
            "category": "vn-stock",
            "sentiment": "TÍCH_CỰC",
            "sentiment_score": 5.0,
            "url": "https://cafef.vn/...",
            "has_image": 1,
            "image_url": "/static/images/<date>/0.jpg",
            "order_in_run": 0
        },
        ...34 more...
    ],
    "recommendations": [
        {
            "id": 1,
            "type": "ACTIONABLE_RECOMMENDATION",
            "source_topic": "Banking Sector Rally",
            "heading": "Monitor VCB for breakout above 35,000",
            "detail_markdown": "**Recommended**: Consider positioning... **Reason**: ...",
            "confidence_hint": "MEDIUM"
        },
        ...11 more...
    ],
    "chain_1_summary": "...full Chain 1 output...",
    "chain_3_summary": "...full Chain 3 (Tech Lab) output..."
}
```

### Endpoint: `/api/v2/ai-finance/health`
Returns pipeline health + last run status.

```json
{
    "last_run_date": "2026-06-10",
    "total_runs_saved": 47,
    "daily_avg_articles": 35,
    "ollama_status": "online"
}
```

---

## 5. New UI: AI Intelligence Tab (`app.py` + `dashboard/templates/index.html`)

### What It Looks Like (replaces existing "AI Intelligence" tab)

**Tab Structure — 3 sub-views via radio buttons:**

```
┌─────────────────────────────────────────────────────┐
│ 👁️  AI INTELLIGENCE DASHBOARD                        │
│ [Articles Timeline] [Recommendations] [Overview Map] │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Filter: All Articles | By Sentiment               │
│  ───────────────────────────────                   │
│  🟢 tích cực (8) | 🟡 trung lập (14) | 🔴 tiêu cực (3) │
│                                                      │
│  [Timeline View - Chronological Order]              │
│                                                      │
│  ╔══════════════════════════════════════╗           │
│  ║  📅 2026-06-10  (35 articles)        ║           │
│  ╠══════════════════════════════════════╣          ║
│  ║  08:24 — EVN miền Bắc lập đỉnh...   ║──────────║  ← article card 1
│  ║  🟢 tích cực | CafeF Doanh nghiệp   ║          ║
│  ║  Preview text truncated to 2 lines... │          ║
│  ╚══════════════════════════════════════╝           │
│                                                      │
│  ╔══════════════════════════════════════╗           │
│  ║  08:24 — Novaland 'khất nợ'...       ║──────────║  ← article card 2
│  ║  🔴 tiêu cực | CafeF Doanh nghiệp   ║          ║
│  ║  Preview text truncated to 2 lines... │          ║
│  ╚══════════════════════════════════════╝           │
│                                                      │
│  [Scroll to see all 35 articles...]                   │
└─────────────────────────────────────────────────────┘
```

### Key Features per Sub-view:

#### A) Articles Timeline (default)
- **Chronological** by `order_in_run` within each day's run
- **Each card shows**: timestamp, title, sentiment badge, source, 2-line preview, first image thumbnail
- **Filter bar** at top: All | VN Stock | AI/Tech | Global Economy | ... (by category)
- **Sentiment filter** sub-row: TÍCH_CỰC (green), TRUNG_LẬP (yellow), TIÊU_CỰC (red)
- **Hover card**: shows full article + linked recommendation
- **Click card**: expands to show all details in sidebar/modal

#### B) Recommendations View
- Separate filtered list showing only from `recommendations` table
- Grouped by type: "ACTIONABLE_RECOMMENDATION" vs "TECH_LAB_PROPOSAL"
- Each rec links back to its source article (click opens article card)
- Shows confidence_hint as a badge

#### C) Overview Map (summary view)
- Sankey-style flow: Source categories → Sentiment distribution → Recommendation types
- Per-day rollup: total articles, avg sentiment, key trend headline
- Clickable cards jumping to specific day's detail

---

## 6. Implementation Plan (Step by Step)

### Phase 1: DB Schema + Save Logic (Backend)
**Files:** `core/db.py`, `core/news.py`

1. **Modify `db.py`**: Add `articles`, `articles_images`, `recommendations`, `run_chains` tables to `init_db()`
2. **Add `save_articles_to_db()` helper** in `news.py` (bulk article + image save)
3. **Add `_extract_image_urls()`** helper parsing the HTML `<img>` tags
4. **Update `get_enriched_articles()`** to accept optional DB save parameter

### Phase 2: Cron Pipeline Changes
**Files:** `core/news.py` pipeline functions

5. **Wire up article save in cron flow**: After articles fetched, call save function
6. **Add run-level metadata tracking**: record total_articles count per run

### Phase 3: API Layer (FastAPI/Flask REST)
**File:** `app.py` (new endpoints only, no changes to existing routes)

7. **Add `/api/v2/ai-intelligence/daily-list`** — list all runs with stats
8. **Add `/api/v2/ai-finance/run/<date>`** — full run detail JSON
9. **Add `/api/v2/ai-finance/health`** — system health summary

### Phase 4: Frontend UI (New HTML + JS)
**Files:** `dashboard/templates/index.html`, `dashboard/static/js/ai-intelligence.js`

10. **Create new tab structure**: Replace "AI Intelligence" with 3 sub-views
    - Articles Timeline (default, full-page)
    - Recommendations list  
    - Overview Map (per-day summary grid)
    
11. **New JavaScript file**: `ai-intelligence.js` for:
    - Fetching articles from API
    - Rendering cards in chronological order
    - Filtering by sentiment/category
    - Handling article click → expand/show recommendation
    - Pagination or infinite-scroll fallback
    
12. **Wire into existing tab HTML**: Add the new tab button + content div

### Phase 5: Testing & Polish
**Files:** All changed files above

13. **Run pipeline test**: Verify DB has correct records after cron run
14. **Test all 3 API endpoints**: curl to verify JSON responses
15. **Test frontend UI in browser**: verify rendering + filtering works
16. **Fix any schema/API/render bugs**

---

## 7. Technical Constraints & Notes

### What MUST NOT Break
- Existing `daily_snapshots` table schema unchanged ✓
- All existing API endpoints (`/api/articles`, `/api/snapshots`, etc.) untouched ✓
- Cron job delivery to Telegram still works (same LLM chain flow) ✓

### Memory Budget Concerns
- Each article row ~500 bytes metadata + image data (avg 2KB per img) → ~2.5KB/article × 35 articles ≈ **87.5 KB/day**
- Over 365 days: ~31 MB total — **negligible impact** on existing DB size
- Images stored locally in `knowledge/images/<date>/*.jpg` to avoid bloating the SQLite DB file

### Image Storage Strategy
- Save downloaded images to `~/jarvis-hub/knowledge/images/<YYYY-MM-DD>/<index>.jpg`
- Track URLs in `articles_images.image_url` as relative paths (e.g., `/static/images/2026-06-10/0.jpg`)
- Add Flask static route for serving: `@app.route('/static/images/<path:path>')`

### Existing Codebase Facts
- app.py already has a `_fresh_cache` dict pattern for per-cycle data (line 82)
- DB path stored in config: `cfg.load_config()["db_path"]`  
- News loading currently done in `get_articles()` (core/news.py, ~400 lines total)
- Sentiment scoring uses heuristic patterns from `news.py` + LLM fallback

---

## 8. Risk Assessment

### High-Risk Items
| # | Risk | Probability | Mitigation |
|---|------|-------------|------------|
| R1 | Breaking existing DB migration | Low (IF NOT EXISTS) | Test on copy first |  
| R2 | New API slow with many articles | Medium | Paginate, add LIMIT to queries |
| R3 | Flask static image serving new route | Low | Simple Route pattern already used |

### Medium-Risk Items
| # | Risk | Probability | Mitigation |
|---|------|-------------|------------|
| R4 | `orders_in_run` breaks on re-crawl | Low | Reset order each run (new run_id) |
| R5 | Cron pipeline adds 10-20s overhead | Medium | Async image download (ThreadPoolExecutor) |

### Low-Risk Items
- Simple SELECT API endpoints
- Existing `run_chains` metadata structure
- Article text content storage

---

## 9. Estimated Work Breakdown (Hours for "coder" or experienced dev)

| Phase | Task Count | Est. Hours | Notes |
|-------|-----------|------------|-------|
| DB Schema (Phase 1 A) | 4 sub-tasks | ~2h | Straightforward SQL + helper funcs |
| Cron Pipeline (Phase 1 B) | 2 tasks | ~3h | Complex because of HTML parsing logic |
| API Layer (Phase 3) | 3 endpoints | ~2h | Relatively straightforward Flask routes |
| Frontend HTML/JS (Phase 4) | 5 sub-tasks | ~4-6h | Hardest part — card rendering + filtering |
| Testing & Polish (Phase 5) | 3 tasks | ~2h | End-to-end testing, visual polish |

**Total: ~13-17 hours of focused coding**

---

## 10. Implementation Order for "coder" Subagent

1. **Sub-agent A (DB + Backend)**: Schema → Save Logic → API Layer
2. **Sub-agent B (Frontend)**: HTML Template + JS + Static Routes
3. **Merge**: Test everything together

**Prerequisite for coder:** Give `plans/ai-intelligence-dashboard-v2.md` full read, then implement exactly as specified (sections 2 through 7).

---

## 11. Success Criteria (Acceptance Tests)

- [ ] Run cron pipeline → DB `articles` table has all crawled articles with correct sentiment
- [ ] `curl /api/v2/ai-intelligence/daily-list` returns list of runs with counts  
- [ ] `curl /api/v2/ai-finance/run/<date>` returns full run detail with articles + recs
- [ ] New "AI Intelligence" tab shows articles in chronological order
- [ ] Sentiment filter (TÍCH_CỰC/TRUNG_LẬP/TIÊU_CỰC) works per-row
- [ ] Category filter (VN Stock, AI Tech, ... ) also filters correctly
- [ ] Recommendations view shows per-source recommendations with proper links to articles
- [ ] Overview Map shows daily summary cards clickable → details
- [ ] No existing dashboard functionality breaks

---

*Plan created: 2026-06-10 | Ready for Rex review → coder execution*
