"""
vnstock4_provider.py -- Data provider using vnstock4 for Vietnamese stock data.

Wraps vnstock4 Market().equity(...).ohlcv() for daily OHLCV candles from KBS/VCI source.
Returns normalized price-data dict compatible with jarvis-hub TA engine (market_service.py).
"""

from typing import Dict, List, Optional

# Lazy load vnstock to avoid hard dependency failures
_vnstock_loaded = False
Market = None


def _ensure_vnstock():
    global _vnstock_loaded, Market
    if not _vnstock_loaded:
        try:
            from vnstock import Market as Mk
            Market = Mk
            _vnstock_loaded = True
        except ImportError as e:
            raise RuntimeError(
                f"vnstock4 package not installed. "
                f"Run: pip install vnstock\nDetails: {e}"
            )


def fetch_daily_ohlcv(
    symbol,
    days=60,
    use_vci=False,
    verbose=True
):
    """Fetch daily OHLCV from vnstock4 and return normalized price-data dict.

    Args:
        symbol: Stock ticker (e.g., 'VCI', 'VCB', 'VIC').
        days: Number of trading days to fetch (default 60).
        use_vci: If True, use VCI source instead of KBS (KBS preferred for most stocks).
        verbose: Print debug output.

    Returns:
        dict: Normalized price-data matching Yahoo Finance schema
             {price, open, high, low, volume, change, change_pct, historical_closes, ...}
        None: On fetch failure (vnstock4 unavailable or no data for symbol).
    """
    _ensure_vnstock()

    sym = symbol.upper().strip()
    source = "vci" if use_vci else "kbs"

    try:
        eq = Market().equity(symbol=sym)
        # Calculate date range from days parameter
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        if verbose:
            print(f"[VNSTOCK4] Fetching {sym} daily OHLCV from {source} ({start_date} to {end_date})")

        df = eq.ohlcv(
            start=start_date,
            end=end_date,
            resolution="1D",
            source=source
        )

    except Exception as e:
        if verbose:
            print(f"[VNSTOCK4] FAILED for {sym} ({source}): {e}")
        return None

    # Handle non-DataFrame results (some vnstock versions return raw dict/list)
    if df is None:
        if verbose:
            print(f"[VNSTOCK4] No data returned for {sym}")
        return None

    import pandas as pd
    if not isinstance(df, pd.DataFrame) or df.empty:
        if verbose:
            print(f"[VNSTOCK4] Empty DataFrame for {sym}")
        return None

    # Normalize columns - vnstock4 returns lowercase: open, high, low, close, volume
    # Build a case-insensitive column map so it works across sources (kbs/vci)
    col_lower = {c.lower().strip(): c for c in df.columns}
    col_map = {}
    for key in ("open", "high", "low", "close", "volume"):
        if key in col_lower:
            col_map[key] = col_lower[key]

    normalized_df = pd.DataFrame()
    for target, src_col in col_map.items():
        normalized_df[target] = pd.to_numeric(df[src_col], errors="coerce")

    # Extract timestamps from 'time' column or index
    dates = []
    if "time" in [c.lower().strip() for c in df.columns]:
        time_col = col_lower.get("time", "")
        if time_col:
            dates = pd.to_datetime(df[time_col]).dt.strftime("%Y-%m-%d").tolist()
    elif hasattr(df.index, 'date'):
        dates = [df.index[i].strftime("%Y-%m-%d") if hasattr(df.index[i], "strftime") else str(df.index[i])[:10] for i in range(len(df))]
    elif "date" in col_lower:
        dates = df[col_lower["date"]].astype(str).str[:10].tolist()

    # Convert to Python-native lists (handles NaN safely)
    if "close" in normalized_df.columns:
        closes_list = [round(float(c), 2) for c in normalized_df["close"].ffill().tolist()]
    else:
        closes_list = []

    if "open" in normalized_df.columns:
        opens_list = [round(float(o), 2) for o in normalized_df["open"].ffill().tolist()]
    else:
        opens_list = []

    if "high" in normalized_df.columns:
        highs_list = [round(float(h), 2) for h in normalized_df["high"].tolist()]
    else:
        highs_list = []

    if "low" in normalized_df.columns:
        lows_list = [round(float(l), 2) for l in normalized_df["low"].tolist()]
    else:
        lows_list = []

    if "volume" in normalized_df.columns:
        volumes_list = [int(v) for v in normalized_df["volume"].fillna(0).astype(int).tolist() if v == v]
    else:
        volumes_list = []

    # Filter out NaN values
    closes_list = [c for c in closes_list if c is not None and c > -999999]
    opens_list = [o for o in opens_list if o is not None and o > -999999]
    highs_list = [h for h in highs_list if h is not None and h > -999999]
    lows_list = [l for l in lows_list if l is not None and l > -999999]
    volumes_list = [v for v in volumes_list if v is not None and v >= 0]

    if len(closes_list) < 2:
        if verbose:
            print(f"[VNSTOCK4] Insufficient close data for {sym}: {len(closes_list)} rows")
        return None

    # Calculate change (latest candle vs previous)
    latest_close = closes_list[-1]
    prev_close = closes_list[-2] if len(closes_list) > 1 else 0

    if prev_close and prev_close != 0:
        change = round(latest_close - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2)
    else:
        change = 0.0
        change_pct = 0.0

    latest_open = opens_list[-1] if opens_list else None
    latest_high = highs_list[-1] if highs_list else None
    latest_low = lows_list[-1] if lows_list else None
    latest_volume = volumes_list[-1] if volumes_list else 0

    # Extract metadata from vnstock equity object
    try:
        if hasattr(eq, 'info') and eq.info:
            meta_info = eq.info
            name = meta_info.get("name", meta_info.get("companyName", f"{sym}"))
            market_cap = meta_info.get("marketCap", None)
            pe_ratio = meta_info.get("peRatio", meta_info.get("PE_TTM", None))
        else:
            raise AttributeError("No info attribute")
    except Exception:
        name = sym
        market_cap = None
        pe_ratio = None

    result = {
        "symbol": symbol,
        "name": name,
        "price": latest_close if latest_close > 0 else None,
        "open": round(latest_open, 2) if latest_open is not None and latest_open > 0 else None,
        "high": round(latest_high, 2) if latest_high is not None and latest_high > 0 else None,
        "low": round(latest_low, 2) if latest_low is not None and latest_low > 0 else None,
        "volume": latest_volume,
        "change": change,
        "change_pct": change_pct,
        "history_source": "vnstock4",
        "source_used": source,
        "type": "VN",
        "currency": "VND",
        "historical_closes": [c for c in closes_list if c > 0],
        "historical_timestamps": dates if dates else [],
        "historical_opens": [o for o in opens_list if o is not None and o > 0],
        "historical_highs": [h for h in highs_list if h is not None and h > 0],
        "historical_lows": [l for l in lows_list if l is not None and l > 0],
        "historical_volumes": volumes_list,
    }

    if market_cap:
        result["market_cap"] = _format_market_cap(market_cap)
    if pe_ratio is not None:
        try:
            result["pe_ratio"] = float(pe_ratio)
        except (ValueError, TypeError):
            pass

    if verbose:
        print(f"[VNSTOCK4] {sym}: price={latest_close}, change={change_pct:+.2f}%, "
              f"candles={len(closes_list)}, open={result['open']}, high={result['high']}, "
              f"low={result['low']}, vol={result['volume']}")

    return result


def _format_market_cap(cap):
    """Format market cap for display (same as market_service.py)."""
    if not cap:
        return "N/A"
    try:
        cap = float(cap)
    except (ValueError, TypeError):
        return str(cap)
    if cap >= 1e12:
        return f"${cap / 1e12:.2f}T"
    elif cap >= 1e9:
        return f"${cap / 1e9:.2f}B"
    elif cap >= 1e6:
        return f"${cap / 1e6:.2f}M"
    else:
        return f"${cap:.0f}"


def fetch_multiple_symbols(symbols, days=30):
    """Fetch data for a list of symbols in serial fashion.

    Args:
        symbols: List of ticker strings.
        days: Days of history (default 30).

    Returns:
        dict: symbol -> price_data or None.
    """
    results = {}
    for sym in symbols:
        try:
            results[sym] = fetch_daily_ohlcv(sym, days=days)
        except Exception as e:
            print(f"[VNSTOCK4] Error fetching {sym}: {e}")
            results[sym] = None
    return results
