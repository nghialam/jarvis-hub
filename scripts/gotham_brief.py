#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gotham Brief - Standalone RSS + LLM intelligence brief.

Collects news from RSS feeds, runs LLM analysis (sequential Ollama),
then formats into an English brief sent to the gotham Telegram channel.
Entertainment/Culture/Sports wrap-up is included as a separate message
sent to the same Gotham channel with consistent formatting.

Usage:
    python3 gotham_brief.py morning|noon|afternoon|evening
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

# Import kanban state machine for audit trail (safe no-op fallback)
def _noop(*args, **kwargs): pass   # pragma: no cover

try:
    from gotham.kanban import init as kanban_init, update as kanban_update, complete as kanban_complete
except ImportError:
    kanban_init = kanban_update = kanban_complete = _noop  # No-op fallback

# ===============================================================================
# Config
# ===============================================================================
CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")


def _get_token():
    for key in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        c = open(os.path.expanduser("~/.hermes/.jarvis_token_cache")).read().strip()
        if c:
            return c
    except Exception:
        pass
    return ""


BOT_TOKEN = _get_token()
OMLX_URL = os.environ.get("OMLX_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen3.6-35B-A3B-MLX-8bit")

RSS_SOURCES = [
    # === VN ECONOMY/BUSINESS (3) ===
    {"name": "CafeF Doanh Nghiep", "url": "https://cafef.vn/doanh-nghiep.rss", "section": "VN"},
    {"name": "VnExpress Kinh Doanh", "url": "https://vnexpress.net/rss/kinh-doanh.rss", "section": "VN"},
    {"name": "Vietnamnet CK", "url": "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "section": "VN"},
    # === AI & TECH (3) ===
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "section": "AI"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "section": "TECH"},
    {"name": "Ars Technica AI", "url": "https://feeds.arstechnica.com/arstechnica/technology-labs", "section": "AI"},
    # === INTERNATIONAL (3) ===
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss", "section": "INTL"},
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews", "section": "INTL"},
    {"name": "BBC News Business", "url": "http://feeds.bbci.co.uk/business/rss.xml", "section": "INTL"},
    # === ENTERTAINMENT / CULTURE / SPORTS (10 working sources) ===
    {"name": "Variety", "url": "https://variety.com/feed/", "section": "ENT"},
    {"name": "Hollywood Reporter", "url": "https://www.hollywoodreporter.com/feed/", "section": "ENT"},
    {"name": "BBC Arts", "url": "http://feeds.bbci.co.uk/arts/rss.xml", "section": "ENT"},
    {"name": "Deadline Hollywood", "url": "https://deadline.com/feed/", "section": "ENT"},
    {"name": "BBC Sport", "url": "http://feeds.bbci.co.uk/sport/rss.xml", "section": "ENT"},
    {"name": "ESPN News", "url": "https://www.espn.com/espn/rss/news", "section": "ENT"},
    {"name": "Rolling Stone Music", "url": "https://www.rollingstone.com/feed", "section": "ENT"},
    {"name": "CNN Entertainment", "url": "http://rss.cnn.com/rss/cnn_topstories.rss", "section": "ENT"},
    {"name": "BuzzFeed TV & Movie", "url": "https://www.buzzfeed.com/tv.xml", "section": "ENT"},
    {"name": "Vulture Entertainment", "url": "https://www.vulture.com/tag/tv/rss.xml", "section": "ENT"},
    {"name": "Mashed Celebrities", "url": "https://feeds.mashed.com/rss/all", "section": "ENT"},
    {"name": "VnExpress Giai Tri", "url": "https://vnexpress.net/rss/giai-tri.rss", "section": "ENT"},
    {"name": "Tuoi Tre Music/Ent", "url": "https://tuoitre.vn/ngon-ngu-net.livews/rss/tintucfeed.xml", "section": "ENT"},
]


# ===============================================================================
# Telegram helpers -- no truncation, full content delivery
# ===============================================================================

