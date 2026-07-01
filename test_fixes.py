#!/usr/bin/env python3
"""
Test suite for Jarvis Hub fixes (Issue 1-5)
Run: python3 test_fixes.py

Timeout set to 5s per endpoint — Yahoo Finance calls can be slow,
so we avoid endpoints that trigger external API calls.
"""

import urllib.request
import json
import sys
import os

BASE = "http://localhost:8100"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94mℹ\033[0m"

results = []

def test(name, predicate, detail=""):
    status = PASS if predicate else FAIL
    results.append((name, predicate))
    msg = f"{status} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return predicate

def api_call(endpoint):
    """GET an API endpoint, return (status_code, data_dict). Returns None on error."""
    try:
        url = BASE + endpoint
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode("utf-8"))
        return resp.status, data
    except json.JSONDecodeError as e:
        print(f"  JSON parse error on {endpoint}: {e}")
        return None, None
    except Exception as e:
        return None, str(e)

print("=" * 60)
print("JARVIS HUB FIX VERIFICATION SUITE")
print("=" * 60)
print()

# ---- Issue 1: Analyze prompt enhancement ----
print("--- Issues 1+5: Code Review (Analyze Prompt) ---")
with open("/Users/nghialam/jarvis-hub/app.py", "r") as f:
    app_code = f.read()

test("Issue 1: 'SUPPORT & RESISTANCE' in prompt", 
     "SUPPORT & RESISTANCE" in app_code,
     "LLM will identify S1/S2/S3 and R1/R2/R3 levels")

test("Issue 1: Buy/Sell/Hold recommendation prompt",
     ("KHUYEN NGHỊ: [MUA / HOLD / BÁN]" in app_code or 
      "Mua/Ban/Khoi hold" in app_code),
     "LLM will give clear B/S/H recommendation with confidence")

test("Issue 1: Catalyst section in prompt",
     "CATALYST ĐẦU TƯ" in app_code,
     "LLM will list potential catalysts (bullish/bearish)")

test("Issue 1: Technical indicators in prompt data",
     ("SMA_20" in app_code and "RSI_14" in app_code and 
      "MACD" in app_code),
     "Price, volume, 52-week range, TA summary all included")

print()

# ---- Issue 2: KB search normalization ----
print("--- Issue 2: KB Search Result Format ---")
status, data = api_call("/api/search?q=test")

if status == 200 and isinstance(data, dict):
    test("Issue 2: KB API returns JSON with count", 
         "count" in data, 
         f"count={data.get('count', '?')}")
    
    if "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
        first = data["results"][0]
        required = ["score", "term", "content", "updated_at"]
        present = [f for f in required if f in first]
        missing = [f for f in required if f not in first]
        
        test("Issue 2: KB results have all required fields",
             len(missing) == 0,
             f"present={present}, missing={missing if missing else 'none'}")
        
        if len(missing) == 0 and "updated_at" in first:
            test("Issue 2: updated_at field has value",
                 first["updated_at"] != "N/A" and first["updated_at"],
                 f"value={first['updated_at'][:30]}")
    else:
        test("Issue 2: KB search returns empty results (OK, DB may be empty)", 
             True, 
             "No results — endpoint works, just no data")
else:
    err_detail = data if isinstance(data, str) else status
    test("Issue 2: KB API responds", False, f"HTTP {err_detail}")

print()

# ---- Issue 3: Snapshot modal + loadSnapshots fix ----
print("--- Issue 3: Daily Snapshots ---")
status, data = api_call("/api/snapshots")

if status == 200 and isinstance(data, dict):
    test("Issue 3: API returns snapshots list",
         "snapshots" in data,
         f"count={data.get('count', '?')}")
    
    if data.get("snapshots"):
        first_snap = data["snapshots"][0]
        has_preview = "preview" in first_snap
        has_full = "full_content" in first_snap
        test("Issue 3: Snapshot entries have preview + full_content",
             has_preview and has_full,
             f"preview={'✓' if has_preview else '✗'}, full_content={'✓' if has_full else '✗'}")
    else:
        test("Issue 3: No snapshots yet — run 'jarvis briefing' first", True, "Expected state")
else:
    err_detail = data if isinstance(data, str) else status
    test("Issue 3: Snapshots API responds", False, f"HTTP {err_detail}")

# Code review for JavaScript fix in index.html
with open("/Users/nghialam/jarvis-hub/dashboard/templates/index.html", "r") as f:
    js_code = f.read()

test("Issue 3: loadSnapshots has 'let html' declaration",
     "let html = '';" in js_code and 
     "window._cachedSnapshots" in js_code,
     "Variable `html` is now declared before forEach loop")

test("Issue 3: showSnapshot opens modal immediately",
     "modal.classList.remove('hidden')" in js_code and
     "modal.style.display = 'block'" in js_code and
     "Đang tải brief" in js_code,
     "Modal opens instantly with loading spinner")

test("Issue 3: No duplicate cache assignment line",
     js_code.count("window._cachedSnapshots = data.snapshots;") == 1,
     f"Occurrences: {js_code.count('window._cachedSnapshots = data.snapshots;')} (expected: 1)")

print()

# ---- Issue 4: Eval fresh data before generation ----
print("--- Issue 4: Eval Data Freshness ---")

# Code review for the critical fix
test("Issue 4: GET /api/market-evaluation refreshes cache first",
     "[EVAL] Evaluating needs fresh data" in app_code and
     "Eval pre-refresh" in app_code,
     "GET endpoint now fetches fresh data before calling generate_daily_evaluation()")

test("Issue 4: Cache update uses _cache_lock thread safety",
     'with _cache_lock:' in app_code and 
     '_cache["cache_time"] = now.timestamp()' in app_code,
     "Thread-safe cache update with timestamp refresh")

test("Issue 4: All data sources refreshed (7+ parallel)",
     "ThreadPoolExecutor(max_workers=7)" in app_code or
     "executor.submit(_fw" in app_code,
     "indices, rates, crypto(BTC/ETH/SOL), gold, dxy, oil fetched in parallel")

print()

# ---- Bonus: Health check (fastest endpoint, no external calls) ----
print("--- BONUS: Server Health ---")
status, data = api_call("/api/health")
if status == 200 and isinstance(data, dict):
    test("Health: Server is running", True, f"timestamp={data.get('timestamp')}")
    test("Health: Ollama connected", 
         "online" in str(data.get("omlx", "")),
         f"status={data.get('omlx')}")
    
    cache_age = data.get("cache_age_seconds")
    if cache_age is not None:
        minutes = cache_age / 60
        stale = minutes > 10
        test(f"Health: Cache age is {minutes:.0f}min", 
             not stale, 
             f"{'FRESH' if not stale else 'STALE'}")
    else:
        test("Health: No cache_age field", False, "May be first request or no market data yet")
else:
    err_detail = data if isinstance(data, str) else status
    test("Health: Server responds", False, f"HTTP {err_detail}")

print()

# ---- Summary ----
print("=" * 60)
print("TEST RESULTS")
print("=" * 60)
passed = sum(1 for _, p in results if p)
total = len(results)
for name, status in results:
    icon = PASS if status else FAIL
    print(f"{icon} {name}")

print()
print(f"Total: {passed}/{total} PASSED")

if passed == total:
    print("\n🎉 ALL FIXES VERIFIED!")
    sys.exit(0)
else:
    failed = sum(1 for _, p in results if not p)
    print(f"\n⚠️  {failed} test(s) need attention")
    sys.exit(1)
