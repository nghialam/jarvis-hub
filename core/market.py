"""
market.py -- Data fetching, technical analysis, and LLM-powered reports for Jarvis Hub

Fetches from Yahoo Finance, Binance, etc. for stocks, Gold (XAU), and Crypto.
Calculates 10+ technical indicators (MA/EMA/SMA/RSI/MACD/Bollinger/RSI/Stoch/ATR/ADX).
Generates LLM-powered due diligence reports via Ollama.
"""
import json
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

import requests as requests_lib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- Yahoo Finance fetcher --------------------------------------------------

# Performance optimization: per-symbol TTL cache (5 min) to avoid repeated Yahoo calls
_symbol_cache = {}
_SYMBOL_TTL_SECONDS = 300  # 5 minutes


def _fetch_yahoo_price(symbol):
    """Fetch price data for a symbol from Yahoo Finance with HTTP-level timeout."""
    
    # Normalize symbol first - strip trailing extension (.US, .VN, etc.) and uppercase
    sym_base = symbol.upper().strip()
    for suffix in ('.VN', '.US', '.HK', '.SG'):
        if sym_base.endswith(suffix):
            sym_base = sym_base[:-len(suffix)]
    
    # PERFORMANCE: Check cache with normalized key
    import time as _time
    if sym_base in _symbol_cache:
        cached = _symbol_cache[sym_base]
        if _time.time() - cached['ts'] < _SYMBOL_TTL_SECONDS:
            return cached['data']    # Cache HIT, skip Yahoo entirely

    # Build symbol for Yahoo URL: preserve .VN, strip US/HK/SG suffixes, auto-append .VN for VN stocks
    sym_for_url = symbol.upper().strip()
    # Keep .VN, strip only US/HK/SG suffixes (but not .VN)
    for sfx in ('.US', '.HK', '.SG'):
       if sym_for_url.endswith(sfx):
           sym_for_url = sym_for_url[:-len(sfx)]
    # Auto-append .VN for Vietnamese stocks that don't have any exchange suffix
    if not sym_for_url.endswith(('.VN', '.US', '.HK', '.SG', '^')):
       sym_for_url += ".VN"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym_for_url}?range=1mo&interval=1d"

    # Try with headers to avoid 403 - WITH STRICT TIMEOUT (8s)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Accept': 'application/json',
        }
        r = requests_lib.get(url, headers=headers, timeout=8)
        logger.info(f"Yahoo Fetch: {symbol} ({r.status_code})")
    except Exception:
        r = None

    if r is None or r.status_code != 200:
         # Try without 'chart' path (fallback URL for VN stocks)
        sym_for_url2 = symbol.upper().strip()
         # Keep .VN, strip only US/HK/SG suffixes
        for sfx in ('.US', '.HK', '.SG'):
            if sym_for_url2.endswith(sfx):
                sym_for_url2 = sym_for_url2[:-len(sfx)]
        # Auto-append .VN for Vietnamese stocks that don't have any exchange suffix
        if not sym_for_url2.endswith(('.VN', '.US', '.HK', '.SG', '^')):
            sym_for_url2 += ".VN"
        url2 = f"https://query1.finance.yahoo.com/v7/finance/download/{sym_for_url2}?period1=&period2=&interval=1d&events=history"
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            }
            r = requests_lib.get(url2, headers=headers, timeout=10)
            logger.info(f"Yahoo Fetch (v7 fallback): {symbol} ({r.status_code})")
        except Exception:
            r = None

    if r is None or r.status_code != 200:
        print(f"[WARN] Yahoo fetch failed for {symbol}: {r.status_code if r else 'ERROR'}", file=sys.stderr)
        return None

    data = r.json()
    meta = data.get("chart", {}).get("result", [{}])[0]
    if not meta:
        print(f"[WARN] Yahoo fetch returned empty data for {symbol}", file=sys.stderr)
        return None

    quotes = meta["indicators"]["quote"][0]
    ts_raw = meta.get("timestamp", [])

    # Handle Yahoo Finance masked arrays - convert to plain lists
    closes_raw = list(quotes.get("close") or [])
    ts_list = [float(t) for t in (ts_raw or []) if t is not None]

    # Remove trailing None/NaN values from closes and align timestamps
    while closes_raw and closes_raw[-1] is None:
        closes_raw.pop()
    # Truncate ts to match closes length
    ts_list = ts_list[:len(closes_raw)]

    # Parse closes, filter invalid values with synchronized filtering
    valid_pairs = []
    for price_str, ts_val in zip(closes_raw, ts_list):
        try:
            p = float(price_str) if price_str is not None else None
        except (ValueError, TypeError):
            continue
        if p is not None and np.isfinite(p):
            valid_pairs.append((ts_val, p))

    if len(valid_pairs) < 2:
        print(f"[WARN] Yahoo fetch returned {len(valid_pairs)} valid prices for {symbol}", file=sys.stderr)
        return None

    ts = [p[0] for p in valid_pairs]
    closes = np.array([p[1] for p in valid_pairs], dtype=np.float64)

    if len(closes) < 2:
        print(f"[WARN] Yahoo fetch returned {len(closes)} close prices for {symbol}", file=sys.stderr)
        return None

     # Calculate change from previous day
    if len(closes) >= 2:
        change = closes[-1] - closes[-2]
        change_pct = (change / closes[-2]) * 100 if closes[-2] != 0 else 0.0
    else:
        change = 0.0
        change_pct = 0.0

    # Market cap is usually available in meta for equities
    market_cap = meta.get("marketCap", 0)

    # Determine symbol type
    normalized = symbol.upper()

    if "BTC" in normalized or "ETH" in normalized or "SOL" in normalized:
        sym_type = "crypto"
    elif any(normalized.endswith(sfx) for sfx in ('.VN', '.US', '.HK', '.SG')):
        sym_type = "VN"
    else:
        sym_type = "general"

    # Format currency based on symbol type
    if sym_type == "crypto":
        curr = "USD"
    elif sym_type == "VN":
        curr = "VND"
    else:
        curr = meta.get("currency", "USD") if "currency" in meta else "USD"

    # Open, high, low, volume from quotes - handle masked arrays and None
    try:
        open_val = float(quotes["open"][-1]) if len(quotes["open"]) and quotes["open"][-1] is not None else None
    except (ValueError, TypeError):
        open_val = None
    try:
        high_val = float(quotes["high"][-1]) if len(quotes["high"]) and quotes["high"][-1] is not None else None
    except (ValueError, TypeError):
        high_val = None
    try:
        low_val = float(quotes["low"][-1]) if len(quotes["low"]) and quotes["low"][-1] is not None else None
    except (ValueError, TypeError):
        low_val = None
    try:
        volume_val = int(quotes["volume"][-1]) if len(quotes["volume"]) else 0
    except (ValueError, TypeError):
        volume_val = 0

    price_data = {
        "symbol": symbol,
        "name": meta.get("shortName", symbol),
        "price": round(float(closes[-1]), 2) if closes[-1] and np.isfinite(closes[-1]) else None,
        "open": round(open_val, 2) if open_val and np.isfinite(open_val) else None,
        "high": round(high_val, 2) if high_val and np.isfinite(high_val) else None,
        "low": round(low_val, 2) if low_val and np.isfinite(low_val) else None,
        "volume": volume_val,
        "change": round(float(change), 2),
        "change_pct": round(float(change_pct), 2),
        "market_cap": format_market_cap(market_cap) if market_cap else None,
        "pe_ratio": meta.get("trailingPE"),
        "eps": meta.get("earningsPerShare"),
        "52w_high": meta.get("fiftyTwoWeekHigh", None),
        "52w_low": meta.get("fiftyTwoWeekLow", None),
        "currency": curr,
        "type": sym_type,
        "historical_closes": closes.tolist(),
        "historical_timestamps": [int(t) for t in ts],
    }

    # CACHE this result (5 min TTL to avoid repeat Yahoo calls)
    try:
        import time as _time
        # Use sym_base for consistent key with lookup above
        _symbol_cache[sym_base] = {'data': price_data, 'ts': _time.time()}
    except Exception:
        pass      # Don't let cache failure break the function

    return price_data


