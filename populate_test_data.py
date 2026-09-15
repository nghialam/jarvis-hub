#!/usr/bin/env python3
"""Populate empty/minimal DB tables in jarvis.db with realistic test data."""
import sqlite3
import random
import json
from datetime import datetime, timedelta

DB_PATH = '/Users/nghialam/jarvis-hub/knowledge/jarvis.db'
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

now = datetime.now()
tickers = ['VIC', 'VCB', 'TCB', 'MBB', 'VPB', 'ACB', 'HDB', 'MB', 'SHB', 'CTG',
           'FPT', 'VHM', 'PNJ', 'MWG', 'GVR', 'HPG', 'VNM', 'SSI', 'HSG', 'STB']
company_names = ['Vingroup', 'Vietinbank', 'Techcombank', 'MB Bank', 'VP Bank',
                 'ACB', 'HDBank', 'Military Bank', 'SHB', 'CT Bank',
                 'FPT Corp', 'VHM Real Estate', 'PNJ Jewelry', 'Mo Form',
                 'Gas PetroVietnam', 'Hoa Phat Group', 'Viet Nam Rice',
                 'SSI Securities', 'HSG Steel', 'STB Bank']
categories = ['market', 'technical', 'fundamental', 'news', 'macro', 'sector']
tags_list = ['VNIndex', 'banking', 'real estate', 'tech', 'energy', 'retail',
             'infrastructure', 'FMCG', 'logistics', 'telecom']
alert_severities = ['low', 'medium', 'high', 'critical']
alert_types = ['price_alert', 'volume_spike', 'technical_breakout', 'news_alert']
entity_types = ['stock', 'sector', 'index', 'company']
evaluation_names = ['VNIndex Daily', 'Banking Sector', 'Real Estate', 'Tech Stocks',
                    'VN30 Momentum', 'Midcap Growth', 'Large Cap Value']
transaction_types = ['buy', 'sell']
research_status_values = ['queued', 'processing', 'completed', 'failed']
signal_types = ['RSI_OVERBOUGHT', 'RSI_OVERSOLD', 'MACD_CROSS', 'BOLLinger squeeze',
                'volume_spike', 'breakout', 'breakdown']
log_actions = ['cron_run', 'api_call', 'db_query', 'cache_hit', 'cache_miss', 'error']

print("=== POPulating test data ===")

# 1. alerts (0 rows)
print("\n1. Inserting alerts...")
alert_templates = [
    (1, 'VIC', 200000),
    (1, 'VCB', 57000),
    (1, 'FPT', 100000),
    (1, 'HPG', 25000),
    (1, 'VNM', 60000),
    (1, 'SSI', 26000),
    (1, 'HSG', 17000),
    (1, 'STB', 31000),
    (1, 'VPB', 42000),
    (1, 'ACB', 43000),
]
for user_id, ticker, threshold in alert_templates:
    cur.execute("""
        INSERT INTO alerts (user_id, ticker, threshold, active)
        VALUES (?, ?, ?, ?)
    """, (user_id, ticker, threshold, 1))

# 2. entity_mentions (0 rows)
print("2. Inserting entity mentions...")
for i in range(20):
    cur.execute("""
        INSERT INTO entity_mentions (article_id, ticker, company_name, mention_type)
        VALUES (?, ?, ?, ?)
    """, (random.randint(1, 45), random.choice(tickers),
          random.choice(company_names), random.choice(entity_types)))

# 3. market_cache (0 rows)
print("3. Inserting market cache...")
for ticker in tickers[:10]:
    cur.execute("""
        INSERT INTO market_cache (symbol, data_json, cached_at, expires_at)
        VALUES (?, ?, ?, ?)
    """, (ticker, json.dumps({"close": random.randint(10000, 200000), "volume": random.randint(1000000, 10000000)}),
          now.isoformat(), (now + timedelta(hours=2)).isoformat()))

# 4. market_evaluation (0 rows)
print("4. Inserting market evaluation...")
for name in evaluation_names:
    cur.execute("""
        INSERT INTO market_evaluation (date, evaluation, summary, generated_at)
        VALUES (?, ?, ?, ?)
    """, (now.strftime('%Y-%m-%d'),
          random.choice(['bullish', 'neutral', 'bearish']),
          f"Evaluation of {name} for today",
          now.isoformat))