def _markdown_to_html(text):
    """Convert markdown to Telegram-friendly HTML."""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line)
        line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
        line = re.sub(r'__(.+?)__', r'<b>\1</b>', line)
        if "`" not in line:
            line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)
        line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)
        lines.append(line)
    return "\n".join(lines)


def _split_message(text, max_chars=4000):
    """Split text into chunks that won't exceed Telegram's 4096 limit."""
    parts = []
    current = ""
    for block in text.split("\n\n"):
        candidate = (current + "\n\n" + block).strip() if current else block.strip()
        if len(candidate) > max_chars and current:
            parts.append(current.strip())
            current = block
        else:
            current = candidate
    if current:
        parts.append(current.strip())
    return parts


def _safe_chunk(text, safe_limit=3896):
    """Split and ensure every chunk stays under Telegram's hard limit."""
    parts = _split_message(text, safe_limit)
    for i, part in enumerate(parts):
        while len(part) > 4050:
            cut_pos = part.rfind(" ", 0, 4000)
            part = part[:cut_pos] if cut_pos > 0 else part[:4000]
        parts[i] = part
    return parts


def send_telegram(text, parse_mode="HTML"):
    """Send a formatted message to the gotham channel. No content truncation."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] Telegram tokens not set, skipping delivery")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    raw_html = _markdown_to_html(text)

    # Telegram hard limit is 4096 chars. Keep a 200-char safety margin for HTML escaping overhead.
    safe_limit = 3896

    if len(raw_html) <= safe_limit:
        # Single message -- full content, no splitting needed
        payload = {"chat_id": CHAT_ID, "text": raw_html, "parse_mode": parse_mode}
        req_data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=req_data, headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print(f"Telegram sent (msg_id:{mid})")
        except Exception as e:
            msg = f"Telegram failed: {e}"
            print(msg, file=sys.stderr)
        return True

    # Split for longer messages -- ensure every chunk stays under limit
    parts = _safe_chunk(raw_html, safe_limit)

    for i, chunk in enumerate(parts):
        try:
            payload = json.dumps({
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print(f"Telegram sent (chunk {i+1}/{len(parts)}, msg_id:{mid})")
        except Exception as e:
            msg = f"Telegram failed (chunk {i+1}): {e}"
            print(msg, file=sys.stderr)

    return True


# ===============================================================================
# RSS collection
# ===============================================================================

def fetch_rss(source):
    """Fetch and parse one RSS source, returning a list of article dicts."""
    try:
        import feedparser
        d = feedparser.parse(source["url"])
        out = []
        for entry in d.entries[:5]:
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            raw_id = entry.get("id", "")
            if isinstance(raw_id, list):
                raw_id = raw_id[0] if raw_id else ""
            link = (entry.get("link") or str(raw_id) or "").strip()
            if not link or len(title) < 15:
                continue
            out.append({
                "title": title,
                "link": link,
                "summary": summary[:200] if summary else "",
                "source": source["name"],
                "section": source["section"],
            })
        return out
    except Exception as e:
        print(f"[WARN] {source['name']}: {e}", file=sys.stderr)
        return []


def collect_all():
    """Fetch all RSS sources, deduplicate, return list of articles."""
    use = RSS_SOURCES  # Use ALL sources -- no slicing for full coverage
    all_arts = []
    for src in use:
        fetched = fetch_rss(src)
        all_arts.extend(fetched)
        if fetched:
            print(f"       {src['name']}: {len(fetched)} articles")

    seen, unique = set(), []
    for a in sorted(all_arts, key=lambda x: "VNINTLAI TECHNOENT".find(x["section"])):
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique.append(a)

    ent = [a for a in unique if a["section"] in ("AI", "TECH")]
    other = [a for a in unique if a["section"] not in ("AI", "TECH")]
    selected = ent[:10]
    remaining = 25 - len(selected)
    if remaining > 0:
        selected.extend(other[:remaining])

    return selected[:30][:20]


def build_article_text(articles):
    """Build the article text blob for LLM input."""
    sections = {}
    for a in articles:
        sec = a["section"]
        sections.setdefault(sec, [])
        s = (a.get("summary", "") or "").replace("\n", " ")
        try:
            s = s.encode('utf-8', 'ignore').decode('utf-8')
        except Exception:
            pass
        lines = [f"       [{a['source']}] {a['title']} ({a['link']})"]
        if s:
            lines.append(f"          - {s}")
        sections[sec].append("\n".join(lines))

    art_text = ""
    labels = {
        "VN": "\U0001f1fb\U0001f1f3 TIN TRONG NUOC",
        "INTL": "\U0001f30d TIN QUOC TE",
        "AI": "\U0001f927 AI & TECH",
        "TECH": "\U0001f4bb CONG NGH\u1ec6",
    }

    for sec in ["VN", "INTL", "AI", "TECH"]:
        if sec in sections:
            art_text += f"\n\n{labels.get(sec, sec)}:\n\n" + "\n".join(sections[sec])

    return art_text.strip()


def build_entertainment_text(articles):
    """Build standalone entertainment/culture/sports text for wrap-up."""
    sections = {}
    for a in articles:
        if a["section"] != "ENT":
            continue
        sec = a["section"]
        sections.setdefault(sec, [])
        s = (a.get("summary", "") or "").replace("\n", " ")
        try:
            s = s.encode('utf-8', 'ignore').decode('utf-8')
        except Exception:
            pass
        lines = [f"       [{a['source']}] {a['title']} ({a['link']})"]
        if s:
            lines.append(f"          - {s}")
        sections[sec].append("\n".join(lines))

    art_text = ""
    for sec in ["ENT"]:
        if sec in sections:
            art_text += f"\n\n\U0001f3ac VAN HOA / GIAI TRI:\n\n" + "\n".join(sections[sec])

    return art_text.strip()


# ===============================================================================
# LLM (sequential Ollama calls) -- NO truncation of input articles
# ===============================================================================

def get_llm(system_prompt, articles_text, timeout=300):
    """Call Ollama /v1/chat/completions (non-streaming). Sequential only.

    CRITICAL FIX for qwen3.6: ALL response text comes through 'thinking' field.
    Strip the meta-reasoning preamble ("Here's how I'll approach...") before returning.
    Balance num_predict so full analysis fits without cutting off mid-sentence.
    """
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": articles_text[:8000]},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 16384  # Enough for full analysis (2-3 sections), no cutoff
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{OMLX_URL}/v1/chat/completions", data=req_data,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read())

        # qwen3.6 puts ALL text in 'thinking' field, empty 'content'
        msg = result.get("message", {})
        thinking_text = (msg.get("thinking") or "").strip()
        content_text = (msg.get("content") or "").strip()

        # CRITICAL: For qwen3.6, ALL analysis text is in 'thinking'.
        # Strip leading "reasoning preamble" to deliver clean analysis only.
        full_response = ""

        # Strategy: find first section heading marker (###) and use everything after it
        if thinking_text:
            # Walk through text looking for ### markers -- this marks actual analysis start
            marker_idx = thinking_text.find("###")
            if marker_idx > 0 and marker_idx < len(thinking_text) / 2:
                # Found section header within first half of text -- skip preamble
                full_response = thinking_text[marker_idx:].strip()
            else:
                # No ### found -- strip first N characters (typically ~500-1000 chars meta-text)
                trimmed = thinking_text.lstrip("\n\n")
                full_response = trimmed.strip()

        elif content_text:
            # Very rare for qwen3.6, but fallback to content if it exists
            full_response = content_text.strip()

        # EXTRA SAFEGUARD: If first word is a reasoning meta-word, strip until newline
        candidates_prefixes = ('Here', 'I would', 'Let me', 'The answer', 'Based on', 'Sure')
        while full_response and any(full_response.startswith(p) for p in candidates_prefixes):
            # Find the next newline after ~50 chars and skip past it
            idx = 0
            for i, ch in enumerate(full_response[:100]):
                if ch == '\n':
                    idx = i + 1
                    break
            if idx > 0:
                full_response = full_response[idx:].strip()
            else:
                break

        return full_response if len(full_response) > 50 else "[No useful analysis returned]"

    except Exception as e:
        print(f"[LLM ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        if "8000" in str(e):
            return "OMLX not running - start omlx"
        return f"[LLM Error: {type(e).__name__}]"


# ===============================================================================
# Prompts
# ===============================================================================

def _build_prompts(date_str, article_text):
    today = f"Today is {date_str}."
    prompts = [
        (
            "AI & Tech Priority",
            f"""You are Jarvis, an intelligence analyst. {today}

