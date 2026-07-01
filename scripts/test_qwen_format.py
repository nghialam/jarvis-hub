#!/usr/bin/env python3
"""Test what Ollama /v1/chat/completions returns for Qwen3.6-35B-A3B-MLX-8bit."""
import json, urllib.request, feedparser, sys
from datetime import datetime

OLLAMA = "http://localhost:11434"
MODEL = "Qwen3.6-35B-A3B-MLX-8bit"
TODAY = datetime.now().strftime('%d/%m/%Y (%A)')

# Fetch feeds
sources = [
        {"name": "CafeF",              "url": "https://cafef.vn/doanh-nghiep.rss",       "section": "VN"},
        {"name": "VnExpress",          "url": "https://vnexpress.net/rss/kinh-doanh.rss","section": "VN"},
        {"name": "The Verge AI",       "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",   "section": "AI"},
        {"name": "TechCrunch",         "url": "https://techcrunch.com/feed/",           "section": "TECH"},
        {"name": "Bloomberg Markets",  "url": "https://feeds.bloomberg.com/markets/news.rss", "section": "INTL"},
]

articles = []
for s in sources:
    d = feedparser.parse(s['url'])
    count = 0
    for e in d.entries[:5]:
        title = (e.get('title') or '').strip()
        summary = (e.get('summary') or e.get('description') or '').strip()[:300]
        if title and len(title) > 12:
            articles.append({"title": title, "link": e.get('link',''), 
                            "summary": summary, "source": s['name'], "section": s['section']})
            count += 1
    print("    %s: %d" % (s['name'], count))

seen = set(); uniq = []
for a in sorted(articles, key=lambda x: "VNINTLAI TECHNOENT".find(x.get('section','X'))):
    k = a['title'].strip().lower()
    if k not in seen and len(k) > 10:
        seen.add(k); uniq.append(a)

print("\nUNIQUE: %d" % len(uniq))

# Build article text EXACTLY like gotham_brief does
sections = {}
for a in uniq:
    sec = a['section']
    sections.setdefault(sec, [])
    s = (a.get('summary', '') or '').replace('\n', ' ')
    try: s = s.encode('utf-8', 'ignore').decode('utf-8')
    except: pass
    lines = ["     [%s] %s (%s)" % (a['source'], a['title'], a.get('link',''))]
    if s: lines.append("        - %s" % s)
    sections[sec].append('\n'.join(lines))

art_text = ""
for sec in ['VN', 'INTL', 'AI', 'TECH']:
    if sec in sections:
        art_text += "\n\n=== %s ===\n\n" % sec + '\n'.join(sections[sec])

print("\nARTICLE BLOB: %d chars" % len(art_text)) 
print(len(uniq), "articles ready for LLM")

# THE ACTUAL TEST
sys_prompt = """You are Jarvis, an AI intelligence analyst. TODAY IS %s.

Analyze these articles from the last 24 hours and output EXACTLY these sections:

### NEWS SYNTHESIS (AI Priority)
List up to 5 AI-related news items: new models, tools, startups, regulations.
Each item format: - title + 1-sentence summary [Source](url)

### MARKET TRENDS
Top 3 market trends and their drivers.
Bullish/Bearish/Neutral with reasoning.""" % TODAY

payload = json.dumps({
       'model': MODEL,
       'messages': [{'role': 'system', 'content': sys_prompt}, 
                    {'role': 'user', 'content': art_text}],
       'stream': False,
       'options': {'num_predict': 5120, 'temperature': 0.3}
}).encode('utf-8')

req = urllib.request.Request(
       "%s/v1/chat/completions" % OLLAMA, data=payload,
       headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req, timeout=120)
result = json.loads(resp.read())

msg = result.get('message', {})
thinking_raw = (msg.get('thinking') or '').strip()
content_raw  = (msg.get('content') or '').strip()

print("\n=== OLLAMA RESPONSE ANALYSIS ===")
print("thinking field: %d chars" % len(thinking_raw)) 
print("content field:  %d chars" % len(content_raw))

# What does gotham_brief currently get?
method_a = (msg.get('thinking') or msg.get('content') or '').strip()
print("\nMethod A (current): (thinking OR content) = %d chars" % len(method_a))
if method_a[:200]:
    print("   FIRST 200:", repr(method_a[:200]))

# What would the user see? First 3500 chars
print("\n--- User sees first 4000 chars ---")
display = method_a if len(method_a) > 4000 else method_a
if len(display) < 10:
    display = thinking_raw
    
# Try to extract only analysis from thinking text
analysis_extracted = ""
for marker in ['### NEWS SYNTHESIS', '### MARKET TRENDS', '### KEY FINDINGS']:
    if marker in thinking_raw:
        idx = thinking_raw.find(marker)
        analysis_extracted = thinking_raw[idx:].strip()
        print("\nMethod B (extract from thinking): FOUND AT CHAR %d" % idx)
        break
        
if not analysis_extracted and len(thinking_raw) > 100:
    # No standard marker - just return all thinking
    analysis_extracted = thinking_raw[:4000].strip()
    print("\nMethod B (fallback): returning full thinking text")

print("\n--- ANALYSIS EXTRACTED (what user ACTUALLY sees after our fix) ---")
# Show what the first ~3500 chars look like
final_output = analysis_extracted if len(analysis_extracted) > 100 else display
if len(final_output) > 4000:
    final_output = final_output[:4000]
print(final_output)
print("\n\nFINAL LENGTH:", len(final_output), "chars (will be chunked to", 
      -(len(final_output)//-3896) if len(final_output) > 3896 else 1, ")")
