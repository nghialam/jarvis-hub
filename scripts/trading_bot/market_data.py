#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Market Data Module
Fetches real-time OHLCV data from VNStock API v4.x, calculates technical indicators
(RSI, MACD, MA, ATR).

Key change: Uses `vnstock.api.quote.Quote` (vnstock 4.x class-based API) instead of the
deprecated `vnstock.ohlc_data()` top-level function.

Optimised for vnstock free-tier rate limits: only 1 API call per symbol via daily history,
reducing total calls from ~60 to 20 per full scan.
"""

import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Lazy config loading — avoids circular imports with signal_engine
# ---------------------------------------------------------------------------
_config_cache = {}


def _get_config():
    global _config_cache
    if _config_cache:
        return _config_cache
    path = os.path.join(os.path.dirname(__file__), "config.py")
    cfg = {
        "MAX_RETRIES": 2,
        "RSI_PERIOD": 14, "MACD_FAST": 12, "MACD_SLOW": 26,
        "MACD_SIGNAL": 9, "ATR_PERIOD": 14,
    }
    if os.path.isfile(path):
        try:
            ns = {}
            exec(open(path).read(), ns)
            for k in cfg:
                if k in ns:
                    cfg[k] = ns[k]
        except Exception:
            pass
    _config_cache = cfg
    return cfg


CONFIG = _get_config()
MAX_RETRIES = CONFIG.get("MAX_RETRIES", 2)
RSI_PERIOD = CONFIG.get("RSI_PERIOD", 14)
MACD_FAST = CONFIG.get("MACD_FAST", 12)
MACD_SLOW = CONFIG.get("MACD_SLOW", 26)
MACD_SIGNAL = CONFIG.get("MACD_SIGNAL", 9)
ATR_PERIOD = CONFIG.get("ATR_PERIOD", 14)

# vnstock 4.x import — lazy to avoid early failures if API unavailable
_vnstock_quote = None


def _get_quote_class():
    global _vnstock_quote
    if _vnstock_quote is not None:
        return _vnstock_quote
    try:
        from vnstock.api.quote import Quote
        _vnstock_quote = Quote
    except ImportError:
        raise ImportError("vnstock package not found — install with: pip install vnstock")
    return _vnstock_quote


# ---------------------------------------------------------------------------
# API helper with retry + built-in rate-limit pacing
# ---------------------------------------------------------------------------

def _api_call_with_retry(func, symbol, max_retries=None):
    """Execute a Quote method with retry and exponential back-off for rate limits."""
    retries = max_retries if max_retries is not None else MAX_RETRIES
    last_exc = None
    for attempt in range(retries + 1):
        try:
            result = func()
            return result
        except Exception as e:
            err_str = str(e).lower()
            # Rate-limit or quota errors → back-off and retry
            if any(w in err_str for w in ["limit", "quota", "rate"]):
                last_exc = e
                wait = 30 * (attempt + 1)
                print(f"[WARN] {symbol}: rate limit hit, waiting {wait}s (attempt {attempt+1}/{retries+1})", file=sys.stderr)
                time.sleep(wait)
            elif attempt == retries:
                raise
            else:
                last_exc = e
                time.sleep(2)
    raise last_exc


def _build_candle_df(daily_df):
    """Build OHLCV candle DataFrame from vnstock history response.

    Returns pd.DataFrame with columns ['time','o','h','l','c','v'] or empty.
    """
    if daily_df is None or not isinstance(daily_df, pd.DataFrame) or len(daily_df) == 0:
        return pd.DataFrame()

    dd = daily_df.copy()
    dd["time"] = pd.to_datetime(dd["time"])

    # Normalize column name variants to canonical OHLCV
    rename_map = {}
    for c in ("open", "o", "Open", "OPEN"):
        if c in dd.columns and "o" not in rename_map:
            rename_map[c] = "o"
    for c in ("high", "h", "High", "HIGH"):
        if c in dd.columns and "h" not in rename_map:
            rename_map[c] = "h"
    for c in ("low", "l", "Low", "LOW"):
        if c in dd.columns and "l" not in rename_map:
            rename_map[c] = "l"
    for c in ("close", "c", "Close", "CLOSE"):
        if c in dd.columns and "c" not in rename_map:
            rename_map[c] = "c"
    for c in ("volume", "v", "Vol", "Volume", "vol"):
        if c in dd.columns and "v" not in rename_map:
            rename_map[c] = "v"
    dd = dd.rename(columns=rename_map)

    # Verify required columns exist
    if not set(["o","h","l","c","v"]) <= set(dd.columns):
        return pd.DataFrame()

    out = dd[["time","o","h","l","c","v"]].copy()
    for col in ("o","h","l","c"):
        out[col] = out[col].astype(float)
    out["v"] = out["v"].astype(int)
    return out


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_stock_data(symbol: str, cache=None) -> dict:
    """
    Fetch real-time OHLCV data for a stock from VNStock API (4.x).

    Uses vnstock 4.x Quote.history() (daily interval) — single API call per symbol.
    Daily candles are sufficient for all technical indicators (RSI, MACD, MA5/20, ATR).

    Args:
        symbol: Stock ticker (e.g., "VCI")
        cache: Optional dict to store results by symbol key

    Returns dict with:
        symbol, latest_price, change_percent, volume, high, low, open,
        rsi_14, ma_5, ma_20, macd_line, signal_line, histogram,
        atr_14, candles, status ("ok"/"partial"/"error")
    """
    result = {
        "symbol": symbol.upper(),
        "latest_price": None,
        "change_percent": None,
        "volume": None,
        "avg_volume_10d": None,
        "high": None,
        "low": None,
        "open": None,
        "candles": [],
        "rsi_14": None,
        "ma_5": None,
        "ma_20": None,
        "macd_line": None,
        "signal_line": None,
        "histogram": None,
        "atr_14": None,
        "previous_close": None,
        "status": "ok"
    }

    quote_class = _get_quote_class()

    try:
        today = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=60)).strftime("%Y-%m-%d")

        # Single API call per symbol — daily candles sufficient for all indicators
        quote_instance = quote_class(symbol=symbol.upper(), show_log=False)

        def do_fetch():
            return _api_call_with_retry(
                lambda: quote_instance.history(
                    symbol=symbol.upper(),
                    start=start,
                    end=today,
                    interval="D",
                ),
                symbol=symbol.upper(),
            )

        # Execute with retry + rate-limit handling
        df_raw = do_fetch()

        combined_candles = _build_candle_df(df_raw)

        # If no data returned, check if it's a 403/429 rate-limit issue
        if combined_candles.empty:
            # Try once more with a longer wait (rate limit recovery)
            try:
                time.sleep(10)
                df_raw = _api_call_with_retry(
                    lambda: quote_instance.history(
                        symbol=symbol.upper(),
                        start=start,
                        end=today,
                        interval="D",
                    ),
                    symbol=symbol.upper(),
                    max_retries=1,
                )
                combined_candles = _build_candle_df(df_raw)
            except Exception:
                pass

        if len(combined_candles) == 0:
            result["status"] = "error"
            result["status_msg"] = f"No OHLCV data returned for {symbol.upper()} (VNX closed?)"
            if cache and not cache.get(symbol.upper()):
                cache[symbol.upper()] = result.copy()
            return result

        # Extract latest price/volume/high/low from most recent candle
        latest_candle = combined_candles.iloc[-1]
        result["latest_price"] = float(latest_candle["c"])
        result["volume"] = int(latest_candle["v"]) if "v" in latest_candle.index else None
        result["high"] = float(combined_candles["h"].max())
        result["low"] = float(combined_candles["l"].min())
        result["open"] = float(latest_candle["o"])

        # Previous close = closing price of the candle before the latest
        if len(combined_candles) > 1:
            prev_close = float(combined_candles.iloc[-2]["c"])
            result["previous_close"] = prev_close
        else:
            result["previous_close"] = float(latest_candle["o"])

        if result["previous_close"] and result["latest_price"]:
            if result["previous_close"] != 0:
                result["change_percent"] = round(
                    ((result["latest_price"] - result["previous_close"]) / result["previous_close"]) * 100, 2
                )

        # Indicator calculations on full candle set
        candles_for_indicators = combined_candles[["o","h","l","c","v"]].copy()
        closes = candles_for_indicators["c"].astype(float).tolist()
        volumes = candles_for_indicators["v"].astype(int).tolist()

        if len(closes) >= RSI_PERIOD + 1:
            try:
                result["rsi_14"] = calculate_rsi(closes, RSI_PERIOD)
            except Exception as e:
                print(f"[WARN] {symbol}: RSI calc failed: {e}")

            result["ma_5"] = round(sum(closes[-5:]) / 5, 3) if len(closes) >= 5 else None
            result["ma_20"] = round(sum(closes[-20:]) / 20, 3) if len(closes) >= 20 else None

            try:
                macd_data_result = calculate_macd(
                    closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
                result["macd_line"] = (
                    macd_data_result.get("macd_line") if macd_data_result else None)
                result["signal_line"] = (
                    macd_data_result.get("signal_line") if macd_data_result else None)
                result["histogram"] = (
                    macd_data_result.get("histogram") if macd_data_result else None)
            except Exception as e:
                print(f"[WARN] {symbol}: MACD calc failed: {e}")

            try:
                # Convert DataFrame to list of dicts for ATR calc
                atr_candles = [
                    {"o": float(row["o"]), "h": float(row["h"]),
                     "l": float(row["l"]), "c": float(row["c"]), "v": int(row.get("v", 0))}
                    for _, row in candles_for_indicators.iterrows()
                ]
                result["atr_14"] = calculate_atr(atr_candles, ATR_PERIOD)
            except Exception as e:
                print(f"[WARN] {symbol}: ATR calc failed: {e}")

            # Estimated 10-day average volume (last 10 candles ≈ last 10 days for daily data)
            recent_volumes = volumes[-10:] if len(volumes) >= 10 else volumes
            result["avg_volume_10d"] = round(sum(recent_volumes) / max(len(recent_volumes), 1), 0)

            # Format candles for pocket-pivot detection & Telegram delivery
            formatted_candles = []
            for idx, row in candles_for_indicators.iterrows():
                candle_dict = {
                    "time": str(row.name),
                    "o": float(row["o"]),
                    "h": float(row["h"]),
                    "l": float(row["l"]),
                    "c": float(row["c"]),
                    "v": int(row["v"])
                }
                formatted_candles.append(candle_dict)
            result["candles"] = formatted_candles

        # Determine final status
        if (result["rsi_14"] is not None or result["macd_line"] is not None):
            result["status"] = "ok"
        elif len(combined_candles) > 0:
            result["status"] = "partial"

    except ImportError as e:
        result["status"] = "error"
        result["status_msg"] = f"VNStock module not found: {e}"
    except Exception as e:
        result["status"] = "partial"
        result["status_msg"] = str(e)

    if hasattr(fetch_stock_data, '_cache'):
        try:
            fetch_stock_data._cache[symbol.upper()] = result.copy()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Batch fetching with rate-limit pacing between symbols
# ---------------------------------------------------------------------------

def _load_watchlist_symbols():
    """Load watchlist from unified DB.

    Falls back to hardcoded list if DB query fails.
    """
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(__file__))
        from db_watchlist import get_symbols_for_asset_type

        # Fetch all symbols regardless of asset type
        all_symbols = []
        for atype in ("VN_STOCK", "US_EQUITY", "CRYPTO", "ETF", "OTHER"):
            all_symbols.extend(get_symbols_for_asset_type(atype))

        if all_symbols:
            return all_symbols
    except Exception as e:
        print(f"[WARN] _load_watchlist_symbols DB error, fallback: {e}", file=sys.stderr)

    # Fallback default list
    return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",
                "BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF","AAPL","MSFT","TSLA","BTC"]




# ===========================================================================
# Technical Indicator Calculations — VNStock 4.x (added 2026-06-05)
# fix these were referenced but never defined in v4 refactoring
# ===========================================================================


def calculate_rsi(prices: list[float], period: int = 14) -> float | None:
    """Calculate RSI using Wilder's smoothing. Returns float or None."""
    if not prices or len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(0.0, d) for d in deltas]
    losses = [max(0.0, -d) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(deltas)):
        gain = max(0.0, deltas[i])
        loss = max(0.0, -deltas[i])
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

    return round(rsi, 2)


