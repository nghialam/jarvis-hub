"""vn_market.py - VN Stock Market Data Module for Jarvis Hub Dashboard."""

import sys
from pathlib import Path

# Add vnstock venv to path
sys.path.insert(0, str(Path("/Users/nghialam/jarvis-hub/venv/lib/python3.11/site-packages")))

try:
    from vnstock.api.quote import Quote
except ImportError as e:
    print(f"[ERROR] vnstock not available: {e}")
    Quote = None


# VN Blue Chips & Market Leaders
DEFAULT_SYMBOLS = [
    "VCB",  # Vietcombank - largest bank
    "HPM",  # Hoang Minh Corp 
    "ACB",  # Asian Commercial Bank
    "VNM",  # Vietnam Food Securities  
    "MBB",  # MB Bank
    "TCB",  # Techcombank
    "FPT",  # FPT Corp - tech leader
    "VIC",  # Vingroup - conglomerate
    "VRE",  # Vinhomes Real Estate
    "MSN",  # Masan Group - consumer staples
]


def fetch_stock_quote(symbol: str) -> dict:
    """Fetch latest quote data for a VN stock symbol."""
    if Quote is None:
        return {"symbol": symbol, "error": "vnstock module not available"}

    try:
        q = Quote(symbol=symbol, show_log=False)
        df = q.history(
            symbol=symbol,
            start="2026-05-01",
            end="2026-07-01",
            interval="D"
        )

        if df.empty:
            return {"symbol": symbol, "error": "No data returned"}

        latest = df.tail(1).iloc[0]

         # vnstock returns prices in "nghìn đồng" — multiply by 1000
         # to get actual VND
        multiplier = 1000
        current_close = float(latest['close']) * multiplier
        prev_close = (float(df.iloc[-2]['close']) * multiplier) if len(df) > 1 else current_close
        change_pct = ((current_close - prev_close) / prev_close) * 100
        
        return {
            "symbol": symbol,
            "date": str(latest['time'].strftime('%Y-%m-%d')),
            "open": float(latest.get("open", 0) or 0) * multiplier,
            "high": float(latest.get("high", 0) or 0) * multiplier,
            "low": float(latest.get("low", 0) or 0) * multiplier,
            "close": current_close,  # already multiplied by 1000 above
            "volume": int(latest['volume']),
            "change_pct": round(change_pct, 2),
            "prev_close": float(prev_close)
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "error": str(e)[:100]
        }


def fetch_all_bluechips() -> list:
    """Fetch quote data for all configured bluechip stocks."""
    results = []
    for symbol in DEFAULT_SYMBOLS:
        try:
            data = fetch_stock_quote(symbol)
            if 'error' not in data or data['error'] == "vnstock module not available":
                results.append(data)
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)[:50]})
    
    return results


def fetch_market_indices() -> dict:
    """Fetch major VN market indices (VN-Index, HNX-Index, UPCOM)."""
    indices = {
        "VN-INDEX": "HSI",   # HOSE index code in vnstock
        "HNX-INDEX": "HMQ",  # HNX code
        "UPCOM": "UPCOM"     # UPCOM index
    }

    data = {}
    for name, vn_symbol in indices.items():
        try:
            q = Quote(symbol=vn_symbol, show_log=False)
            df = q.history(
                symbol=vn_symbol,
                start="2026-05-01",
                end="2026-07-01", 
                interval="D"
            )

            if not df.empty:
                latest = df.tail(1).iloc[0]
                prev = df.iloc[-2]['close'] if len(df) > 1 else latest['close']
                change_pct = ((latest['close'] - prev) / prev) * 100
                
                data[name] = {
                    "value": round(float(latest['close']), 2),
                    "change_pct": round(change_pct, 2),
                    "date": str(latest['time'].strftime('%Y-%m-%d'))
                }
        except Exception as e:
            data[name] = {"error": str(e)[:50]}

    return data


def fetch_market_summary() -> dict:
    """Return complete market summary for dashboard display."""
    # Get all blue chips  
    bluechips = fetch_all_bluechips()
    
    # Get VN indices
    indices = fetch_market_indices()
    
    # Calculate market depth metrics
    valid_quotes = [c for c in bluechips if 'close' in c and 'change_pct' in c]
    gainers = sum(1 for c in valid_quotes if c['change_pct'] > 0)
    losers = sum(1 for c in valid_quotes if c['change_pct'] < 0)
    
    # Average volume
    total_vol = sum(c.get('volume', 0) for c in valid_quotes)
    avg_vol = total_vol // len(valid_quotes) if valid_quotes else 0

    return {
        "bluechips": bluechips,
        "indices": indices, 
        "summary": {
            "total_stocks": len(valid_quotes),
            "gainers": gainers,
            "losers": losers,
            "neutrals": len(valid_quotes) - gainers - losers,
            "avg_volume": f"{avg_vol:,}" if avg_vol > 0 else "N/A"
        }
    }