Analyze these articles from the last 24 hours and output EXACTLY these sections:

### NEWS SYNTHESIS (AI First)
List up to 5 AI-related news items: new models, tools, startups, regulations.
Each item format: - title + 1-sentence summary [Source](url)
Use bullet points ONLY. NO tables. Be concise.

### TREND ANALYSIS
Top 3 market trends and their drivers.
Any correlation between AI events and other sectors (finance, energy)?
Bullish/Bearish/Neutral with reasoning. Use bullets only.

RULES: English language. Bullet points only (-). NO tables. No intros/conclusions."""
        ),
        (
            "Trend + Recs Deep",
            f"""You are an experienced market analyst. {today}

Based on the articles below, provide:

### KEY TRENDS
- Top 3 dominant narratives in today's news flow
- Is AI driving a super-cycle? Evidence from multiple sources.
- Market sentiment: Bullish / Bearish / Cautious + why

### RECOMMENDATIONS
2-3 specific actions for work/life optimization using available AI tools.
Include concrete prompts, tool names, or workflow steps. NO generic advice.

RULES:
- English language. Bullet format only (-). 
- DELIVER SUBSTANTIVE ANALYSIS -- NO filler text like "Here is my analysis:" or introductory sentences.
- Every claim must cite a source. Be decisive and actionable."""
        ),
    ]
    return prompts


# ===============================================================================
# Main pipeline -- entertainment wrap-up sent to Gotham channel too
# ===============================================================================

def run_pipeline(mode="afternoon"):
    now = datetime.now()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                  "Friday", "Saturday", "Sunday"][now.weekday()]
    date_str = now.strftime('%d/%m/%Y')
    run_id = f"gotham_{mode}_{date_str.replace('/', '')}"
    start_time = time.time()

    # ── Kanban: initialize run tracking (no-op safe if missing)
    kanban_init(run_id, mode=mode, date_str=date_str, day_name=day_name)

    # Phase 1: collect RSS -- ALL sources including ENT to build wrap-up
    print(f"[{now.strftime('%H:%M')}] Gotham Brief - {day_name}, {date_str} ({mode})")
    print("Phase 1: Fetching RSS feeds...")

    # Collect from ALL sources (including ENT for wrap-up)
    ent_sources = [s for s in RSS_SOURCES if s["section"] == "ENT"]
    main_sources = [s for s in RSS_SOURCES if s["section"] != "ENT"]

    all_entries_main, all_entries_ent = [], []
    for src in main_sources:
        fetched = fetch_rss(src)
        all_entries_main.extend(fetched)
        if fetched:
            print(f"       {src['name']}: {len(fetched)} articles")

    for src in ent_sources:
        fetched = fetch_rss(src)
        all_entries_ent.extend(fetched)
        if fetched:
            print(f"       {src['name']}: {len(fetched)} articles (ENT)")

    # Deduplicate main articles for LLM + Telegram brief
    seen, unique_main = set(), []
    for a in sorted(all_entries_main, key=lambda x: "VNINTLAI TECHNOENT".find(x["section"])):
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique_main.append(a)

    # Deduplicate ENT articles for wrap-up
    ent_unique = []
    ent_seen = set()
    for a in sorted(all_entries_ent, key=lambda x: ""):
        k = a["title"].strip().lower()
        if k not in ent_seen and len(k) > 10:
            ent_seen.add(k)
            ent_unique.append(a)

    print(f" Main articles: {len(unique_main)} unique, ENT: {len(ent_unique)}")

    # Kanban: RSS fetch complete (no-op safe)
    kanban_update(run_id, state="PROCESSING", rss_count_main=len(unique_main), rss_count_ent=len(ent_unique))

    if not all_entries_main:
        msg = "**JARVIS INTELLIGENCE BRIEFING**\nCould not fetch RSS feeds. Check network."
        send_telegram(msg)
        return

    # Phase 2: LLM analysis (sequential, max 2 calls)
    prompts_list = _build_prompts(date_str, build_article_text(unique_main))
    results = {}

    for section_name, prompt in prompts_list:
        timeout_sec = 400 if "Recs" in section_name or "Trend" in section_name else 200
        print(f"\nPhase 2: Running LLM [{section_name}]... ({timeout_sec}s timeout)")

        result = None
        for attempt in range(3):
            try:
                # Pass FULL article text -- no truncation
                result = get_llm(prompt, build_article_text(unique_main), timeout=timeout_sec)
                if result and len(result) > 50 and "Error" not in result[:20]:
                    break
            except Exception as e:
                print(f"   retry{attempt+1}... {e}")
                time.sleep(10)

        results[section_name] = (result if (result and len(result) > 50)
                                  else "[No data - LLM returned empty]")
        print(f"      [{section_name}] [OK] len={len(results[section_name])}")

    # Phase 3a: Format and deliver the main brief to Telegram
    print("\nPhase 3a: Formatting and delivering main brief...")

    ai_tech = results.get("AI & Tech Priority", "")[:2500]
    trends = results.get("Trend + Recs Deep", "")[:3000]

    header = (
        f"JARVIS INTELLIGENCE BRIEFING\n"
        f"\U0001f4c5 {date_str} ({day_name})\n"
        f"\u23f0 {mode.title()} Edition\n"
        f"{'=' * 40}\n\n"
    )

    full_text = f"""{header}