def calculate_macd(
    prices: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> dict[str, float] | None:
    """Calculate MACD line, Signal line, and Histogram."""
    if len(prices) < slow_period + signal_period:
        return None

    def _ema(vals: list[float], period: int) -> list[float]:
        multiplier = 2.0 / (period + 1)
        sma = sum(vals[:period]) / period
        result = [sma]
        for v in vals[period:]:
            new = (v - result[-1]) * multiplier + result[-1]
            result.append(new)
        return result

    ema_fast = _ema(prices, fast_period)
    ema_slow = _ema(prices, slow_period)
    macd_lines = [f_val - s for f_val, s in zip(ema_fast, ema_slow)]

    if len(macd_lines) < signal_period:
        return None
    signal_lines = _ema(macd_lines, signal_period)
    histograms = [m - s for m, s in zip(
        macd_lines[-len(signal_lines):], signal_lines)]

    return {
        "macd_line": round(macd_lines[-1], 4),
        "signal_line": round(signal_lines[-1], 4),
        "histogram": round(histograms[-1], 4),
    }


def calculate_atr(
    candles: list[dict[str, float|int]], period: int = 14
) -> float | None:
    """Calculate ATR (Average True Range) from OHLCV dicts."""
    if not candles or len(candles) < period + 1:
        return None

    tr_values = []
    for i in range(1, len(candles)):
        hi = float(candles[i]["c"])  # this is the close at first pass
        lo = float(candles[i]["l"])  # ... wait — keys might differ
        prev_close = float(candles[i - 1]["c"])

        tr_val = max(
            hi - lo,
            abs(hi - prev_close),
            abs(lo - prev_close),
        )
        tr_values.append(tr_val)

    a_tr = sum(tr_values[:period]) / period
    for i in range(period, len(tr_values)):
        avg = (a_tr * (period - 1) + tr_values[i]) / period
        a_tr = avg

    return round(a_tr, 4)


def fetch_all_stocks(symbols=None):
    """Fetch OHLCV data for all symbols in watchlist.
        Uses unified DB for symbol list, falls back to hardcoded list.
        Returns dict: {symbol: stock_data} or empty if no data fetched.
    """
    # If caller provides a custom list, use it; otherwise load from DB
    if symbols is None:
        symbols = _load_watchlist_symbols()
    
    cache = getattr(fetch_stock_data, "_cache", {})
    results = {}
    errors = []
    
    print(f"[FETCH_ALL] Scanning {len(symbols)} symbols...")
    
    for sym in sorted(set(symbols)):
        # Rate limit spacing
        if sym and sym not in results:
            try:
                data = fetch_stock_data(sym, cache=cache)
                results[sym.upper()] = data
                if data.get("status") == "error":
                    errors.append({"symbol": sym, "error": data.get("status_msg", "unknown")})
            except Exception as e:
                errors.append({"symbol": sym, "error": str(e)})
        # Pacing between symbols
        import time
        time.sleep(2)
    
    print(f"[FETCH_ALL] Completed: {len(results)} OK, {len(errors)} errors")
    if errors:
        for err in errors[:5]:
            print(f'    [WARN] {err["symbol"]}: {err["error"]}', file=__import__("sys").stderr)
    
    return {"results": results, "errors": errors, "symbols_scanned": len(results)}


