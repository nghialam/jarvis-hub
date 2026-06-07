"""
market_service.py -- Unified market data service for Jarvis Hub.

Encapsulates ALL external data fetching (vnstock4 primary, Yahoo Finance fallback,
Binance crypto, Vietcombank FX) with a single per-symbol TTL cache + retry logic.

Usage:
    svc = MarketService(db)                   # db is optional for persistence
    result = svc.analyze_stock("VNM")         # stock analysis with TA
    indices = svc.get_indices()                # global + VN indices snapshot
    btc = svc.get_crypto_price("BTC")          # crypto price
    gold = svc.get_gold_price()                # XAU/USD price
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from html import unescape as html_unescape

import numpy as np
import requests


csv_module = None
try:
    import csv as csv_module  # noqa
except ImportError:
    pass

# vnstock4 provider import (lazy-loaded for graceful degradation)
_vnstock_provider = None


def _get_vnstock_provider():
    """Lazy-load vnstock4 provider."""
    global _vnstock_provider
    if _vnstock_provider is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import vnstock4_provider as vsp
            _vnstock_provider = vsp
        except ImportError:
            _vnstock_provider = None
    return _vnstock_provider


# Cache Manager (inline)

class MarketCache:
    """Thread-safe per-key TTL cache for market data."""

    DEFAULT_TTLS = {
        'stock': 300,         # Yahoo stock prices: 5 min
        'crypto': 60,         # Binance: 1 min
        'gold': 300,          # Gold: 5 min
        'dxy': 300,           # DXY: 5 min
        'oil': 300,           # Oil: 5 min
        'indices': 300,       # Market indices: 5 min
        'fx_rates': 60,       # FX rates: 1 min
    }

    def __init__(self):
        self._store = {}     # key -> {data, ts}
        self._ttls = dict(self.DEFAULT_TTLS)
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, symbol, category):
        """Get cached data if fresh; else None (cache miss)."""
        key = f'{category}:{symbol.upper()}'
        entry = self._store.get(key)
        if not entry:
            self._misses += 1
            return None
        ttl = self._ttls.get(category, 300)
        age = datetime.utcnow().timestamp() - entry['ts']
        if age >= ttl:
            del self._store[key]
            self._evictions += 1
            self._misses += 1
            return None
        self._hits += 1
        return entry

    def put(self, symbol, category, data, ttl=None):
        """Store result with TTL."""
        key = f'{category}:{symbol.upper()}'
        if ttl is None:
            ttl = self._ttls.get(category, 300)
        self._store[key] = {
            'data': data,
            'ts': datetime.utcnow().timestamp(),
            'ttl': ttl,
        }

    def clear_key(self, symbol, category):
        """Force-invalidate a key."""
        key = f'{category}:{symbol.upper()}'
        self._store.pop(key, None)

    @property
    def cache_stats(self):
        """Return hit/miss counters for monitoring."""
        total = self._hits + self._misses
        return {
            'hits': int(self._hits),
            'misses': int(self._misses),
            'hit_ratio_pct': round(self._hits / total * 100, 1) if total > 0 else 0,
            'evictions': int(self._evictions),
            'cached_keys': len(self._store),
        }


# Yahoo Finance helper

_YAHOO_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Accept': 'application/json',
}


def _fmt_market_cap(cap):
    if not cap:
        return 'N/A'
    if cap >= 1e12:
        return f'${cap / 1e12:.2f}T'
    if cap >= 1e9:
        return f'${cap / 1e9:.2f}B'
    if cap >= 1e6:
        return f'${cap / 1e6:.2f}M'
    return f'${cap:.0f}'


def _parse_yahoo_chart(resp_json, symbol):
    """Parse a Yahoo chart JSON response into a normalized price-data dict."""
    result_list = resp_json.get('chart', {}).get('result')
    if not result_list:
        return None

    meta = result_list[0].get('meta', {})
    quotes = result_list[0]['indicators']['quote'][0]

    # Extract closes / timestamps, strip trailing Nones
    closes_raw = list(quotes.get('close') or [])
    ts_raw = result_list[0].get('timestamp', [])
    ts_list = [float(t) for t in (ts_raw or []) if t is not None]

    while closes_raw and closes_raw[-1] is None:
        closes_raw.pop()
    ts_list = ts_list[:len(closes_raw)]

    pairs = []
    for p, t in zip(closes_raw, ts_list):
        try:
            price = float(p) if p is not None else None
        except (ValueError, TypeError):
            continue
        if price is not None and np.isfinite(price):
            pairs.append((t, price))

    if len(pairs) < 2:
        return None

    closes = np.array([p for _, p in pairs], dtype=np.float64)
    timestamps = [int(t) for t, _ in pairs]

    change = float(closes[-1] - closes[-2])
    change_pct = (change / closes[-2]) * 100 if closes[-2] else 0.0

    # OHLCV helper
    def _last(series):
        try:
            v = series[-1] if len(series) > 0 and series[-1] is not None else None
            return float(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    # Determine type / currency
    sym_upper = symbol.upper()
    if any(c in sym_upper for c in ('BTC', 'ETH', 'SOL', 'BNB')):
        sym_type = 'crypto'
    elif any(sym_upper.endswith(sfx) for sfx in ('.VN', '.US', '.HK', '.SG')):
        sym_type = 'stock_vn'
    else:
        sym_type = 'general'

    return {
        'symbol': symbol,
        'name': meta.get('shortName', symbol),
        'price': round(float(closes[-1]), 2) if np.isfinite(closes[-1]) else None,
        'open': _last(quotes['open']),
        'high': _last(quotes['high']),
        'low': _last(quotes['low']),
        'volume': int(quotes['volume'][-1]) if quotes.get('volume') and len(quotes['volume']) > 0 else 0,
        'change': round(change, 2),
        'change_pct': round(change_pct, 2),
        'market_cap': _fmt_market_cap(meta.get('marketCap')) if meta.get('marketCap') else None,
        'pe_ratio': meta.get('trailingPE'),
        'eps': meta.get('earningsPerShare'),
        '52w_high': meta.get('fiftyTwoWeekHigh'),
        '52w_low': meta.get('fiftyTwoWeekLow'),
        'currency': 'USD' if sym_type == 'crypto' else (meta.get('currency') or 'USD'),
        'type': sym_type,
        'historical_closes': closes.tolist(),
        'historical_timestamps': timestamps,
    }


def _parse_yahoo_csv(csv_text, symbol):
    """Fallback: parse CSV download from Yahoo."""
    if csv_module is None:
        return None
    reader = csv_module.DictReader(csv_text.splitlines())
    rows = []
    for row in reader:
        try:
            ts = int(datetime.strptime(row['Date'], '%Y-%m-%d').timestamp()) if 'Date' in row else 0
            price = float(row.get('Close', 0))
            if np.isfinite(price):
                rows.append((ts, price))
        except (ValueError, KeyError, TypeError):
            continue
    if len(rows) < 2:
        return None
    closes = np.array([p for _, p in rows], dtype=np.float64)
    change = float(closes[-1] - closes[-2])
    change_pct = (change / closes[-2]) * 100 if closes[-2] else 0.0
    return {
        'symbol': symbol, 'name': symbol,
        'price': round(float(closes[-1]), 2),
        'open': round(float(closes[-2]), 2) if len(closes) >= 2 else None,
        'high': round(float(max(closes)), 2),
        'low': round(float(min(closes)), 2),
        'volume': 0, 'change': round(change, 2),
        'change_pct': round(change_pct, 2),
        'currency': 'USD', 'type': 'general',
        'historical_closes': closes.tolist(),
        'historical_timestamps': [t for t, _ in sorted(rows)],
    }


def _fetch_yahoo(symbol, timeout_sec=8):
    """Fetch chart data from Yahoo Finance. Returns dict or None."""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d'
    try:
        r = requests.get(url, headers=_YAHOO_HEADERS, timeout=timeout_sec)
        if r.status_code == 200:
            return _parse_yahoo_chart(r.json(), symbol)
    except Exception:
        pass

    # Fallback to CSV download endpoint
    url2 = f'https://query1.finance.yahoo.com/v7/finance/download/{symbol}?period1=&period2=&interval=1d&events=history'
    try:
        r2 = requests.get(url2, headers=_YAHOO_HEADERS, timeout=timeout_sec + 2)
        if r2.status_code == 200:
            return _parse_yahoo_csv(r2.text, symbol)
    except Exception:
        pass

    return None


# Technical Indicators

def _sma(prices, period):
    """Simple Moving Average."""
    price_list = prices.tolist() if isinstance(prices, np.ndarray) else list(prices)
    result = [float('nan')] * (period - 1)
    for i in range(period - 1, len(price_list)):
        window = price_list[i - period + 1:i + 1]
        clean = [p for p in window if p is not None and np.isfinite(float(p))]
        result.append(float(np.mean(clean)) if clean else float('nan'))
    return np.array(result, dtype=np.float64)


def _ema(prices, period):
    """Exponential Moving Average."""
    price_list = prices.tolist() if isinstance(prices, np.ndarray) else list(prices)
    clean_prices = [float(p) for p in price_list if p is not None and np.isfinite(float(p))]
    if len(clean_prices) < period:
        return None
    result = [float('nan')] * (period - 1)
    multiplier = 2 / (period + 1)
    ema_val = float(np.mean(clean_prices[:period]))
    result.append(ema_val)
    for i in range(period, len(price_list)):
        p = price_list[i] if i < len(price_list) else None
        if p is not None and np.isfinite(float(p)):
            ema_val = (float(p) - ema_val) * multiplier + ema_val
        result.append(ema_val)
    return np.array(result, dtype=np.float64)


def _calc_rsi(prices, period=14):
    """RSI (Relative Strength Index). Returns float or None."""
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
    return round(100 - (100 / (1 + rs)), 2)


def _calculate_technical_indicators(price_data):
    """Calculate 10+ TA indicators from price-data dict."""
    closes = np.array([float(p) for p in price_data.get('historical_closes', []) if p is not None], dtype=np.float64)
    if len(closes) < 2:
        return {'error': 'Not enough data'}

    # SMA-20
    sma_20 = round(float(np.mean(closes[-20:])), 2) if len(closes) >= 20 else None

    # EMA for MACD (EMA-12, EMA-26)
    ema_12 = _ema(closes, min(12, len(closes)))
    ema_26 = _ema(closes, min(26, len(closes)))
    macd_histogram = 0.0
    if ema_12 is not None and ema_26 is not None:
          
          # Align arrays by length before subtraction
        e12_arr = np.ma.array(ema_12, mask=~np.isfinite(np.array(ema_12))).compressed()
        e26_arr = np.ma.array(ema_26, mask=~np.isfinite(np.array(ema_26))).compressed()
        
          # Trim both to the same length (use the shorter)
        min_len = min(len(e12_arr), len(e26_arr))
        if min_len > 0:
            e12_arr = e12_arr[-min_len:]
            e26_arr = e26_arr[-min_len:]
            macd_line = e12_arr - e26_arr
            
              # MACD histogram: signal line is EMA(9) of MACD line
            clean_macd = macd_line[~np.isnan(macd_line)]
            if len(clean_macd) >= 9:
                signal_ema = _ema(clean_macd, 9)
                if signal_ema is not None:
                    last_sig_idx = max(0, (~np.isnan(signal_ema)).nonzero()[0][-1] - 1)
                    macd_histogram = round(float(macd_line[-1] - signal_ema[last_sig_idx]), 4)

    # RSI-14
    rsi_val = _calc_rsi(closes, period=14)

    # Bollinger Bands (20-period, 2 SD)
    bb_upper = bb_lower = None
    if len(closes) >= 20:
        recent = closes[-20:]
        mean_20 = float(np.mean(recent))
        std_20 = float(np.std(recent, ddof=1))
        bb_upper = round(mean_20 + 2 * std_20, 2)
        bb_lower = round(mean_20 - 2 * std_20, 2)

    # Support / Resistance from last ~20 candles
    support_val = resistance_val = None
    if len(closes) >= 10:
        highs, lows = [], []
        for i in range(-20, 0):
            idx = min(len(closes) - 1, abs(i))
            if (-i) % 3 == 0:
                highs.append(closes[idx])
            elif (-i) % 3 == 1:
                lows.append(closes[idx])
        resistance_val = round(float(max(highs)), 2) if highs else None
        support_val = round(float(min(lows)), 2) if lows else None

    # Momentum (10-day rate of change)
    momentum_val = None
    if len(closes) >= 10:
        first_val = float(closes[-10])
        last_val = float(closes[-1])
        if first_val != 0:
            momentum_val = round(((last_val - first_val) / first_val) * 100, 2)

    # Volume profile
    vol_data = price_data.get('historical_volumes') or []
    if not isinstance(vol_data, list):
        vol_data = [vol_data] if vol_data else []
    recent_vol = [float(v) for v in vol_data[-10:] if v is not None]
    avg_vol_10 = round(float(np.mean(recent_vol))) if recent_vol else None

    # Generate signals
    signals = []
    if rsi_val:
        if rsi_val < 30:
            signals.append('RSI oversold - buy opportunity')
        elif rsi_val > 70:
            signals.append('RSI overbought - watch for reversal')
    if sma_20 and rsi_val is not None:
        trend = 'bullish (above SMA20)' if rsi_val > 50 else ('bearish (below SMA20)' if rsi_val < 50 else 'neutral')
        signals.append(f'SMA20 trend: {trend}')
    if bb_upper and bb_lower:
        signals.append('Bollinger Bands active - watch for breakout')
    if momentum_val is not None:
        if abs(momentum_val) > 5:
            direction = 'positive' if momentum_val > 0 else 'negative'
            signals.append(f'Strong momentum ({direction})')

    return {
        'rsi': rsi_val,
        'sma_20': sma_20,
        'support_level': support_val,
        'resistance_level': resistance_val,
        'bollinger_upper': bb_upper,
        'bollinger_lower': bb_lower,
        'macd_histogram': macd_histogram,
        'avg_volume_10': avg_vol_10,
        'momentum': momentum_val,
        'signals': signals if signals else [],
    }


# ============================================================================
#  MARKET SERVICE - unified facade for all market data operations
# ============================================================================

class MarketService:
    """Entrance point for ALL market data in Jarvis Hub.

    Wraps Yahoo Finance (stocks), Binance (crypto), Vietcombank (FX),
    and global index endpoints with unified TTL cache + retries.

    Parameters:
        db: Optional Database instance for persistent market_cache table.
    """

    YAHOO_TIMEOUT = 8       # seconds per Yahoo call
    BINANCE_TIMEOUT = 10    # seconds per Binance call

    def __init__(self, db=None):
        self.cache = MarketCache()
        self.db = db

    def analyze_stock(self, symbol):
        """Analyze a stock/crypto: fetch price + compute TA indicators.

        Priority: vnstock4 (VN stocks) > Yahoo Finance (international).
        Results cached for TTL seconds.
        """
        normalized = self._normalize_symbol(symbol)
        sym_upper = symbol.upper()

        # Skip vnstock4 if the symbol looks international
        is_vn_stock = (
            sym_upper in ('VN', '.VN') or 
            self._is_vietnamese_symbol(symbol, normalized)
        )

        price_data = None

        # Try vnstock4 first for Vietnamese stocks
        if is_vn_stock:
            vs_provider = _get_vnstock_provider()
            if vs_provider and hasattr(vs_provider, 'fetch_daily_ohlcv'):
                try:
                    price_data = vs_provider.fetch_daily_ohlcv(
                        normalized, days=60, use_vci=False, verbose=False
                    )
                    if price_data:
                        price_data['history_source'] = 'vnstock4'
                except Exception:
                    pass

        # Fallback to Yahoo Finance for international stocks or if vnstock4 fails
        if not price_data:
            candidates = [normalized]
            if not any(sym_upper.endswith(sfx) for sfx in ('.VN', '.US', '.HK', '.SG')):
                candidates = [f'{sym_upper}.US', normalized, f'{sym_upper}.VN']

            for try_sym in candidates:
                try:
                    price_data = _fetch_yahoo(try_sym, timeout_sec=self.YAHOO_TIMEOUT)
                    if price_data:
                        price_data['history_source'] = 'yahoo'
                        break
                except Exception:
                    pass

        if not price_data:
            return {'error': f'Could not fetch data for {symbol} (tried vnstock4 + Yahoo)'}

        # Compute technical indicators
        ta = _calculate_technical_indicators(price_data)

        # Merge TA into top-level response and also keep in 'technical' sub-object
        price_data['rsi'] = ta.get('rsi')
        price_data['sma_20'] = ta.get('sma_20')
        price_data['support_level'] = ta.get('support_level')
        price_data['resistance_level'] = ta.get('resistance_level')
        price_data['bollinger_upper'] = ta.get('bollinger_upper')
        price_data['bollinger_lower'] = ta.get('bollinger_lower')
        price_data['macd_histogram'] = ta.get('macd_histogram')
        price_data['momentum'] = ta.get('momentum')

        # Keep technical dict for structured responses / frontend use
        price_data['technical'] = ta

        # Persist to DB market_cache if db available
        if self.db:
            try:
                self.db.save_market_data(symbol, price_data, ttl_minutes=5)
            except Exception:
                pass

        # Cache in-memory with 5 min TTL
        self.cache.put(normalized, 'stock', price_data, ttl=300)

        return price_data

    def _is_vietnamese_symbol(self, symbol, normalized):
        """Heuristic: decide if a symbol is likely a VN stock."""
        # If the original symbol had no extension, treat as VN stock
        if normalized == symbol.upper():
            return True
        # Known VN exchanges/symbols patterns
        vn_patterns = ['.VN', 'HNX', 'UPCOM', 'HOSE', 'VNM', 'VIC', 'VCB', 'VPB']
        sym = symbol.upper()
        for p in vn_patterns:
            if p in sym:
                return True
        # Common VN tickers are 2-5 uppercase letters
        stripped = re.sub(r'[^A-Z]', '', sym)
        return len(stripped) >= 2 and len(stripped) <= 6 and not any(
            stripped.startswith(c) for c in ['AAPL', 'GOOG', 'TSLA', 'AMZN', 'MSFT', 'META', 'NVDA', 'NFLX']
        )


    def get_crypto_price(self, symbol):
        """Fetch 24h price from Binance API."""
        sym_upper = symbol.upper().lstrip('$')
        binance_map = {'BTC': 'BTCUSDT', 'ETH': 'ETHUSDT', 'SOL': 'SOLUSDT', 'BNB': 'BNBUSDT'}
        b_symbol = binance_map.get(sym_upper, f'{sym_upper}USDT')

        cached = self.cache.get(b_symbol, 'crypto')
        if cached:
            return cached

        try:
            url = f'https://api.binance.com/api/v3/ticker/24hr?symbol={b_symbol}'
            r = requests.get(url, timeout=self.BINANCE_TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                name_sym = 'Bitcoin' if 'BTC' in sym_upper \
                    else ('Ethereum' if 'ETH' in sym_upper else symbol.title())
                result = {
                    'symbol': symbol,
                    'name': name_sym,
                    'price': round(float(data.get('lastPrice', 0)), 2),
                    'change_pct': round(float(data.get('priceChangePercent', 0)), 2),
                    'volume': data.get('quoteVolume'),
                    'high_24h': round(float(data.get('highPrice', 0)), 2),
                    'low_24h': round(float(data.get('lowPrice', 0)), 2),
                    'currency': 'USD',
                    'type': 'crypto',
                }
                self.cache.put(b_symbol, 'crypto', result, ttl=60)
                return result
        except Exception as e:
            print(f'[WARN] Binance fetch failed for {symbol}: {e}', file=sys.stderr)

        return None

    def get_gold_price(self):
        """Fetch gold spot price via Yahoo or fallback sources."""
        cached = self.cache.get('XAU/USD', 'gold')
        if cached:
            return cached

        # Try direct Yahoo API with proper headers - GC=F is most reliable
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        candidates = ['GC=F', 'GLD', 'XAUUSD=X']

        for sym in candidates:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code != 200:
                    print(f"[GOLD] Yahoo returned {r.status_code} for {sym}, trying next...")
                    continue

                result = r.json().get('chart', {}).get('result')
                if not result:
                    print(f"[GOLD] No chart result for {sym}")
                    continue

                meta = result[0].get('meta', {})
                price = meta.get('regularMarketPrice')
                prev_close = meta.get('previousClose')
                currency = meta.get('currency', 'USD')

                if price and prev_close:
                    try:
                        price_f = float(price)
                        prev_close_f = float(prev_close)
                        if price_f > 0 and prev_close_f > 0:
                            change_pct = round((price_f - prev_close_f) / prev_close_f * 100, 2)
                            data = {
                                'symbol': 'XAU/USD',
                                'name': f'Gold ({sym})',
                                'price': price_f,
                                'change_pct': change_pct,
                                'currency': currency,
                                'type': 'gold',
                            }
                            self.cache.put('XAU/USD', 'gold', data, ttl=300)
                            print(f"[GOLD] Fetched {sym}: ${price_f} ({change_pct:+.2f}%)")
                            return data
                    except (TypeError, ValueError):
                        pass
                else:
                    print(f"[GOLD] Invalid price data for {sym}: price={price}, prev_close={prev_close}")

            except Exception as e:
                print(f"[GOLD] Failed for {sym}: {e}")
                continue

        print("[GOLD] All Yahoo sources failed, returning None")
        return None

    def get_market_indices(self):
        """Fetch VN-Index + global indices in parallel. Returns nested dict."""
        cached = self.cache.get('indices_all', 'indices')
        if cached:
            return cached

        name_map = {
            '^VNINDEX.VN': 'VN-Index',
            '^GSPC': ('S&P 500', 'US'),
            '^DJI': ('Dow Jones', 'US'),
            '^IXIC': ('NASDAQ', 'US'),
            '^N225': ('Nikkei 225', 'Asia'),
            '^HSI': ('Hang Seng', 'Asia'),
            '^KS11': ('KOSPI', 'Asia'),
            '^GDAXI': ('DAX', 'Europe'),
            '^FTSE': ('FTSE 100', 'Europe'),
        }

        vn_indices = {}
        global_indices = {}
        failures = []

        # VN-Index (sequential)
        try:
            r = _fetch_yahoo('^VNINDEX.VN', timeout_sec=5)
            if r:
                vn_indices['VN-Index'] = {
                    'price': r.get('price'),
                    'change': r.get('change'),
                    'change_pct': r.get('change_pct'),
                    'prev_close': None,
                }
        except Exception:
            failures.append('VN-Index')

        # Global indices (parallel)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def fetch_index(sym):
            try:
                r = _fetch_yahoo(sym, timeout_sec=5)
                display = name_map.get(sym, (sym, 'Unknown'))
                if r:
                    return (display, {
                        'price': r.get('price'),
                        'change': r.get('change'),
                        'change_pct': r.get('change_pct'),
                    })
                else:
                    return (display, None)
            except Exception:
                return (name_map.get(sym, (sym, '')), None)

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fetch_index, s): s for s in name_map}
            for f in as_completed(futures):
                try:
                    display, data = f.result()
                    if isinstance(display, str):  # VN case
                        if data:
                            vn_indices[display] = data
                        else:
                            failures.append(f'VN {display}')
                    elif data:  # Global index: (name, region)
                        name = display[0]
                        global_indices[name] = data
                    else:
                        if isinstance(display, tuple) and len(display) > 0:
                            failures.append(display[0])
                except Exception:
                    pass

        result = {
            'vn_indices': vn_indices,
            'global_indices': global_indices,
        }
        self.cache.put('indices_all', 'indices', result, ttl=300)
        return result

    def get_exchange_rates(self):
        """Get USD/VND and other FX rates from Vietcombank."""
        cached = self.cache.get('vietcombank', 'fx_rates')
        if cached:
            return cached

        rate_obj = {'source': 'vietcombank', 'updated': 'N/A'}
        try:
            resp = requests.get(
                'https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia',
                timeout=10, headers=_YAHOO_HEADERS,
            )
            if resp.status_code == 200:
                match = re.search(r'id="currentDataExchange"\s+value="([^"]+)"', resp.text)
                if match:
                    raw = html_unescape(match.group(1))
                    data = json.loads(raw)
                    for curr in (data if isinstance(data, dict) else {}).get('Data', []):
                        code = curr.get('currencyCode', '')
                        rate_obj[code] = {
                            'cash': round(float(curr.get('cash', 0)) / 100, 4),
                            'transfer': round(float(curr.get('transfer', 0)) / 100, 4),
                            'sell': round(float(curr.get('sell', 0)) / 100, 4),
                        }
        except Exception as e:
            print(f'[WARN] FX rates fetch failed: {e}', file=sys.stderr)

        self.cache.put('vietcombank', 'fx_rates', rate_obj, ttl=60)
        return rate_obj

    def refresh_all_market_data(self):
        """Refresh ALL data sources immediately. Returns dict of results."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _safe_fetch(fn, name):
            try:
                result = fn()
                status = 'ok' if result is not None else 'empty'
                return (name, status, result)
            except Exception as e:
                return (name, f'error: {str(e)}', None)

        results = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            funcs = [
                ('vn_indices', self.get_market_indices),
                ('rates', self.get_exchange_rates),
                ('gold', self.get_gold_price),
                ('BTC', lambda: self.get_crypto_price('BTC')),
                ('ETH', lambda: self.get_crypto_price('ETH')),
                ('SOL', lambda: self.get_crypto_price('SOL')),
            ]
            futures = {ex.submit(fn, name): name for name, fn in funcs}
            for f in as_completed(futures):
                try:
                    name, status, result = f.result()
                    results[name] = {'status': status, 'data': result}
                except Exception:
                    pass

        # Invalidate all caches so next call reloads fresh
        self.cache.clear_key('indices_all', 'indices')
        self.cache.clear_key('vietcombank', 'fx_rates')

        return results

    @property
    def cache_stats(self):
        """Return cache statistics."""
        return self.cache.cache_stats

    @staticmethod
    def _normalize_symbol(symbol):
        """Normalize symbol: strip extension, upper case."""
        sym = symbol.upper().strip()
        for suffix in ('.VN', '.US', '.HK', '.SG'):
            if sym.endswith(suffix):
                return sym[:-len(suffix)]
        return sym