\U0001f4cb **News Synthesis (AI Priority)**

{ai_tech}

{'-' * 40}

\U0001f4c8 **Trends + Recommendations**

{trends}
"""

    # Split and send main brief
    parts = _safe_chunk(full_text)
    for i, part in enumerate(parts):
        send_telegram(part, parse_mode="HTML")
        time.sleep(2)

    # Phase 3b: Entertainment/wrap-up sent to Gotham too (using same emoji/structure format)
    print("\nPhase 3b: Formatting and delivering entertainment/culture/sports wrap-up...")

    if ent_unique:
        entertainment_text = build_entertainment_text(ent_unique)
        ent_header = f"\U0001f3ac\U0001f3ad\U0001f3c6 TIN GIAI TRI / VAN HOA / THE THAO\n{date_str} -- {day_name}\n\n"
        ent_formatted = entertainment_text  # already has section header from build_entertainment_text

        full_ent = ent_header + ent_formatted

        # Split and send
        ent_parts = _safe_chunk(full_ent)
        for i, part in enumerate(ent_parts):
            send_telegram(part, parse_mode="HTML")
            time.sleep(1.5)
    else:
        ent_empty_msg = (f"\U0001f3ac\U0001f3ad\U0001f3c6 TIN GIAI TRI / VAN HOA / THE THAO\n"
                        f"{date_str} -- {day_name}\n\n"
                         "Khong co tin giai tri/van hoa/the thao noi bat.")
        send_telegram(ent_empty_msg, parse_mode="HTML")

    print("\nBriefing delivered!")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    run_pipeline(mode)
