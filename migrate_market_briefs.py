#!/usr/bin/env python3
"""Add market_briefs table to jarvis.db for storing cron brief outputs."""

import sqlite3
import sys

DB_PATH = "data/jarvis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    raw_json TEXT,
    formatted_output TEXT,
    source TEXT DEFAULT 'cron',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_market_briefs_date ON market_briefs(date);
"""

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    
    # Verify
    cur = conn.execute("PRAGMA table_info(market_briefs)")
    cols = [row[1] for row in cur.fetchall()]
    print(f"✓ Table market_briefs created with columns: {', '.join(cols)}")
    conn.close()