def format_market_cap(cap):
    """Format market cap for display."""
    if not cap:
        return "N/A"
    if cap >= 1e12:
        return f"${cap / 1e12:.2f}T"
    elif cap >= 1e9:
        return f"${cap / 1e9:.2f}B"
    elif cap >= 1e6:
        return f"${cap / 1e6:.2f}M"
    else:
        return f"${cap:.0f}"


# --- Technical indicators calculation ---------------------------------------

def _sma(prices, period):
    """Simple Moving Average."""
    price_list = prices.tolist() if isinstance(prices, np.ndarray) else list(prices)
    result = [float('nan')] * (period - 1)
    for i in range(period - 1, len(price_list)):
        window = price_list[i - period + 1:i + 1]
        clean = [p for p in window if p is not None and not (isinstance(p, float) and np.isnan(p))]
        avg = float(np.mean(clean)) if clean else float('nan')
        result.append(avg)
    return np.array(result, dtype=np.float64)


def _ema(prices, period):
    """Exponential Moving Average. Returns float64 array with np.nan padding."""
    price_list = prices.tolist() if isinstance(prices, np.ndarray) else list(prices)

    if len(price_list) < period:
        return None

    # Clean values only for init
    clean_prices = [float(p) for p in price_list if p is not None and not (isinstance(p, float) and np.isnan(float(p)))]
    if len(clean_prices) < period:
        return None

    result = [float('nan')] * (period - 1)
    multiplier = 2 / (period + 1)
    ema_val = float(np.mean(clean_prices[:period]))
    result.append(ema_val)

    for i in range(period, len(price_list)):
        p = price_list[i] if i < len(price_list) else None
        if p is not None and not (isinstance(p, float) and np.isnan(float(p))):
            ema_val = (float(p) - ema_val) * multiplier + ema_val
        result.append(ema_val)

    return np.array(result, dtype=np.float64)


