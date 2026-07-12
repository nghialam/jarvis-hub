#!/usr/bin/env python3
"""Jarvis Intelligence Brief v7 - Fixed Telegram delivery with paragraph-safe chunking."""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.6:35b-a3b-mxfp8")
TG_CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")


def _load_token():
    for k in ("JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        v = os.environ.get(k, "")
        if v:
            return v.strip()
    try:
        p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        with open(p) as f:
            t = f.read().strip()
        return t
    except Exception:
        pass
    return ""


TG_BOT_TOKEN = _load_token()
if not TG_BOT_TOKEN:
    print("FATAL: No Telegram token set (env + cache both empty)")
    sys.exit(1)
if not TG_CHAT_ID:
    print("FATAL: No Telegram Chat ID set")
    sys.exit(1)


def fetch_articles():
    """Collect articles from RSS sources, deduplicate by title."""
    import feedparser

    sources = [
        {"name": "Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "sec": "AI"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "sec": "TECH"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/markets/news.rss", "sec": "INTL"},
        {"name": "CafeF", "url": "https://cafef.vn/doanh-nghiep.rss", "sec": "VN"},
    ]

    all_arts = []
    for s in sources:
        try:
            parsed = feedparser.parse(s["url"])
            arts = []
            for entry in parsed.entries[:5]:
                t = str(entry.get("title") or "").strip()
                sm = str(entry.get("summary", "")).strip()
                lnk = str(entry.get("link") or "")
                if lnk and len(t) > 14:
                    arts.append({
                        "t": t,
                        "l": lnk,
                        "s": sm[:200],
                        "n": s["name"],
                        "sec": s["sec"]
                    })
            all_arts.extend(arts)
        except Exception:
            pass

    seen = set()
    uniq = []
    for a in sorted(all_arts, key=lambda x: "AI TECHNOINTL VN".find(x["sec"])):
        k = (a["t"] or "").strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k)
            uniq.append(a)
    ai_art = [a for a in uniq if a["sec"] in ("AI", "TECH")]
    other_art = [a for a in uniq if a["sec"] not in ("AI", "TECH")]
    return ai_art[:12] + other_art[:13]


def build_text(articles):
    """Format articles into a single text blob for LLM input."""
    fmt = {}
    for a in articles:
        sec = a["sec"]
        fmt.setdefault(sec, [])
        line = "    [" + a["n"] + "] " + a["t"] + " (" + a["l"] + ")"
        if a.get("s"):
            line += "\n        " + a["s"][:300]
        fmt[sec].append(line)

    txt = ""
    for sec in ["AI", "TECH", "INTL", "VN"]:
        if sec in fmt:
            txt += "\n\n" + sec.upper() + ":\n\n" + "\n".join(fmt[sec])
    return txt[:5000]


def call_llm(sys_prompt, user_text, timeout=420):
    """Call Ollama /v1/chat/completions with 3x retry."""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_text[:4500]}
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 3000}
    }).encode("utf-8")

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                OLLAMA_HOST + "/v1/chat/completions", data=payload,
                headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=timeout)
            result = json.loads(resp.read())
            text = result.get("message", {}).get("content", "").strip()
            if len(text) > 100:
                return text
        except Exception:
            pass
    return "[LLM Error]"


def _telegram_error_text(e):
    """Extract Telegram error details from HTTPError."""
    try:
        body = e.read().decode(errors="replace")
        try:
            err_obj = json.loads(body)
            return f"[{e.code}] {err_obj.get('description', body)}"
        except Exception:
            return f"[{e.code}] {body}"
    except Exception:
        return str(e)


