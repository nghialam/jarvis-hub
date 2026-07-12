"""Seed market_overview data from fresh fetched data into jarvis.db."""
import json
import sys
from datetime import date, datetime

sys.path.insert(0, '.')
from core.market_overview import fetch_all_overview
from core.db import Database

print("[MAIN] Fetching fresh data...")
data = fetch_all_overview()

if not data.get('vn_indices'):
    print("[ERROR] No VN data - market data source still failing!")
    sys.exit(1)

db = Database()
today = date.today().isoformat()

# Clear old today data
db._conn.execute("DELETE FROM market_overview WHERE date=?", (today,))
db._conn.commit()

rows = []
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

for name, d in data['vn_indices'].items():
    rows.append((today, name, name, 'VN_INDEX', d['price'], d.get('change_pct'), None, None, None, None, None, now))

for name, d in data.get('global_indices', {}).items():
    rows.append((today, name, name, 'GLOBAL_INDEX', d['price'], d.get('change_pct'), d.get('market_cap'), d.get('volume'), None, None, None, now))

for name, d in data.get('crypto', {}).items():
    rows.append((today, name, name, 'CRYPTO', d['price'], d.get('change_pct'), None, d.get('volume'), None, None, None, now))

if data.get('gold'):
    d = data['gold']
    rows.append((today, 'XAU/USD', 'Gold', 'COMMODITY', d['price'], d.get('change_pct'), None, None, None, None, None, now))

if data.get('oil'):
    d = data['oil']
    rows.append((today, 'WTI Oil', 'Crude Oil (WTI)', 'COMMODITY', d['price'], d.get('change_pct'), None, None, None, None, None, now))

if data.get('dxy'):
    d = data['dxy']
    rows.append((today, 'DXY', 'US Dollar Index', 'FX', d['price'], d.get('change_pct'), None, None, None, None, None, now))

# Sync schema if needed
c = db._conn.cursor()
existing_cols = [r[1] for r in c.execute("PRAGMA table_info(market_overview)").fetchall()]
if 'updated_at' not in existing_cols:
    print("[DB] Adding missing 'updated_at' column...")
    c.execute("ALTER TABLE market_overview ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    db._conn.commit()

ins = """INSERT INTO market_overview (date, symbol, name, asset_type, price, 
             change_pct, market_cap, volume, week_change, month_change, quarter_change, updated_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

for r in rows:
    c.execute(ins, r)

db._conn.commit()
print(f"[OK] Seeded {len(rows)} market_overview rows for today ({today})")

# Quick verify
count = db._conn.execute("SELECT COUNT(*) FROM market_overview WHERE date=?", (today,)).fetchone()[0]
print(f"[VERIFY] DB contains {count} rows for {today}")

# Check news tables too
news_count = db._conn.execute("SELECT COUNT(*) FROM news_enhanced").fetchone()[0]
article_count = db._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"[NEWS] news_enhanced: {news_count} rows, articles: {article_count} rows")