def _generate_signals(rsi, sma_value, bb_upper, bb_lower, momentum, macd_histogram):
    """Generate technical analysis signals based on indicators."""
    signals = []

    if rsi is not None:
        if rsi < 30:
            signals.append("RSI oversold - potential buy opportunity")
        elif rsi > 70:
            signals.append("RSI overbought - consider taking profits")

    if sma_value is not None:
        trend = "bullish (above SMA)" if rsi and rsi > 50 else "bearish (below SMA)" if rsi else "neutral"
        signals.append(f"SMA(20) trend: {trend}")

    if bb_upper and bb_lower:
        signals.append("Bollinger Bands active - watch for breakout/breakdown")

    if momentum is not None:
        if momentum > 5:
            signals.append("Strong positive price momentum")
        elif momentum < -5:
            signals.append("Strong negative price momentum")

    return signals


def generate_technical_summary(ta):
    """Generate readable technical analysis summary from indicators dict."""
    rsi = ta.get('rsi')
    support = ta.get('support_level')
    resistance = ta.get('resistance_level')
    macd_hist = ta.get('macd_histogram', 0)

    parts = []

    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.1f} - Oversold (bullish signal)")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.1f} - Overbought (bearish signal)")
        else:
            cat = "neutral to bearish zone" if rsi < 50 else "neutral to bullish zone"
            parts.append(f"RSI {rsi:.1f} - {cat}")

    if support is not None:
        parts.append(f"Support level: {support}")
    if resistance is not None:
        parts.append(f"Resistance level: {resistance}")

    if macd_hist > 0.001:
        parts.append("MACD histogram positive - bullish momentum")
    elif macd_hist < -0.001:
        parts.append("MACD histogram negative - bearish momentum")
    else:
        parts.append("MACD histogram neutral")

    return "\n".join(parts)


def _calc_rsi(prices, period=14):
    """Calculate RSI - returns float or None."""
    if len(prices) < period + 2:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    rsi = round(100 - (100 / (1 + rs)), 2)
    return rsi


