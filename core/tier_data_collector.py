#!/usr/bin/env python3
"""tier_data_collector.py - Tier 1: Raw Data Collection (NO LLM)

Collects live market data, news headlines, and global macro indicators
from multiple sources and stores them in jarvis.db.

Schema targets actual jarvis.db columns:
- market_quotes: ticker, name, exchange, price, pe_ratio, pb_ratio, market_cap, sector, updated_at
- news_articles: headline, source, category, sentiment, relevance_score, published_at, lang
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add vnstock venv to path immediately - prefer hermes-agent venv (vnstock3) if available
for _path in [
    "/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages",
    "/Users/nghialam/jarvis-hub/venv/lib/python3.11/site-packages",
]:
    if Path(_path).exists() and _path not in sys.path:
        sys.path.insert(0, _path)

# Now import normally
try:
    import requests as req
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"[FATAL] Missing dependencies: {e}")
    sys.exit(1)

DB_PATH = str(Path.home() / "jarvis-hub" / "knowledge" / "jarvis.db")


def get_conn(db_path=None):
    """Get database connection."""
    if db_path is None:
        db_path = DB_PATH
    p = Path(db_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_vn_stocks(conn, symbols=None):
    """Fetch VN stock quotes from vnstock and store in market_quotes table."""
    if symbols is None:
        symbols = [
            "VIC", "VCB", "VNM", "VPB", "TCB", "ACB", "MBB", "SSI",
            "FPT", "HPG", "MSN", "GVR",
        ]

    try:
        from vnstock.api.quote import Quote
    except ImportError:
        print("[WARN] vnstock module not available, skipping VN stocks")
        return 0

    VND_MULTIPLIER = 1000
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0

    for sym in symbols:
        try:
            q = Quote(symbol=sym, show_log=False)
            df = q.history(
                symbol=sym,
                start=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                end=today
            )

            if len(df) < 1:
                print(f"     [SKIP] {sym}: no data")
                continue

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            current_close = round(float(latest["close"]) * VND_MULTIPLIER, 0)
            prev_close = round(float(prev["close"]) * VND_MULTIPLIER, 0)

            pct = (current_close - prev_close) / prev_close * 100 if prev_close else 0
            print(f"     [OK] {sym}: price={current_close:,.1f} ({pct:+.1f}%)")
            count += 1

        except Exception as e:
            if sym.startswith(".VNINDEX") or sym.startswith(".VNI30"):
                print(f"     [SKIP] {sym}: Yahoo index format, skip VN stock fetcher")
            continue

    conn.commit()
    print(f"[Tier 1] VN stocks fetched: {count}/{len(symbols)}")
    return count


def _fetch_yahoo_price(conn, sym, name, exchange_type):
    """Helper to fetch a single price from Yahoo Finance."""
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            + "?range=5d&interval=1d"
        )
        r = req.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if r.status_code != 200:
            return False

        data = r.json()
        result_list = data.get("chart", {}).get("result")
        if not result_list:
            return False

        meta = result_list[0].get("meta", {})
        quotes_arr = result_list[0]["indicators"]["quote"][0]
        closes_raw = [p for p in (quotes_arr.get("close") or []) if p is not None]
        latest_close = closes_raw[-1] if closes_raw else meta.get("regularMarketPrice", 0)

        conn.execute(
            "INSERT OR REPLACE INTO market_quotes "
            "(ticker, name, exchange, price, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (sym, name, exchange_type, latest_close),
        )
        print(f"     [OK] {name}: {latest_close:,.2f}")
        return True
    except Exception as e:
        print(f"     [WARN] {name} ({sym}): {e}")
        return False


def fetch_market_indices(conn):
    """Fetch VN indices from Yahoo Finance."""
    indices = {
        ".VNINDEX.VN": "VN-Index",
        ".VNI30.VN": "VNI30",
    }
    count = 0
    for sym, name in indices.items():
        if _fetch_yahoo_price(conn, sym, name, "INDEX"):
            count += 1
    print(f"[Tier 1] VN market indices fetched: {count}/{len(indices)}")
    return count


def fetch_global_indices(conn):
    """Fetch US indices from Yahoo."""
    tickers = {
        "^DJI": "DJIA",
        "^GSPC": "S&P500",
        "^IXIC": "NASDAQ",
    }
    count = 0
    for sym, name in tickers.items():
        if _fetch_yahoo_price(conn, sym, name, "GLOBAL"):
            count += 1
    print(f"[Tier 1] Global indices fetched: {count}/{len(tickers)}")
    return count


def fetch_crypto(conn):
    """Fetch crypto prices from Binance."""
    cryptos = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    count = 0
    for sym in cryptos:
        try:
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym}"
            r = req.get(url, timeout=8)
            if r.status_code == 200:
                data = r.json()
                name = sym.replace("USDT", "")
                conn.execute(
                    "INSERT OR REPLACE INTO market_quotes "
                    "(ticker, name, exchange, price, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (name, name, "CRYPTO", float(data["lastPrice"])),
                )
                print(f"     [OK] {name}: ${float(data['lastPrice']):,.2f}")
                count += 1
            else:
                print(f"     [WARN] Crypto {sym}: status {r.status_code}")
        except Exception as e:
            print(f"     [WARN] Crypto {sym}: {e}")

    conn.commit()
    print(f"[Tier 1] Crypto prices fetched: {count}/{len(cryptos)}")
    return count


def fetch_commodities(conn):
    """Fetch Gold & Oil from Yahoo Finance."""
    commodities = {"GC=F": "Gold", "CL=F": "Oil"}
    count = 0
    for sym, name in commodities.items():
        if _fetch_yahoo_price(conn, sym, name, "COMMODITY"):
            count += 1
    print(f"[Tier 1] Commodities fetched: {count}/{len(commodities)}")
    return count


def fetch_news_headlines(conn, max_pages=3):
    """Fetch news from VN RSS feeds and save to news_articles."""
    feeds = [
        ("VNExpress", "https://vnexpress.vn/rss/kinh-te.rss"),
        ("CafeF", "https://cafef.vn/Chungkhoan-c3.rss"),
        ("Vietstock", "https://feed.stockbiz.vn/vn/hose/feed.xml"),
    ]

    count = 0
    for source, url in feeds:
        try:
            r = req.get(url, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "xml")
                items = soup.find_all("item")[:max_pages * 3]

                for item in items:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_date_elem = item.find("pubDate")

                    if not title_elem:
                        continue

                    title = str(title_elem.get_text())
                    pub_date = (
                        pub_date_elem.get_text().strip()
                        if pub_date_elem else datetime.now().isoformat()
                    )

                    if "Download" in title:
                        link_text = link_elem.get_text() if link_elem else ""
                        if ".pdf" in link_text:
                            continue

                    conn.execute(
                        "INSERT OR REPLACE INTO news_articles "
                        "(headline, source, category, published_at, lang, relevance_score) "
                        "VALUES (?, ?, 'VN Market', ?, 'vn', 85)",
                        (title[:200], source, pub_date),
                    )
                    count += 1
            else:
                print(f"     [WARN] Feed {source}: status {r.status_code}")
        except Exception as e:
            print(f"     [WARN] Feed {source}: {e}")

    conn.commit()
    print(f"[Tier 1] News headlines collected: {count}")
    return count


def save_data_snapshot(conn, run_date=None):
    """Save a comprehensive data snapshot for Tier 2 to reference."""
    if not run_date:
        run_date = datetime.now().strftime("%Y-%m-%d")

    quote_rows = conn.execute("SELECT * FROM market_quotes ORDER BY ticker").fetchall()
    quotes_data = []
    for row in quote_rows:
        d = dict(row)
        d.pop("id", None)
        d.pop("updated_at", None)
        quotes_data.append(d)

    news_ids = conn.execute("SELECT id FROM news_articles ORDER BY published_at DESC LIMIT 50").fetchall()
    article_ids = [r["id"] for r in news_ids]

    snapshot = {
        "date": run_date,
        "collected_at": datetime.now().isoformat(),
        "market_quotes": quotes_data,
        "news_article_ids": article_ids,
        "total_stocks": len(quotes_data),
        "total_news_articles": len(article_ids),
    }

    conn.execute(
        "INSERT OR REPLACE INTO daily_ohlcv (ticker, date, volume) VALUES (?, ?, ?)",
        ("SNAPSHOT_META", run_date, json.dumps(snapshot)),
    )

    return snapshot


def run_collection(db_path=None):
    """Execute full Tier 1 data collection pipeline."""
    conn = get_conn(db_path)

    today = datetime.now().strftime("%Y-%m-%d")
    run_start = datetime.now()

    total_count = {
        "stocks": 0, "indices": 0, "news": 0,
        "crypto": 0, "commodities": 0,
    }

    print(f"\n{'=' * 60}")
    print(f"[Tier 1] Starting data collection for run: {today}")
    print(f"{'=' * 60}\n")

    # Phase 1: VN Stocks (highest priority)
    symbols = [
        "VIC", "VCB", "VNM", "VPB", "TCB", "ACB", "MBB", "SSI",
        "FPT", "HPG", "MSN", "GVR",
    ]
    total_count["stocks"] = fetch_vn_stocks(conn, symbols=symbols)

    # Phase 2: VN & Global Indices
    total_count["indices"] += fetch_market_indices(conn)
    total_count["indices"] += fetch_global_indices(conn)

    # Phase 3: Crypto
    total_count["crypto"] = fetch_crypto(conn)

    # Phase 4: Commodities
    total_count["commodities"] = fetch_commodities(conn)

    # Phase 5: News headlines
    total_count["news"] = fetch_news_headlines(conn)

    conn.commit()

    elapsed = datetime.now() - run_start
    print(f"\n{'=' * 60}")
    print(f"[Tier 1] Collection complete in {elapsed.total_seconds():.1f}s")
    print(f"         VN Stocks:              {total_count['stocks']}")
    print(f"           Market Indices:         {total_count['indices']}")
    print(f"          Crypto:                 {total_count['crypto']}")
    print(f"             Commodities:          {total_count['commodities']}")
    print(f"              News Headlines:       {total_count['news']}")
    print(f"{'=' * 60}\n")

    snapshot = save_data_snapshot(conn, today)

    stock_count = len(conn.execute("SELECT ticker FROM market_quotes WHERE exchange = 'HOSE'").fetchall())
    index_count = len(conn.execute("SELECT ticker FROM market_quotes WHERE exchange IN ('INDEX', 'GLOBAL')").fetchall())
    news_count = len(conn.execute("SELECT id FROM news_articles").fetchall())

    print(f"[Tier 1] Final DB state:")
    print(f"{stock_count} VN stocks")
    print(f"{index_count} indices/macro data points")
    print(f"          News articles:          {news_count}")

    return snapshot, total_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Jarvis Hub Tier 1: Raw Data Collector (no LLM)"
    )
    parser.add_argument("--date", help="Override run date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.date:
        print(f"[Tier 1] Running for date override: {args.date}")

    snapshot, counts = run_collection()
    print("\n[Success] Tier 1 completed. Ready for Tier 2 analysis.")
