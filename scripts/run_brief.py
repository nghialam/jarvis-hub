#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jarvis Intelligence Brief - One-shot run for today's morning briefing."""
import json, urllib.request, time, sys, os, re, feedparser
from datetime import datetime


OMLX_URL = os.environ.get("OMLX_HOST", "http://localhost:11434")
LLM_MODEL = "Qwen3.6-35B-A3B-MLX-8bit"  # Local model only
CHAT_ID = "-1003801745265"


def _get_token():
    for key in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        with open(p) as f:
            c = f.read().strip()
        return c
    except Exception:
        pass
    return ""


BOT_TOKEN = _get_token()
if not BOT_TOKEN:
    print("FATAL: No Telegram token found. Set JARVIS_BOT_TOKEN or write it to ~/.hermes/.jarvis_token_cache")
    sys.exit(1)


def send_telegram(text, mode="HTML"):
    """Send text to Telegram with markdown->HTML conversion, auto-split at 3500 chars."""
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
            while True:
                start = line.find(tag)
                if start < 0:
                    break
                end = line.find(tag, start + 2)
                if end < 0:
                    break
                before = line[:start]
                inside = line[start + 2:end]
                after = line[end + 2:]
                tag_html = '<b>' if tag == '**' else '<strong>'
                line = f"{before}{tag_html}{inside}</{tag_html}>{after}"
        # Italic (only no backtick on same line to avoid breaking code)
        if "`" not in line:
            s = 0
            while True:
                s = line.find("*", s)
                if s < 0:
                    break
                e = line.find("*", s + 1)
                if e < 0:
                    break
                line = f"{line[:s]}<i>{line[s+1:e]}</i>{line[e+1:]}"
                s += 9  # Move past the closing tag
        # Inline code
        line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
        lines.append(line)
    html_text = "\n".join(lines)

    max_len = 3500
    parts = []
    current = ""
    for block in html_text.split("\n\n"):
        test = (current + "\n\n" + block).strip() if current else block.strip()
        if len(test) > max_len:
            if current:
                split_at = min(max_len, current.rfind(" "))
                if split_at > 50:
                    parts.append(current[:split_at])
                else:
                    parts.append(current)
                current = block.strip()
            else:
                i = int(len(block) * max_len / max(len(block), 1))
                parts.append(block[:i])
                current = block[i:]
        else:
            if current:
                current += "\n\n" + block
            else:
                current = block
    if current.strip():
        parts.append(current.strip())

    print(f"\nSending {len(parts)} Telegram message(s) to {CHAT_ID}...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for i, part in enumerate(parts):
        try:
            payload = json.dumps({
                "chat_id": CHAT_ID,
                "text": part,
                "parse_mode": mode if mode else None,
                "disable_web_page_preview": True,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print(f"  Sent chunk {i+1}/{len(parts)} (msg_id:{mid})")
        except Exception as e:
            print(f"[ERROR] Telegram chunk {i+1}: {e}")


def get_llm(system_prompt, user_prompt, timeout=360):
    """Sequential Ollama call with 3x retry."""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt[:7000]},
        ],
        "stream": False,
        "options": {"temperature": 0.25, "num_predict": 4096}
    }).encode("utf-8")

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{OMLX_URL}/v1/chat/completions", data=payload,
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = json.loads(resp.read())
            text = result.get("message", {}).get("content", "").strip()
            if len(text) > 100:
                return text
        except Exception as e:
            print(f"    Retry {attempt + 1}/3: {e}")
            time.sleep(8)
    return "[LLM Error - no meaningful response returned]"


