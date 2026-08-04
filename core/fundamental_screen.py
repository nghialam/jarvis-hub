"""fundamental_screen.py -- Shared database for weekly fundamental screening data.

Reads the JSON output from `weekly-fundamental-screen-data.py` and provides
a unified API for both cron scripts AND Jarvis Hub dashboard endpoints.

Usage:
    from core.fundamental_screen import (
        get_top_fundamental,
        get_low_pe_tickers,
        get_high_roe_tickers,
        load_fundamental_data,
    )

     # Get top 10 fundamental stocks in JSON format
    data = raw_json()                       # dict from the JSON file
    
     # Load the latest run
    data = load_fundamental_data()

     # Access individual ticker data
    for stock in data["results"][:5]:
        print(f"{stock['symbol']} - P/E: {stock['pe_ratio']}, ROE: {stock.get('roe_avg')}")
"""

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default path for the fundamental screen JSON output.
DEFAULT_OUTPUT_PATH = str(
    Path.home() / ".hermes" / "cron" / "output" / "weekly-fundamental.json"
)


class _CacheManager:
    """Module-level singleton cache for fundamental screen data."""

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._expires: Optional[date] = None

    def get(self) -> Dict[str, Any]:
        if not self._expires or date.today() >= self._expires:
            data = _load_file(None)
            self._cache = data if data else {}
            self._expires = date.today() + timedelta(days=7)
        return self._cache if self._cache else {}

    def reload(self, path: Optional[str] = None) -> Dict[str, Any]:
        data = _load_file(path)
        self._cache = data if data else {}
        self._expires = date.today() + timedelta(days=7)
        return self._cache


# Global cache singleton -- used by all module-level functions.
_cache_mgr = _CacheManager()