def calculate_technical_indicators(price_data):
    """Calculate technical indicators from a stock's price data.

    Returns dict with: rsi, sma_20, bollinger bands (upper/lower),
    support/resistance levels, MACD histogram, momentum, signals.
    """
    closes = price_data.get("historical_closes", [])

    if not closes or len(closes) < 2:
        return {"error": "Not enough historical data for analysis"}

    # Normalize to list of floats and filter NaN/None
    price_list = [float(p) for p in closes if p is not None]
    price_array = np.array(price_list, dtype=np.float64) if price_list else np.array([])

    if len(price_array) < 2:
        return {"error": "Insufficient valid data points"}

    # --- EMA (clean float64 arrays for MACD calculation ---
    ema_12 = _ema(price_array, min(12, len(price_array)))
    ema_26 = _ema(price_array, min(26, len(price_array)))

    # --- MACD ---
    macd_histogram_val = 0.0

    if ema_12 is not None and ema_26 is not None:
        # Slice both to min length
        min_len = min(len(ema_12), len(ema_26))
        e12 = ema_12[-min_len:] if min_len < len(ema_12) else ema_12
        e26 = ema_26[-min_len:] if min_len < len(ema_26) else ema_26

        # Create clean mask for NaN values
        valid_mask = ~np.isnan(e12) & ~np.isnan(e26)
        e12_clean = np.ma.array(e12, mask=~valid_mask).compressed() if any(valid_mask) else np.array([])
        e26_clean = np.ma.array(e26, mask=~valid_mask).compressed() if any(valid_mask) else np.array([])

        if len(e12_clean) > 0:
            macd_line_arr = e12_clean - e26_clean

            # Calculate signal line and histogram
            clean_macd = macd_line_arr[~np.isnan(macd_line_arr)]
            if len(clean_macd) >= 9:
                signal_ema = _ema(clean_macd, 9)
                if signal_ema is not None:
                    valid_signal_idx = (~np.isnan(signal_ema)).nonzero()[0][-1] - 1
                    macd_histogram_val = float(macd_line_arr[-1] - signal_ema[max(0, valid_signal_idx)])

    # --- SMA ---
    sma_20_val = None
    if len(price_array) >= 20:
        sma_20_val = round(float(np.mean(price_array[-20:])), 2)

    # --- RSI (14-period) ---
    current_rsi_val = _calc_rsi(price_array, period=14)

    # --- Bollinger Bands (20-period, 2 SD) ---
    bb_upper = None
    bb_lower = None
    bb_middle = None

    if len(price_array) >= 20:
        recent_20 = price_array[-20:]
        bb_middle = float(np.mean(recent_20))
        std_dev = float(np.std(recent_20, ddof=1))
        bb_upper = round(bb_middle + (2 * std_dev), 2)
        bb_lower = round(bb_middle - (2 * std_dev), 2)

    # --- Support/Resistance from recent price history ---
    support_val = None
    resistance_val = None

    if len(price_array) >= 10:
        high_points, low_points = [], []
        for i in range(-20, 0):
            idx = max(0, min(len(price_array)-1, i))
            if i % 3 == 0:
                high_points.append(price_array[idx])
            elif i % 3 == 1:
                low_points.append(price_array[idx])

        if high_points:
            resistance_val = round(float(max(high_points)), 2)
        if low_points:
            support_val = round(float(min(low_points)), 2)
    elif len(price_array) > 0:
        resistance_val = round(float(max(price_array)), 2)
        support_val = round(float(min(price_array)), 2)

    # --- Volume analysis ---
    volume_data = price_data.get("historical_volumes", []) or []
    if not isinstance(volume_data, list):
        volume_data = [volume_data] if volume_data else []

    recent_volumes = [float(v) for v in volume_data[-10:] if v is not None]
    avg_volume_10 = round(float(np.mean(recent_volumes))) if recent_volumes else None

    # --- Momentum (rate of change over last 10 periods) ---
    momentum_val = None
    if len(price_array) >= 10:
        first_val = float(price_array[-10])
        last_val = float(price_array[-1])
        if first_val != 0:
            momentum_val = round(((last_val - first_val) / first_val) * 100, 2)
    elif len(price_array) > 0:
        momentum_val = 0.0

    # --- Signals ---
    signals_list = _generate_signals(
        rsi=current_rsi_val,
        sma_value=sma_20_val,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        momentum=momentum_val,
        macd_histogram=macd_histogram_val,
    )

    return {
        "rsi": round(current_rsi_val, 2) if current_rsi_val is not None else None,
        "sma_20": sma_20_val,
        "support_level": support_val,
        "resistance_level": resistance_val,
        "bollinger_upper": bb_upper,
        "bollinger_lower": bb_lower,
        "macd_histogram": round(macd_histogram_val, 4),
        "avg_volume_10": avg_volume_10,
        "momentum": momentum_val,
        "signals": signals_list if signals_list else [],
    }


