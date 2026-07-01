#!/usr/bin/env python3
"""Run full Jarvis intelligence briefing with Ollama LLM - file-based approach."""
import json, urllib.request, sys
from datetime import datetime

def call_ollama(system_prompt, user_text, model="gemma4:e4b-mxfp8", timeout_sec=120):
    """Call Ollama /v1/chat/completions and return the response content."""
    payload = {
         "model": model,
         "messages": [
             {"role": "system", "content": system_prompt},
             {"role": "user", "content": user_text[:4000]},
         ],
         "stream": False,
         "options": {"temperature": 0.3}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:11434/v1/chat/completions", data=req_data,
        headers={"Content-Type": "application/json"}
     )
    resp = urllib.request.urlopen(req, timeout=timeout_sec)
    result = json.loads(resp.read())
    return (result.get("message", {}).get("content") or "").strip()

articles_json = json.load(open("/tmp/jarvis_articles.json"))

art_text = ""
for i, a in enumerate(articles_json[:15], 1):
    s = (a.get("summary", "") or "").replace("\n", " ")
    link = a.get("link", "")
    art_text += f"{i}. [{a['source']}] {a['title']} ({link})\n- {s}\n\n"

print(f"Article text: {len(art_text)} chars from {len(set(a['section'] for a in articles_json[:15]))} sources")

prompts = [
    ("AI & Tech Analysis",
     """You are Jarvis, an intelligent news analyst. Analyze these articles from the last 24h:
- Priority: AI breakthroughs (new models, tools, regulatory updates)
- Also cover: Politics/Macro economy, Technology trends
IMPORTANT FORMATTING:
- Use bullet points only (- or *). DO NOT use tables.
- Every major point MUST cite its source using link format: [Source Name](url)
- Be sharp and strategic. Use Vietnamese."""),

    ("Trend Analysis",
     """Based on the collected news, analyze current trends using bullet points:
1. What's the focal point? Are AI events correlating with other sectors?
2. Key trends to watch this week
3. Any emerging themes across multiple sources?
IMPORTANT: Bullet points only, no tables. Every major trend/conclusion MUST cite its source as [Name](url). Be concise and strategic. Use Vietnamese."""),

    ("Recommendations",
     """Based on market context and AI trends, provide 2-3 actionable recommendations using bullet points:
1. How to apply new AI tools for work/life optimization
2. Investment/tech direction observations
IMPORTANT: Bullet points only, no tables. Every recommendation MUST cite its supporting source as [Name](url). Be specific and practical. Use Vietnamese."""),
]

print("Running LLM analysis (gemma4 model)...")
results = {}
for i, (name, prompt) in enumerate(prompts):
    print(f"  Section {i+1}/{len(prompts)}: {name}...", file=sys.stderr)
    result = None
    try:
        for attempt in range(3):
            try:
                result = call_ollama(prompt, art_text, model="gemma4:e4b-mxfp8", timeout_sec=120)
                if result and not result.startswith("[Error:") and "Ollama" not in result:
                    break
            except Exception as retry_e:
                print(f"    Attempt {attempt+1} failed: {retry_e}", file=sys.stderr)
    except Exception as e:
        result = f"[Error: {e}]"

    results[name] = result if result else f"[Error: All attempts failed for {name}]"
    print(f"   {name}: done ({len(results[name])} chars)", file=sys.stderr)

# Save individual sections
for name, text in results.items():
    safe_name = name.replace(" ", "_").lower()
    with open(f"/tmp/jarvis_{safe_name}.txt", "w") as f:
        f.write(text)

# Save combined briefing
now = datetime.now()
day_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][now.weekday()]

with open("/tmp/jarvis_combined.txt", "w") as f:
    header = f"JARVIS INTELLIGENCE FEED - {now.strftime('%d/%m/%Y')} ({day_name})\n{'='*40}\n\n"
    f.write(header)
    f.write(f"{results.get('AI & Tech Analysis', '[No data]')[:3000]}\n")
    f.write("\n" + "="*40 + "\n\n")
    f.write(f"{results.get('Trend Analysis', '[No data]')[:3500]}\n")
    f.write("\n" + "="*40 + "\n\n")
    f.write(results.get("Recommendations", "[No data]"))

print("Briefing saved to /tmp/jarvis_combined.txt")
