#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""jarvis_noon_briefing.py - Noon briefing runner for cron job"""
import json, re, sys, os, time, urllib.request, urllib.error
from datetime import datetime

try:
    import feedparser
except ImportError:
    print("FATAL: feedparser not installed")
    sys.exit(1)

OMLX_URL = "http://localhost:11434"
MODEL = "Qwen3.6-35B-A3B-MLX-8bit"

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
        if not d.entries:
            return []
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


def ollama_chat(system_prompt, user_content, timeout=600):
    """Call Ollama /v1/chat/completions endpoint."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content[:5000]},
        ],
        "stream": False,
        "options": {"temperature": 0.3}
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OMLX_URL}/v1/chat/completions", data=req_data,
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read())
        return (result.get("message", {}).get("content") or "").strip()
    except Exception as e:
        print(f"[LLM ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        return f"[LLM Error - {type(e).__name__}]"


def retry_ollama(system_prompt, user_content, section_name, max_attempts=2):
    """Retry LLM call with delay."""
    for attempt in range(max_attempts):
        try:
            result = ollama_chat(system_prompt, user_content)
            if result and not result.startswith("[LLM Error"):
                return result
        except Exception as e:
            print(f"  {section_name} attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(10)
    return "[Unavailable - LLM service error]"


def main():
    now = datetime.now()
    day_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][now.weekday()]

    print(f"[{now.strftime('%H:%M')}] Jarvis Noon Briefing - {day_name}, {now.strftime('%d/%m/%Y')}")

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
    articles = unique[:15]

    print(f"Fetched {len(articles)} articles from {len(set(a['section'] for a in articles))} sources")

    if not articles:
        print("ERROR: No RSS feeds fetched. Exiting.")
        return

    # Build article text
    art_text = ""
    for i, a in enumerate(articles[:15], 1):
        s = (a.get("summary", "") or "").replace("\n", " ")
        link = a.get("link", "")
        art_text += f"{i}. [{a['source']}] {a['title']} ({link})\n- {s}\n\n"

    # Phase 2: LLM Analysis sections (sequential to avoid Ollama overload)
    now_s = f"{now.strftime('%d/%m/%Y')} ({day_name}), around noon local time"

    print("\nPhase 2: LLM Analysis...")

    # Section 1: Global Macro & Geopolitical Summary
    print("  [1/3] Computing global macro & geopolitical summary...")
    macro_prompt = f"""You are Jarvis, an intelligent news analyst. Today is {now_s}. Analyze these articles from the last 24 hours covering global and Vietnam news:

PROVIDE a structured analysis with exactly these sections using bullet points (NO tables):

## 🌍 Global Macro & Geopolitical Summary
- Key geopolitical developments and their economic implications
- Major policy/macro trends (central banks, trade, sanctions, conflicts)
- Impact assessment on global markets

FORMAT: Bullet points only. Cite sources as [Source Name](url). Be concise but thorough."""

    macro = retry_ollama(macro_prompt, art_text, "Global Macro")
    print(f"  Global macro ready: {len(macro)} chars")
    time.sleep(2)

    # Section 2: Market Movements
    print("  [2/3] Computing market movements...")
    market_prompt = f"""You are a financial markets analyst. Today is {now_s}. Based on these news articles from the last 24h, provide an analysis of:

PROVIDE using bullet points (NO tables):

## 📈 Key Market Movements
- Global indices performance (S&P500, NASDAQ, SSE, etc.) and key levels
- Sector highlights (AI/Tech, Energy, Finance, etc.)
- Commodities (gold, oil, copper) and currency movements
- Vietnamese market (VN-Index, HOSE, HNX) if mentioned

Cite sources as [Source Name](url). Be specific about numbers and trends."""

    market = retry_ollama(market_prompt, art_text, "Market Movements")
    print(f"  Market analysis ready: {len(market)} chars")
    time.sleep(2)

    # Section 3: Notable News & AI/Tech Breakthroughs
    print("  [3/3] Computing notable news and AI breakthroughs...")
    news_prompt = f"""You are an intelligent analyst. Today is {now_s}. Analyze these articles:

PROVIDE using bullet points (NO tables):

## 🤖 Notable News & AI/Tech Highlights
- Top 3-5 most important new developments (prioritize AI, tech breakthroughs)
- Major corporate/industry news with brief context
- Emerging themes across multiple sources

Cite sources as [Source Name](url). Be sharp and strategic."""

    news = retry_ollama(news_prompt, art_text, "Notable News")
    print(f"  Notable news ready: {len(news)} chars")

    # Phase 3: Actionable Signals
    print("\nPhase 2b: Computing actionable signals...")
    signal_prompt = f"""You are Jarvis, an AI-powered investment and strategy advisor. Today is {now_s}. Based on this news analysis:

PROVIDE using bullet points (NO tables):

## 💡 Actionable Signals & Conclusions
- Top 3 market outlook signals (bullish / bearish / cautious) with reasoning
- Key investment implications or risk warnings for the coming days
- Strategic observation on AI/tech direction

Cite sources as [Source Name](url). Be specific and actionable, not generic."""

    signals = retry_ollama(signal_prompt, art_text, "Actionable Signals")
    print(f"  Signals ready: {len(signals)} chars")

    # Compile final briefing
    header = f"☕ JARVIS NOON BRIEFING — {now_s}\n{'=' * 40}"

    briefing = f"""{header}

🌍 **Global Macro & Geopolitical**

{macro[:2500]}

---

📈 **Key Market Movements**

{market[:2500]}

---

🤖 **Notable News & Highlights**

{news[:2500]}

---

💡 **Actionable Signals**

{signals[:2000]}"""

    # Output to stdout for cron system to deliver
    print("\n" + "=" * 60)
    print("FINAL BRIEFING:\n")
    print(briefing)


if __name__ == "__main__":
    main()