def send_telegram(msg):
    """Send message to Telegram, paragraph-safe split at ~3800 chars."""
    url = "https://api.telegram.org/bot" + TG_BOT_TOKEN + "/sendMessage"

    # Strip control characters that break JSON/Telegram parser
    cleaned = ''.join(c for c in msg if ord(c) >= 32 or c in '\n\r\t')
    msg = cleaned

    # Split at paragraph boundaries (not mid-char like flat split)
    paragraphs = [p for p in msg.split('\n\n') if p.strip()]
    chunks = []
    for para in paragraphs:
        test = "\n\n".join(chunks + [para]) if chunks else para
        json_len = len(json.dumps({"chat_id": TG_CHAT_ID, "text": test}))
        if json_len <= 3800 and len(test) < 3800:
            chunks.append(para)
        elif chunks:
            combined = chunks[-1] + "\n\n" + para
            if len(json.dumps({"chat_id": TG_CHAT_ID, "text": combined})) <= 3800:
                chunks[-1] = combined
            else:
                chunks.append(para[:3500])
        else:
            chunks.append(para[:3500])

    print("\nSending " + str(len(chunks)) + " Telegram chunk(s)...")

    for i, chunk in enumerate(chunks):
        pl = json.dumps({
            "chat_id": TG_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=pl)
            resp = urllib.request.urlopen(req, timeout=15)
            r2 = json.loads(resp.read())
            mid = r2.get("result", {}).get("message_id", "?")
            print("  Sent chunk " + str(i+1) + " -> msg_id:" + str(mid))
        except urllib.error.HTTPError as e:
            err_text = _telegram_error_text(e)
            print("  ERR chunk " + str(i+1) + ": " + err_text)


def run_brief():
    now = datetime.now()
    date_str = now.strftime("%d/%m/%Y")
    day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][now.weekday()]

    print(now.strftime("%H:%M") + " Jarvis Intelligence Brief | " + date_str + " | " + day_name)

    # Phase 1: RSS
    articles = fetch_articles()
    article_text = build_text(articles)
    print("Articles fetched: " + str(len(articles)) + ", text blob: " + str(len(article_text)) + " chars")

    if len(article_text) < 500:
        print("ERROR: Too few articles collected")
        return

    # Phase 2: LLM chains (4 sequential calls)
    prompts = [
        ("NEWS",
         "You are Jarvis AI analyst. Today is " + date_str + ". " +
         "Analyze news from the last 24 hours and provide a top-5 list of the most important AI/tech news with impact analysis.",
         "Top 5 AI/tech items with title, why it matters [Source link], then brief coverage of other notable finance/economy/news."),
        ("TREND",
         "You are market intelligence analyst. Today is " + date_str + ". " +
         "Analyze these articles and provide trend analysis.",
         "Top 4 dominant narratives of the news period, AI super-cycle assessment with evidence, market sentiment per sector (Bullish/Bearish/Cautious) + reasoning."),
        ("RECS",
         "You are an AI strategy advisor. Today is " + date_str + ". " +
         "Review these articles and provide actionable recommendations.",
         "2-3 specific actions for work/life optimization using new AI tools with concrete tool names, prompt examples, workflow steps."),
        ("TECH",
         "You are a technical architect building practical prototypes. Today is " + date_str + ". " +
         "Propose ONE concrete project we can build starting today.",
         "Project name and description (why now), tech stack using available tools (Ollama, LangChain, OpenAI APIs), architecture overview 3-5 bullets, Week 1 milestones."),
    ]

    sections = {}
    for name, sys_prompt, user_extra in prompts:
        t0 = time.time()
        print("Phase 2: [" + name + "] -> Ollama...")
        result = call_llm(sys_prompt, article_text + "\n\n" + user_extra, timeout=420)
        sections[name] = result[:3000]
        elapsed = time.time() - t0
        print("     " + str(len(sections[name])) + " chars (" + str(round(elapsed)) + "s)")

    # Phase 3: Format and send to Telegram
    sep = "=" * 50
    header = "Jarvis Intelligence Brief | " + date_str + " | " + day_name + "\n" + sep

    full_brief = header + "\n"
    for k, v in sections.items():
        full_brief += "\n--- " + k + " ---\n" + v + "\n"

    print("\nPhase 3: Delivering brief to Telegram...")
    send_telegram(full_brief)
    print("\nDone! Jarvis Intelligence Brief delivered.\n")


if __name__ == "__main__":
    run_brief()