def run_brief():
    now = datetime.now()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]
    date_str = now.strftime('%d/%m/%Y')

    print(f"[{now.strftime('%H:%M')}] Jarvis Intelligence Brief - {date_str} ({day_name})")

    # ===== Phase 1: RSS Collection =====
    RSS_SOURCES = [
        {"name": "CafeF Doanh Nghiep", "url": "https://cafef.vn/doanh-nghiep.rss", "section": "VN"},
        {"name": "VnExpress Kinh Doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "section": "VN"},
        {"name": "Vietnamnet CK", "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "section": "VN"},
        {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "section": "AI"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "section": "TECH"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "section": "INTL"},
    ]

    all_arts = []
    for src in RSS_SOURCES:
        try:
            d = feedparser.parse(src["url"])
            fetched = []
            for entry in d.entries[:5]:
                title = str(entry.get("title") or "").strip()
                summary = (str(entry.get("summary") or entry.get("description") or "")).strip()
                link = str(entry.get("link") or entry.get("id") or "")
                if link and len(title) >= 15:
                    fetched.append({
                        "title": title, "link": link, "summary": summary[:200],
                        "source": src["name"], "section": src["section"]
                    })
            all_arts.extend(fetched)
            print(f"    {src['name']}: {len(fetched)} articles")
        except Exception as e:
            print(f"   [WARN] {src['name']}: {e}")

    # Deduplicate and prioritize AI/TECH first
    seen, unique = set(), []
    all_arts.sort(key=lambda x: "AI TECHOINTL VN".find(x["section"]))
    for a in all_arts:
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique.append(a)

    ai_tech = [a for a in unique if a["section"] in ("AI", "TECH")]
    intl = [a for a in unique if a["section"] == "INTL"]
    vn = [a for a in unique if a["section"] == "VN"]
    selected = ai_tech[:12] + intl[:8] + vn[:10]

    print(f"\n  Total: {len(all_arts)} -> {len(unique)} unique -> {len(selected)} selected")

    # Format article text for LLM input
    sections_fmt = {}
    for a in selected:
        sec = a["section"]
        sections_fmt.setdefault(sec, [])
        lines = [f"    [{a['source']}] {a['title']} ({a['link']})"]
        if a.get("summary"):
            s = a["summary"][:300].encode("utf-8", "ignore").decode("utf-8")
            lines.append(f"        - {s}")
        sections_fmt[sec].append("\n".join(lines))

    articles_text = ""
    for sec in ["AI", "TECH", "INTL", "VN"]:
        if sec in sections_fmt:
            articles_text += f"\n\n{sec.upper()}:\n\n" + "\n".join(sections_fmt[sec])

    print(f"  Articles text blob: {len(articles_text)} chars")
    print("   --- FIRST 500 CHARS --- ")
    print(articles_text[:500])
    print("---------------------------------\n")

    # ===== Phase 2: Sequential LLM Analysis (4 sections) =====
    prompts = [
        ("NEWS SYNTHESIS", 
         f"""You are Jarvis intelligence analyst. Today is May 31st, 2026. 

Analyze these articles from the last 24 hours:

{articles_text[:7000]}

Provide section: **NEWS SYNTHESIS (AI Priority)** 

List up to 6 most prominent items organized by priority:
- For AI/tech: Focus on new models, tools, regulatory updates, startup funding, partnerships. 
- Then cover finance & economy, politics/international, any notable developments elsewhere.

Format each item as:
- **Brief title/summary** + one-sentence insight on why it matters [Source](url)

RULES: Bullet points only. NO tables. Be sharp and analytical - what does each news SIGNAL? 
Keep to roughly 800 words.""", 360),

        ("TREND ANALYSIS",
         f"""You are an experienced market intelligence analyst. 

Based on these articles from the last 24 hours:

{articles_text[:6500]}

Provide **TREND ANALYSIS:**
- Top 4 dominant narratives/focal points this period
- Is AI driving a super-cycle? Evidence from multiple sources
- Market sentiment assessment: Bullish / Bearish / Cautious for each sector (finance, energy, geopolitics) + why
RULES: Bullet format only. NO tables. English.""", 420),

        ("RECOMMENDATIONS",
         f"""You are Jarvis, AI strategy advisor analyzing these articles:

{articles_text[:5000]}

Provide **ACTIONABLE RECOMMENDATIONS** for work/life optimization using newly available AI tools/tech:
- 2-3 specific actions with concrete tool names, prompt examples, workflow steps
- NOT generic "learn more about X" advice - actual implementation details anyone can do immediately

RULES: Bullet format. English.""", 240),

        ("TECH LAB",
         f"""You are a technical architect who builds practical AI prototypes (not research concepts that are years away).

Analyzing these emerging trends from today's news:

{articles_text[:5000]}

Propose ONE practical project/prototype we can start building TODAY with currently available technology. Consider:
- Ollama local LLMs, LangChain/LlamaIndex for RAG pipelines
- OpenAI API, Groq, HuggingFace models
- Agentic workflows, multi-agent systems, workflow automation

Include for your proposed project:
1. Project name + 1 sentence: what problem it solves and why NOW is the time
2. Tech stack: specific tools/libraries/APIs available today  
3. Architecture: 3-5 bullet points of system design
4. Implementation milestones for Week 1 (what to build first/second/third)
5. Why this is feasible immediately vs theoretical

RULES: Bullet format. English.""", 360),
    ]

    sections_output = {}
    total_time = 0
    for section_name, prompt, timeout_sec in prompts:
        t0 = time.time()
        print(f"\n[LLM] [{section_name}] sending to Ollama ({timeout_sec}s timeout)...")
        result = get_llm(prompt, articles_text[:7000], timeout=timeout_sec)
        elapsed = time.time() - t0
        total_time += elapsed
        sections_output[section_name] = result
        print(f"  => {len(result)} chars returned ({elapsed:.1f}s)")
    
    print(f"\n\n=== Total LLM time: {total_time:.1f}s ===\n")

    # ===== Phase 3: Delivery to Telegram =====
    header = f"**JARVIS INTELLIGENCE BRIEF** May 31st, 2026 (Sunday)\n\u23f0 Morning Edition"

    full_brief = header + "\n\n"
    for section, content in [
        ("\ud83d\udd27 NEWS SYNTHESIS & AI TRENDS", sections_output.get("NEWS SYNTHESIS")),
        ("\ud83d\udcc8 TREND ANALYSIS", sections_output.get("TREND ANALYSIS")),
        ("\ud83e\udde0 ACTIONABLE RECOMMENDATIONS", sections_output.get("RECOMMENDATIONS")),
        ("\ud83d\udee0\ufe0f TECH LAB - Project Proposal", sections_output.get("TECH LAB")),
    ]:
        full_brief += f"\n{'-' * 40}\n\n{section}\n\n"
        if content and len(content) > 50:
            full_brief += content[:3000]
        else:
            full_brief += "[No data - LLM returned insufficient response]"
        full_brief += "\n\n"

    send_telegram(full_brief)
    print("\n\u2705 Jarvis Intelligence Brief delivery complete!")


if __name__ == "__main__":
    run_brief()
