#!/usr/bin/env python3
"""Phase 1.6-1.7: Add JH3.0 and v2.0 compatibility tables to data/jarvis.db"""
import sqlite3
import os
import sys

DB_PATH = "/Users/nghialam/jarvis-hub/data/jarvis.db"

SCHEMA_SQL = """
-- JH3.0 Tables (Phase 1.6)
CREATE TABLE IF NOT EXISTS llm_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_llm_tasks_status ON llm_tasks(status);
CREATE INDEX IF NOT EXISTS idx_llm_tasks_type ON llm_tasks(task_type);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    result TEXT NOT NULL,
    ttl_seconds INTEGER DEFAULT 21600,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS circuit_breaker (
    endpoint TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'closed',
    failure_count INTEGER DEFAULT 0,
    last_failure TIMESTAMP,
    opened_at TIMESTAMP,
    half_open_allowed_at TIMESTAMP
);

-- v2.0 Compatibility Tables (Phase 1.7)
CREATE TABLE IF NOT EXISTS sector_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sector TEXT NOT NULL,
    change_pct REAL,
    market_cap REAL,
    top_stock TEXT,
    trend TEXT,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sector_performance ON sector_performance(sector);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    entity_type TEXT DEFAULT 'company',
    article_id INTEGER,
    mention_count INTEGER DEFAULT 1,
    sentiment TEXT DEFAULT 'NEUTRAL',
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_entity_mentions ON entity_mentions(entity_name);

CREATE TABLE IF NOT EXISTS report_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    raw_content TEXT,
    author TEXT,
    source_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broker_overview (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    broker TEXT NOT NULL,
    target_price REAL,
    rating TEXT,
    stock_covered TEXT,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_broker_overview ON broker_overview(broker);
"""

def main():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check existing tables
    existing = [row[0] for row in c.execute(
        'SELECT name FROM sqlite_master WHERE type="table" AND name NOT LIKE "sqlite_%"'
    ).fetchall()]
    
    print(f"Existing tables in {DB_PATH}: {len(existing)}")
    for t in existing:
        print(f"  - {t}")
    
    # Execute new schema
    c.executescript(SCHEMA_SQL)
    conn.commit()
    
    # Verify
    all_tables = [row[0] for row in c.execute(
        'SELECT name FROM sqlite_master WHERE type="table" AND name NOT LIKE "sqlite_%" ORDER BY name'
    ).fetchall()]
    
    print(f"\nAfter migration: {len(all_tables)} tables")
    new_tables = [t for t in all_tables if t not in existing]
    for t in all_tables:
        marker = " [NEW]" if t in new_tables else ""
        count = c.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
        print(f"  - {t} ({count} rows){marker}")
    
    print(f"\n✅ Phase 1.6-1.7 COMPLETE: Added {len(new_tables)} new tables")
    conn.close()

if __name__ == "__main__":
    main()