# ── Module-level singleton instance ───────────────────────────────────────────
_service = None


def _get_service():
    global _service
    if _service is None:
        from core.db import Database as _DB
        db_inst = None
        try:
            cfg_mod = __import__('core.config', fromlist=['load_config'])
            cfg_data = cfg_mod.load_config() if hasattr(cfg_mod, 'load_config') else {}
            db_path = cfg_data.get('db_path', ':memory:')
            db_inst = _DB(db_path) if db_path != ':memory:' else _DB()
        except Exception:
            db_inst = None
        _service = MarketService(db=db_inst)
    return _service


def analyze_stock(symbol):
     return _get_service().analyze_stock(symbol)


def fetch_crypto(symbol):
     return _get_service().get_crypto_price(symbol)


def fetch_gold():
     return _get_service().get_gold_price()


def fetch_dxy():
     from concurrent.futures import ThreadPoolExecutor, as_completed
     
     dxy_map = {'^DXY': 'US Dollar Index'}
     results = {}
     try:
         with ThreadPoolExecutor(max_workers=1) as ex:
             f = ex.submit(_fetch_yahoo, '^DXY', timeout_sec=5)
             results = f.result() or {}
     except Exception as e:
         print('[WARN] DXY fetch failed: %s' % e, file=sys.stderr)
     
     if 'chart' in str(type(results)) if isinstance(results, dict) and 'result' in results else False:
         try:
             meta = results.get('chart', {}).get('result', [{}])[0].get('meta', {})
             price = meta.get('regularMarketPrice')
             prev_close = meta.get('previousClose')
             if price and prev_close and float(prev_close) > 0:
                 return {
                     'symbol': 'DXY',
                     'name': 'US Dollar Index',
                     'price': round(float(price), 2),
                     'change_pct': round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                     'currency': 'USD',
                     'type': 'dxy',
                 }
         except Exception:
             pass
     elif isinstance(results, dict):
         return results
     return None


def fetch_oil():
     results = {}
     try:
         results = _fetch_yahoo('CL=F', timeout_sec=5) or {}
     except Exception as e:
         print('[WARN] Oil fetch failed: %s' % e, file=sys.stderr)
     
     if 'result' in results and isinstance(results.get('chart'), dict):
         try:
             meta = results.get('chart', {}).get('result', [{}])[0].get('meta', {})
             price = meta.get('regularMarketPrice')
             prev_close = meta.get('previousClose')
             if price and prev_close and float(prev_close) > 0:
                 return {
                     'symbol': 'WTI',
                     'name': 'Crude Oil (WTI)',
                     'price': round(float(price), 2),
                     'change_pct': round((float(price) - float(prev_close)) / float(prev_close) * 100, 2),
                     'currency': 'USD',
                     'type': 'oil',
                 }
         except Exception:
             pass
     elif isinstance(results, dict):
         return results
     return None


def calculate_technical_indicators(price_data):
     return _calculate_technical_indicators(price_data)
