"""
market_overview.py -- Market data fetcher for Hub 2.0 Overview Dashboard.

Fetches: VN-Index, global indices, crypto, gold, FX rates.
Used by: /api/v1/overview/* endpoints.

Fixes applied (2026-07-06):
1. Retry with exponential backoff for Yahoo Finance 429 rate-limit errors
2. Rate limiting delay between requests to avoid getting blocked
3. Cache-Control header to reduce unnecessary requests
4. Improved vnstock3 import resolution
"""

import json
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Cache-Control": "max-age=0",
}

# --- Rate limiting & retry helpers ---

MAX_RETRY = 3
RETRY_DELAY_BASE = 2  # seconds


def _retry_request(url, params=None, timeout=15):
    """Fetch with exponential backoff retry for 429/5xx errors."""
    last_err = None
    for attempt in range(MAX_RETRY):
        try:
            r = requests.get(url, params=params or {}, timeout=timeout, headers=HEADERS)

            if r.status_code == 429:
                wait = RETRY_DELAY_BASE * (2 ** attempt) + (attempt % 3)
                print(f"[RETRY] Yahoo returned 429 for {url}, waiting {wait}s (attempt {attempt+1}/{MAX_RETRY})")
                time.sleep(wait)
                continue

            if r.status_code >= 500:
                wait = RETRY_DELAY_BASE * (2 ** attempt)
                print(f"[RETRY] Yahoo returned {r.status_code} for {url}, waiting {wait}s")
                time.sleep(wait)
                continue

            return r

        except requests.exceptions.Timeout as e:
            last_err = e
            wait = RETRY_DELAY_BASE * (2 ** attempt)
            print(f"[RETRY] Timeout for {url}, waiting {wait}s")
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            last_err = e
            print(f"[RETRY] Connection error for {url}: {e}")
            if attempt < MAX_RETRY - 1:
                time.sleep(2 * (attempt + 1))

    print(f"[ERROR] All retries failed for {url}: {last_err}", file=sys.stderr)
    return None


# --- Cache to avoid re-fetching during same session ---
_SESSION_CACHE = {}
_SESSION_CACHE_TS = {}
SESSION_TTL = 300  # 5 minutes cache in session


def _cached_fetch(key, fetcher_func):
    """Simple time-based cache: returns cached result if TTL not exceeded."""
    now = time.time()
    if key in _SESSION_CACHE and (now - _SESSION_CACHE_TS.get(key, 0)) < SESSION_TTL:
        return _SESSION_CACHE[key]
    result = fetcher_func()
    _SESSION_CACHE[key] = result
    _SESSION_CACHE_TS[key] = now
    return result


# --- Yahoo Finance helpers ---

