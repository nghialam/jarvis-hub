#!/usr/bin/env python3
"""Systematic Regression Test Suite for Jarvis Hub Flask Dashboard.

Run after ANY code change to verify no regression has been introduced.
Usage: python scripts/verify-flask-dashboard.py
       JARVIS_BASE=http://localhost:8100 python scripts/verify-flask-dashboard.py

Author: auto-generated from flask-dashboard-troubleshooting skill
"""
import requests
import sys
import os

BASE = os.environ.get("JARVIS_BASE", "http://localhost:8100")

# Define the test suite
SUITE = [
    ("Health check", f"{BASE}/api/health"),
    ("Snapshots list", f"{BASE}/api/snapshots"),
    ("Single snapshot (2026-05-20)", f"{BASE}/api/snapshots/2026-05-20"),
    ("KB search (tai chinh)", f"{BASE}/api/search?q=tai+chinh"),
    ("Knowledge search (portfolio)", f"{BASE}/api/search?q=portfolio+diversification"),
    ("Analyze valid symbol (VNM)", f"{BASE}/api/analyze?symbol=VNM"),
    ("Analyze empty symbol", f"{BASE}/api/analyze?symbol="),
    ("Eval force refresh", f"{BASE}/api/evaluation?force=true"),
]

def test_endpoint(name, url):
    """Test a single endpoint and print result."""
    try:
        r = requests.get(url, timeout=30)
        
        # Check HTTP status
        if r.status_code >= 500:
            print(f"❌ {name}: HTTP {r.status_code} — {r.text[:200]}")
            return False
        
        # Parse response JSON
        try:
            data = r.json()
        except requests.exceptions.JSONDecodeError:
            print(f"⚠️  {name}: Non-JSON response ({r.status_code}, {len(r.content)}b)")
            return False
        
        if not isinstance(data, dict):
            print(f"⚠️  {name}: Response is not a JSON object (type={type(data).__name__})")
            return False
        
        payload_size = len(r.content)
        key_count = len(data)
        
        print(f"✅ {name}: OK ({r.status_code}, {payload_size}b, {key_count} keys: {', '.join(list(data.keys())[:5])})")
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"❌ {name}: CONNECTION ERROR — is the server running on {BASE}?")
        sys.exit(1)
    except Exception as e:
        print(f"❌ {name}: UNEXPECTED ERROR — {type(e).__name__}: {e}")
        return False

def verify_response_structure(name, url):
    """Deep verify: check specific keys exist for critical endpoints."""
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return False
        
        data = r.json()
        
        # Health must have 'status'
        if name == "Health check":
            assert "status" in data, f"Missing 'status' key"
        
        # Snapshots must have 'snapshots' list and 'count'
        elif name == "Snapshots list":
            assert "snapshots" in data, f"Missing 'snapshots' key"
            assert "count" in data, f"Missing 'count' key"
            assert isinstance(data["snapshots"], list), "snapshots must be a list"
        
        # Single snapshot must have 'date' and 'content'
        elif "Single snapshot" in name:
            assert "date" in data, f"Missing 'date' key"
            assert "content" in data, f"Missing 'content' key"
        
        # KB search must have 'results' list and 'count'
        elif name == "KB search (tai chinh)":
            assert "results" in data, f"Missing 'results' key"
            assert "count" in data, f"Missing 'count' key"
            if isinstance(data.get("results"), list) and len(data["results"]) > 0:
                first = data["results"][0]
                assert "score" in first or isinstance(first, dict), "Results must be dicts with 'score'"
        
        # Analyze must have price_data + technical_indicators or llm_report
        elif name == "Analyze valid symbol (VNM)":
            has_price = "price_data" in data or "data" in data
            has_ta = "technical_indicators" in data or "llm_report" in data
            assert has_price and has_ta, f"Missing price_data or technical_indicators in response: keys={list(data.keys())}"
        
        # Eval force must return evaluation content or error (not stale fallback silently)
        elif name == "Eval force refresh":
            assert "evaluation" in data or "error" in data, f"Missing 'evaluation' or 'error' key"
        
        return True
        
    except AssertionError as e:
        print(f"⚠️  {name}: STRUCTURE VIOLATION — {e}")
        return False
    except Exception:
        return False

def main():
    print("=" * 70)
    print(f"🔧 Jarvis Hub Regression Test Suite")
    print(f"   Target: {BASE}")
    print("=" * 70)
    
    results = []
    
    # Phase 1: Health Baseline
    print("\n--- Phase 1: Health Baseline ---")
    health_ok = test_endpoint("Health check", f"{BASE}/api/health")
    if not health_ok:
        print("\n❌ Server is not healthy. Aborting further tests.")
        sys.exit(1)
    
    # Phase 2 & 3: All endpoints
    print("\n--- Phase 2-3: Endpoint Regression ---")
    for name, url in SUITE[1:]:
        success = test_endpoint(name, url)
        deep_ok = verify_response_structure(name, url) if success else False
        results.append((name, success, deep_ok))
    
    # Phase 4: Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, s, d in results if s and d)
    partial = sum(1 for _, s, d in results if s and not d)
    failed = sum(1 for _, s, d in results if not s)
    total = len(results)
    
    for name, ok, deep_ok in results:
        status = "✅" if (ok and deep_ok) else ("⚠️" if ok else "❌")
        detail = " [MISSING KEYS]" if deep_ok is False else (" [no data]" if not ok else "")
        print(f"{status}  {name}{detail}")
    
    print("-" * 70)
    print(f"PASSED: {passed}/{total}")
    print(f"PARTIAL (keys missing): {partial}/{total}")
    print(f"FAILED: {failed}/{total}")
    
    if failed > 0:
        print("\n❌ REGRESSION TESTS FAILED — do NOT deploy/demonstrate")
        sys.exit(1)
    elif partial > 0:
        print("\n⚠️  Some endpoints missing expected keys — review before finalizing.")
    else:
        print("\n✅ ALL TESTS PASSED — ready to deploy/showcase")
    
    print("=" * 70)

if __name__ == "__main__":
    main()
