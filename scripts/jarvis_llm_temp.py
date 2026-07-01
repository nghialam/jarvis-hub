#!/usr/bin/env python3
"""Run Ollama analysis and output result."""
import json, urllib.request

with open("/tmp/jarvis_articles.txt") as f:
    articles_text = f.read()

ai_prompt = """You are Jarvis, an intelligent news analyst. Analyze these articles from the last 24h:

Priority: AI breakthroughs (new models, tools, regulatory updates)
Also cover: Politics/Macro economy, Technology trends, other sectors

IMPORTANT FORMATTING:
- Use bullet points only (- or *). DO NOT use tables.
- Every major point MUST cite its source using link format: [Source Name](url)
- Be sharp and strategic. Use Vietnamese."""

articles_text = articles_text[4000:]  # Take first 4000 chars
system_prompt = ai_prompt + "\n\n" + articles_text

payload = {
    "model": "gemma4:e4b-mxfp8",
    "messages": [
        {"role": "system", "content": system_prompt},
    ],
    "stream": False,
    "options": {"temperature": 0.3}
}

req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:11434/v1/chat/completions", data=req_data,
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req, timeout=120)
result = json.loads(resp.read())
content = result.get("message", {}).get("content") or ""
print(content[:5000])