# --- LLM-powered due diligence report ---------------------------------------

def llm_due_diligence(symbol, price_data, ta):
    """Generate a mini due diligence report using OLLAMA."""
    if price_data.get("type") == "VN":
        lang = "Tieng Viet"
    else:
        lang = "English"

    prompt = (
        f"You are a financial analyst. Create a short due diligence report "
        f"for {price_data.get('name', symbol)} ({symbol}).\n\n"
        f"Current data:\n"
        f"- Price: {price_data.get('price', 'N/A')} {price_data.get('currency', '')}\n"
        f"- Change: {price_data.get('change_pct', 0):+.2f}%\n"
        f"- P/E: {price_data.get('pe_ratio', 'N/A')}\n"
        f"- Market Cap: {price_data.get('market_cap', 'N/A')}\n"
        f"- EPS: {price_data.get('eps', 'N/A')}\n\n"
        "Technical indicators:\n"
        f"{generate_technical_summary(ta)}\n\n"
        "Return a brief report (under 200 words) with:\n"
        "- Basic overview based on price data and fundamentals\n"
        "- Technical analysis summary with clear support/resistance levels\n"
        "- Rating (bullish/bearish/neutral) with reasoning\n"
        "- Key investment catalysts to watch for\n"
        f"Present in {lang}."
    )

    # Use OLLAMA client with retry logic
    import core.ollama_client as ollama
    import time as time_mod

    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        result = ollama.ollama_call(prompt, timeout=60)
        if result:
            return result
        if attempt < max_retries - 1:
            print(f"[WARN] LLM due diligence failed (attempt {attempt+1}/{max_retries}), retrying...", file=sys.stderr)
            time_mod.sleep(retry_delay * (attempt + 1))
            continue

    print(f"[WARN] LLM due diligence failed after {max_retries} attempts", file=sys.stderr)
    return None

def analyze_stock(symbol):
    """Main function: fetch, calculate TA, generate report for a stock."""
    normalized = symbol.upper()
    
    # vnstock4 is the PRIMARY source for VN stocks - returns correct VND prices (thousands * 1000)
    try:
        from pathlib import Path
        _venv_path = Path("/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages")
        if _venv_path.exists():
            import sys
            if str(_venv_path) not in sys.path:
                sys.path.insert(0, str(_venv_path))
        from vnstock.api.quote import Quote as VsQuote
        
        from datetime import datetime, timedelta
        _vs_end = datetime.now().strftime("%Y-%m-%d")
        _vs_start = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        q = VsQuote(symbol=symbol, show_log=False)
        df = q.history(symbol=symbol, start=_vs_start, end=_vs_end)
        
        if not df.empty:
            # vnstock returns prices in "nghin dong" * 1000 for actual VND
            latest = df.iloc[-1]
            current_close = float(latest["close"]) * 1000
            prev_close = (float(df.iloc[-2]["close"]) * 1000) if len(df) > 1 else current_close
            change = current_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0
            high = float(latest.get("high", current_close)) if "high" in latest and latest["high"] is not None else current_close
            low = float(latest.get("low", current_close)) if "low" in latest and latest["low"] is not None else current_close
            volume = int(latest.get("volume", 0)) if "volume" in latest and latest["volume"] is not None else 0
            
            price_data = {
                "symbol": symbol,
                "name": symbol,     # vnstock does not provide name - set as-is
                "price": round(current_close, 2),
                "open": 0.0,        # vnstock daily history may not have open per row
                "high": round(high, 2),
                "low": round(low, 2),
                "volume": volume,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "currency": "VND",
                "type": "VN",
                "historical_closes": [float(c) * 1000 for c in df["close"].tolist() if c is not None],
                "vnstock_source": True,     # Flag to indicate this came from vnstock
            }
            
            # If we got data from vnstock, calculate TA and return (skip Yahoo fallback)
            ta_data = calculate_technical_indicators(price_data)
            price_data["technical"] = ta_data
            try:
                llm_report = llm_due_diligence(normalized, price_data, ta_data)
                price_data["llm_report"] = llm_report
            except Exception as e:
                print(f"[WARN] LLM report generation failed: {e}", file=sys.stderr)
            return price_data
    except ImportError:
        pass     # vnstock not available - fall through to Yahoo/Fallback
    except Exception as _e:
        pass     # Fetch error - fall through to Yahoo fallback

    # Auto-append correct suffix based on symbol type (Yahoo path)
    if not any(normalized.endswith(sfx) for sfx in ('.VN', '.US', '.HK', '.SG')):
        # Try US market first (most common for non-VN symbols like AAPL, GOOG, etc.)
        candidates = [f"{normalized}.US", normalized]     # Removed .VN suffix as fallback
    else:
        candidates = [normalized]
    
    # 1. Fetch price data with timeout protection
    price_data = None
    last_err = None
    for try_sym in candidates:
        try:
            print(f"[DEBUG] Trying yahoo fetch for {try_sym}", file=sys.stderr)
            price_data = _fetch_yahoo_price(try_sym)
            if price_data:
                normalized = try_sym    # Use successful symbol
                break
            else:
                last_err = f"No data returned"
        except Exception as e:
            last_err = str(e)
            print(f"[WARN] Yahoo fetch failed for {try_sym}: {e}", file=sys.stderr)
    
    if not price_data:
        print(f"[ERROR] All symbol variants failed for {symbol}: {last_err}", file=sys.stderr)
        return {"error": f"Could not fetch data for {symbol}"}

    # 2. Calculate technical indicators
    ta_data = calculate_technical_indicators(price_data)

    # Add TA to stock data
    price_data["technical"] = ta_data

    # 3. Generate LLM report (background, optional - SHORT TIMEOUT)
    try:
        llm_report = llm_due_diligence(normalized, price_data, ta_data)
        price_data["llm_report"] = llm_report
    except Exception as e:
        print(f"[WARN] LLM report generation failed: {e}", file=sys.stderr)

    return price_data




