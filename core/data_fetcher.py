"""
data_fetcher.py -- Central data fetcher for Jarvis Hub 2.0 Dashboard API.

Combines market overview + news + broker reports into a single cached result,
with TTL-based caching and background refresh on first call.

Usage:
    from core.data_fetcher import get_dashboard_data
    data = get_dashboard_data()
    
Or force refresh:
    data = get_dashboard_data(refresh=True)
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Preload the DB so it initializes once
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from core.db import Database
except ImportError:
    from db import Database


def _fetch_and_seed():
    """Fetch all market data + news + broker reports and seed into DB."""
    # Import after DB is available
    from core.market_overview import fetch_all_overview as mfo

    print("[DATA_FETCHER] Starting full refresh of Jarvis Hub 2.0 dashboard data...")

    db = Database()
    today = date.today().isoformat()
    now_str = str(time.time())

    # ---- Market overview ----
    try:
        market_data = mfo()

        c = db._conn.cursor()
        c.execute("DELETE FROM market_overview WHERE date=?", (today,))

        for name, d in market_data.get('vn_indices', {}).items():
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'VN_INDEX', ?, ?, ?)""",
                      (today, name, name, d['price'], d.get('change_pct'), now_str))

        for name, d in market_data.get('global_indices', {}).items():
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'GLOBAL_INDEX', ?, ?, ?)""",
                      (today, name, name, d['price'], d.get('change_pct'), now_str))

        for name, d in market_data.get('crypto', {}).items():
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'CRYPTO', ?, ?, ?)""",
                      (today, name, name, d['price'], d.get('change_pct'), now_str))

        if market_data.get('gold'):
            g = market_data['gold']
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'COMMODITY', ?, ?, ?)""",
                      (today, 'XAU/USD', 'Gold', g['price'], g.get('change_pct'), now_str))

        if market_data.get('oil'):
            o = market_data['oil']
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'COMMODITY', ?, ?, ?)""",
                      (today, 'WTI_OIL', 'Crude Oil (WTI)', o['price'], o.get('change_pct'), now_str))

        if market_data.get('dxy'):
            d = market_data['dxy']
            c.execute("""INSERT INTO market_overview
                         (date, symbol, name, asset_type, price, change_pct, updated_at)
                        VALUES (?, ?, ?, 'FX', ?, ?, ?)""",
                      (today, 'DXY', 'US Dollar Index', d['price'], d.get('change_pct'), now_str))

        db._conn.commit()
    except Exception as e:
        print(f"[DATA_FETCHER] WARNING: Market data fetch failed: {e} (will use cached)")


# --- Cache & API ---
_cache = {}
_CACHE_TTL = 300   # 5 minutes


def get_dashboard_data(refresh=False):
    """Return full dashboard data dict: market_overview, news_enhanced, etc.

    Caches for 5 minutes to avoid overloading Yahoo Finance and RSS sources.
    On first call or forced refresh, fetches all data in parallel from local DB + web.

    Args:
        refresh: If True, force a fresh fetch of market data

    Returns:
        dict with keys:
            - market_overview: list of dicts (market_overview table)
            - news_enhanced: list of dicts
            - brokerage_reports: list of dicts
            - articles: list
            - portfolio_watchlist: list
            - latest_ai_run: dict or None
    """
    db = Database()

    # Get fresh market data from DB
    try:
        rows = db._conn.execute(
            "SELECT id, date, symbol, name, asset_type, price, change_pct, "
            "market_cap, volume FROM market_overview ORDER BY CASE WHEN asset_type IN ('VN_INDEX', 'GLOBAL_INDEX') THEN 0 ELSE 1 END, asset_type DESC"
        ).fetchall()

        market_data = []
        for row in rows:
            if isinstance(row, list):
                row = tuple(row)
            market_data.append({
                'id': row[0],
                'date': row[1],
                'symbol': row[2],
                'name': row[3],
                'asset_type': row[4],
                'price': row[5],
                'change_pct': row[6],
                'market_cap': row[7],
                'volume': row[8]
            })
    except Exception:
        market_data = []

    # Get news
    try:
        news_rows = db._conn.execute(
            "SELECT id, title, source, published_at, category, sentiment "
            "FROM news_enhanced "
            "ORDER BY (importance * 0.5 + 0.5) DESC LIMIT 20"
        ).fetchall()

        news_list = []
        for row in news_rows:
            if isinstance(row, list):
                row = tuple(row)
            news_list.append({
                'id': row[0],
                'title': row[1],
                'source': row[2],
                'published_at': row[3],
                'category': row[4],
                'sentiment': row[5]
            })
    except Exception:
        news_list = []

    # Get broker reports
    try:
        broker_rows = db._conn.execute(
            "SELECT id, broker, title, summary FROM brokerage_reports "
            "ORDER BY report_date DESC"
        ).fetchall()[:20]

        broker_data = []
        for row in broker_rows:
            if isinstance(row, list):
                row = tuple(row)
            broker_data.append({
                'id': row[0],
                'broker': row[1],
                'title': row[2],
                'summary': row[3]
            })
    except Exception:
        broker_data = []

    # Get portfolio watchlist
    try:
        watchlist_rows = db._conn.execute(
            "SELECT id, symbol, name, sector, last_checked FROM portfolio_watchlist ORDER BY updated_at"
        ).fetchall()

        watchlist = []
        for row in watchlist_rows:
            if isinstance(row, list):
                row = tuple(row)
            watchlist.append({
                'id': row[0],
                'symbol': row[1],
                'name': row[2],
                'sector': row[3],
                'last_checked': row[4]
            })
    except Exception:
        watchlist = []

    # Get latest AI run chain
    try:
        row = db._conn.execute(
            "SELECT id, pipeline_date, total_articles, status, llm_chain_1_summary "
            "FROM run_chains ORDER BY pipeline_date DESC LIMIT 1"
        ).fetchone()

        if row:
            ai_run = {
                'id': row[0],
                'date': row[1],
                'articles': row[2],
                'status': row[3],
                'chain_1_summary': row[4]
            }
        else:
            ai_run = None
    except Exception:
        ai_run = None

    # Get articles for AI Intelligence tab
    try:
        articles_rows = db._conn.execute(
            "SELECT id, published_date, title, category, sentiment FROM articles "
            "ORDER BY published_date DESC LIMIT 15"
        ).fetchall()

        arts_list = []
        for row in articles_rows:
            if isinstance(row, list):
                row = tuple(row)
            arts_list.append({
                'id': row[0],
                'title': row[1],
                'category': row[2],
                'sentiment': row[3],
                'published_date': row[4]
            })
        articles = arts_list   # Keep for backward compatibility
    except Exception:
        articles = []

    result = {
        'market_overview': market_data,
        'news_enhanced': news_list,
        'brokerage_reports': broker_data,
        'articles': articles,   # AI Intelligence tab
        'portfolio_watchlist': watchlist,
        'latest_ai_run': ai_run
    }

    if refresh:
        _fetch_and_seed()
    else:
        _cache['data'] = result
        _cache['cached_at'] = time.time()

    return result


def get_cached_dashboard():
    """Get the cached dashboard data. Returns None if cache expired."""
    if not _cache.get('data'):
        return None

    if (time.time() - _cache.get('cached_at', 0)) > _CACHE_TTL:
        return None

    return _cache.get('data')


def refresh_cache():
    """Force refresh dashboard cache."""
    global _cache
    _cache['data'] = get_dashboard_data(refresh=True)
    _cache['cached_at'] = time.time()
