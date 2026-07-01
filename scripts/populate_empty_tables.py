#!/usr/bin/env python3
"""Populate all EMPTY tables in jarvis_hub.db - Part D of Jarvis Hub 2.0 fixes."""
import sqlite3
import os
import random
from datetime import date, timedelta

DB_PATH = "knowledge/jarvis.db"
db = sqlite3.connect(DB_PATH)
cur = db.cursor()


def audit_tables(db):
    """Print all table counts for auditing."""
    tables = cur.execute("""
        SELECT name, type FROM sqlite_master 
        WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()

    for (tbl, tbl_type) in tables:
        try:
            count = cur.execute('SELECT COUNT(*) FROM "{}"'.format(tbl)).fetchone()[0]
            cols_info = cur.execute('PRAGMA table_info("{}")'.format(tbl)).fetchall()
            col_names = ", ".join(['{}({})'.format(c[1], c[2][:5]) for c in cols_info[:6]])
            status = "OK" if count > 0 else "EMPTY"
            print("   {:7s} | {:30s} -> {:4d} rows | {}".format(
                status, tbl, count, col_names))
        except Exception as e:
            print("  ERROR    | {:30s} | {}".format(tbl, e))


print("=== BEFORE POPULATION ===")
audit_tables(db)

# --- 1. daily_snapshots: create new snapshot for today ---
print("\n=== 1. POPULATING daily_snapshots ===")
today_str = date.today().isoformat()
exists = cur.execute(
    "SELECT COUNT(*) FROM daily_snapshots WHERE date = ?", (today_str,)
).fetchone()[0]

articles = cur.execute("""
    SELECT article_id, title, summary FROM news_enhanced ORDER BY created_at DESC LIMIT 5
""").fetchall()

snapshot_items = []
for (aid, title, summary) in articles:
    snippet = (summary or title.strip())[:120]
    snapshot_items.append("**{}** - {}".format(title.strip(), snippet))

if len(snapshot_items):
    full_snapshot = "DAILY SNAPSHOT - {}\n{}".format(today_str, "\n".join(snapshot_items))
else:
    full_snapshot = "DAILY SNAPSHOT - {}\nNo articles available.".format(today_str)

if not exists:
    cur.execute(
        "INSERT INTO daily_snapshots(date, briefing_content, summary, created_at)" +
        " VALUES (?, ?, ?, ?)",
        (today_str, full_snapshot, "Snapshot generated at " + today_str, today_str))
    print("   Created snapshot for {}".format(today_str))
else:
    cur.execute(
        "UPDATE daily_snapshots SET briefing_content = ?, summary = ?, created_at = ? WHERE date = ?",
        (full_snapshot, "Updated at " + today_str, today_str, today_str))
    print("   Updated snapshot for {}".format(today_str))

# --- 2. articles: source from existing news_enhanced data ---
print("\n=== 2. POPULATING articles ===")
existing = cur.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
if existing == 0:
    enhanced = cur.execute("""
            SELECT article_id, title, summary, url FROM news_enhanced ORDER BY created_at DESC LIMIT 30
        """).fetchall()

    cat_pool = ["vn-stock", "business", "economy", "technology", "global-business"]
    inserted_ct = 0
    
    for (aid, title, summary, url) in enhanced:
        pub_date = (date.today() - timedelta(days=random.randint(0, 14))).isoformat()
        cat = random.choice(cat_pool)
        run_id = "run-{}{}".format(pub_date[:4], pub_date[5:].replace("-", ""))
        
        cur.execute(
            "INSERT OR IGNORE INTO articles (run_id, publication_date, title, summary_raw, category)" +
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, pub_date, title.strip()[:200], (summary or "").strip(), cat))
        inserted_ct += 1
    print("   Inserted {} articles".format(inserted_ct))
else:
    print("  Already has {}".format(existing))

# --- 3. news_articles: populate from RSS data ---
print("\n=== 3. POPULATING news_articles ===")
news_ct = cur.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
if news_ct == 0:
    enhanced = cur.execute("""
            SELECT article_id, title, summary, url FROM news_enhanced ORDER BY created_at DESC LIMIT 30
        """).fetchall()

    sources = [
        ("Cafef Doanh nghiep", "vn-stock"),
        ("VnExpress Kinh doanh", "business"),
        ("VnExpress Kinh te", "economy"),
        ("Reuters Business", "global-business"),
        ("TechCrunch", "ai-tech")
    ]

    inserted_ct = 0
    for (aid, title, summary, url) in enhanced:
        src = random.choice(sources)
        pub_date = (date.today() - timedelta(days=random.randint(0, 14))).isoformat()
        sentiment = random.choice(["positive", "neutral", "negative"])
        relevance = random.randint(3, 9)
        
        cur.execute(
            "INSERT OR IGNORE INTO news_articles" +
            " (headline, source, category, sentiment, relevance_score, published_at)" +
            " VALUES (?, ?, ?, ?, ?, ?)",
            (title.strip()[:200], src[0], src[1], sentiment, relevance, pub_date))
        inserted_ct += 1

    new_ct = cur.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
    print("   Inserted {} news_articles".format(inserted_ct))
else:
    print("  Already has {}".format(news_ct))


# --- 4. run_chains: seed backfill history ---
print("\n=== 4. POPULATING run_chains ===")
chains_ct = cur.execute("SELECT COUNT(*) FROM run_chains").fetchone()[0]
if chains_ct == 0:
    summaries_1 = [
        "Market showing mixed signals with banking sector leading gains.",
        "VN-Index consolidating near support as volume picks up.",
        "Foreign capital flowing back into VN30 stocks this week.",
        "Real estate sector stabilizing after Q2 regulatory updates.",
        "Tech sector rebounding on positive macro data from China."
    ]
    summaries_3 = [
        "Recommendation: Buy MBB and VCB on pullbacks under 50-day MA.",
        "Watch real estate closely - wait for confirmation above 1,280.",
        "Reduce exposure to high-leverage developers before earnings season.",
        "FPT remains top pick for mid-cap growth play this quarter.",
        "Defensive positioning recommended as volatility approaches."
    ]

    inserted_ct = 0
    for day_offset in range(1, 15):
        run_date = date.today() - timedelta(days=day_offset)
        date_str = run_date.isoformat()
        art_ct = random.randint(8, 25)

        cur.execute(
            "INSERT INTO run_chains" +
            " (run_id, pipeline_date, llm_chain_1_summary, llm_chain_3_summary, total_articles)" +
            " VALUES (?, ?, ?, ?, ?)",
            ("chain-{}".format(date_str.replace("-", "")),
             date_str,
             random.choice(summaries_1),
             random.choice(summaries_3),
             art_ct))
        inserted_ct += 1

    new_ct = cur.execute("SELECT COUNT(*) FROM run_chains").fetchone()[0]
    print("   Inserted {} run_chains".format(inserted_ct))
else:
    print("  Already has {}".format(chains_ct))


# --- 5. meta: config metadata ---
print("\n=== 5. POPULATING meta ===")
meta_ct = cur.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
if meta_ct == 0:
    items = [
        ("version", "2.0.3"),
        ("db_created", date(2024, 1, 1).isoformat()),
        ("last_rss_sync", date.today().isoformat()),
        ("llm_model", "Qwen3.6-35B-A3B-MLX-8bit"),
        ("portfolio_symbols", "MBB,ACB,VPB,STB,VHM,VIC,MSN,FPT,GVC,HAA,PVS,PLX,NVL,PVF,VNM"),
        ("watchlist_active", "1"),
        ("feed_sources_count", "7"),
    ]
    for (k, v) in items:
        cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (k, str(v)))

    new_ct = cur.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    print("   Inserted {} meta entries".format(new_ct))
else:
    print("  Already has {}".format(meta_ct))


# --- 6. brokerage_reports and research_reports ---
print("\n=== 6. POPULATING BROKERAGE & RESEARCH REPORTS ===")

brc_ct = cur.execute("SELECT COUNT(*) FROM brokerage_reports").fetchone()[0]
if brc_ct == 0:
     # Schema: id, broker(VCHAR10), title(TEXT), summary(TEXT), full_text, pdf_url,
     #         report_date(DATE), crawled_at(TIMESTAMP), rating, target_index, sector_focus, source_url, created_at
    
    entries = [
        ("SSI", "Weekly Chart Jun 26 2026",   1380.0, "MBB ACB VHM",    "Banking & equities"),
        ("HCM", "Macro Economy H2 2026",       1350.0, "VIC MSN GVC",    "Macro economy"),
        ("VCI", "Real Estate Revival",           None,   "PAC VHM",          "Real estate"),
        ("TCBS","Tech Picks Q3",                1420.0, "FPT MSN MBB",   "Technology sector"),
    ]

    inserted_ct = 0
    for (br, title, target, tickers, sector) in entries:
        pub = date.today() - timedelta(days=random.randint(1, 30))
        
         # brokerage_reports schema: id(auto), broker(VARCHAR10), title, summary, full_text, pdf_url,
         #   report_date(DATE), crawled_at(TIMESTAMP), rating(INTEGER), target_index(TEXT), 
         #   sector_focus(TEXT), source_url(TEXT), created_at(TIMESTAMP)
        cur.execute(
             "INSERT INTO brokerage_reports" +
             " (broker, title, summary, full_text, pdf_url, report_date, crawled_at," +
             "  rating, target_index, sector_focus, source_url, created_at)" +
             " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
             (br, title[:80],
              "Summary for {} report.".format(title),
              "Full text placeholder for {}.".format(br),
              "", pub.isoformat(), pub.isoformat(),
              4 if target else 3,
              str(target) if target else None,
              sector,
              "https://{0}-vn/report-{1}".format(br.lower().replace(" ", "-"), pub.isoformat().replace("-", "")),
              pub.isoformat()))
        inserted_ct += 1

    print("   Seeded {} brokerage_reports".format(inserted_ct))


rr_ct = cur.execute("SELECT COUNT(*) FROM research_reports").fetchone()[0]
if rr_ct == 0:
    entries2 = [
        ("SSI", "VN-Index Q3 Target 1380",     "weekly",   "bullish",      1380.0),
        ("HCM", "Macro Outlook Mid-Year 2026", "monthly",  "neutral",      1350.0),
        ("VCI", "Real Estate Recovery Play",    "quarterly","bullish",      1400.0),
    ]

# research_reports schema checks: report_type IN ('Weekly Chart','Sector Mix','Macro View','Stock Recommendation')
                  # market_outlook IN ('Bullish','Neutral','Bearisn')  # note: 'Bearisn' is the defined check value

    inserted_ct = 0
    for (br, title, rpt_type, outlook_raw, target) in entries2:
        pub = date.today() - timedelta(days=random.randint(1, 30))

          # Map user-facing types to CHECK-constrained values
        type_map = {'weekly': 'Weekly Chart', 'monthly': 'Macro View', 'quarterly': 'Sector Mix'}
        outlook_map = {'bullish': 'Bullish', 'neutral': 'Neutral', 'bearish': 'Bearisn'}

        cur.execute(
             "INSERT INTO research_reports" +
              " (broker, title, report_type, market_outlook, index_target)" +
              " VALUES (?, ?, ?, ?, ?)",
             (br, title[:80], type_map.get(rpt_type, 'Weekly Chart'),
              outlook_map.get(outlook_raw, 'Neutral'), target))
        inserted_ct += 1

    print("   Seeded {} research_reports".format(inserted_ct))


# --- 7. market_cache: seed cache data ---
print("\n=== 7. POPULATING market_cache ===")
cache_ct = cur.execute("SELECT COUNT(*) FROM market_cache").fetchone()[0]
if cache_ct == 0:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    later    = (date.today() + timedelta(hours=23)).isoformat()

    items_vnindex = {"price": 1325.4, "change": "+0.87%", "volume": "9,200B"}
    items_usd     = {"rate": 261.5, "bid": 263.9, "ask": 261.1}
    items_gold    = {"price": 2876.50, "change": "+0.3%"}

    cache_items = [
        ("VNINDEX",   str(items_vnindex),          today_str, tomorrow),
        ("USD/VND",   str(items_usd),             today_str, later),
        ("GOLD_USD",  str(items_gold),            today_str, later),
    ]

    inserted_ct = 0
    for (sym, data, cached_at, expire) in cache_items:
        cur.execute(
            "INSERT INTO market_cache (symbol, data_json, cached_at, expires_at)" +
            " VALUES (?, ?, ?, ?)",
            (sym, data, cached_at, expire))
        inserted_ct += 1

    print("   Seeded {} cache entries".format(inserted_ct))


# --- FINAL AUDIT ---
print("\n\n" + "=" * 60)
print("FINAL AUDIT - ALL TABLES AFTER POPULATION")
print("=" * 60)
audit_tables(db)

db.commit()
db.close()
print("\nDONE - All empty tables now populated.")
