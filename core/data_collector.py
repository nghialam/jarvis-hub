#!/usr/bin/env python3
"""
Tier 1 Data Collector - Jarvis Hub 2.0
=======================================
Fetches ALL raw market data + RSS news WITHOUT LLM calls.
Stores directly into jarvis_hub.db for dashboard rendering.

Architecture:
    - Runs standalone (called by cron, no Flask needed)
    - Fetches in parallel where possible
    - Heuristic sentiment only (pattern matching), NO LLM
    - Results persisted to DB tables: articles, news_enhanced, market_quotes,
    daily_ohlcv, price_history, market_overview, meta

Usage:
    cd /Users/nghialam/jarvis-hub && python3 core/data_collector.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# When running from project root: 'python3 core/data_collector.py' -> sys.path includes 'core/'
try:
    from db import Database
except ImportError:
    from core.db import Database


# --- CONSTANTS ---

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge", "jarvis.db")

BULLISH_PATTERNS = [
    "tang", "lai", "khoi sac", "bung no", "tang manh", "vuot",
    "loi nhuan", "doanh thu", "trong diem", "mua them", "nap them",
    "phat hanh co phieu", "chia co Tuc", "mua vao", "vuot trai",
    "tang truong", "mo rong", "dau tu", "hop dong", "vuot muc",
    "tich luy", "lai gop", "lai tang", "doanh thu thuan",
    "xuat khau", "phuc hoi", "tang gia", "tot", "tot hon",
    "khang dinh", "thuan loi", "vuot du doan", "khoi diem",
    "buc pha", "lai suat tang", "fpi", "fdi", "dong von",
    "so lai", "loi nhuan cao", "doanh so tang", "top dau",
    "von hoa tang", "khoi ngoai mua", "tang diem", "phuc hoi manh",
    "mua vong", "don song", "hung thu", "nang luc", "dot pha",
]

BEARISH_PATTERNS = [
    "giam", "rot", "sut giam", "that bai", "thua lo", "roi ro",
    "dinh chi", "rut lui", "rut tien", "suy giam", "roi tu do",
    "pha san", "sup dot", "giam gia", "rao can", "cang thang",
    "sai sot", "vi pham", "bi phat", "suy thoa", "so lo",
    "so lo", "no", "khong cao", "thua", "sut", "dong bang",
    "dung yen", "bat on", "khung hoang", "sap nhap", "doi",
    "ban thao", "rut von", "dong von chay ra", "khoi ngoai ban",
    "ap luc giam", "roi sau", "sap", "thatchat", "tang no",
    "roi ro cao", "de doa", "to cao", "bi dieu tra", "lam phat",
    "dinh chi giao dich", "canh bao", "phoi nhiet", "that thot",
    "xam nhap", "bat giu", "chot loi", "ban vong", "thap ky luc",
    "te nhat", "cao ky luc", "day", "nghiem trong", "tham hoa",
]

SECTOR_TAGS = {
    "ngan hang": ["ngan hang", "bank", "acb", "vcb", "vpb", "tcb", "mb", " bid", "ctg", "tpb", "hdb", "stb", "vib"],
    "bat dong san": ["bat dong san", "real estate", "vhm", "vic", "nha", "hut"],
    "nang luong": ["nang luong", "energy", "pow", "gas", "dcs", "tpp"],
    "cong nghe": ["cong nghe", "technology", "fpt", "gvr", "hsg"],
    "chung khoan": ["chung khoan", "brokerage", "ssi", " vnd", "vps"],
    "thuc pham": ["thuc pham", "fmcb", "vnm", "dhg", "msn"],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}

FEED_SOURCES = [
    {"name": "Cafef Doanh nghiep", "url": "https://cafef.vn/doanh-nghiep.rss", "category": "vn-stock", "priority": 1},
    {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "category": "business", "priority": 2},
    {"name": "VnExpress Kinh te", "url": "https://vnexpress.net/rss/kinh-te.rss", "category": "economy", "priority": 2},
]


# --- UTILITIES ---

def heuristic_sentiment(title, summary):
    """Heuristic sentiment scoring. Layer 1 only, NO LLM."""
    text = (title + " " + summary).lower()
    bull = sum(1 for w in BULLISH_PATTERNS if w in text)
    bear = sum(1 for w in BEARISH_PATTERNS if w in text)
    if bull > bear and bull >= 1:
        label = "TICH_CUC"
    elif bear > bull and bear >= 1:
        label = "TIEU_CUC"
    else:
        label = "TRUNG_LAP"
    return label, bull, bear


def categorize_article(article):
    """Category by keyword matching. NO LLM."""
    text = (article["title"] + " " + article.get("summary_raw", "")).lower()
    max_score = 0
    best_sector = "general"
    for sector, keywords in SECTOR_TAGS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > max_score:
            max_score = score
            best_sector = sector
    return best_sector


def fetch_json(url, timeout=8):
    """Fetch JSON from URL. Returns None on any failure."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except Exception as e:
        print(f"   [FETCH] {url} FAILED: {e}")
        return None


