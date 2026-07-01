"""
market_overview.py -- Market data fetcher for Hub 2.0 Overview Dashboard.

Fetches: VN-Index, global indices, crypto, gold, FX rates.
Used by: /api/v1/overview/* endpoints.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _fetch_yahoo_price(symbol: str):
    """Fetch a single symbol from Yahoo Finance chart API."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        result_data = data.get("chart", {}).get("result")
        if not result_data:
            return None

        meta = result_data[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if price is None or prev_close is None:
            return None

        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        # Get 1W / 1M / 1Q changes
        periods = {
            "1wk": {"interval": "1d", "range": "5d"},
            "1mo": {"interval": "1d", "range": "21d"},
            "1q": {"interval": "1d", "range": "63d"},
        }
        time_changes = {}
        for period, params in periods.items():
            try:
                turl = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN"
                params_dict = {
                    "interval": params["interval"],
                    "range": params["range"],
                }
                tr = requests.get(turl, params=params_dict, timeout=10, headers=HEADERS)
                tdata = tr.json()
                tmeta = tdata.get("chart", {}).get("result", [{}])[0].get("meta", {})
                open_price = tmeta.get("chartPreviousClose") or tmeta.get("open")
                if open_price and open_price > 0:
                    pct = ((price - open_price) / open_price) * 100
                    time_changes[period] = round(pct, 2)
            except Exception:
                time_changes[period] = None

        # Chart data for candlestick (last 1 month)
        chart_data = None
        try:
            chart_r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN",
                params={"interval": "30m", "range": "5d"},
                timeout=10, headers=HEADERS
            )
            chart_json = chart_r.json()
            chart_result = chart_json.get("chart", {}).get("result", [{}])[0]
            timestamps = chart_result.get("timestamp", [])
            ohlcv = chart_result.get("indicators", {}).get("quote", [{}])[0]
            if timestamps:
                chart_data = []
                for j, ts in enumerate(timestamps[:100]):
                    chart_data.append({
                        "time": datetime.fromtimestamp(ts).isoformat(),
                        "open": ohlcv.get("open", [None])[j],
                        "high": ohlcv.get("high", [None])[j],
                        "low": ohlcv.get("low", [None])[j],
                        "close": ohlcv.get("close", [None])[j],
                        "volume": ohlcv.get("volume", [None])[j],
                    })
        except Exception:
            pass

        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 2),
            "time_changes": time_changes,
            "chart_data": chart_data,
            "symbol": symbol,
        }
    except Exception as e:
        print(f"[WARN] Yahoo fetch failed for {symbol}: {e}", file=__import__("sys").stderr)
        return None


def fetch_vn_indices():
    """Fetch VN-Index and major VN stocks."""
    vn_symbols = {
        "^VNINDEX.VN": "VN-Index",
        "^HOSECAP": "HOSE Cap",
    }
    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_yahoo_price, sym): name for sym, name in vn_symbols.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                if data:
                    results[name] = data
            except Exception as e:
                print(f"[WARN] VN index error for {name}: {e}", file=__import__("sys").stderr)
    return results


def fetch_global_indices():
    """Fetch global indices from Yahoo Finance."""
    config_module = __import__("core.config", fromlist=["load_config"])
    config = config_module.load_config()
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
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_yahoo_price, sym): name for sym, name in global_map.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                if data:
                    results[name] = data
            except Exception as e:
                print(f"[WARN] Global index error for {name}: {e}", file=__import__("sys").stderr)
    return results


def fetch_crypto():
    """Fetch BTC, ETH, SOL prices."""
    crypto_map = {"BTC-USD": "BTC", "ETH-USD": "ETH", "SOL-USD": "SOL"}
    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_yahoo_price, sym): name for sym, name in crypto_map.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                if data:
                    results[name] = data
            except Exception as e:
                print(f"[WARN] Crypto fetch error for {name}: {e}", file=__import__("sys").stderr)
    return results


def fetch_gold():
    """Fetch gold price (GC=F)."""
    data = _fetch_yahoo_price("GC=F")
    if data:
        return {"name": "Gold", "symbol": "GC=F", **data}
    return None


def fetch_oil():
    """Fetch WTI oil price (CL=F)."""
    data = _fetch_yahoo_price("CL=F")
    if data:
        return {"name": "WTI Oil", "symbol": "CL=F", **data}
    return None


def fetch_dxy():
    """Fetch DXY (US Dollar Index)."""
    data = _fetch_yahoo_price("DX-Y.NYB")
    if data:
        return {"name": "DXY", "symbol": "DX-Y.NYB", **data}
    return None


def fetch_all_overview():
    """Fetch ALL market overview data in parallel.
    Returns: dict with keys: vn_indices, global_indices, crypto, gold, oil, dxy
    """
    results = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(fetch_vn_indices): "vn_indices",
            executor.submit(fetch_global_indices): "global_indices",
            executor.submit(fetch_crypto): "crypto",
            executor.submit(fetch_gold): "gold",
            executor.submit(fetch_oil): "oil",
            executor.submit(fetch_dxy): "dxy",
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                data = future.result()
                if data:
                    results[key] = data
            except Exception as e:
                print(f"[WARN] Overview fetch failed for {key}: {e}", file=__import__("sys").stderr)

    results["updated_at"] = datetime.now().isoformat()
    return results


def get_top_motions(symbols=None, limit=10):
    """Get top movers from a list of VN stocks.
    Uses TCInvest or direct Yahoo fetch for VN stocks.
    """
    # Default VN-30 symbols if none provided
    if not symbols:
        symbols = ["VIC", "VNM", "VCB", "HPG", "MSN", "GAS", "MWG", "FPT", "TCB", "MBB",
                   "HDB", "BID", "CTG", "STB", "ACB", "VPB", "TPB", "SHB", "VCB", "TPB"]

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_single_vn_stock, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
            except Exception:
                pass

    # Sort by change_pct and return top N gainers + losers
    results.sort(key=lambda x: x.get("change_pct", 0), reverse=True)
    top_gainers = results[:limit // 2]
    top_losers = results[-(limit // 2):]
    return {
        "gainers": top_gainers,
        "losers": top_losers,
    }


def _fetch_single_vn_stock(symbol: str):
    """Fetch a single VN stock via vnstock4 API (primary) or Yahoo Finance (fallback)."""
    # Try vnstock4 first ? it returns correct VND prices (thousands * 1000)
    try:
        import sys
        from pathlib import Path
        _venv_path = Path("/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages")
        if _venv_path.exists() and "/usr" not in str(_venv_path):
            sys.path.insert(0, str(_venv_path))
        from vnstock.api.quote import Quote as VsQuote
        
        q = VsQuote(symbol=symbol, show_log=False)
        df = q.history(symbol=symbol, start="2026-04-01", end="2026-07-01")
        
        if not df.empty:
            latest = df.iloc[-1]
            # vnstock returns prices in "ngh?n đồng" * 1000 for actual VND
            current_close = float(latest["close"]) * 1000
            prev_close = (float(df.iloc[-2]["close"]) * 1000) if len(df) > 1 else current_close
            change = current_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0
            
            return {
                "symbol": symbol,
                "price": round(current_close, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev_close, 2),
            }
    except Exception as _e:
        pass   # Fall through to Yahoo
    
    try:
        # vnstock unavailable or failed ? fallback to Yahoo Finance
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.VN"
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        result_data = data.get("chart", {}).get("result")
        if not result_data:
            return None

        meta = result_data[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("previousClose")

        if price is None or prev_close is None:
            return None

        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 2),
        }
    except Exception as e:
        return None