# 5. news_enrichment (0 rows)
print("5. Inserting news enrichment...")
for i in range(15):
    cur.execute("""
        INSERT INTO news_enrichment (article_id, llm_summary_text, key_tickers_extracted, sentiment_explicit, impact_on_vn, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (random.randint(1, 64),
          f"Enriched summary for news article {i+1}",
          json.dumps(random.sample(tickers, k=2)),
          random.choice(['positive', 'negative', 'neutral']),
          random.choice(['positive impact', 'neutral impact', 'negative impact']),
          now.isoformat))

# 6. research_items (0 rows)
print("6. Inserting research items...")
research_topics = [
    ("https://example.com/banking-q3", "Banking sector Q3 outlook", "Analysis of banking sector performance",
     "Detailed analysis of banking sector Q3 2026", "analyst1", "2026-08-15", "2026-08-15",
     "banking,sector", "completed"),
    ("https://example.com/real-estate", "Real estate policy impact", "Impact of new real estate policies",
     "Analysis of new real estate policies", "analyst2", "2026-08-14", "2026-08-14",
     "real estate,policy", "completed"),
    ("https://example.com/tech", "Tech stock valuation", "Valuation analysis of tech stocks",
     "Tech stock valuation report", "analyst3", "2026-08-13", "2026-08-13",
     "tech,valuation", "processing"),
    ("https://example.com/energy", "Energy sector trends", "Energy sector trend analysis",
     "Energy sector trends report", "analyst1", "2026-08-12", "2026-08-12",
     "energy,trends", "queued"),
    ("https://example.com/fmcg", "FMCG consumer spending", "FMCG consumer spending analysis",
     "FMCG consumer spending report", "analyst2", "2026-08-11", "2026-08-11",
     "FMCG,consumer", "queued"),
]
for source_url, title, summary, content, author, published_at, research_date, tags, status in research_topics:
    cur.execute("""
        INSERT INTO research_items (source_url, title, summary, content, author, published_at, research_date, tags, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_url, title, summary, content, author, published_at, research_date, tags, status,
          now.isoformat(), now.isoformat))