def _load_file(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load the weekly fundamental JSON data from disk."""
    filepath = path or DEFAULT_OUTPUT_PATH

    if not os.path.exists(filepath):
        logger.warning("Fundamental screen file not found: %s", filepath)
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read fundamental data from %s: %s", filepath, e)
        return None


def load_fundamental_data(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the latest fundamental screen output.

    This is the primary entry point for reading fundamental screening data.
    It returns a complete dict with timestamp, quarter_reported, results[],
    low_pe[], low_pb[], high_roe[], total_scanned, and successful keys.

    Args:
        path: Optional custom file path (default uses DEFAULT_OUTPUT_PATH).

    Returns:
        Dict with fundamental screening results, or an empty structure on failure.
    """
    data = _load_file(path)
    if data is None:
        return {
            "timestamp": date.today().strftime("%Y-%m-%d"),
            "quarter_reported": "N/A",
            "total_scanned": 0,
            "successful": 0,
            "top_n_returned": 30,
            "results": [],
            "low_pe": [],
            "low_pb": [],
            "high_roe": [],
        }
    return data


def raw_json(path: Optional[str] = None) -> Dict[str, Any]:
    """Get the full JSON data as-is from the file.

    If a path is provided, bypasses cache and reads directly. Otherwise uses
    the module-level singleton cache (refreshed at most once per day).

    Args:
        path: Optional custom file path to read instead of DEFAULT_OUTPUT_PATH.

    Returns:
        Dict with the complete fundamental screening output.
    """
    if path:
        return _load_file(path) or {}
    return _cache_mgr.get()


def get_top_fundamental(top_n: int = 30) -> List[Dict[str, Any]]:
    """Get the top N fundamental stocks, ranked by score.

    Args:
        top_n: Number of top stocks to return (default 30).

    Returns:
        List of dicts with symbol, score, P/E, ROE, and other metrics.
    """
    data = _cache_mgr.get()
    return list(data.get("results", []))[:top_n]


def get_low_pe_tickers(max_pe: float = 15.0) -> List[Dict[str, Any]]:
    """Get tickers with low P/E ratio (below the given threshold).

    Checks both the results[] array and the explicit low_pe[] list from the JSON
    to ensure nothing is missed. No duplicates are returned.

    Args:
        max_pe: Maximum P/E ratio threshold (default 15).

    Returns:
        List of dicts like {"symbol": "HPG", "pe_ratio": 11.98}.
    """
    data = _cache_mgr.get()
    results: List[Dict[str, Any]] = []

    for entry in data.get("results", []):
        pe = entry.get("pe_ratio")
        if pe is not None and 0 < pe < max_pe:
            results.append({"symbol": entry["symbol"], "pe_ratio": pe})

    # Also check explicit low_pe list from JSON for any extra tickers.
    raw_low = data.get("low_pe", [])
    existing_symbols = {e["symbol"] for e in results}
    for item in raw_low:
        sym = item.get("symbol")
        if sym and sym not in existing_symbols:
            results.append(item)

    return sorted(results, key=lambda x: x["pe_ratio"])


def get_high_roe_tickers(min_roe: float = 15.0) -> List[Dict[str, Any]]:
    """Get tickers with high ROE (>= min_roe).

    For bank stocks where ROE may be None, falls back to NIM-based screening
    (~6% NIM approximates a 15% ROE tier for banks). Also checks the explicit
    high_roe[] list from JSON for additional tickers.

    Args:
        min_roe: Minimum ROE threshold in percent (default 15).

    Returns:
        List of dicts like {"symbol": "VCB", "roe_avg": 16.2, ...} or None.
    """
    data = _cache_mgr.get()
    results: List[Dict[str, Any]] = []

    for entry in data.get("results", []):
        roe = entry.get("roe_avg")
        nim = entry.get("nim")

        # Direct ROE match.
        if roe is not None and roe >= min_roe:
            results.append({
                "symbol": entry["symbol"],
                "roe_avg": roe,
                "fundamental_score": entry.get("fundamental_score", 0),
            })
        # Banking alternative: NIM-based screening (~6% for banks ≈ 15% ROE tier).
        elif nim is not None and nim >= (min_roe * 0.4):
            results.append({
                "symbol": entry["symbol"],
                "roe_avg": None,
                "nim": nim,
                "fundamental_score": entry.get("fundamental_score", 0),
            })

    # Include explicit high_roe list for any additional tickers.
    raw_high = data.get("high_roe", [])
    existing_symbols = {e["symbol"] for e in results}
    for item in raw_high:
        sym = item.get("symbol")
        if sym and sym not in existing_symbols:
            results.append(item)

    return sorted(results, key=lambda x: x.get("fundamental_score") or 0, reverse=True)


def get_low_pb_tickers(max_pb: float = 2.0) -> List[str]:
    """Get tickers with a low P/B ratio (below the given threshold).

    Args:
        max_pb: Maximum P/B ratio (default 2.0).

    Returns:
        Sorted list of ticker symbol strings.
    """
    data = _cache_mgr.get()
    symbols: set = set(data.get("low_pb", []))

    for entry in data.get("results", []):
        pb = entry.get("pb_ratio")
        if pb is not None and 0 < pb < max_pb:
            symbols.add(entry["symbol"])

    return sorted(symbols)


def get_stocks_by_sector(sector_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get stocks filtered by sector keyword.

    Note: vnstock4 fundamental screen does not include sector info directly,
    so this returns all results when no applicable filter is available.

    Args:
        sector_keyword: Unused in current data, kept for future extensions.

    Returns:
        Full list of stocks from the fundamental screen.
    """
    data = _cache_mgr.get()
    return list(data.get("results", []))


def get_ticker_detail(symbol: str) -> Optional[Dict[str, Any]]:
    """Get detailed fundamental data for a single ticker symbol.

    Searches results[], low_pe[], and high_roe[] lists to find the ticker.
    The returned dict includes all extracted ratios plus a
    `detailed_fundamentals` key with the full row from results[].

    Args:
        symbol: Stock ticker (e.g., "VIC", "HPG").

    Returns:
        Dict with fundamental ratios, or None if not found.
    """
    data = _cache_mgr.get()
    symbol_upper = symbol.upper()

    for entry in data.get("results", []):
        if entry.get("symbol") == symbol_upper:
            return entry.copy()

    # Also check low_pe/high_roe lists.
    for lst_key in ("low_pe", "high_roe"):
        for item in data.get(lst_key, []):
            if isinstance(item, dict) and item.get("symbol") == symbol_upper:
                result = item.copy()
                for entry in data.get("results", []):
                    if entry.get("symbol") == symbol_upper:
                        result["detailed_fundamentals"] = entry.copy()
                        return result
                break

    logger.warning("Ticker %s not found in fundamental screen results", symbol_upper)
    return None


def get_summary() -> Dict[str, Any]:
    """Get a quick summary dict of the latest screen run.

    Returns:
        Dict with timestamp, quarter_reported, total_scanned, successful,
        and counts for low_pe, low_pb, and high_roe categories.
    """
    data = _cache_mgr.get()
    return {
        "timestamp": data.get("timestamp"),
        "quarter_reported": data.get("quarter_reported"),
        "total_scanned": data.get("total_scanned", 0),
        "successful": data.get("successful", 0),
        "low_pe_count": len(get_low_pe_tickers()),
        "low_pb_count": len(get_low_pb_tickers()),
        "high_roe_count": len(get_high_roe_tickers()),
    }


def force_reload(path: Optional[str] = None) -> Dict[str, Any]:
    """Force reload the JSON file from disk (bypasses module cache).

    Args:
        path: Optional custom file path; otherwise uses DEFAULT_OUTPUT_PATH.

    Returns:
        The freshly loaded data dict.
    """
    return _cache_mgr.reload(path)


# ---------------------------------------------------------------------------
# CLI usage -- quick terminal testing interface.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    action = sys.argv[1] if len(sys.argv) > 1 else "summary"

    if action == "summary":
        summary = get_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    elif action == "top":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        results = get_top_fundamental(n)
        for i, r in enumerate(results, 1):
            pe = f"{r['pe_ratio']:.2f}" if r.get("pe_ratio") else "N/A"
            roe = f"{r['roe_avg']:.2f}%" if r.get("roe_avg") else "N/A"
            print(f"{i:2d}. {r['symbol']} | score={r['fundamental_score']}| P/E={pe} | ROE={roe}")

    elif action == "low_pe":
        pe = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
        results = get_low_pe_tickers(pe)
        for r in results:
            print(f"{r['symbol']} -- P/E: {r['pe_ratio']:.2f}")

    elif action == "high_roe":
        roe = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
        results = get_high_roe_tickers(roe)
        for r in results:
            print(f"{r['symbol']} -- ROE: {r.get('roe_avg') or 'N/A'}")

    elif action == "detail":
        sym = sys.argv[2] if len(sys.argv) > 2 else "VIC"
        detail = get_ticker_detail(sym)
        print(json.dumps(detail, indent=2, ensure_ascii=False))

    else:
        print("Usage: python -m jarvis_hub.core.fundamental_screen <action>")
        print("Actions: summary, top [N], low_pe [max], high_roe [min], detail <SYMBOL>")

