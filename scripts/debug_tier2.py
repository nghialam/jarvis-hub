#!/usr/bin/env python3
"""Debug script to test Tier 2 with verbose output."""
import sys, os
sys.path.insert(0, '/Users/nghialam/jarvis-hub')

os.environ.setdefault('JARVIS_HUB_PATH', '/Users/nghialam/jarvis-hub')

from core.tier_llm_analyst import fetch_analysis_data, build_analysis_prompt, get_conn
import requests
import time

conn = get_conn()
raw = fetch_analysis_data(conn)
prompt = build_analysis_prompt(raw)

print(f"Prompt length: {len(prompt)} chars")

# Warm-up
print("Warming up...")
r_warm = requests.post(
     "http://localhost:11434/api/generate",
    json={"model": "qwen3.6:35b-a3b-mxfp8", "prompt": "OK", "stream": False, "options": {"num_predict": 1}},
    timeout=120,
)
print(f"Warm-up: {r_warm.status_code}")

# Run full prompt
print(f"\nRunning full analysis (timeout 600s)...")
payload = {
     "model": "qwen3.6:35b-a3b-mxfp8",
     "prompt": prompt,
     "stream": False,
     "options": {"temperature": 0.3, "num_predict": 2048, "top_p": 0.9},
}

start = time.time()
r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=600)
elapsed = time.time() - start

print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    resp = data.get('response', '')
    print(f"\n=== RESULT ===")
    print(f"Response length: {len(resp)} chars")
    print(f"Done: {data.get('done')}")
    print(f"Eval count: {data.get('eval_count', 'N/A')} tokens")
    print(f"Time: {elapsed:.1f}s")
    print(f"\n--- PREVIEW ---\n{resp[:800]}...")
else:
    print(f"Error: {r.text[:500]}")

conn.close()