# 7. backlog_tasks (0 rows)
print("7. Inserting backlog tasks...")
backlog_items = [
    (None, "HUB01 - Oollama connection", "Fix Oollama API connection", "P1", "In Progress", 4.0, "Oollama not responding", None, None),
    (None, "HUB02 - Cache refresh", "Implement cache TTL mechanism", "P1", "In Progress", 2.0, "Cache stale", None, None),
    (None, "HUB03 - Route 404s", "Register missing Flask routes", "P2", "Open", 3.0, "4 routes not registered", None, None),
    (None, "HUB04 - Page 404s", "Add dashboard/admin pages", "P2", "Open", 2.0, "2 pages missing", None, None),
    (None, "HUB05 - DB data thin", "Populate tables with real data", "P3", "Open", 6.0, "Tables need real data", None, None),
    (None, "HUB06 - Syntax error", "Fix _fix_tier2.py line 35", "P3", "Open", 1.0, "Escaped quote syntax error", None, None),
    (None, "S02 - Namespace normal", "Audit opencl*/finance* refs", "P1", "Open", 2.0, "Namespace cleanup", None, None),
    (None, "C04 - Regression QA", "Weekly verification", "P2", "Open", 1.0, "Keep running", None, None),
    (None, "CTX01 - Context overflow", "Monitor LLM tuning", "P2", "Open", 2.0, "LCM tuning", None, None),
    (None, "M01 - Health cron", "Add /health cron checker", "P2", "Open", 1.0, "Health monitoring", None, None),
    (None, "H01 - Bloat cleanup", "Prune old .py files", "P2", "Open", 3.0, "Codebase cleanup", None, None),
    (None, "CRON01 - Cron timeout", "Migrate to 27b-mxfp8", "P2", "Open", 2.0, "35b too slow", None, None),
    (None, "AI01 - Multimodal input", "Vision pipeline", "P3", "Open", 4.0, "Vision variant", None, None),
    (None, "AI02 - vnstock ModuleError", "Fix PYTHONPATH", "P1", "Open", 2.0, "10 occurrences", None, None),
    (None, "AI03 - Connection error", "Handle network errors", "P1", "Open", 3.0, "8 occurrences", None, None),
    (None, "AI04 - Invalid reasoning", "Validate input params", "P2", "Open", 1.0, "4 occurrences", None, None),
]
for research_item_id, title, description, priority, status, estimated_hours, notes, completed_at, updated_at in backlog_items:
    cur.execute("""
        INSERT INTO backlog_tasks (research_item_id, title, description, priority, status, estimated_hours, notes, created_at, completed_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (research_item_id, title, description, priority, status, estimated_hours, notes,
          now.isoformat(), completed_at, updated_at))

# 8. portfolio_transactions (1 row - need more)
print("8. Inserting portfolio transactions...")
for i in range(10):
    idx = random.randint(0, len(tickers)-1)
    cur.execute("""
        INSERT INTO portfolio_transactions (symbol, name, action, quantity, price, txn_date, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (tickers[idx], company_names[idx], random.choice(transaction_types),
          random.randint(100, 1000), round(random.uniform(10000, 200000), 0),
          (now - timedelta(days=random.randint(1, 90))).strftime('%Y-%m-%d'),
          f"Transaction {i+1}",
          (now - timedelta(days=random.randint(1, 90))).isoformat))

# 9. recommendations (1 row - need more)
print("9. Inserting recommendations...")
recommendations = [
    ("run_001", "VIC - Strong Buy", "Vingroup shows strong fundamentals with real estate recovery",
     "VIC fundamentals are strong. Real estate segment recovering. Target: 210,000 VND.", "VN Index", "buy", "high"),
    ("run_002", "VCB - Hold", "Vietinbank stable banking sector performance",
     "VCB is stable. Banking sector outlook neutral. Target: 58,000 VND.", "VN Index", "hold", "medium"),
    ("run_003", "FPT - Buy", "FPT Corp has tech growth potential",
     "FPT tech growth strong. IT sector expanding. Target: 115,000 VND.", "VN Index", "buy", "high"),
    ("run_004", "HPG - Sell", "Hoa Phat overvalued at current levels",
     "HPG overvalued. Steel demand slowing. Target: 24,000 VND.", "VN Index", "sell", "medium"),
    ("run_005", "VNM - Hold", "Viet Nam Rice stable FMCG player",
     "VNM stable. FMCG sector steady. Target: 60,500 VND.", "VN Index", "hold", "low"),
    ("run_006", "SSI - Buy", "SSI Securities brokerage sector recovery",
     "SSI brokerage recovering. Market volume up. Target: 28,000 VND.", "VN Index", "buy", "high"),
    ("run_007", "HSG - Buy", "HSG Steel demand increasing",
     "HSG steel demand up. Infrastructure spending rising. Target: 19,000 VND.", "VN Index", "buy", "medium"),
    ("run_008", "STB - Hold", "STB neutral outlook",
     "STB performance neutral. Banking sector mixed. Target: 31,500 VND.", "VN Index", "hold", "low"),
    ("run_009", "VPB - Buy", "VPB banking sector strength",
     "VPB banking sector strong. Credit growth up. Target: 45,000 VND.", "VN Index", "buy", "high"),
    ("run_010", "ACB - Hold", "ACB stable performance",
     "ACB performance stable. Banking sector steady. Target: 43,500 VND.", "VN Index", "hold", "medium"),
]
for run_id, heading, detail_markdown, source_topic, recommendation_type, confidence_level in recommendations:
    cur.execute("""
        INSERT INTO recommendations (run_id, heading, detail_markdown, source_topic, recommendation_type, confidence_level, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (run_id, heading, detail_markdown, source_topic, recommendation_type, confidence_level,
          now.isoformat))

# 10. activity_log (4 rows - need more)
print("10. Inserting activity logs...")
for i in range(20):
    cur.execute("""
        INSERT INTO activity_log (timestamp, command, args, status, summary, duration_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ((now - timedelta(hours=random.randint(1, 168))).isoformat,
          random.choice(log_actions),
          random.choice(tickers),
          random.choice(['success', 'failed', 'pending']),
          f"Activity log entry for {random.choice(tickers)}",
          random.randint(100, 10000)))

conn.commit()

# Verify
print("\n=== VERIFICATION ===")
for table in ['alerts', 'entity_mentions', 'market_cache', 'market_evaluation',
              'news_enrichment', 'research_items', 'backlog_tasks',
              'portfolio_transactions', 'recommendations', 'activity_log']:
    cur.execute(f"SELECT COUNT(*) as cnt FROM [{table}]")
    count = cur.fetchone()['cnt']
    print(f"  {table}: {count}")

conn.close()
print("\nDone!")
