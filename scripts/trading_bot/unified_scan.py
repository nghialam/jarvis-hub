#!/usr/bin/env python3
"""
UnifiedScan - Single source of truth for all Jarvis scan outputs.

Both intraday_scan_poller.py and scan_reporter.py will use this module 
to fetch data, run signal analysis, and cache results atomically.

Usage:
    from unified_scan import UnifiedScan
    
    scan = UnifiedScan()
    # Full scan of all watchlist symbols (cached to disk)
    results = scan.full_scan()          # returns dict{sym: {signal, confidence, data...}}
    
    # Single symbol
    result = scan.scan_symbol('VCI')    # returns signal dict for one stock
    
    # Clear cache (e.g., after market close)
    scan.clear_cache()
"""

import json
import os
import sys
import signal
from datetime import datetime
from pathlib import Path


# -- Timeout config for per-symbol scans (in seconds) --
SYMBOL_SCAN_TIMEOUT = 30

def _timeout_handler(signum, frame):
    raise TimeoutError(f"Symbol scan timed out after {SYMBOL_SCAN_TIMEOUT}s")


# flake8: noqa / pyright: ignore   # module-level conditional imports
try:
    from market_data import fetch_stock_data
    from signal_engine import SignalEngine
except (ImportError, ModuleNotFoundError):
    pass


# -- Cache location --

CACHE_DIR = Path(os.path.expanduser("~")) / ".hermes" / "jarvis_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
SCAN_RESULT_CACHE = CACHE_DIR / "jarvis_scan_result.json"


# -- Atomic file operations --

def _atomic_write(data, path):
    """Write data to JSON file atomically."""
    tmp_path = str(path) + ".tmp"
    final_path = str(path)
    with open(tmp_path, 'w') as f:
        json.dump(data, f, default=str)
    os.rename(tmp_path, final_path)


def _atomic_read(path):
    """Read JSON file with basic error handling."""
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


# -- Unified Scan Engine --