def fetch_rss_feed(url, name, category, priority, seen_links, limit_per_source=5):
    """Fetch a single RSS feed. Returns list of article dicts."""
    try:
        import feedparser
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            return []

        articles = []
        for entry in feed.entries[:limit_per_source]:
            link = entry.get("link", "") or entry.get("id", "")
            if not link or link in seen_links:
                continue

            import html as html_module
            title = entry.get("title", "").strip()
            summary = html_module.unescape(entry.get("summary", "")).strip()

            pub_parsed = entry.get("published_parsed")
            is_recent = False
            if pub_parsed:
                pub_dt = datetime(*pub_parsed[:6])
                hours_old = (datetime.now() - pub_dt).total_seconds() / 3600
                is_recent = hours_old <= 48

            articles.append({
                "title": title,
                "link": link,
                "summary_raw": summary.replace("<[^>]+>", ""),
                "published": entry.get("published", entry.get("updated", "")),
                "source": name,
                "category": category,
                "priority": priority,
                "is_recent": is_recent,
                "fetched_at": datetime.now().isoformat(),
            })
            seen_links.add(link)
        return articles
    except Exception as e:
        print(f"   [RSS] {name} FAILED: {e}")
        return []


# --- DATA FETCHERS (TIER 1 - NO LLM) ---

def fetch_rss_articles():
    """Fetch RSS feeds from all sources."""
    articles = []
    seen_links = set()

    for source in FEED_SOURCES:
        fetched = fetch_rss_feed(
            source["url"], source["name"],
            source["category"], source["priority"],
            seen_links, limit_per_source=5
        )
        articles.extend(fetched)

    # Apply heuristic sentiment + categorization (no LLM)
    for a in articles:
        sent_label, bull_c, bear_c = heuristic_sentiment(a["title"], a.get("summary_raw", ""))
        sent_map = {
            "TICH_CUC": "\U0001f7e2 tich cuc",
            "TIEU_CUC": "\U0001f534 tieu cuc",
        }
        a["sentiment_layer1"] = sent_map.get(sent_label, "\U0001f7e1 trung lap")
        a["sentiment_class"] = sent_label
        a["bull_count"] = bull_c
        a["bear_count"] = bear_c
        a["sector"] = categorize_article(a)

    articles.sort(key=lambda ax: (ax.get("priority", 2), not ax["is_recent"]))
    return articles


def fetch_vn_indices():
    """Fetch VN-Index from Yahoo Finance."""
    try:
        data = fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/^VNINDEX.VN")
        if data and data.get("chart", {}).get("result"):
            meta = data["chart"]["result"][0].get("meta", {})
            prev = float(meta.get("previousClose", 1))
            p = float(meta.get("regularMarketPrice", 0))
            return {
                "price": round(p, 2),
                "change": round(p - prev, 2),
                "change_pct": round((p - prev) / max(prev, 1) * 100, 2),
                "prev_close": round(prev, 2),
            }
    except Exception as e:
        print(f"   [INDICES] VN-Index FAILED: {e}")
    return None


def fetch_single_index(symbol, timeout=8):
    """Fetch a single market index from Yahoo Finance."""
    try:
        data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN", timeout)
        if data and data.get("chart", {}).get("result"):
            meta = data["chart"]["result"][0].get("meta", {})
            prev = float(meta.get("previousClose", 1))
            p = float(meta.get("regularMarketPrice", 0))
            return {
                "price": round(p, 2),
                "change_pct": round((p - prev) / max(prev, 1) * 100, 2),
                "prev_close": round(prev, 2),
            }
    except Exception:
        pass
    return None


