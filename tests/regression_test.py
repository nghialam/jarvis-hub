#!/usr/bin/env python3
"""
Jarvis Hub - Daily Regression Test Suite
Chay vao 1:00 AM hang ngay de kiem tra toan bo chuc nang

Usage:
    python regression_test.py [--host localhost] [--port 8100]

Output: JSON report saved to reports/ directory
"""
import sys
import json
import time
import logging
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    np = None

# --- Configuration ---
DEFAULT_BASE_URL = "http://localhost:8100"
REPORT_DIR = Path(__file__).parent.parent / "reports"
TEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("regression")


# --- Helpers ---

def wait_for_server(base_url, timeout=60):
    """Wait until server is ready."""
    logger.info("Waiting for server to be ready...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{base_url}/api/health", timeout=5)
            if r.status_code == 200:
                logger.info("Server is ready!")
                return True
        except Exception:
            pass
        time.sleep(RETRY_DELAY)
    logger.error("Server not ready after %ds", timeout)
    return False


def api_request(base_url, method, path, **kwargs):
    """Make API request with retries."""
    url = f"{base_url}{path}"
    kwargs.setdefault("timeout", TEST_TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            if method.upper() == "GET":
                r = requests.get(url, **kwargs)
            elif method.upper() == "POST":
                r = requests.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            return {"status_code": r.status_code, "data": r.json(), "raw": r.text}
        except Exception as e:
            logger.warning("Attempt %d/%d failed for %s %s: %s",
                          attempt + 1, MAX_RETRIES, method, path, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    return {"status_code": 0, "data": None, "error": str(e)}


def create_test(name):
    """Create a test result object."""
    return {
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "duration_ms": 0,
        "status": "PENDING",
        "message": "",
        "data": None
    }


def finish_test(test, status="PASS", message="", data=None):
    """Finish a test result."""
    test["status"] = status
    test["message"] = message
    if data is not None:
        test["data"] = data
    return test


# --- Test Cases ---

def test_server_health(test, base_url):
    """Test 1: Check if server is running and responding."""
    test["name"] = "Server Health"
    result = api_request(base_url, "GET", "/api/health")

    if result.get("status_code") != 200:
        return finish_test(test, "FAIL", f"Health check failed: status {result.get('status_code')}")

    data = result.get("data", {})
    if data.get("status") != "ok":
        return finish_test(test, "FAIL", f"Server status not ok: {data.get('status')}")

    ollama_ok = data.get("ollama") == "online"
    cache_age = data.get("cache_age_seconds", 999)

    msg = f"OK | Ollama: {'online' if ollama_ok else 'OFFLINE'} | Cache age: {cache_age}s"
    return finish_test(test, "PASS" if ollama_ok else "WARN", msg, data)


def test_market_data(test, base_url):
    """Test 2: Verify market data is fresh and complete."""
    test["name"] = "Market Data Freshness"
    result = api_request(base_url, "GET", "/api/health")

    if result.get("status_code") != 200:
        return finish_test(test, "FAIL", "Cannot reach health endpoint")

    data = result.get("data", {})
    issues = []

    cache_age = data.get("cache_age_seconds", 999)
    if cache_age > 43200:
        issues.append(f"Cache very stale: {cache_age}s")

    indices = data.get("indices", {})
    if not indices or "VN-Index" not in indices:
        issues.append("VN-Index price data missing")

    rates = data.get("rates", {})
    if not rates or "USD" not in rates:
        issues.append("USD/VND exchange rate missing")

    crypto = data.get("crypto", {})
    if not crypto or "BTC" not in crypto:
        issues.append("BTC price data missing")

    status = "PASS" if not issues else "WARN"
    msg = f"Cache age: {cache_age}s. " + (", ".join(issues) if issues else "All market data present")
    return finish_test(test, status, msg, {"cache_age": cache_age})


def test_analyze_stock(test, base_url):
    """Test 3: Analyze a VN stock - checks for NaN crash fix."""
    import numpy as np

    test["name"] = "Stock Analysis (VNM)"
    start = time.time()

    result = api_request(base_url, "GET", "/api/analyze?symbol=VNM")
    duration = int((time.time() - start) * 1000)
    test["duration_ms"] = duration

    if result.get("error"):
        return finish_test(test, "FAIL", f"API returned error: {result['error']}", result)

    data = result.get("data") or {}
    if not data:
        return finish_test(test, "FAIL", "No data returned")

    issues = []
    required_fields = ["symbol", "name", "price"]
    for field in required_fields:
        if field not in data or data.get(field) is None:
            issues.append(f"Missing field: {field}")

    has_technical = "technical" in data and isinstance(data.get("technical"), dict)
    if not has_technical:
        issues.append("No technical indicators calculated")
    else:
        ta = data["technical"]
        for field in ["rsi", "sma_20", "support_level", "resistance_level", "macd_histogram"]:
            if field not in ta:
                issues.append(f"Missing TA field: {field}")

    closes = data.get("historical_closes", []) or []
    if any(np.isnan(c) for c in closes):
        issues.append("Contains NaN values in historical closes")

    status = "PASS" if not issues else "FAIL"
    msg_parts = [
        f"Price: {data.get('price')} {data.get('currency', '?')}",
        f"TA fields: {'OK' if has_technical else 'MISSING'}",
        f"Duration: {duration}ms"
    ]
    if issues:
        msg_parts.append("Issues: " + ", ".join(issues))

    return finish_test(test, status, " | ".join(msg_parts), data)


def test_analyze_crypto(test, base_url):
    """Test 4: Analyze Bitcoin - should NOT crash."""
    test["name"] = "Crypto Analysis (BTC)"
    start = time.time()

    result = api_request(base_url, "GET", "/api/analyze?symbol=BTC")
    duration = int((time.time() - start) * 1000)
    test["duration_ms"] = duration

    if result.get("error"):
        return finish_test(test, "FAIL", f"API error: {result['error']}", result)

    data = result.get("data") or {}
    if not data or data.get("type") != "crypto":
        return finish_test(test, "FAIL", f"Not crypto (got {data.get('type')})", data)

    price = data.get("price")
    if not price or price <= 0:
        return finish_test(test, "FAIL", f"Invalid BTC price: {price}")

    msg = f"BTC: ${price:,} (24h: {data.get('change_pct', 'N/A'):.2f}%) | Duration: {duration}ms"
    return finish_test(test, "PASS", msg, {"price": price})


def test_kb_search(test, base_url):
    """Test 5: Knowledge base search."""
    test["name"] = "KB Search (vndirect)"
    result = api_request(base_url, "GET", "/api/search?q=vndirect")

    if result.get("error"):
        return finish_test(test, "FAIL", f"Search error: {result['error']}", result)

    data = result.get("data") or {}
    results = data.get("results", [])
    count = data.get("count", len(results))

    if not results:
        return finish_test(test, "WARN", "No results (may be OK)", {"count": 0})

    msg = f"Found {count} results. First: {results[0].get('term', 'N/A')}"
    return finish_test(test, "PASS", msg, count)


def test_daily_snapshots(test, base_url):
    """Test 6: Daily snapshots listing and detail."""
    test["name"] = "Daily Snapshots"
    result_list = api_request(base_url, "GET", "/api/snapshots")

    if result_list.get("error"):
        return finish_test(test, "FAIL", f"Snapshots list error: {result_list['error']}", result_list)

    data = result_list.get("data") or {}
    snapshots = data.get("snapshots", [])

    if not snapshots:
        return finish_test(test, "WARN", "No snapshots found (may be OK)")

    date_str = snapshots[0].get("date", "")
    result_detail = api_request(base_url, "GET", f"/api/snapshots/{date_str}")

    msg = f"Found {len(snapshots)} snapshots. Testing fetch for {date_str}: "
    if result_detail.get("error") or not result_detail.get("data"):
        return finish_test(test, "WARN", msg + f"FAIL: {result_detail.get('error')}")

    content = result_detail["data"].get("content", "")
    return finish_test(test, "PASS", msg + f"OK ({len(content)} chars)", {"count": len(snapshots)})


def test_eval_ending(test, base_url):
    """Test 7: Market evaluation - check for fresh data."""
    test["name"] = "Market Evaluation"
    start = time.time()

    result = api_request(base_url, "GET", "/api/eval")
    duration = int((time.time() - start) * 1000)
    test["duration_ms"] = duration

    if result.get("error"):
        return finish_test(test, "FAIL", f"Eval error: {result['error']}", result)

    data = result.get("data") or {}
    if not data:
        return finish_test(test, "WARN", "No eval data returned")

    status_field = data.get("status", "")
    date = data.get("date", "")
    today_str = datetime.now().strftime("%Y-%m-%d")

    if status_field == "ok":
        is_today = date == today_str
        evaluation = data.get("evaluation", "")
        msg = f"For {date} | Today: {'OK' if is_today else 'historical'} | Len: {len(evaluation)}"
        return finish_test(test, "PASS" if is_today else "WARN", msg)
    elif status_field == "pending":
        return finish_test(test, "WARN", f"Pending. Duration: {duration}ms")
    else:
        return finish_test(test, "FAIL", f"Unexpected status: {status_field}")


def test_eval_force_refresh(test, base_url):
    """Test 8: Force refresh evaluation."""
    test["name"] = "Eval Force Refresh"
    start = time.time()

    result = api_request(base_url, "POST", "/api/market-evaluation/generate")
    duration = int((time.time() - start) * 1000)
    test["duration_ms"] = duration

    if result.get("error"):
        result = api_request(base_url, "GET", "/api/eval?force=true")

    data = result.get("data") or {}
    if not data:
        return finish_test(test, "WARN", "No response from refresh")

    status_field = data.get("status", "")
    eval_len = len(data.get("evaluation", ""))
    today_str = datetime.now().strftime("%Y-%m-%d")
    msg = f"Status: {status_field} | Eval length: {eval_len} chars | Duration: {duration}ms"

    return finish_test(test, "PASS" if status_field == "ok" else "WARN", msg)


def test_watchlist(test, base_url):
    """Test 9: Watchlist API."""
    test["name"] = "Watchlist"

    result = api_request(base_url, "GET", "/api/watchlist")
    if result.get("error"):
        return finish_test(test, "FAIL", f"Watchlist error: {result['error']}", result)

    data = result.get("data") or {}
    count = data.get("count", 0)
    items = data.get("items", [])

    if count == 0:
        add_result = api_request(base_url, "POST", "/api/watchlist/add", json={"symbol": "VCB"})
        if add_result.get("error") or not (add_result.get("data") and add_result["data"].get("ok")):
            return finish_test(test, "WARN", "Failed to add VCB")
        return finish_test(test, "PASS", "Added VCB as test item")

    first_sym = items[0].get("symbol", "N/A") if isinstance(items, list) and items else "N/A"
    return finish_test(test, "PASS", f"Watchlist: {count} items. First: {first_sym}")


def test_articles_endpoint(test, base_url):
    """Test 10: News/Articles endpoint."""
    test["name"] = "News Articles Feed"

    result = api_request(base_url, "GET", "/api/articles")
    if result.get("error"):
        return finish_test(test, "FAIL", f"Articles error: {result['error']}", result)

    data = result.get("data") or {}
    articles = data.get("articles", [])
    count = data.get("count", len(articles))

    if articles and isinstance(articles, list):
        categories = set(a.get("category", "unknown") for a in articles)
        sentiments = {"positive": 0, "negative": 0, "neutral": 0}
        for a in articles:
            sc = a.get("sentiment_class", "neutral")
            if sc in sentiments:
                sentiments[sc] += 1

        msg = f"{count} articles. Categories: {', '.join(categories)}. Sentiment: P={sentiments['positive']}, N={sentiments['negative']}"
        return finish_test(test, "PASS", msg)

    return finish_test(test, "WARN", "No articles available")


# --- Orchestration ---

def run_all_tests(base_url):
    """Run all regression tests and generate report."""
    logger.info("=" * 70)
    logger.info("JARVIS HUB DAILY REGRESSION TEST - %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info("=" * 70)

    if not wait_for_server(base_url):
        report = {"timestamp": datetime.now().isoformat(), "status": "FAILED",
                  "message": "Server not available after 60s", "tests": []}
        save_report(report)
        logger.error("Server unavailable. Aborting.")
        return report

    test_definitions = [
        {"func": test_server_health, "timeout": 10},
        {"func": test_market_data, "timeout": 15},
        {"func": test_analyze_stock, "timeout": TEST_TIMEOUT},
        {"func": test_analyze_crypto, "timeout": TEST_TIMEOUT},
        {"func": test_kb_search, "timeout": 10},
        {"func": test_daily_snapshots, "timeout": 15},
        {"func": test_eval_ending, "timeout": 30},
        {"func": test_eval_force_refresh, "timeout": 120},
        {"func": test_watchlist, "timeout": 30},
        {"func": test_articles_endpoint, "timeout": 15},
    ]

    results = []
    start_time = time.time()

    for i, definition in enumerate(test_definitions, 1):
        func = definition["func"]
        test = create_test(f"Test {i}: {func.__doc__.strip()}")

        logger.info("\n[%d/%d] %s...", i, len(test_definitions), test["name"])

        try:
            result = func(test, base_url)
        except Exception as e:
            import traceback
            result = finish_test(test, "ERROR", f"Error: {e}\n{traceback.format_exc()[:200]}")

        results.append(result)
        icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL", "ERROR": "ERROR"}[result["status"]]
        dur = result.get("duration_ms", 0) / 1000
        logger.info("[%s] %s (%.1fs)", icon, result["message"][:80], dur)

        if i < len(test_definitions):
            time.sleep(2)

    total_duration = int((time.time() - start_time) * 1000)
    passed = sum(1 for r in results if r["status"] == "PASS")
    warnings = sum(1 for r in results if r["status"] == "WARN")
    failed = sum(1 for r in results if r["status"] in ("FAIL", "ERROR"))

    overall = "PASS" if (failed == 0 and passed >= len(results) * 0.7) else "WARNING" if failed == 0 else "FAILED"

    report = {
        "timestamp": datetime.now().isoformat(),
        "status": overall,
        "summary": {"total": len(results), "passed": passed, "warnings": warnings,
                    "failed": failed, "duration_ms": total_duration},
        "tests": results
    }

    save_report(report)

    logger.info("\n" + "=" * 70)
    logger.info("REGRESSION TEST SUMMARY")
    logger.info("=" * 70)
    logger.info("Status: %s", overall)
    logger.info("Total: %d | PASSED: %d | WARN: %d | FAILED: %d",
                passed + warnings + failed, passed, warnings, failed)
    logger.info("Duration: %.1fs", total_duration / 1000)

    if failed > 0:
        logger.info("\nFAILED TESTS:")
        for r in results:
            if r["status"] in ("FAIL", "ERROR"):
                logger.info("  - %s: %s", r["name"], r["message"][:120])

    return report


def save_report(report):
    """Save test report to JSON file."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = REPORT_DIR / f"regression_{ts}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    latest = REPORT_DIR / "latest.json"
    with open(latest, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("\nReport saved: %s", path)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Jarvis Hub Regression Test Suite")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    logger.info("Jarvis Hub Regression Tests - Target: %s", base_url)

    report = run_all_tests(base_url)

    if report["status"] == "FAILED":
        sys.exit(1)
    sys.exit(0)
