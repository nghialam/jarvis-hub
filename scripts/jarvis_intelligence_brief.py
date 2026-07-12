#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jarvis Intelligence Brief - Standalone RSS + LLM pipeline.
Outputs 4 sections: AI News Synthesis, Trend Analysis, Recommendations, Tech Lab.
Sent to Telegram as HTML chunks.

Usage: python3 jarvis_intelligence_brief.py [morning|afternoon|evening|bedtime]
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime


# ===================================================================
# Config
# ===================================================================
CHAT_ID = "-1003801745265"  # gotham private channel


def _get_token():
    for key in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        with open(p) as f:
            c = f.read().strip()
        if c:
            return c
    except Exception:
        pass
    return ""


BOT_TOKEN = _get_token()
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.6:35b-a3b-mxfp8")

RSS_SOURCES = [
    {"name": "CafeF Doanh Nghiep", "url": "https://cafef.vn/doanh-nghiep.rss", "section": "VN"},
    {"name": "VnExpress Kinh Doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "section": "VN"},
    {"name": "Vietnamnet CK", "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "section": "VN"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "section": "AI"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "section": "TECH"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "section": "INTL"},
]


# ===================================================================
# LLM Call - Sequential only (no ThreadPoolExecutor)
# ===================================================================

def get_llm(system_prompt, user_prompt, timeout=360):
    """Call Ollama /v1/chat/completions non-streaming. Retries 3x."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt[:8000]},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 4096}
    }
    req_data = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_URL}/v1/chat/completions", data=req_data,
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = json.loads(resp.read())
            text = (result.get("message", {}).get("content") or "").strip()
            if len(text) > 100:
                return text
        except Exception as e:
            if attempt < 2:
                print(f"    Retry {attempt+1}/3 after error: {e}")
                time.sleep(10)
            else:
                print(f"[LLM FAILED] Last error: {e}", file=sys.stderr)
    return "[No data - LLM pipeline failure]"


# ===================================================================
# Telegram delivery (HTML parse_mode, auto-split 3800 chars)
# ===================================================================

def _md_to_html(text):
    """Convert markdown to Telegram-compatible HTML."""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        # Links -> <a>
        line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)
        # Bold
        for tag in ['**', '__']:
            p = f"{line[0]}{line[1]}" if len(line) >= 2 else ""
            while p == "**" or "__":
                start = line.find(tag)
                end = line.find(tag, start+2)
                if start < 0 or end < 0:
                    break
                before = line[:start]
                inside = line[start+2:end]
                after = line[end+2:]
                line = f"{before}<b>{inside}</b>{after}"
        # Italic (only if no backtick on same line)
        if "`" not in line:
            while "*" in line:
                s = line.find("*")
                e = line.find("*", s+1)
                if s < 0 or e < 0:
                    break
                line = f"{line[:s]}<i>{line[s+1:e]}</i>{line[e+1:]}"
        # Inline code
        line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
        lines.append(line)
    return "\n".join(lines)


def send_telegram_chunks(text, mode="HTML"):
    """Send text to Telegram as HTML chunks (split at 3800 chars)."""
    if not BOT_TOKEN:
        print("[WARN] No Telegram token; skipping delivery")
        # Just print to stdout instead
        print(f"\n{'='*60}\n{text}\n{'='*60}")
        return True
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    html = _md_to_html(text)
    
    max_len = 3600
    parts = []
    for block in html.split("\n\n"):
        chunk = (chr(10)*2 + block).strip() if parts else block.strip()
        if len(chunk) > max_len and parts:
            parts.append(parts[-1][:max_len-50])  # Append to last
            # Actually, let's just split by chunks of max_len
            pass
    
    # Simpler splitting approach
    parts = []
    current = ""
    for block in html.split("\n\n"):
        test = (current + "\n\n" + block).strip() if current else block.strip()
        if len(test) > max_len:
            if current:
                parts.append(current[:max_len])
            current = block.strip()
        else:
            if current:
                current += "\n\n" + block
            else:
                current = block
    if current.strip():
        parts.append(current[:max_len] if len(current) > max_len else current.strip())

    print(f"\nSending {len(parts)} Telegram message(s)...")
    for i, part in enumerate(parts):
        try:
            payload = json.dumps({
                "chat_id": CHAT_ID,
                "text": part,
                "parse_mode": mode,
                "disable_web_page_preview": True,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print(f"  Sent chunk {i+1}/{len(parts)} (msg_id:{mid})")
        except Exception as e:
            print(f"[ERROR] Telegram chunk {i+1}: {e}", file=sys.stderr)

    return True


# ===================================================================
# RSS Collection
# ===================================================================

def fetch_rss(source):
    """Fetch and parse one RSS source, return list of article dicts."""
    try:
        import feedparser
        d = feedparser.parse(source["url"])
        out = []
        for entry in d.entries[:5]:
            title = (str(entry.get("title") or "")).strip()
            summary = (str(entry.get("summary") or entry.get("description") or "")).strip()
            raw_id = entry.get("id") or ""
            link = str(raw_id if not isinstance(raw_id, list) else (raw_id[0] if raw_id else ""))
            link = (entry.get("link") or link or "").strip()
            if not link:
                raw_id = entry.get("id", "")
                if isinstance(raw_id, list):
                    raw_id = raw_id[0] if raw_id else ""
                link = str(raw_id)
            if not link or len(title) < 15:
                continue
            clean_summary = summary[:400].encode("utf-8", "ignore").decode("utf-8")
            out.append({
                "title": title,
                "link": link,
                "summary": clean_summary,
                "source": source["name"],
                "section": source["section"],
                "published": entry.get("published", ""),
            })
        return out
    except Exception as e:
        print(f"[WARN] {source['name']}: {e}", file=sys.stderr)
        return []


def collect_and_dedupe():
    """Fetch all RSS sources, deduplicate by title, return sorted list."""
    all_arts = []
    for src in RSS_SOURCES:
        fetched = fetch_rss(src)
        all_arts.extend(fetched)
        if fetched:
            print(f"     {src['name']}: {len(fetched)} articles")

    # Deduplicate by title
    seen, unique = set(), []
    for a in sorted(all_arts, key=lambda x: "VNINTLAI TECHNOENT".find(x["section"])):
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique.append(a)

    # Prioritize AI/TECH, then INTL, VN
    ai_tech = [a for a in unique if a["section"] in ("AI", "TECH")]
    intl = [a for a in unique if a["section"] == "INTL"]
    vn = [a for a in unique if a["section"] == "VN"]

    selected = ai_tech[:12]           # AI/TECH top priority
    remaining = 20 - len(selected)
    if remaining > 0:
        selected.extend(intl[:remaining//2])
        selected.extend(vn[:remaining//2 + (remaining % 2)])

    return selected[:25]


def format_articles(articles):
    """Format articles grouped by section for LLM input."""
    sections = {}
    for a in articles:
        sec = a["section"]
        sections.setdefault(sec, [])
        lines = [f"  [{a['source']}] {a['title']} ({a['link']})"]
        if a.get("summary"):
            lines.append(f"      - {a['summary'][:200]}")
        sections[sec].append("\n".join(lines))

    art_text = ""
    labels = {
         "VN": "\ud83c\uddfb\ud83c\uddf3  TIN TRONG NUOC",
         "INTL": "\ud83c\udf0d  TIN QUOC TE",
         "AI": "\ud83e\udd27 AI & TECH",
         "TECH": "\ud83d\udcbb CONG NGHỆ",
    }

    for sec in ["AI", "TECH", "INTL", "VN"]:
        if sec in sections:
            art_text += f"\n\n{labels.get(sec, sec)}:\n\n" + ("\n".join(sections[sec]))

    return art_text[:12000]  # Cap at 12k chars for LLM context window


# ===================================================================
# Prompts - one per section to keep focused
# ===================================================================

def _build_prompts(date_str, articles_text):
    today = f"Today is {date_str}."
    
    prompts = [
        # Section 1: AI & News Synthesis
        (
            "NEWS SYNTHESIS",
            f"""You are Jarvis, an intelligence analyst. {today}

Analyze these articles from the last 24 hours:

{articles_text[:6000]}

---

Provide **NEWS SYNTHESIS:**
- List up to 5 most prominent AI news items: new models, tools, regulatory updates, prominent startups. 
- Format each: - title + 1 sentence summary [Source](url)
- Bullet points ONLY. NO tables. Be concise and sharp.""",
            200
        ),
        # Section 2: Trend Analysis  
        (
            "TREND ANALYSIS",
            f"""You are an experienced market analyst. {today}

Based on these articles:

{articles_text[:6000]}

---

Provide **TREND ANALYSIS:**
- Top 4 dominant news narratives/focal points from this period
- What is the correlation between AI/tech events and other sectors (finance, energy, geopolitics)?
- Market sentiment: Bullish / Bearish / Cautious + brief reasoning for each category
- Use bullet format only. NO tables.""",
            300
        ),
        # Section 3: Recommendations
        (
            "RECOMMENDATIONS",
            f"""You are an AI strategy consultant. {today}

From the news above, provide **ACTIONABLE RECOMMENDATIONS:**

2-3 specific work/life optimizations using newly available AI tools or technologies mentioned in the articles.
Include: exact tool names, concrete prompts/workflows, not generic advice.
Be strategic and actionable - what should I DO differently today?

Bullet format only. English.""",
            200
        ),
        # Section 4: Tech Lab
        (
            "TECH LAB",
            f"""You are a technical architect who builds practical AI prototypes. {today}

Analyzing these emerging tech trends from the news:

{articles_text[:6000]}

---

Propose **ONE concrete project/prototype** we can start building TODAY using currently available technology (OpenAI API, local LLMs via Ollama, huggingface transformers, RAG, agentic workflows, etc.)

Include:
- Project name + 1 sentence description  
- What real-world problem it solves (practical value)
- Tech stack: specific tools/libraries/APIs available today
- Architecture overview (3-5 bullet points of the system design)
- First week milestones (what to build first, second, third)

Be specific. No "future-looking" ideas - only what works NOW.""",
            300
        ),
    ]
    return prompts


# ===================================================================
# Main Pipeline
# ===================================================================

def run_brief(mode="morning"):
    now = datetime.now()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"][now.weekday()]
    date_str = now.strftime('%d/%m/%Y')
    header = (
        f"**JARVIS INTELLIGENCE BRIEF** {date_str} ({day_name})\n"
        f"\u23f0 {mode.title()} Edition"
    )

    print(f"[{now.strftime('%H:%M')}] Jarvis Intelligence Brief - {mode}")

    # Phase 1: RSS collection
    print("Phase 1: Fetching RSS feeds...")
    articles = collect_and_dedupe()
    print(f"     Fetched {len(articles)} unique articles (after dedup)")

    if not articles:
        msg = f"{header}\n\n\u26a0\ufe0f Could not fetch any RSS feeds. Check network."
        send_telegram_chunks(msg)
        return

    articles_text = format_articles(articles)
    print(f"     Articles blob: {len(articles_text)} chars")

    # Phase 2: Sequential LLM analysis (4 calls, ~3-6 min total)
    prompts = _build_prompts(date_str, articles_text)
    sections_output = {}

    for section_name, prompt, timeout_sec in prompts:
        print(f"\nPhase 2: Running [{section_name}]... ({timeout_sec}s)")
        result = get_llm(prompt, articles_text[:8000], timeout=timeout_sec)
        sections_output[section_name] = result
        print(f"     => {len(result)} chars received")

    # Phase 3: Format into Telegram-friendly brief
    print("\nPhase 3: Formatting and delivering...")

    full_brief = f"{header}\n\n{'=' * 40}\n\n"
    
    for section, content in [
        ("\ud83d\udd27 NEWS SYNTHESIS & AI TRENDS", sections_output.get("NEWS SYNTHESIS", "No data")),
        ("\ud83d\udcc8 TREND ANALYSIS", sections_output.get("TREND ANALYSIS", "No data")),
        ("\ud83e\udde0 ACTIONABLE RECOMMENDATIONS", sections_output.get("RECOMMENDATIONS", "No data")),
        ("\ud83d\udee0\ufe0f TECH LAB - Project Proposal", sections_output.get("TECH LAB", "No data")),
    ]:
        full_brief += f"\n{section}\n\n{content[:2500]}\n\n"

    send_telegram_chunks(full_brief, mode="HTML")
    print("\n\u2705 Jarvis Intelligence Brief delivered!")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "morning"
    run_brief(mode)