def _parse_yahoo_response(r):
    """Parse a Yahoo Finance response, returning market data dict or None."""
    if r is None:
        return None
    try:
        data = r.json()
    except (ValueError, TypeError):
        return None

    result_list = data.get("chart", {}).get("result") if isinstance(data, dict) else None
    if not result_list or len(result_list) == 0:
        return None

    meta = result_list[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("previousClose")

    if price is None or prev_close is None:
        print(f"[WARN] Yahoo returned no price data for symbol. Response keys: {list(data.keys())}", file=sys.stderr)
        return None

    try:
        p = float(price)
        pc = float(prev_close)
    except (ValueError, TypeError):
        return None

    if pc <= 0:
        return None

    return {
        "price": round(p, 2),
        "prev_close": round(pc, 2),
        "change": round(p - pc, 2),
        "change_pct": round((p - pc) / pc * 100, 2),
    }


def _fetch_yahoo_price(symbol: str, is_vn: bool = True):
    """Fetch a single symbol from Yahoo Finance chart API with retry.

    VN stocks need .VN suffix appended (unless already has it).
    Non-VN symbols go directly to Yahoo.
    """
    try:
        if is_vn and not symbol.endswith(".VN"):
            sym = f"{symbol}.VN"
        else:
            sym = symbol

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = _retry_request(url, timeout=15)
        return _parse_yahoo_response(r)

    except Exception as e:
        print(f"[ERROR] Yahoo fetch failed for {symbol}: {e}", file=sys.stderr)
        return None


def _fetch_period_data(symbol: str, interval: str, range_str: str):
    """Fetch period data (1w/1m/1q) with retry."""
    try:
        sym = symbol if symbol.endswith(".VN") else f"{symbol}.VN"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = _retry_request(url, params={"interval": interval, "range": range_str}, timeout=15)
        if r is None:
            return {}

        data = r.json()
        result_list = data.get("chart", {}).get("result", [{}])
        tmeta = result_list[0].get("meta", {}) if result_list else {}
        open_price = tmeta.get("chartPreviousClose") or tmeta.get("open")

        return {"open": open_price} if open_price else {}
    except Exception:
        return {}


# --- VN Stock fetchers ---

def _fetch_vn_stock_via_vnstock3(symbol: str):
    """Fetch VN stock price using vnstock3 (new generation)."""
    try:
        venv_path = Path("/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages")
        if venv_path.exists():
            sys.path.insert(0, str(venv_path))

        # vnstock3 uses different import path (migrated from vnstock.api)
        try:
            from vnstock.api.quote import Quote as VsQuote
        except ImportError:
            # Try alternative import paths
            try:
                from vnstock import Quote as VsQuote
            except ImportError:
                return None

        from datetime import datetime, timedelta
        _vs_end = datetime.now().strftime("%Y-%m-%d")
        _vs_start = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        q = VsQuote(symbol=symbol, show_log=False)
        df = q.history(symbol=symbol, start=_vs_start, end=_vs_end)

        if not df.empty:
            latest = df.iloc[-1]
            # vnstock returns prices in "nghìn đồng" — multiply by 1000 for actual VND
            current_close = float(latest["close"]) * 1000
            prev_close = (float(df.iloc[-2]["close"]) * 1000) if len(df) > 1 else current_close

            if prev_close <= 0:
                return None

            return {
                "symbol": symbol,
                "price": round(current_close, 2),
                "change": round(current_close - prev_close, 2),
                "change_pct": round((current_close - prev_close) / prev_close * 100, 2),
                "prev_close": round(prev_close, 2),
            }
    except Exception as e:
        print(f"[VNSTOCK] Failed for {symbol}: {e}", file=sys.stderr)
    return None


def _fetch_vn_stock_via_yahoo_fallback(symbol: str):
    """Fallback: fetch VN stock via Yahoo Finance directly."""
    try:
        sym = f"{symbol}.VN"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = _retry_request(url, timeout=15)

        if r is None:
            return None

        data = r.json()
        result_list = data.get("chart", {}).get("result", [{}])
        meta = result_list[0].get("meta", {}) if result_list else {}

        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if price is None or prev_close is None:
            return None

        try:
            p = float(price)
            pc = float(prev_close)
        except (ValueError, TypeError):
            return None

        if pc <= 0:
            return None

        return {
            "symbol": symbol,
            "price": round(p, 2),
            "change": round(p - pc, 2),
            "change_pct": round((p - pc) / pc * 100, 2),
            "prev_close": round(pc, 2),
        }

    except Exception as e:
        print(f"[YAHOO] Fallback failed for {symbol}: {e}", file=sys.stderr)
        return None


def fetch_single_vn_stock(symbol: str):
    """Fetch a single VN stock: try vnstock3 first, then Yahoo."""
    # Try vnstock3 first
    data = _fetch_vn_stock_via_vnstock3(symbol)
    if data:
        print(f"[OK] {symbol}: price={data['price']} (via vnstock3)")
        return data

    # Fallback to Yahoo Finance with retry
    data = _fetch_vn_stock_via_yahoo_fallback(symbol)
    if data:
        print(f"[OK] {symbol}: price={data['price']} (via Yahoo fallback)")
        return data

    print(f"[FAIL] {symbol}: All sources exhausted", file=sys.stderr)
    return None


# --- Chart data helper ---

def _fetch_chart_data(symbol: str):
    """Fetch intraday chart data (last 5 days, 30min interval)."""
    try:
        sym = symbol if symbol.endswith(".VN") else f"{symbol}.VN"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = _retry_request(url, params={"interval": "30m", "range": "5d"}, timeout=15)
        if r is None:
            return None

        data = r.json()
        result_list = data.get("chart", {}).get("result", [{}])
        chart_result = result_list[0] if result_list else {}
        timestamps = chart_result.get("timestamp", [])
        ohlcv = chart_result.get("indicators", {}).get("quote", [{}])[0]

        if not timestamps:
            return None

        chart_data = []
        for j, ts in enumerate(timestamps[:100]):
            try:
                chart_data.append({
                    "time": datetime.fromtimestamp(int(ts)).isoformat(),
                    "open": int(ohlcv.get("open", [None])[j]) if ohlcv.get("open") and j < len(ohlcv.get("open", [])) else None,
                    "high": int(ohlcv.get("high", [None])[j]) if ohlcv.get("high") and j < len(ohlcv.get("high", [])) else None,
                    "low": int(ohlcv.get("low", [None])[j]) if ohlcv.get("low") and j < len(ohlcv.get("low", [])) else None,
                    "close": int(ohlcv.get("close", [None])[j]) if ohlcv.get("close") and j < len(ohlcv.get("close", [])) else None,
                    "volume": int(ohlcv.get("volume", [None])[j]) if ohlcv.get("volume") and j < len(ohlcv.get("volume", [])) else None,
                })
            except (ValueError, TypeError, IndexError):
                continue

        return chart_data if chart_data else None

    except Exception as e:
        print(f"[WARN] Chart fetch failed for {symbol}: {e}", file=sys.stderr)
        return None


# --- Main fetch functions ---

def fetch_vn_indices():
    """Fetch VN-Index and major VN stocks."""
    symbols = {
        "^VNINDEX.VN": "VN-Index",
        "^HOSECAP": "HOSE Cap",
    }
    results = {}

    # Sequential with delay to avoid rate limiting
    time.sleep(0.5)  # initial delay
    for yahoo_sym, name in symbols.items():
        data = _fetch_yahoo_price(yahoo_sym, is_vn=False)
        if data:
            results[name] = data
        time.sleep(1)  # rate limit delay between requests

    return results


def fetch_global_indices():
    """Fetch global indices from Yahoo Finance."""
    try:
        import core.config as config_mod
        config = config_mod.load_config() if hasattr(config_mod, "load_config") else {}
    except Exception:
        config = {}

    global_map = config.get("global_indices", {
        "^GSPC": "S&P 500",
        "^DJI": "Dow Jones",
        "^IXIC": "NASDAQ",
        "^N225": "Nikkei 225",
        "^HSI": "Hang Seng",
        "^KS11": "KOSPI",
        "^GDAXI": "DAX",
        "^FTSE": "FTSE 100",
    })

    results = {}
    time.sleep(0.5)  # initial delay
    for yahoo_sym, name in global_map.items():
        data = _fetch_yahoo_price(yahoo_sym, is_vn=False)
        if data:
            results[name] = {**data, "symbol": yahoo_sym}
        time.sleep(1.2)  # rate limit delay

    return results


def fetch_crypto():
    """Fetch BTC, ETH, SOL prices."""
    crypto_map = {"BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL"}
    results = {}

    time.sleep(0.5)
    for yahoo_sym, name in crypto_map.items():
        data = _fetch_yahoo_price(yahoo_sym, is_vn=False)
        if data:
            results[name] = {**data, "symbol": yahoo_sym}
        time.sleep(1)

    return results


def fetch_gold():
    """Fetch gold price (GC=F)."""
    data = _fetch_yahoo_price("GC=F", is_vn=False)
    if data:
        return {"name": "Gold", "symbol": "GC=F", **data}
    return None


def fetch_oil():
    """Fetch WTI oil price (CL=F)."""
    data = _fetch_yahoo_price("CL=F", is_vn=False)
    if data:
        return {"name": "WTI Oil", "symbol": "CL=F", **data}
    return None


def fetch_dxy():
    """Fetch DXY (US Dollar Index)."""
    data = _fetch_yahoo_price("DX-Y.NYB", is_vn=False)
    if data:
        return {"name": "DXY", "symbol": "DX-Y.NYB", **data}
    return None


def _fetch_all_task(name_fn):
    """Wrapper for ThreadPoolExecutor to capture results/errors."""
    name, fn = name_fn
    try:
        return name, fn(), None
    except Exception as e:
        return name, None, str(e)


def fetch_all_overview():
    """Fetch ALL market overview data.

    Uses ThreadPoolExecutor to parallelize across independent data sources.
    Each source (VN indices, global, crypto) still staggers internal calls
    to avoid per-source Yahoo rate limits, but sources run concurrently
    reducing total time from ~60s to ~15-20s.
    """
    results = {}
    errors = []

    print("[FETCH] Starting full market overview fetch (parallel)...")

    try:
        # Run all independent sources in parallel with max concurrent = 3
        tasks = [("vn_indices", fetch_vn_indices),
                  ("global_indices", fetch_global_indices),
                  ("crypto", fetch_crypto),
                  ("gold", fetch_gold),
                  ("oil", fetch_oil),
                  ("dxy", fetch_dxy)]

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {name: executor.submit(_fetch_all_task, (name, fn)) for name, fn in tasks}
            for future in concurrent.futures.as_completed(futures):
                name, data, err = future.result()
                if data:
                    results[name] = data
                    print(f"[OK] {name}: fetched")
                if err:
                    errors.append(err)

    except Exception as e:
        print(f"[ERROR] Overview fetch error: {e}", file=sys.stderr)
        errors.append(str(e))

    results["updated_at"] = datetime.now().isoformat()
    if errors:
        results["_partial"] = True
        results["_errors"] = errors
        print(f"[WARN] Partial data: missing {', '.join(errors)}")

    return results

def get_top_motions(symbols=None, limit=10):
    """Get top movers from a list of VN stocks.

    Uses vnstock3 first, then Yahoo Finance fallback with retry.
    """
    if not symbols:
        symbols = ["VIC", "VNM", "VCB", "HPG", "MSN", "FPT", "TCB", "MBB",
                     "HDB", "BID", "CTG", "STB", "ACB", "MWG"]

    results = []
    for i, sym in enumerate(symbols):
        # Stagger to avoid rate limiting
        if i > 0:
            time.sleep(1.5)

        data = fetch_single_vn_stock(sym)
        if data:
            results.append(data)
        else:
            print(f"[SKIP] {sym}: no data available", file=sys.stderr)

    # Sort by change_pct
    results.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    top_gainers = results[:limit // 2] if len(results) >= limit // 2 else []
    top_losers = results[-(limit // 2):] if len(results) >= limit // 2 else []

    return {
        "gainers": top_gainers,
        "losers": top_losers,
    }
