"""CafeF fallback module for Vietnamese stock data.

Provides price data when Yahoo Finance and vnstock are unavailable.
Uses multiple CafeF endpoints with progressive fallback.
"""

import re
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from http.client import HTTPException


def _safe_get(url: str, timeout: int = 8) -> str | None:
    """Fetch a URL and return its text content, or None on failure."""
    try:
        req = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            },
        )
        resp = urlopen(req, timeout=timeout)
        raw = resp.read()
        # Try utf-8 first, fall back to euc-vn then latin-1
        for enc in ("utf-8", "euc_vn", "latin-1"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("latin-1", errors="replace")
    except Exception as e:
        print(f"    [CAFEF] HTTP fail for {url}: {e}")
        return None


def _parse_vcip_price(html: str) -> dict | None:
    """Try to parse the vcip-price element from a CafeF stock page (V4/V5 layout).

    Looks for patterns like:
      <div class="vcip-price" data-symbol="MBB">3100</div>
      or price inside span/strong with class "vcip".
    """
    if not html:
        return None

    # Pattern 1: div.vcip-price content
    m = re.search(r'class=["\']vcip-price["\'][^>]*>([0-9,.]+)', html)
    if m:
        price_str = m.group(1).replace(",", "").strip()
        try:
            price = float(price_str)
            return {"price": price, "source": "cafef_vcip"}
        except ValueError:
            pass

    # Pattern 2: data-vcip attribute
    m = re.search(r'data-vcip=["\']([0-9]+)', html)
    if m:
        try:
            return {"price": float(m.group(1)), "source": "cafef_data_vcip"}
        except ValueError:
            pass

    # Pattern 3: <span class="vcip-price"> inside a div
    m = re.search(r'<div[^>]*class=["\'][^"\']*vcip-stock-price["\'][^>]*>\s*'
                   r'[\s\S]*?<span[^>]*>([0-9,]+)</span>', html)
    if m:
        price_str = m.group(1).replace(",", "").strip()
        try:
            return {"price": float(price_str), "source": "cafef_stock_price"}
        except ValueError:
            pass

    # Pattern 4: Look for current price inside chart data
    m = re.findall(r'"(\d{3,5}[\d.]*)"', html[:20000])
    large_prices = [float(p) for p in m if "." in p and float(p) > 100]
    if large_prices:
        # Typical VN stock prices: most are < 5000, filter out volume-like numbers
        valid = [p for p in large_prices if p < 100000]
        if valid:
            return {"price": max(valid), "source": "cafef_regex"}

    return None


def _parse_rss_feed(html: str) -> dict | None:
    """Parse CafeF RSS feed for a stock to get recent price data.

    CafeF RSS format contains <item> elements with title like:
      MBB: Giá phục hồi ... 3100 (+2.6%) ...
    """
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(html)
        items = root.findall(".//channel/item")
        if not items:
            return None
        # Take the first/most recent item
        title = items[0].findtext("title", "").strip()
        # Try to extract price from title like "MBB: 3100 (+2.6%)"
        m = re.search(r'[:：]\s*(\d{3,5}[\d.]*)', title)
        if m:
            price = float(m.group(1).replace(",", ""))
            prev_m = re.search(r'\(([+-]\d+\.?\d*%)\)', title)
            change_pct = None
            if prev_m:
                try:
                    change_pct = float(prev_m.group(1).rstrip("%"))
                except ValueError:
                    pass
            return {"price": price, "change_pct": change_pct, "source": "cafef_rss"}
    except Exception as e:
        print(f"    [CAFEF] RSS parse error: {e}")
    return None


def fetch_stock_data(symbol: str) -> dict | None:
    """Fetch stock data for a VN stock from CafeF.

    Tries multiple endpoints in order of reliability:
      1. RSS feed (lightest, most reliable)
      2. Stock page VHTML (heavier but more data)

    Returns dict with keys: symbol, price, change_pct (when available) or None on failure.

    Example usage:
        >>> fetch_stock_data("MBB")
        {'symbol': 'MBB', 'price': 3100.0, 'change_pct': 2.6, ...}
    """
    symbol = symbol.upper().strip()
    if not re.match(r'^[A-Z]{2,5}$', symbol):
        return {"symbol": symbol, "error": "invalid_symbol_format"}

    results = {"symbol": symbol, "sources_tried": []}

    # --- Method 1: RSS feed (preferred) ---
    rss_url = f"https://cafef.vn/{symbol}.rss"
    print(f"    [CAFEF] Fetching RSS: {rss_url}")
    results["sources_tried"].append("rss")
    rss_html = _safe_get(rss_url)
    if rss_html:
        data = _parse_rss_feed(rss_html)
        if data and data.get("price"):
            data["symbol"] = symbol
            print(f"    [CAFEF] RSS OK - {symbol}: price={data['price']}")
            return data

    # --- Method 2: Stock page HTML ---
    stock_url = f"https://cafef.vn/{symbol}.chn"
    print(f"    [CAFEF] Fetching stock page: {stock_url}")
    results["sources_tried"].append("stock_page")
    page_html = _safe_get(stock_url)
    if page_html:
        data = _parse_vcip_price(page_html)
        if data and data.get("price"):
            data["symbol"] = symbol
            print(f"    [CAFEF] Page OK - {symbol}: price={data['price']}")
            return data

    # --- Method 3: Try the old cafeF API (deprecated but sometimes still works) ---
    api_url = f"https://cafef.vn/api/quoc-te/{symbol}.html"
    print(f"    [CAFEF] Fetching legacy API: {api_url}")
    results["sources_tried"].append("legacy_api")
    try:
        req = Request(
            api_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp = urlopen(req, timeout=8)
        raw = resp.read().decode("utf-8", errors="replace")
        # Try parsing as JSON or JS object
        try:
            data_dict = json.loads(raw)
            if isinstance(data_dict, dict):
                price_key = "price" if "price" in data_dict else list(data_dict.keys())[0] if data_dict else None
                if price_key and str(data_dict[price_key]).replace(".", "").isdigit():
                    parsed = {"symbol": symbol, "price": float(data_dict[price_key]), "source": "cafef_legacy_json"}
                    print(f"    [CAFEF] Legacy JSON OK - {symbol}: price={parsed['price']}")
                    return parsed
        except json.JSONDecodeError:
            pass
    except Exception as e:
        print(f"    [CAFEF] Legacy API failed: {e}")

    # All methods exhausted without success
    results["error"] = "all_sources_failed"
    print(f"    [CAFEF] ALL FAILED for {symbol}: {results['sources_tried']}")
    return results if results.get("error") else None


def fetch_multiple(symbols: list[str]) -> dict:
    """Fetch CafeF data for multiple symbols.

    Returns dict mapping symbol -> data dict (or error dict).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_stock_data, s): s for s in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                results[sym] = future.result()
            except Exception as e:
                results[sym] = {"symbol": sym, "error": str(e)}
    return results


if __name__ == "__main__":
    import sys
    symbols = sys.argv[1:] if len(sys.argv) > 1 else ["MBB", "ACB", "VCB"]
    print(f"Testing CafeF fetch for: {symbols}\n")
    data = fetch_multiple(symbols)
    for sym, d in data.items():
        print(f"\n{sym}: {json.dumps(d, default=str)}")