class UnifiedScan:
    """Single scan pipeline used by both poller and reporter."""

    def _load_watchlist(self):
        watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
        try:
            with open(watchlist_path) as f:
                data = json.load(f)
                stocks = data.get("stocks", [])
                if stocks:
                    return stocks
        except Exception as e:
            print(f"[WARN] watchlist load failed: {e}", file=sys.stderr)
        return ["VCI","VIC","VCB","DGW","FTS","TCB","HCM","PDR","NLG","DXG",
                 "BMP","VGI","FRT","VIX","CTD","MBB","FPT","VHM","PVS","EVF"]

    def _detect_1h_pivots(self, symbol):
        """Run Pocket Pivot 1H detection for a single symbol.

        Uses vnstock4 Market().equity(symbol).ohlcv(resolution="1H") format.
         """
        try:
            from vnstock import Market
            import pandas as pd
            from datetime import timedelta, datetime

             # Fetch hourly candles from vnstock4 for the last 15 trading days
            eq = Market().equity(symbol=symbol.upper())
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

            df = eq.ohlcv(
                start=start_date,
                end=end_date,
                resolution="1H",  # Hourly candles for pocket pivot detection
             )

            if not isinstance(df, pd.DataFrame) or len(df) == 0:
                return None

            df = df.copy()
            df['time'] = pd.to_datetime(df.get('time', df.index))
            df = df.sort_values('time', ascending=True).reset_index(drop=True)

             # Group by hour to build OHLCV candles
            df['hour'] = df['time'].dt.floor('h')
            ohlcv = []
            for hour, group in df.groupby('hour'):
                if len(group) < 3:
                    continue
                o = float(group.get('price', group['close']).iloc[0])
                h = float(group['price'].max() if 'price' in group.columns else group['high'].max())
                l = float(group['price'].min() if 'price' in group.columns else group['low'].min())
                c = float(group.get('price', group['close']).iloc[-1])
                v = int(group['volume'].sum())
                if h > 0:
                    ohlcv.append({'time': hour, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})

            if not ohlcv or len(ohlcv) < 4:
                return None

             # Find prior session high/low from previous calendar day
            last_hour = ohlcv[-1]['time'].hour
            current_day_start = ohlcv[-1]['time'].replace(hour=0, minute=0, second=0, microsecond=0)
            prev_day_end = current_day_start
            prev_day_start = current_day_start - timedelta(days=1)

             # Collect candles from all hours except today's session (last session)
            prev_candles = [c for c in ohlcv[:-1] if c['time'] < prev_day_end]
            if len(prev_candles) < 2:
                # Fallback: use all but last candle
                pivots_highs = [c['h'] for c in ohlcv[:-1]]
                pivots_lows = [c['l'] for c in ohlcv[:-1]]
            else:
                pivots_highs = [c['h'] for c in prev_candles]
                pivots_lows = [c['l'] for c in prev_candles]

            prior_session_high = max(pivots_highs) if pivots_highs else None
            prior_session_low = min(pivots_lows) if pivots_lows else None

            latest = ohlcv[-1]
            is_buy_pp = False
            buy_breakout_pct = 0.0
            buy_vol_ratio = 0.0
            if prior_session_high and prior_session_high > 0:
                buy_breakout_pct = ((latest['c'] - prior_session_high) / prior_session_high) * 100.0
                recent_vols = [c['v'] for c in ohlcv[-4:-1]]
                avg_recent_vol = sum(recent_vols) if recent_vols else 1
                buy_vol_ratio = latest['v'] / max(avg_recent_vol, 1)
                is_buy_pp = (buy_breakout_pct > 2.0 and buy_vol_ratio >= 1.5)

            is_sell_pp = False
            sell_breakout_pct = 0.0
            sell_vol_ratio = 0.0
            if prior_session_low and prior_session_low > 0:
                sell_breakout_pct = ((latest['c'] - prior_session_low) / prior_session_low) * 100.0
                recent_vols = [c['v'] for c in ohlcv[-4:-1]]
                avg_recent_vol = sum(recent_vols) if recent_vols else 1
                sell_vol_ratio = latest['v'] / max(avg_recent_vol, 1)
                is_sell_pp = (sell_breakout_pct < -2.0 and sell_vol_ratio >= 1.5)

            if not (is_buy_pp or is_sell_pp):
                return None

            direction = "BUY" if is_buy_pp else "SELL"
            pivot_level = 0
            if is_buy_pp and prior_session_high is not None:
                pivot_level = prior_session_high
            elif (not is_buy_pp) and prior_session_low is not None:
                pivot_level = prior_session_low
            final_breakout_pct = buy_breakout_pct if is_buy_pp else sell_breakout_pct
            final_vol_ratio = buy_vol_ratio if is_buy_pp else sell_vol_ratio

            return {
                 'pivot_info': {
                     'pivot_direction': direction,
                     'pivot_high': round(pivot_level, 1),
                     'breakout_pct': round(final_breakout_pct, 2),
                     'volume_ratio': round(final_vol_ratio, 2),
                     'is_pocket_pivot': True,
                 }
             }
        except ImportError:
            return None
        except Exception as e:
            print(f"[WARN] 1h pivot detection failed {symbol}: {e}", file=sys.stderr)
            return None

    def scan_symbol(self, symbol):
        """Scan single symbol, return signal dict or None."""
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(SYMBOL_SCAN_TIMEOUT)
            data = fetch_stock_data(symbol)
            engine = SignalEngine()
            signal_info = engine.analyze_stock(data)
            pivots = self._detect_1h_pivots(symbol)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
            if pivots and signal_info:
                signal_info["pivot_info"] = pivots["pivot_info"]
            return signal_info
        except TimeoutError as e:
            signal.alarm(0)
            try:
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.signal(signal.SIGALRM, old_handler)
            except Exception:
                pass
            print(f"[WARN] scan timeout {symbol}: {e}", file=sys.stderr)
            return None
        except Exception as e:
            try:
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.signal(signal.SIGALRM, old_handler)
            except Exception:
                pass
            print(f"[WARN] scan failed {symbol}: {e}", file=sys.stderr)
            return None

    def full_scan(self):
        """Run full scan of all watchlist symbols. Returns dict{sym: signal_data}."""
        results = {}
        for sym in self._load_watchlist():
            result = self.scan_symbol(sym)
            if result:
                results[sym] = result
        _atomic_write(results, SCAN_RESULT_CACHE)
        return results

    def get_cached_scan(self):
        """Read last cached scan result from disk."""
        return _atomic_read(SCAN_RESULT_CACHE)

    def clear_cache(self):
        """Clear the shared scan cache (e.g., after market close)."""
        if SCAN_RESULT_CACHE.exists():
            os.remove(SCAN_RESULT_CACHE)
            print("[Unified] Scan cache cleared")


# -- Standalone CLI entry point --

if __name__ == "__main__":
    import time
    scan = UnifiedScan()

    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        scan.clear_cache()
    else:
        print("=== UNIFIED SCAN (all symbols) ===")
        results = scan.full_scan()

        buys = [k for k, v in results.items() if v.get('signal') == 'BUY']
        sells = [k for k, v in results.items() if v.get('signal') == 'SELL']
        holds = [k for k, v in results.items() 
                 if not v or v.get('signal') in ('HOLD', None)]

        print(f"\nTotal: {len(results)} symbols scanned")
        print(f"BUY:    {len(buys)} | SELL: {len(sells)} | HOLD: {len(holds)}")

        if buys:
            print("\nGREEN BUY signals:")
            for b in sorted(buys, key=lambda x: results[x].get('confidence', 0), reverse=True):
                r = results[b]
                print(f"     {b}: {r['latest_price']} VND | Conf: {r.get('confidence', 0)}%")

        if sells:
            print("\nRED SELL signals:")
            for s in sorted(sells, key=lambda x: results[x].get('confidence', 0), reverse=True):
                r = results[s]
                print(f"     {s}: {r['latest_price']} VND | Conf: {r.get('confidence', 0)}%")

        pivots = [(k, v) for k, v in results.items() 
                  if v and v.get('pivot_info') and v['pivot_info'].get('is_pocket_pivot')]
        if pivots:
            print("\nALERT POCKET PIVOTS:")
            for sym, v in pivots:
                pp = v['pivot_info']
                price = v.get('latest_price', '?')
                print(f"     {sym}: {price} VND | Breakout: {pp['breakout_pct']}% | Vol: {pp['volume_ratio']}x")