def fetch_global_indices():
    """Fetch global market indices in parallel."""
    name_map = {
        "^GSPC": ("S&P 500", "US"),
        "^DJI": ("Dow Jones", "US"),
        "^IXIC": ("NASDAQ", "US"),
        "^N225": ("Nikkei 225", "Asia"),
        "^HSI": ("Hang Seng", "Asia"),
        "^KS11": ("KOSPI", "Asia"),
        "^GDAXI": ("DAX", "Europe"),
        "^FTSE": ("FTSE 100", "Europe"),
    }

    indices = {"vn_indices": {}, "global_indices": {}}

    # VN-Index separate
    vn_data = fetch_vn_indices()
    if vn_data:
        indices["vn_indices"]["VN-Index"] = vn_data

    # Global in parallel
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {}
        for sym, name in name_map.items():
            f = ex.submit(fetch_single_index, sym)
            futures[f] = name
        for f in as_completed(futures):
            try:
                display_name, region = name_map[futures[f]]
                data = f.result()
                if data:
                    indices["global_indices"][display_name] = {**data, "region": region}
            except Exception:
                pass

    return indices


def fetch_crypto(symbols=None):
    """Fetch crypto prices from Binance."""
    sym_map = {
        "BTC": "BTCUSDT", "ETH": "ETHUSDT",
        "SOL": "SOLUSDT", "BNB": "BNBUSDT",
    }
    symbols = symbols or ["BTC", "ETH", "SOL"]
    results = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        for s in symbols:
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym_map.get(s, s+'USDT')}"
            f = ex.submit(fetch_json, url)
            futures[f] = s
        for f in as_completed(futures):
            try:
                sym_label = futures[f]
                data = f.result()
                if data and "lastPrice" in data:
                    name_sym = {"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solanas"}.get(sym_label, sym_label)
                    results.append({
                        "symbol": sym_label,
                        "name": name_sym,
                        "price": round(float(data.get("lastPrice", 0)), 2),
                        "change_pct": round(float(data.get("priceChangePercent", 0)), 2),
                        "volume": data.get("quoteVolume"),
                        "high_24h": round(float(data.get("highPrice", 0)), 2),
                        "low_24h": round(float(data.get("lowPrice", 0)), 2),
                        "currency": "USD",
                        "type": "crypto",
                        "fetched_at": datetime.now().isoformat(),
                    })
            except Exception as e:
                sym_label = futures[f]
                print(f"   [CRYPTO] {sym_label} FAILED: {e}")

    return results


def fetch_commodity(target):
    """Fetch gold or oil via Yahoo Finance."""
    candidates = {"GOLD": ["XAU/USD", "GC=F", "GLD", "XAUUSD=X"],
                "OIL":   ["CL=F", "BZ=F"]}
    sym_list = candidates.get(target, [target])

    for sym in sym_list:
        try:
            data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.VN")
            if data and data.get("chart", {}).get("result"):
                meta = data["chart"]["result"][0].get("meta", {})
                price_raw = meta.get("regularMarketPrice")
                 # vnstock returns VN prices in "nghin dong" - multiply by 1000 for actual VND
                price = (float(price_raw) * 1000) if price_raw is not None else None
                prev_close = meta.get("previousClose")
                currency = meta.get("currency", "USD")

                if price and prev_close and float(prev_close) > 0:
                    return {
                        "symbol": sym,
                        "price": round(float(price), 2),
                        "change_pct": round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                        "currency": currency,
                        "type": target.lower(),
                        "fetched_at": datetime.now().isoformat(),
                    }
        except Exception:
            continue
    return None


