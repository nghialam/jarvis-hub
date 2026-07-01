#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evening Brief Pipeline: RSS fetch -> 3 LLM chains (sequential) -> Telegram.
Delivers 3 messages to chat -1003801745265 at ~20:00 weekdays:
  Msg 1: News Synthesis + Trend Analysis  
  Msg 2: Evening Recommendations
  Msg 3: Entertainment / Culture wrap-up (if >=8 ENT articles)
"""

import json, os, re, sys, time, urllib.request
from datetime import datetime

CHAT_ID = "-1003801745265"
OMLX_HOST = "http://localhost:11434"
MODEL_NAME  = "Qwen3.6-35B-A3B-MLX-8bit"


def get_token():
    for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        v = os.environ.get(key, "").strip()
        if v:
            return v
    try:
        p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        c = open(p).read().strip()
        if c:
            return c
    except Exception:
        pass
    return ""


BOT_TOKEN = get_token()
TG_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

RSS_SOURCES = [
    ("CafeF",         "https://cafef.vn/doanh-nghiep.rss",                      "VN"),
    ("VnExpress KD",  "https://vnexpress.net/rss/kinh-doanh.rss",               "VN"),
    ("Vietnamnet CK", "https://vietnamnet.vn/vi/rss/chung-khoan.rss",           "VN"),
    ("Verge AI",      "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "AI"),
    ("TechCrunch",    "https://techcrunch.com/feed/",                           "TECH"),
    ("Ars Technica AI","https://feeds.arstechnica.com/arstechnica/technology-labs",   "AI"),
    ("Bloomberg Mkt",  "https://feeds.bloomberg.com/markets/news.rss",          "INTL"),
    ("Reuters Bus",    "https://feeds.reuters.com/reuters/businessNews",         "INTL"),
    ("BBC News Bus",   "http://feeds.bbci.co.uk/business/rss.xml",               "INTL"),
    ("Variety",        "https://variety.com/feed/",                              "ENT"),
    ("Hollywood Rpt",  "https://www.hollywoodreporter.com/feed/",                "ENT"),
    ("BBC Arts",       "http://feeds.bbci.co.uk/arts/rss.xml",                   "ENT"),
    ("Deadline HOL",   "https://deadline.com/feed/",                             "ENT"),
    ("BBC Sport",      "http://feeds.bbci.co.uk/sport/rss.xml",                  "ENT"),
    ("ESPN News",      "https://www.espn.com/espn/rss/news",                     "ENT"),
    ("Rolling Stone",  "https://www.rollingstone.com/feed",                      "ENT"),
    ("CNN Top Stories","http://rss.cnn.com/rss/cnn_topstories.rss",              "ENT"),
    ("VnExpress GT",   "https://vnexpress.net/rss/giai-tri.rss",                 "ENT"),
    ("Tuoi Tre NT",    "https://tuoitre.vn/ngon-ngu-net.livews/rss/tintucfeed.xml","ENT"),
]


# ===== Telegram helpers ===== #

def _md2html(text):
    out = []
    for raw in text.split("\n"):
        ln = raw.strip()
        if not ln:
            out.append("")
            continue
        ln = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2">\1</a>', ln)
        ln = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', ln)
        if "`" not in ln:
            ln = re.sub(r'\*(.+?)\*', r'<i>\1</i>', ln)
        out.append(ln)
    return "\n".join(out)


def _safe_chunks(text, limit=3896):
    parts = []
    cur = ""
    for block in text.split("\n\n"):
        c = (cur + "\n\n" + block).strip() if cur else block.strip()
        if len(c) > limit and cur:
            parts.append(cur.strip())
            cur = block
        else:
            cur = c
    if cur:
        parts.append(cur.strip())
    return [p[:4050] for p in parts]


def send_tg(text, mode="HTML"):
    """Send Telegram message. Splits into chunks if >3896 chars."""
    if not BOT_TOKEN:
        print("[WARN] No bot token found")
        return False

    html = _md2html(text)

    def _deliver(json_bytes):
        try:
            req = urllib.request.Request(
                TG_URL, data=json_bytes,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=15)
            res  = json.loads(resp.read())
            mid  = res.get("result", {}).get("message_id", None)
            return mid
        except Exception as e:
            print(f"  TG err: {e}", file=sys.stderr)
            return None

    if len(html) <= 3896:
        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": html,
            "parse_mode": mode
        }).encode()
        mid = _deliver(payload)
        if mid is not None:
            print(f"  TG sent (msgid: {mid})")
        return mid is not None
    else:
        for i, ch in enumerate(_safe_chunks(html)):
            payload = json.dumps({
                "chat_id": CHAT_ID,
                "text": ch,
                "parse_mode": mode,
                "disable_web_page_preview": True,
            }).encode()
            mid = _deliver(payload)
            print(f"  TG chunk {i+1}")
        return True


# ===== RSS collection ===== #

def rss_fetch(url):
    """Fetch one RSS source. Returns list of (title, summary, link, section)."""
    try:
        import feedparser
        sec = "OTHER"
        for n, u, s in RSS_SOURCES:
            if u == url:
                sec = s
                break
        d = feedparser.parse(url)
        out = []
        for entry in d.entries[:5]:
            t = (entry.get("title") or "").strip()
            s = (entry.get("summary") or
                 entry.get("description") or "").strip()
            l = (entry.get("link") or "").strip()
            if not l or len(t) < 15:
                continue
            out.append((t, s[:200] if s else "", l, sec))
        return out
    except Exception as e:
        print(f"   [WARN feed]: {e}")
        return []


def collect_all():
    """Fetch all RSS. Returns up to 30 unique articles."""
    raw = []
    for n, u, s in RSS_SOURCES:
        fc = rss_fetch(u)
        raw.extend(fc)
        if fc:
            print(f"   +{n}: {len(fc)} articles")

    seen = set()
    uniq = []
    order = {"VN": 0, "INTL": 1, "AI": 2, "TECH": 3, "ENT": 4}
    for x in sorted(raw, key=lambda a: order.get(a[3], 9)):
        kw = x[0].strip().lower()
        if kw not in seen and len(kw) > 10:
            seen.add(kw)
            uniq.append(x)

    ai_tech = [x for x in uniq if x[3] in ("AI", "TECH")][:10]
    rest    = [x for x in uniq if x[3] not in ("AI", "TECH")][:20]
    return (ai_tech + rest)[:30]


def build_text(articles, ent=False):
    """Build multi-section text blob from articles."""
    sections = {}
    for title, summary, link, sec in articles:
        sections.setdefault(sec, []).append(
            (title, summary, link))

    result = ""
    seqs = ["VN", "INTL", "AI", "TECH"] if not ent else \
           ["VN", "INTL", "AI", "TECH", "ENT"]

    lbls = {
        "VN": "\U0001f1fb\U0001f1f3 TIN TRONG NUOC",
        "INTL": "\U0001f30d TIN QUOC TE",
        "AI": "\U0001f927 AI & TECH",
        "TECH": "\U0001f4bb CONG NGH\u1ec6",
    }

    for sec in seqs:
        if sec in sections:
            header = (f"\n\n{lbls.get(sec, sec)}\n\n"
                      if sec != "ENT" else "\n\nENT:\n\n")
            result += header
            for title, summary, link in sections[sec]:
                result += f"- **[{title}]** ({link})\n"
                if summary:
                    result += f"     - {summary[:180]}\n"

    return result.strip()


# ===== LLM helpers ===== #

def omlx_call(prompt, text_blob, timeout=90):
    """Call OMLX /v1/chat/completions non-streaming. Return cleaned analysis."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text_blob[:8000]},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 4096,
        }
    }
    data = json.dumps(payload).encode()
    try:
        api_url = f"{OMLX_HOST}/v1/chat/completions"
        req = urllib.request.Request(
            api_url, data=data,
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw  = json.loads(resp.read())

        msg   = raw.get("message", {})
        think = (msg.get("thinking") or "").strip()
        cont  = (msg.get("content") or "").strip()

        full = ""
        if think:
            mi = think.find("###")
            # If ### is in first half, skip preamble
            if mi > 0 and mi < len(think) // 2:
                full = think[mi:].strip()
            else:
                full = think.lstrip("\n\n").strip()
        elif cont:
            full = cont.strip()

        return (full if len(full) > 50 or not full
                else "[No useful result]")

    except Exception as e:
        print(f"[OMLX err] {e}")
        if "8000" in str(e):
            return "OMLX down"
        return "[Error]"


def llm_seq(prompt, text_blob, timeout=90):
    """Retry up to 3 times on failure with 3s backoff."""
    result = ""
    for attempt in range(3):
        try:
            result = omlx_call(prompt, text_blob,
                                 min(timeout, 80))
            ok = (result and len(result) > 50
                  and "Error" not in result[:20]
                  and "OMLX down" not in result
                  and "down" not in result.lower()[:10])
            if ok:
                break
        except Exception as e:
            print(f"  retry {attempt+1}")
            time.sleep(3)
    return result


# ===== Prompt builder (3 chains, evening variant) ===== #

def make_prompts(date_str):
    today = f"Today is {date_str}."

    p1 = (f"You are an elite news analyst. {today}\n" +
          "Analyze these articles from the last 24 hours.\n\n" +
          "### KEY HEADLINES\n" +
          "List up to 8 headlines across ALL categories: " +
          "VN economy, international, AI/tech.\n" +
          "- Format: - Headline -- one-sentence summary [Source](url)\n"
          "- Prioritize: market-moving > policy/regulation\n" +
          "  > tech launches > geopolitics.\n\n" +
          "RULES: English only. Bullets (-). No tables. No intro/outro.")

    p2 = (f"You are a senior market strategist. {today}\n" +
          "From the articles above:\n\n" +
          "### TRENDS\n" +
          "1-3 dominant narratives with evidence from sources.\n" +
          "For each: What? Evidence (sources). Status:\n" +
          "  developing / peaking / fading?\n\n" +
          "### MARKET SENTIMENT\n" +
          "Label: Bullish or Bearish or Cautious\n" +
          "+ 2-sentence rationale.\n\n" +
          "### RECOMMENDATIONS\n" +
          "- Pre-market catalysts for tomorrow\n" +
          "- Positioning suggestions\n" +
          "- One productivity tool tip\n\n" +
          "RULES: Bullets only. Evidence-based. No filler.")

    return [("Synthesis", p1), ("Trends+Recs", p2)]


# ===== Main pipeline ===== #

def run():
    now     = datetime.now()
    dn      = now.strftime("%A")        # Monday..Sunday
    ds      = f"{now.month:02d}/" \
              f"{now.day:02d}/{now.year}"

    e_BD  = "\U0001f4c5"              # JARVIS bullet
    e_GL  = "\U0001f30d"              # Globe  
    e_BK  = "\U0001f4b8"              # Money bag
    eql   = "=" * 50

    print(f"[{now:%H:%M}] === Evening Brief --- {dn} - {ds} ===\n")
    t0    = time.time()

    # ---- Phase 1: RSS ----
    print("Phase 1: Fetching RSS feeds...")
    articles   = collect_all()
    ent_arts   = [a for a in articles if len(a) > 3 and a[3] == "ENT"]

    if not ent_arts:
        print("  No ENT; re-fetching all...")
        raw2 = []
        for n, u, s in RSS_SOURCES:
            fc = rss_fetch(u)
            raw2.extend(fc)
            if fc:
                print(f"   +{n}: {len(fc)} articles")
        articles = raw2[:30]
        ent_arts = [x for x in articles if x[3] == "ENT"]

    text_main = build_text(articles, False)
    print(f"  {len(articles)} unique ({len(ent_arts)} ENT)\n")

    # ---- Phase 2: LLM (sequential) ----
    prompts     = make_prompts(ds)
    results     = {}

    for pname, ptxt in prompts:
        print(f"Chain: {pname}...")
        r = llm_seq(ptxt, text_main, timeout=90)
        results[pname] = r
        print(f"  len={len(r)} chars\n")

    # Ollama health check
    try:
        chk     = urllib.request.urlopen(
            f"{OMLX_HOST}/v1/models", timeout=5)
        info    = json.loads(chk.read())
        models  = [m.get("name", "?") for m
                    in info.get("models", [])]
        print(f"  Ollama OK: {', '.join(models)}\n")
    except Exception:
        print("  Ollama UNREACHABLE!")
        models = []

    # ---- Phase 3a: Message 1 - Headlines + Trends ===== #

    hdr  = f"{e_BD}{e_GL} JARVIS EVENING BRIEF\n"
    hdr  += eql + "\n"
    hdr  += f"Today {ds} ({dn})\n"
    hdr  += "\n**" + e_GL + " KEY HEADLINES**\n\n"

    r1        = results.get("Synthesis",     "[No data]")[:3000]
    r2        = results.get("Trends+Recs",   "[No data]")[:3000]

    msg1_body  = f"{r1}\n---\n{e_BK} **TRENDS & SENTIMENT**\n\n"
    msg1       = hdr + msg1_body + r2

    print("Phase 3a: Sending Message 1 [headlines+sentiment]...")
    send_tg(msg1)
    time.sleep(2.0)

    # ---- Phase 3b: Message 2 - Evening Recommendations + Ent ===== #

    hdr2     = f"{e_BK} JARVIS EVENING BRIEF -- Part II\n"
    hdr2    += eql + "\n"
    hdr2    += "Tonight's recommendations:\n\n**Recommendations**\n\n"

    msg2      = hdr2 + r2[:1500]

    if ent_arts:
        eh       = f"\n---\n\n*Entertainment/Culture Wrap*\n"
        for i in range(min(5, len(ent_arts))):
            art    = ent_arts[i]
            eh     += f"\n- **{art[0]}**\n"
            if art[1]:
                eh  += f"   - {art[1][:200]}"
        msg2    += eh
    else:
        msg2    += "\n*No entertainment news today.*"

    print("Phase 3b: Sending Message 2 [recs+ent]...")
    send_tg(msg2)
    time.sleep(1.5)

    # Phase 3c: Entertainment as standalone (if >=8 ENT articles)
    if len(ent_arts) >= 8:
        hd3      = f"{e_BD} NIGHT ENT / CULTURE WRAP\n"
        hd3     += eql + "\n"
        hd3     += f"{ds} ({dn})\nTop stories tonight:\n"
        for i in range(min(8, len(ent_arts))):
            art    = ent_arts[i]
            hd3   += f"\n- **{art[0]}**\n"
            if art[1]:
                hd3  += f"   - {art[1][:250]}"

        print("Phase 3c: Msg3 [Ent standalone]...")
        send_tg(hd3)

    dur = round(time.time() - t0, 1)
    print(f"\n=== Done in {dur}s ===")


if __name__ == "__main__":
    run()
