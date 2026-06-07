#!/usr/bin/env python3
"""Comprehensive test for all 4 issues."""
import requests
import json
from datetime import datetime, timedelta

BASE = "http://localhost:8100"

print("=" * 60)
print("COMPREHENSIVE SYSTEM TEST")
print("=" * 60)

# ========== ISSUE 1: Analyze missing fields ==========
print("\n📊 ISSUE 1: /api/analyze - Missing fields")
print("-" * 80)
t0 = datetime.now()
r = requests.get(f"{BASE}/api/analyze?symbol=VCB", timeout=60)
elapsed = (datetime.now() - t0).total_seconds()

data = r.json()
d = data.get("data", {})
keys = list(d.keys())

print(f"   Status: {r.status_code}")
print(f"   Response time: {elapsed:.1f}s")
print(f"   Keys: {', '.join(keys)}")
print(f"   Price: {d.get('price', 'N/A')}")
print(f"   Name: {d.get('name', 'N/A')}")
print(f"   Technical Summary: {'✅ YES' if d.get('technical_summary') else '❌ NO'}")
print(f"   LLM Report: {'✅ YES' if d.get('llm_report') else '❌ NO (empty)'}")

if d.get("llm_report"):
    report = d["llm_report"][:500]
    print(f"\n   📝 LLM Report preview:\n{report}\n")

# ========== ISSUE 2: KB search error ==========
print("\n📚 ISSUE 2: Knowledge Base Search Error")
print("-" * 80)
r = requests.get(f"{BASE}/api/search?q=portfolio&generate=false", timeout=10)
data = r.json()

if "results" in data:
    results = data["results"]
    print(f"   Found {len(results)} results")
    if results:
        for i, item in enumerate(results[:3]):
            print(f"\n   Result {i+1}:")
            # Backend returns [score, term, content] list format
            if isinstance(item, list):
                score, term, content = item[0], item[1], item[2]
                print(f"     Term: {term}")
                print(f"     Score: {score}")
                print(f"     Content: {content[:150]}")
            else:
                print(f"     Term: {item.get('term', 'N/A')}")
else:
    print(f"   ❌ No 'results' key")
    print(f"   Response keys: {list(data.keys())}")

# ========== ISSUE 3: Daily snapshots click handler ==========
print("\n📅 ISSUE 3: Daily Snapshots (2026-05-20)")
print("-" * 80)
r = requests.get(f"{BASE}/api/snapshots", timeout=10)
data = r.json()

snapshots = data.get("snapshots", [])
print(f"   Found {len(snapshots)} snapshots total")

# Check if 2026-05-20 exists
has_20may = any("2026-05-20" in str(s) for s in snapshots)
print(f"   Has 2026-05-20: {'✅ YES' if has_20may else '❌ NO'}")

for entry in snapshots[:3]:
    print(f"\n   Entry: {entry}")

# ========== ISSUE 4: Evaluations endpoint + cache freshness ==========
print("\n📋 ISSUE 4: Market Eval stale data")
print("-" * 80)

r = requests.get(f"{BASE}/api/eval", timeout=10)
print(f"   /api/eval status: {r.status_code}")

# Check cache freshness via health endpoint
r = requests.get(f"{BASE}/api/health", timeout=10)
health = r.json()
cache_age = health.get("cache_age_seconds", 0)
updated = health.get("timestamp", "Unknown")

print(f"   Cache age: {cache_age}s ({cache_age/60:.1f} min)")
print(f"   Last updated: {updated}")
print(f"   Status: ✅ {'Fresh' if cache_age < 300 else 'OLD DATA ⚠️'}")