def fetch_fx_rates():
    """Fetch USD/VND rates from Vietcombank."""
    try:
        req = urllib.request.Request(
            "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="replace")

        import html as html_module
        match = re.search(r'id="currentDataExchange"\s+value="([^"]+)"', html)
        if match:
            raw = html_module.unescape(match.group(1))
            data = json.loads(raw)
            updated = data.get("UpdatedDate", "N/A")
            rate_obj = {"source": "vietcombank", "updated": updated}

            for curr in (data if isinstance(data, dict) else {}).get("Data", []):
                code = curr.get("currencyCode", "")
                if code:
                    rate_obj[code] = {
                        "cash": round(float(curr.get("cash", 0)) / 100, 4),
                        "transfer": round(float(curr.get("transfer", 0)) / 100, 4),
                        "sell": round(float(curr.get("sell", 0)) / 100, 4),
                    }
            return rate_obj
    except Exception as e:
        print(f"   [FX] Vietcombank FAILED: {e}")

    return {"source": "vietcombank", "updated": "ERROR", "USD": {"transfer": 0}}


def fetch_dxy():
    """Fetch US Dollar Index (DXY)."""
    data = fetch_json("https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB")
    if data and data.get("chart", {}).get("result"):
        meta = data["chart"]["result"][0].get("meta", {})
        prev = float(meta.get("previousClose", 0) or 1)
        p = float(meta.get("regularMarketPrice", 0))
        if p > 0:
            return {
                "symbol": "DXY",
                "price": round(p, 3),
                "change_pct": (p - prev) / prev * 100,
                "prev_close": round(prev, 3),
                "fetched_at": datetime.now().isoformat(),
            }
    return None


# --- DB PERSISTENCE (TIER 1 STORES TO DB) ---

def store_articles(db_conn, articles, run_id):
    """Persist RSS articles + enhanced data to DB."""
    cur = db_conn._c()
    now = datetime.now().isoformat()

    for i, art in enumerate(articles):
        try:
            sent_score = max(art.get("bull_count", 0) - art.get("bear_count", 0), -9)
            cur.execute("""
                INSERT OR IGNORE INTO articles 
                    (run_id, publication_date, title, summary_raw, category, sentiment, score, url, order_in_run, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (run_id, art.get("published") or date.today().isoformat(), art["title"],
                art.get("summary_raw", ""), art.get("category", "general"),
                art.get("sentiment_class", "TRUNG_LAP"), sent_score,
                art.get("link", ""), i, now))

            aid = cur.lastrowid

            # Enhance news_enhanced with sentiment + sector
            cur.execute("""
                INSERT OR IGNORE INTO news_enhanced 
                    (article_id, title, summary, content, source, published_at, fetched_at, category, sentiment, sentiment_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (aid, art["title"], art.get("summary_raw", ""), art.get("summary_raw", ""),
                art.get("source", ""), 
                art.get("published") or now, now,
                art.get("sector", "general"),
                art.get("sentiment_class", "TRUNG_LAP"),
                float(max(sent_score, 0))))
        except Exception as e:
            print("[STORE] Article {} insert failed: {}".format(i+1, e))

    db_conn._conn.commit()
    print(f"    [STORE] Saved {len(articles)} articles + news_enhanced entries")


def store_market_quotes(db_conn, indices_data, crypto, gold, oil, fx):
    """Persist market data to DB tables."""
    cur = db_conn._c()
    today = date.today().isoformat()

    # Market quotes - VN indices + crypto
    watchlist_symbols = ["MBB", "ACB", "VPB", "STB", "VHM", "VIC", "MSN", "FPT"]
    vn_idx_data = indices_data.get("vn_indices", {}).get("VN-Index", {})

    for sym in watchlist_symbols:
        cur.execute("SELECT COUNT(*) FROM market_quotes WHERE ticker=?", (sym,))
        if cur.fetchone()[0] == 0:
            try:
                   # vnstock fallback for VN stocks
                stock_data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.VN")
                if stock_data and stock_data.get("chart", {}).get("result"):
                    m = stock_data["chart"]["result"][0].get("meta", {})
                    price = float(m.get("regularMarketPrice", 0))
                else:
                    price = 0.0
            except Exception:
                price = 0.0

            cur.execute("""
                INSERT OR IGNORE INTO market_quotes (ticker, name, exchange, price, pe_ratio, updated_at)
                VALUES (?, ?, ?, ?, 0, ?)
            """, (sym, sym, "HOSE", price, today))

    # Crypto quotes
    for c in crypto:
        existing = cur.execute("SELECT COUNT(*) FROM market_overview WHERE symbol=?", (c["symbol"],)).fetchone()[0]
        if existing == 0:
            cur.execute("""
                INSERT INTO market_overview (date, symbol, name, asset_type, price)
                VALUES (?, ?, ?, 'crypto', ?)
            """, (today, c["symbol"], c.get("name", c["symbol"]), c.get("price", 0)))

    # Gold + DXY + Oil
    for commodity in [gold]:
        if commodity and "GOLD" in commodity.get("symbol", ""):
            existing = cur.execute("SELECT COUNT(*) FROM market_overview WHERE symbol=?", ("GOLD_USD",)).fetchone()[0]
            if existing == 0:
                cur.execute("""
                    INSERT INTO market_overview (date, symbol, name, asset_type, price)
                    VALUES (?, 'GOLD_USD', 'Gold Spot USD', 'commodity', ?)
                """, (today, commodity.get("price", 0)))

    dxy_existing = cur.execute("SELECT COUNT(*) FROM market_overview WHERE symbol=?", ("DXY",)).fetchone()[0]
    if dxy_existing == 0:
        try:
            dxy_data = fetch_dxy()
            if dxy_data:
                cur.execute("""
                    INSERT INTO market_overview (date, symbol, name, asset_type, price)
                    VALUES (?, 'DXY', 'US Dollar Index', 'currency', ?)
                """, (today, dxy_data.get("price", 0)))
        except Exception:
            pass

    db_conn._conn.commit()
    print(f"   [STORE] Market quotes + overviews persisted")


def store_exchange_rates(db_conn, fx_data):
    """Persist FX rates into meta table for quick dashboard read."""
    cur = db_conn._c()

    # Store as JSON in meta for quick dashboard read
    existing = cur.execute("SELECT value FROM meta WHERE key='live_fx_rates'").fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO meta (key, value) VALUES ('live_fx_rates', ?)",
            (json.dumps(fx_data),)
        )
    else:
        cur.execute("UPDATE meta SET value=? WHERE key='live_fx_rates'", (json.dumps(fx_data),))

    # Also store individual rates
    usd_data = fx_data.get("USD", {})
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('usd_vnd_transfer', ?)",
                (str(usd_data.get("transfer", 0)),))
    cur.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('usd_vnd_sell', ?)",
                (str(usd_data.get("sell", 0)),))

    db_conn._conn.commit()
    print(f"   [STORE] FX rates saved")


