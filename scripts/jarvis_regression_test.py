#!/usr/bin/env python3
"""jarvis_regression_test.py — Jarvis Hub API Regression Tests.
Automated tests run at 3am daily to detect bugs early."""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "http://localhost:8100"
BOT_TOKEN = "8733142640:AAHs32LJp2bdJhbjYlVCaOYWwMl0ERZ0rQk"
CHAT_ID = "-1003801745265"     # private chat

tests_passed = 0
tests_failed = 0
test_results = []


def add_result(name, passed, details=""):
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        icon = "OK"
    else:
        tests_failed += 1
        icon = "FAIL"
    test_results.append(f"{icon} {name}: {details}")


def http_get(path, timeout=10):
    try:
        url = f"{BASE_URL}{path}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read())
        return resp.status, data
    except Exception as e:
        raise


def test_health_endpoint():
    try:
        status, data = http_get("/api/health")
        if status == 200 and "indices" in data:
            add_result("Health Endpoint", True, f"OK ({len(data.get('indices', {}))} indices)")
        else:
            add_result("Health Endpoint", False, f"Status {status}, missing indices field")
    except Exception as e:
        add_result("Health Endpoint", False, str(e))


def test_articles_api():
    try:
        status, data = http_get("/api/articles?limit=5")
        if status == 200 and "articles" in data:
            count = len(data["articles"])
            add_result("Articles API", True, f"{count} articles returned")
        else:
            add_result("Articles API", False, f"Status {status}, missing articles key")
    except Exception as e:
        add_result("Articles API", False, str(e))


def test_articles_filter():
    try:
        status, data = http_get("/api/articles?category=vn-stock&limit=10")
        if status == 200:
            articles = data.get("articles", [])
            all_match = all(a.get("category") == "vn-stock" for a in articles)
            add_result("Articles Filter", all_match,
                        f"{len(articles)} returned, {'All match' if all_match else 'Some mismatch'}")
        else:
            add_result("Articles Filter", False, f"Status {status}")
    except Exception as e:
        add_result("Articles Filter", False, str(e))


def test_kb_search():
    try:
        status, data = http_get("/api/search?q=RSI")
        if status == 200 and "results" in data:
            add_result("KB Search", True, f"{len(data.get('results', []))} results found")
        else:
            add_result("KB Search", False, f"Status {status}, missing results key")
    except Exception as e:
        add_result("KB Search", False, str(e))


def test_watchlist():
    try:
        status, data = http_get("/api/watchlist")
        if status == 200 and isinstance(data, dict):
            items = data.get("watchlist", [])
            add_result("Watchlist", True, f"{len(items)} items in watchlist")
        else:
            add_result("Watchlist", False, f"Status {status}, unexpected format")
    except Exception as e:
        add_result("Watchlist", False, str(e))


def test_market_eval():
    try:
        status, data = http_get("/api/market-evaluation?force=true")
        if status == 200 and ("evaluation" in data or "error" not in data):
            eval_len = len(data.get("evaluation", ""))
            add_result("Market Eval", True, f"OK ({eval_len} chars)")
        else:
            add_result("Market Eval", False, f"Status {status}, missing evaluation")
    except Exception as e:
        add_result("Market Eval", False, str(e))


def send_telegram(text, max_parts=4):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) > 3800:
            parts.append(current)
            current = line
        else:
            current = (current + "\n" + line).strip() if current else line
    if current:
        parts.append(current)

    for i, part in enumerate(parts[:max_parts]):
        payload = {
            "chat_id": CHAT_ID,
            "text": part,
            "parse_mode": "Markdown",
        }
        req_data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            msg_id = result.get("result", {}).get("message_id", "?")
            print(f"Telegram chunk {i+1}/{len(parts)} sent (msg: {msg_id})")
        except Exception as e:
            print(f"Telegram send failed: {e}")


def run_tests(test_mode=False):
    now = datetime.now()

    print("=" * 60)
    print("JARVIS HUB DAILY REGRESSION TEST")
    print(f"Date: {now.strftime('%d/%m/%Y %H:%M')}")
    print("=" * 60)

    test_health_endpoint()
    test_articles_api()
    test_articles_filter()
    test_kb_search()
    test_watchlist()
    test_market_eval()

    total = tests_passed + tests_failed
    passed_pct = int(tests_passed / total * 100) if total > 0 else 0

    lines = [f"JARVIS HUB REGRESSION REPORT - {now.strftime('%d/%m/%Y')}", "",
             f"Total: {total} tests, OK: {tests_passed}, FAIL: {tests_failed} ({passed_pct}%)",
             "", "-- TEST RESULTS --"]

    for result in test_results:
        lines.append(result)

    lines.extend(["", "-- SUMMARY --",
                  f"Run at: {now.strftime('%Y-%m-%d %H:%M')}", "Next run: Tomorrow 03:02 AM"])

    report = "\n".join(lines)
    print("\n" + report + "\n")

    if not test_mode:
        send_telegram(report)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    if mode in ("--test", "test"):
        run_tests(test_mode=True)
    else:
        print("Starting regression tests...")
        run_tests()
        print("\nAll tests complete!")
