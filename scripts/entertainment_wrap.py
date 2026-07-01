#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENTERTAINMENT WRAP v2.11 -- Jarvis Intelligence Feed (FINAL CLEAN BUILD)

Mirror gotham_brief: Professional entertainment/culture brief with 4 sections.
Fix: Consistent 4-space indent, no Unicode surrogate crashes, single BOT_TOKEN.
Pipeline: Fetch feeds -> LLM Chain 1 (Hot Stories + Trends) -> LLM Chain 2 (Watch + Cultural) -> Telegram deliver
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "1670013239")

def get_token():
    """Fetch BOT_TOKEN from env or cache file."""
    for key in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    cp = os.path.expanduser("~/.hermes/.jarvis_token_cache")
    try:
        with open(cp) as fh:
            c = fh.read().strip()
            if c and len(c) > 50:
                return c
    except Exception:
        pass
    return ""

BOT_TOKEN = get_token()
OMLX_HOST = os.environ.get("OMLX_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("JARVIS_LLM", "Qwen3.6-35B-A3B-MLX-8bit")

ENT_FEEDS = [
    {"name": "Variety",            "url": "https://variety.com/feed/"},
    {"name": "Hollywood Reporter", "url": "http://www.hollywoodreporter.com/feed/"},
    {"name": "Deadline Hollywood", "url": "https://deadline.com/feed/"},
    {"name": "BBC Sport",          "url": "http://feeds.bbci.co.uk/sport/rss.xml"},
    {"name": "Rolling Stone",      "url": "https://www.rollingstone.com/feed"},
    {"name": "CNN Entertainment",  "url": "http://rss.cnn.com/rss/cnn_topstories.rss"},
    {"name": "The Wrap",           "url": "https://www.thewrap.com/feed/"},
]

def markdown2html(text):
    """Convert **bold** and [link]() to Telegram HTML."""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', line)
        lines.append(line)
    return "\n".join(lines)

def safe_chunk(text, limit=None):
    """Split long text into Telegram-safe chunks."""
    L = limit or 3850
    parts, current = [], ""
    for p in text.split("\n\n"):
        c = "{}\n\n{}".format(current, p).strip() if current else p.strip()
        if len(c) > L and current:
            parts.append(current.strip())
            current = p
        else:
            current = c
    if current:
        parts.append(current.strip())
    return [x for x in parts if x]

def send_telegram(text, parse_mode="HTML"):
    """Send formatted message to Telegram. Mirror gotham pattern."""
    token = BOT_TOKEN
    if not token or len(token) < 10:
        print("[WARN] Bot token not set -- skipping delivery")
        return False

    raw = markdown2html(text)
    safe_limit = 3850

    if len(raw) <= safe_limit:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": raw,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        try:
            req = Request(
                "https://api.telegram.org/bot{}/sendMessage".format(token),
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print("[OK] Telegram SENT msg_id=%s chars=%d" % (mid, len(raw)))
            return True
        except Exception as exc:
            print("[ERR] Single message failed: %s" % str(exc))
            return False

    parts = safe_chunk(raw, 3800)
    sc = 0
    for idx, chunk in enumerate(parts):
        try:
            payload = json.dumps({
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }).encode("utf-8")
            req = Request(
                "https://api.telegram.org/bot{}/sendMessage".format(token),
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urlopen(req, timeout=15)
            json.loads(resp.read())
            sc += 1
            print("[OK] Chunk %d/%d" % (idx + 1, len(parts)))
        except Exception as exc:
            print("[ERR] Chunk %d failed: %s" % (idx + 1, str(exc)))
        time.sleep(0.5)

    return sc > 0

def fetch_rss(source):
    """Fetch and parse one RSS source."""
    try:
        import feedparser
        d = feedparser.parse(source["url"])
        out = []
        for entry in d.entries[:5]:
            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            rid = entry.get("id", "")
            if isinstance(rid, list):
                rid = rid[0] if rid else ""
            link = (entry.get("link") or str(rid) or "").strip()
            if not link or len(title) < 15:
                continue
            out.append({"title": title[:300], "link": link,
                         "summary": summary[:250] if summary else "",
                         "source": source["name"], "section": "ENT"})
        return out
    except Exception as exc:
        print("[WARN Source]: %s: %s" % (source["name"], str(exc)))
        return []

def collect_all():
    """Fetch all ENT feeds and deduplicate."""
    arts = []
    for src in ENT_FEEDS:
        fetching = fetch_rss(src)
        arts.extend(fetching)
        if fetching:
            print("   %s => %d articles" % (src["name"], len(fetching)))

    seen, unique = set(), []
    for a in sorted(arts, key=lambda x: len(x["title"])):
        k = a["title"].strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            unique.append(a)
    return unique[:50]

def omlx_call(prompt, system_prompt="", max_tokens=5000):
    """Call OMLX /v1/chat/completions endpoint. qwen3.6 uses 'thinking' field."""
    payload = json.dumps({
         "model": LLM_MODEL,
         "messages": [
             {"role": "system", "content": system_prompt},
             {"role": "user", "content": prompt},
         ],
         "stream": False,
         "options": {"num_predict": max_tokens, "temperature": 0.4},
    }).encode("utf-8")

    try:
        req = Request("%s/v1/chat/completions" % OMLX_HOST, data=payload,
                       headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=60)
        result = json.loads(resp.read())
        # qwen3.6 puts all text in 'thinking', not 'content'
        msg = result.get("message", {})
        full_resp = (msg.get("thinking") or msg.get("content") or "").strip()
        # Strip thinking/reasoning for cleaner output  
        if "thinking" in msg and len(msg.get("thinking","")) > 500:
            content = msg.get("content","").strip()
            if content:
                full_resp = content
        return full_resp.strip()
    except Exception as exc:
        print("[OMLX ERROR]: %s: %s" % (type(exc).__name__, str(exc)))
        if "8000" in str(exc):
            return "OMLX not running -- start omlx"
        return ""

def build_prompts(date_str, art_text):
    """Build two sequential LLM prompts."""
    sp = ("You are Jarvis, an entertainment industry analyst. "
          "Analyze articles and produce actionable insights in Vietnamese. "
          "Use bullet points only. Include [Source](url). "
          "Be specific with names, dates, titles.")

    prompts = {
        "hot": (
            "%s\n\nToday's entertainment news:\n\n"
            "### HOT STORIES TOP 5\n"
            "Top 5 stories ranked by impact:\n"
            "- **VIETNAMESE TITLE**\n   Summary + [Source](url)\n\n"
            "Focus: box office, streaming, awards buzz, controversy.\n\n"

            "### INDUSTRY TRENDS SHAPING THE MARKET\n"
            "3 dominant narratives with evidence.\n"
            "State bullish/bearish/neutral with reasoning."
        ) % date_str,

        "watch": (
            "%s\n\n"

            "### WHAT TO WATCH THIS WEEK\n"
            "5 key releases in next 7 days:\n"
            "- **[NAME]** -- Date + preview + [Source](url)\n\n"

            "### CULTURAL NOTE OF THE WEEK\n"
            "Lighter piece: nostalgia, milestone, human-interest."
        ) % date_str,
    }

    return sp, prompts

def run():
    """Run the complete entertainment wrap pipeline."""
    now = datetime.now()
    day_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_name = day_order[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")

    time_display = now.strftime("%H:%M")
    print("\n    [@s@] Entertainment Wrap -- %s (%s, %s)\n" % (
        time_display, date_str, day_name))

     # Sanity check: verify Ollama is running before wasting time
    try:
        from urllib.request import urlopen as _ur
        resp = _ur("%s/v1/models" % OMLX_HOST, timeout=5)
        tags = json.loads(resp.read())
        models_list = [m["name"] for m in tags.get("models", [])]
        if LLM_MODEL not in models_list:
            print("[ERR] Model '%s' not loaded in Ollama" % LLM_MODEL)
            print("[WARN] Falling back gracefully.")
            send_telegram("*Ollama error* — model not available. Check ollama serve.\n")
            return
    except Exception:
        print("[ERR] Ollama not reachable at %s" % OMLX_HOST)
        print("[WARN] Falling back gracefully.")
        send_telegram("*Ollama error* — backend not running. Can't run LLM.\n")
        return

     # Phase 1: Fetch feeds
    print("Phase 1: Fetching entertainment RSS feeds...")
    articles = collect_all()
    print("   Total unique: %d\n" % len(articles))

    if not articles:
        msg = "*No entertainment news detected today.*"
        send_telegram(msg)
        print("[COMPLETE] Empty wrap sent.")
        return

    # Phase 2a: Build LLM input
    print("Phase 2a: Building LLM input...")
    art_text = ""
    seen_titles = set()
    for a in articles[:35]:
        k = a["title"].strip().lower()
        if k in seen_titles:
            continue
        seen_titles.add(k)
        art_text += "   [%s] **%s**\n" % (a.get("source", "?"), a["title"])
        if a.get("summary"):
            art_text += "    Summary: %s\n" % a["summary"][:200]

    print("   Blob: %d chars\n" % len(art_text))

    # LLM Call 1 -- Hot Stories + Trends
    print("Phase 2b: LLM Call 1 -- Hot Stories & Trends...")
    sp, prompts = build_prompts(date_str, art_text)
    llm_hot = ""
    llm_watch = ""
    for attempt in range(3):
        try:
            p = prompts["hot"] + "\n\n" + art_text
            r = omlx_call(p, system_prompt=sp, max_tokens=5000)
            if len(r) > 100 and "Error" not in r[:20]:
                llm_hot = r
                print("     [OK] Hot: %d chars" % len(llm_hot))
                break
        except Exception as exc:
            print("   Retry %d: %s" % (attempt + 1, str(exc)))
            time.sleep(3)

    if not llm_hot or len(llm_hot) < 100:
        print("    [WARN] LLM 1 failed -- using fallback")
        items = "\n".join("- #n: %s" % a["title"][:80]
                         for a in articles[:5])
        llm_hot = ("*HOT STORIES TOP 5*\n\n# total: %d articles\n%s\n"
                    % (len(articles), items))

    # LLM Call 2 -- What To Watch
    print("\nPhase 2c: LLM Call 2 -- What To Watch...")
    llm_watch = ""
    for attempt in range(3):
        try:
            p = prompts["watch"] + "\n\n" + art_text
            r = omlx_call(p, system_prompt=sp, max_tokens=32768)
            if len(r) > 50 and "Error" not in r[:20]:
                llm_watch = r
                print("     [OK] Watch: %d chars" % len(llm_watch))
                break
        except Exception as exc:
            print("   Retry %d: %s" % (attempt + 1, str(exc)))
            time.sleep(3)

    if not llm_watch or len(llm_watch) < 50:
        print("    [WARN] LLM 2 failed -- using fallback")
        items = "\n".join("- #s: %s" % a["title"][:80]
                         for a in articles[:5])
        llm_watch = ("*WHAT TO WATCH THIS WEEK*\n\n# total: %d\n%s\n"
                    % (len(articles), items))

    # Assemble final report
    print("\nPhase 3: Assembling final report...")

    header = ("**=== JARVIS ENTERTAINMENT & CULTURE WRAP ===**\n"
              "   %s (%s)\n"
              "*---%s---*\n"
             ) % (date_str, day_name, "=" * 37)

    footer = ("\n*---%s---*\n"
              "**JARVIS Intelligence Feed -- Entertainment & Culture**\n"
              "   %s %s\n"
             ) % ("-" * 40, date_str, day_name)

    main = "%s\n\n%s\n\n%s" % (llm_hot, "=" * 45, llm_watch)
    full_report = "%s\n%s\n%s" % (header, main, footer)

    n_chunks = len(full_report) // 3000 + 1
    print("   Full: %d chars | %d Telegram messages\n" % (
        len(full_report), n_chunks))

    # Phase 4: Deliver to Telegram
    print("Phase 4: Sending to Telegram...")
    chunks = safe_chunk(full_report, 3500)
    sent_count = 0
    for idx, chunk in enumerate(chunks):
        try:
            if send_telegram(chunk):
                sent_count += 1
        except Exception as exc:
            print("   Chunk %d failed" % (idx + 1))
        time.sleep(1.0)

    print("\n[COMPLETE] Sent %d/%d chunks to Telegram\n" % (
        sent_count, len(chunks)))


if __name__ == "__main__":
    run()