# --- MAIN COLLECTOR PIPELINE ---

def collect_all(run_id=None):
    """Run complete Tier 1 data collection. Returns stats dict."""
    if run_id is None:
        run_id = f"auto-{date.today().isoformat()}"

    print(f"\n{'='*60}")
    print(f"TIER 1 DATA COLLECTOR - run: {run_id}")
    print(f"{'='*60}")

    start = datetime.now()
    db_conn = Database(DB_PATH)
    stats = {"sources": {}, "errors": [], "duration_sec": 0}

    try:
        # Phase 1: RSS articles (parallel fetches within)
        print("\n[PHASE 1] Fetching RSS feeds...")
        articles = fetch_rss_articles()
        stats["sources"]["rss"] = {"articles": len(articles)}

        print("\n[PHASE 1b] Persisting articles to DB...")
        store_articles(db_conn, articles, run_id)

        # Phase 2: Market indices (parallel)
        print("\n[PHASE 2] Fetching market indices + global...")

        def fetch_combined():
            return {
                "indices": fetch_global_indices(),
                "crypto": fetch_crypto(["BTC", "ETH", "SOL"]),
                "gold": fetch_commodity("GOLD"),
                "oil": fetch_commodity("OIL"),
                "fx": fetch_fx_rates(),
                "dxy": fetch_dxy(),
            }

        combined = fetch_combined()
        stats["sources"]["indices"] = len(combined["indices"].get("vn_indices", {})) + len(combined["indices"].get("global_indices", {}))
        stats["sources"]["crypto"] = len(combined["crypto"])

        print("\n[PHASE 2b] Persisting market data to DB...")
        store_market_quotes(db_conn, combined["indices"], combined["crypto"],
                        combined["gold"], combined["oil"], combined["fx"])
        stats["sources"]["market_data"] = "persisted"

        print("\n[PHASE 3] Storing FX rates...")
        store_exchange_rates(db_conn, combined["fx"])
        stats["sources"]["fx"] = "persisted"

        # Update meta with collection timestamp
        db_conn._c().execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_collection', ?)",
            (datetime.now().isoformat(),)
        )
        db_conn._conn.commit()

    except Exception as e:
        print(f"\n[COLLECT] FAILED: {e}")
        stats["errors"].append(str(e))

    elapsed = (datetime.now() - start).total_seconds()
    stats["duration_sec"] = round(elapsed, 2)

    print(f"\n{'='*60}")
    print(f"COLLECTION DONE - {stats['sources']} - {elapsed:.1f}s")
    if stats["errors"]:
        print(f"errors: {stats['errors']}")
    print(f"{'='*60}\n")

    return stats


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    collect_all(run_id)
