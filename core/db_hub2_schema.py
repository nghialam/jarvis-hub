#!/usr/bin/env python3
"""db_hub2_schema.py -- Create and initialize Jarvis Hub 2.0 tables in jarvis.db

Tables (per JARVIS_HUB_2.0_DESIGN.md §5):
  - market_quotes       : live/last-prices for tracked tickers
  - daily_ohlcv         : daily OHLCV time-series per ticker
  - news_articles       : aggregated news headlines/snippets
  - entity_mentions     : ticker/company mentions in articles
  - research_reports    : broker research report metadata
  - alerts              : user-configured price/volume alerts

Usage:
    cd /Users/nghialam/jarvis-hub
    python core/db_hub2_schema.py          # create tables only
    python core/db_hub2_seed.py           # seed with demo data (calls init)
"""
import sqlite3
import sys
import os
from pathlib import Path

# ── DB path: use the existing jarvis.db under knowledge/ or a dedicated hub2 db ──
DEFAULT_DB = str(Path.home() / "jarvis-hub" / "knowledge" / "jarvis.db")


def get_conn(db_path=None):
    if db_path is None:
        db_path = DEFAULT_DB
    p = Path(db_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ────────────────────────────────────────────────
#  TABLE DEFINITIONS  (exact per DESIGN §5)
# ────────────────────────────────────────────────

MARKET_QUOTES_SQL = """
CREATE TABLE IF NOT EXISTS market_quotes (
    id            INTEGER PRIMARY KEY,
    ticker        TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    exchange      TEXT    CHECK(exchange IN ('HOSE','HNX','UPCoM')),
    current_price REAL DEFAULT 0,
    open_price    REAL DEFAULT 0,
    high_price    REAL DEFAULT 0,
    low_price     REAL DEFAULT 0,
    prev_close    REAL DEFAULT 0,
    volume        REAL DEFAULT 0,
    value         REAL DEFAULT 0,
    change        REAL DEFAULT 0,
    change_pct    REAL DEFAULT 0,
    pe_ratio      REAL,
    pb_ratio      REAL,
    market_cap    REAL,   -- VND (trillions)
    sector        TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DAILY_OHLCV_SQL = """
CREATE TABLE IF NOT EXISTS daily_ohlcv (
    id            INTEGER PRIMARY KEY,
    ticker        TEXT    NOT NULL,
    date          DATE   NOT NULL,
    open_price    REAL,
    high_price    REAL,
    low_price     REAL,
    close_price   REAL,
    volume        REAL DEFAULT 0,
    value         REAL DEFAULT 0,
    UNIQUE(ticker, date)
);
"""

NEWS_ARTICLES_SQL = """
CREATE TABLE IF NOT EXISTS news_articles (
    id              INTEGER PRIMARY KEY,
    headline        TEXT    NOT NULL,
    snippet         TEXT,
    content         TEXT,
    source          TEXT    NOT NULL,
    url             TEXT,
    category        TEXT CHECK(category IN (
                              'Global Macro','VN Market','Forex',
                              'Crypto','Commodities','Earnings',
                              'Dividend','IPO','Strategy',
                              'Regulation','M&A','Alert')),
    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment       TEXT CHECK(sentiment IN ('Bullish','Bearish','Neutral')),
    relevance_score INTEGER CHECK(relevance_score BETWEEN 1 AND 5),
    is_featured     INTEGER DEFAULT 0,
    lang            TEXT    DEFAULT 'vn'
);
"""

ENTITY_MENTIONS_SQL = """
CREATE TABLE IF NOT EXISTS entity_mentions (
    id           INTEGER PRIMARY KEY,
    article_id   INTEGER,
    ticker       TEXT,
    company_name TEXT,
    mention_type TEXT CHECK(mention_type IN ('direct','indirect','sector')),
    FOREIGN KEY(article_id) REFERENCES news_articles(id)
);
"""

RESEARCH_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS research_reports (
    id                INTEGER PRIMARY KEY,
    broker            TEXT    NOT NULL CHECK(broker IN ('SSI','VCI','HCM','TCBS','VCBS')),
    title             TEXT    NOT NULL,
    report_type       TEXT CHECK(report_type IN (
                          'Weekly Chart','Sector Mix',
                          'Macro View','Stock Recommendation',
                          'Earnings Forecast')),
    published_at      DATE,
    file_url          TEXT,
    local_file_path   TEXT,
    index_target      REAL,
    market_outlook    TEXT CHECK(market_outlook IN ('Bullish','Neutral','Bearish')),
    key_tickers       TEXT,   -- comma-sep ticker list
    summary           TEXT,
    sector_weights    TEXT,   -- JSON of sector->weight
    downloaded        INTEGER DEFAULT 0,
    summary_generated INTEGER DEFAULT 0
);
"""

ALERTS_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    id                    INTEGER PRIMARY KEY,
    user_id               INTEGER DEFAULT 1,
    ticker                TEXT    NOT NULL,
    condition             TEXT    CHECK(condition IN (
                               'price_above','price_below',
                               'volume_spike','price_change_pct')),
    threshold             REAL,
    active                INTEGER DEFAULT 1,
    notification_channels TEXT    DEFAULT '',
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    triggered_at          TIMESTAMP
);
"""

# Tier 2: LLM Analysis Results Storage
ANALYTICAL_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS analytical_reports (
    id                  INTEGER PRIMARY KEY,
    run_date            DATE      NOT NULL,
    report_type         TEXT      CHECK(report_type IN (
                               'daily_brief','market_overview',
                               'stock_picks','news_summary',
                               'sentiment_analysis','auto_update')),
    title               TEXT,
    summary             TEXT,       -- condensed summary of the analysis
    full_content        TEXT,       -- full markdown analysis output
    status              TEXT        DEFAULT 'completed' CHECK(status IN ('pending','running','completed','failed')),
    data_snapshot_json  TEXT,       -- JSON snapshot of raw data used for this analysis
    confidence_scores   TEXT,       -- JSON: {report_type: score_0_100}
    model_used          TEXT,
    tokens_consumed     INTEGER DEFAULT 0,
    error_message       TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Tier 2: News enrichment results (LLM-scored news)
NEWS_ENRICHMENT_SQL = """
CREATE TABLE IF NOT EXISTS news_enrichment (
    article_id          INTEGER     PRIMARY KEY REFERENCES news_articles(id) ON DELETE CASCADE,
    llm_summary_text    TEXT,       -- LLM-generated summary of the headline
    key_tickers_extracted TEXT,     -- comma-sep tickers extracted e.g. "VIC,VNM"
    sentiment_explicit  TEXT        CHECK(sentiment_explicit IN ('Bullish','Bearish','Neutral')),
    impact_on_vn        TEXT,       -- short text explaining impact on VN market
    updated_at          TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
);
"""

# ------------------------------------------------------------------


def init_tables(db_path=None):
    """Create all Hub 2.0 tables; safe to call repeatedly."""
    conn = get_conn(db_path)
    c = conn.cursor()
    for sql in [MARKET_QUOTES_SQL, DAILY_OHLCV_SQL, NEWS_ARTICLES_SQL,
                ENTITY_MENTIONS_SQL, RESEARCH_REPORTS_SQL, ALERTS_SQL,
                ANALYTICAL_REPORTS_SQL, NEWS_ENRICHMENT_SQL]:
        c.executescript(sql)
    conn.commit()
    
    # Verify
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r["name"] for r in c.fetchall()]
    count = len(tables)
    print(f"[schema] Created/verified {count} tables: {', '.join(tables)}")
    conn.close()
    return tables


if __name__ == "__main__":
    init_tables()
