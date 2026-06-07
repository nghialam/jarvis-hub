#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""Fast briefing - streamlined pipeline to Telegram chat 1670013239"""
import json, re, sys, os, time, urllib.request, urllib.error, textwrap
from datetime import datetime

try:
    import feedparser
except ImportError:
    print("FATAL: feedparser not installed. pip install feedparser")
    sys.exit(0)

CHAT_ID = "1670013239"
BOT_TOKEN = os.environ.get("JARVIS_BOT_TOKEN", "").strip() or \
            os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() or \
            open(os.path.expanduser("~/.hermes/.jarvis_token_cache")).read().strip()

RSS_SOURCES = [
    {"name": "Cafef Doanh nghiệp", "url": "https://cafef.vn/doanh-nghiep.rss", "section": "VN"},
    {"name": "VnExpress Kinh doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "section": "VN"},
    {"name": "Vietnamnet CK", "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "section": "VN"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "section": "AI"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "section": "TECH"},
]

def fetch_rss(source):
    try:
        d = feedparser.parse(source["url"])
        results = []
        for entry in d.entries[:4]:
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            link = (entry.get("link") or entry.get("id") or "").strip()
            if not link or len(title) < 15:
                continue
            results.append({
                "title": title, "link": link,
                "summary": summary[:200] if summary else "",
                "source": source["name"], "section": source["section"]
            })
        return results
    except Exception as e:
        print(f"[WARN] {source['name']}: {e}", file=sys.stderr)
        return []

def get_llm(section_name, sys_prompt, articles_text):
    ollama_url = "http://localhost:11434"
    model = "qwen3.6:35b-mlx"
    payload = {
        "model": model, "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": articles_text[:4000]},
        ], "stream": False, "options": {"temperature": 0.3, "num_predict": 32768}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url}/api/chat", data=req_data,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.loads(resp.read())
    return (result.get("message", {}).get("content") or "").strip()

def split_message(text, max_chars=3800):
    parts = []
    current = ""
    for line in text.split("\n\n"):
        if len(current) + len(line) > max_chars * 0.9 and current:
            parts.append(current.strip())
            current = line
        else:
            current = (current + "\n\n" + line).strip() if current else line
    if current:
        parts.append(current.strip())
    return parts

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": CHAT_ID, "text": chunk, "parse_mode": "Markdown"}
        req_data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            mid = json.loads(resp.read()).get("result", {}).get("message_id", "?")
            print(f"Sent chunk {i+1}/{len(chunks)} (msg_id:{mid})")
        except Exception as e:
            print(f"Telegram send failed: {e}", file=sys.stderr)

now = datetime.now()
day_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][now.weekday()]

print(f"[{now.strftime('%H:%M')}] Fast Briefing - {day_name}, {now.strftime('%d/%m/%Y')}")

# Phase 1: Fetch RSS
articles = []
for src in RSS_SOURCES:
    articles.extend(fetch_rss(src))

seen, unique = set(), []
for a in sorted(articles, key=lambda x: x.get("section", "")):
    k = a["title"].strip().lower()
    if k not in seen and len(k) > 10:
        seen.add(k)
        unique.append(a)
articles = unique[:20]
print(f"Fetched {len(articles)} articles from {len(set(a['section'] for a in articles))} sources")

if not articles:
    send_telegram("JARVIS INTELLIGENCE - Could not fetch RSS feeds. Check your network.")
    sys.exit(0)

# Build article text
art_text = ""
for i, a in enumerate(articles[:15], 1):
    s = (a.get("summary", "") or "").replace("\n", " ")
    link = a.get("link", "")
    art_text += f"{i}. [{a['source']}] {a['title']} ({link})\n- {s}\n\n"

# Phase 2: LLM Analysis
print("Running LLM analysis...")
now_s = now.strftime("%d/%m/%Y (%A)")

ai_prompt = f"""You are Jarvis, an intelligent news analyst. Today is {now_s}. Analyze these articles from the last 24 hours:
- Priority: AI breakthroughs (new models, tools, regulatory updates)
- Also cover: Politics/Macro economy, Technology trends, other important sectors
IMPORTANT FORMATTING:
- Use bullet points only (- or *). DO NOT use tables.
- Every major point MUST cite its source using markdown link format: [Source Name](url)
- Be sharp and strategic. Use Vietnamese language."""

trend_prompt = f"""Based on the collected news, analyze current trends as of {now_s}. Answer using bullet points:
1. What's the focal point? Are AI events correlating with other sectors?
2. Key trends to watch this week
3. Any emerging themes across multiple sources?
IMPORTANT: Bullet points only, no tables. Every major trend/conclusion MUST cite its source as [Name](url). Be concise and strategic. Use Vietnamese."""

rec_prompt = f"""Based on market context and AI trends as of {now_s}, provide 2-3 actionable recommendations using bullet points:
1. How to apply new AI tools for work/life optimization
2. Investment/tech direction observations
IMPORTANT: Bullet points only, no tables. Every recommendation MUST cite its supporting source as [Name](url). Be specific and practical, not generic. Use Vietnamese."""

try:
    ai_result = get_llm("AI", ai_prompt, art_text)
    print(f"AI analysis done: {len(ai_result)} chars")
except Exception as e:
    ai_result = f"[LLM Error - AI Section]: {e}"

try:
    trend_result = get_llm("Trend", trend_prompt, art_text)
    print(f"Trend analysis done: {len(trend_result)} chars")
except Exception as e:
    trend_result = f"[LLM Error - Trend Section]: {e}"

try:
    rec_result = get_llm("Recs", rec_prompt, art_text)
    print(f"Recommendations done: {len(rec_result)} chars")
except Exception as e:
    rec_result = f"[LLM Error - Recs Section]: {e}"

# Phase 3: Deliver to Telegram
header = f"⚡ JARVIS INTELLIGENCE FEED - {now_s}\n{'='*40}"

part1 = f"""{header}

🤖 AI & Tech Analysis:

{ai_result[:2500]}"""

part2 = f"""{'-'*40}

📊 Trend Analysis:

{trend_result}"""

part3 = f"""{'-'*40}

💡 Recommendations:

{rec_result}"""

print(f"\nDelivering briefing to Telegram chat {CHAT_ID}...")
send_telegram(part1)
time.sleep(2)
send_telegram(part2)
time.sleep(2)
send_telegram(part3)

print("\n✅ Briefing delivered!")