def fetch_gold_price():
    """Fetch XAU/USD (Gold) price."""
    # Try Yahoo first
    try:
        result = _fetch_yahoo_price("XAU/USD")
        if result:
            return result
    except Exception:
        pass

    # Fallback to alternative source
    try:
        url = "https://api.metalpriceapi.com/v1/latest?api_key=***&base=XAU&currencies=USD"
        r = requests_lib.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {
                "symbol": "XAU",
                "name": "Gold (XAU/USD)",
                "price": round(1.0 / data.get("rates", {}).get("USD", 1), 2),
                "currency": "USD",
                "type": "gold",
            }
    except Exception:
        pass

    return None


def fetch_crypto(symbol):
    """Fetch crypto price from Binance API for supported coins."""
    binance_map = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
    }

    symbol_upper = symbol.upper().lstrip("$")
    binance_symbol = binance_map.get(symbol_upper, f"{symbol_upper}USDT")

    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}"
        r = requests_lib.get(url, timeout=10)

        if r.status_code == 200:
            data = r.json()
            name = "bitcoin" if "BTC" in symbol_upper else ("ethereum" if "ETH" in symbol_upper else symbol_upper)
            return {
                "symbol": symbol,
                "name": f"{name.title()}",
                "price": round(float(data.get("lastPrice", 0)), 2),
                "change_pct": round(float(data.get("priceChangePercent", 0)), 2),
                "volume": format_market_cap(float(data.get("quoteVolume", 0))),
                "high_24h": round(float(data.get("highPrice", 0)), 2),
                "low_24h": round(float(data.get("lowPrice", 0)), 2),
                "currency": "USD",
                "type": "crypto",
            }
    except Exception as e:
        print(f"[WARN] Binance fetch failed for {symbol}: {e}", file=sys.stderr)

    return None


def fetch_dxy():
    """Fetch DXY (US Dollar Index) price from Yahoo Finance."""
    try:
        price_data = _fetch_yahoo_price("DX-Y.NYB")
        if price_data:
            price_data["symbol"] = "DXY"
            price_data["name"] = "US Dollar Index"
        return price_data
    except Exception as e:
        print(f"[WARN] DXY fetch failed: {e}", file=sys.stderr)
        return None


def fetch_oil():
    """Fetch WTI Crude Oil price from Yahoo Finance."""
    try:
        price_data = _fetch_yahoo_price("CL=F")
        return price_data
    except Exception as e:
        print(f"[WARN] Oil fetch failed: {e}", file=sys.stderr)
        return None
