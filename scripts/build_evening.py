#!/usr/bin/env python3
"""Generate the clean evening_brief.py."""
import textwrap

PY = textwrap.dedent("""\
    #!/usr/bin/env python3
    # -*- coding: utf-8 -*-
    \"\"\"Evening Brief Pipeline.
    
    Delivers 3 Telegram messages to chat -1003801745265:
      Msg1: News Synthesis + Trend Analysis
      Msg2: Evening Recommendations  
      Msg3: Entertainment / Culture wrap-up (if enough ENT articles)
    RSS -> dedupe -> 3 sequential Ollama calls -> Telegram.
    \"\"\"

    import json, os, re, sys, time, urllib.request
    from datetime import datetime

    CHAT_ID = "-1003801745265"
    OMLX_HOST = "http://localhost:11434"
    MODEL_NAME   = "Qwen3.6-35B-A3B-MLX-8bit"

    def get_token():
        for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
            v = os.environ.get(key, "").strip()
            if v: return v
        try:
            p = os.path.expanduser("~/.hermes/.jarvis_token_cache")
            c = open(p).read().strip()
            if c: return c
        except Exception:
            pass
        return ""

    BOT_TOKEN = get_token()
    TG_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"

    RSS_SOURCES = [
         ("CafeF",              "https://cafef.vn/doanh-nghiep.rss",            "VN"),
         ("VnExpress KD",       "https://vnexpress.net/rss/kinh-doanh.rss",     "VN"),
         ("Vietnamnet CK",      "https://vietnamnet.vn/vi/rss/chung-khoan.rss", "VN"),
         ("Verge AI",           "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "AI"),
         ("TechCrunch",         "https://techcrunch.com/feed/",                 "TECH"),
         ("Ars Technica AI",    "https://feeds.arstechnica.com/arstechnica/technology-labs",   "AI"),
         ("Bloomberg Markets",  "https://feeds.bloomberg.com/markets/news.rss",          "INTL"),
         ("Reuters Business",   "https://feeds.reuters.com/reuters/businessNews",        "INTL"),
         ("BBC News Bus",       "http://feeds.bbci.co.uk/business/rss.xml",             "INTL"),
         ("Variety",            "https://variety.com/feed/",                            "ENT"),
         ("Hollywood Rpt",      "https://www.hollywoodreporter.com/feed/",              "ENT"),
         ("BBC Arts",           "http://feeds.bbci.co.uk/arts/rss.xml",                 "ENT"),
         ("Deadline HOL",       "https://deadline.com/feed/",                           "ENT"),
         ("BBC Sport",          "http://feeds.bbci.co.uk/sport/rss.xml",                "ENT"),
         ("ESPN News",          "https://www.espn.com/espn/rss/news",                   "ENT"),
         ("Rolling Stone",      "https://www.rollingstone.com/feed",                    "ENT"),
         ("CNN Top Stories",    "http://rss.cnn.com/rss/cnn_topstories.rss",            "ENT"),
         ("VnExpress GT",       "https://vnexpress.net/rss/giai-tri.rss",               "ENT"),
         ("Tuoi Tre NT",        "https://tuoitre.vn/ngon-ngu-net.livews/rss/tintucfeed.xml","ENT"),
    ]

    def _md2html(text):
        lines = []
        for raw in text.split("\\n"):
            ln = raw.strip()
            if not ln:
                lines.append("")
                continue
            ln = re.sub(r'\\[([^\\]]+)\\]\\(([^)]+)\\)', r'<a href="\\2">\\1</a>', ln)
            ln = re.sub(r'\\*\\*(.+?)\\*\\*', r'<b>\\1</b>', ln)
            if "`" not in ln:
                ln = re.sub(r'\\*(.+?)\\*', r'<i>\\1</i>', ln)
            lines.append(ln)
        return "\\n".join(lines)

    def _chunks(text, limit=3896):
        parts = []
        cur = ""
        for block in text.split("\\n\\n"):
            c = (cur + "\\n\\n" + block).strip() if cur else block.strip()
            if len(c) > limit and cur:
                parts.append(cur.strip())
                cur = block
            else:
                cur = c
        if cur:
            parts.append(cur.strip())
        return [p[:4050] for p in parts]

    def send_tg(text, fmt="HTML"):
        if not BOT_TOKEN:
            print("[WARN] No bot token")
            return False
        html = _md2html(text)

        def do_send(json_data):
            try:
                req = urllib.request.Request(
                    TG_URL, data=json_data,
                    headers={"Content-Type": "application/json"})
                resp = urllib.request.urlopen(req, timeout=15)
                res = json.loads(resp.read())
                mid = res.get("result", {}).get("message_id", "?")
                return mid
            except Exception as e:
                print("  TG err:", e, file=sys.stderr)
                return None

        if len(html) <= 3896:
            payload = json.dumps({
                 "chat_id": CHAT_ID,
                 "text": html,
                 "parse_mode": fmt
             }).encode()
            mid = do_send(payload)
            if mid is not None:
                print("  TG sent (msgid:", str(mid) + ")")
            return mid is not None
        else:
            parts = _chunks(html)
            for i, ch in enumerate(parts):
                payload = json.dumps({
                     "chat_id": CHAT_ID,
                     "text": ch,
                     "parse_mode": fmt,
                     "disable_web_page_preview": True,
                 }).encode()
                mid = do_send(payload)
                print("  TG chunk %d/%d" % (i+1, len(parts)))
            return True

    def rss_fetch(url):
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
                s = ((entry.get('summary') or entry.get('description') or "")).strip()
                l = (entry.get("link") or "").strip()
                if not l or len(t) < 15:
                    continue
                out.append((t, s[:200] if s else "", l, sec))
            return out
        except Exception as e:
            print("   [WARN:", str(e), "]")
            return []

    def collect_all():
        raw = []
        for n, u, s in RSS_SOURCES:
            fc = rss_fetch(u)
            raw.extend(fc)
            if fc:
                print("   +" + n + ":", len(fc))
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

    def build_text(arts, ent=False):
        secs = {}
        for title, summary, link, sec in arts:
            secs.setdefault(sec, []).append((title, summary, link))
        res = ""
        seqs = ["VN", "INTL", "AI", "TECH"]
        if ent:
            seqs.append("ENT")
            res += "\\n\\n\\U0001f3ac ENT:\n\\n"
        for sec in seqs:
            if sec in secs:
                lbl = {"VN": "\\U0001f1fb\\U0001f1f3 TIN TRONG NUOC",
                       "INTL": "\\U0001f30d TIN QUOC TE",
                       "AI": "\\U0001f927 AI & TECH",
                       "TECH": "\\U0001f4bb CONG NGH\\u1ec6"}.get(sec, sec)
                res += "\\n\\n" + lbl + "\\n\\n"
                for title, summary, link in secs[sec]:
                    res += "- **[" + title + "]** (" + link + ")\\n"
                    if summary:
                        res += "    - " + summary[:180] + "\\n"
        return res.strip()

    def ollama(prompt, text, timeout=90):
        payload = {
             "model": MODEL_NAME,
             "messages": [
                 {"role": "system", "content": prompt},
                 {"role": "user",      "content": text[:8000]},
             ],
             "stream": False,
             "options": {"temperature": 0.3, "num_predict": 4096}
         }
        data = json.dumps(payload).encode()
        try:
            req = urllib.request.Request(
                OMLX_HOST + "/v1/chat/completions", data=data,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            r    = json.loads(resp.read())
            msg  = r.get("message", {})
            tk   = (msg.get("thinking") or "").strip()
            ct   = (msg.get("content") or "").strip()
            full = ""
            if tk:
                mi = tk.find("###")
                if mi > 0 and mi < len(tk) // 2:
                    full = tk[mi:].strip()
                else:
                    full = tk.lstrip("\\n\\n").strip()
            elif ct:
                full = ct.strip()
            return (full if len(full) > 50 or not full else "[No useful result]")
        except Exception as e:
            print("[OMLX err] " + str(e))
            et = str(e)
            if "8000" in et:
                return "OMLX down"
            return "[Error]"

    def llm_seq(prompt, text, timeout=90):
        result = ""
        for attempt in range(3):
            try:
                result = ollama(prompt, text, min(timeout, 80))
                if (result and len(result) > 50
                    and "Error" not in result[:20]
                    and "Ollama down" not in result):
                    break
            except Exception as e:
                print("   retry", attempt+1)
                time.sleep(3)
        return result

    def get_prompt_list(date_str):
        today = "Today is " + date_str
        p1 = ("You are an elite news analyst. " + today
              + "\\nAnalyze these articles from the last 24 hours:\\n\\n### KEY HEADLINES\\n"
              + "List up to 8 headlines that matter most across ALL categories (VN economy, international, AI/tech).\\n"
              + "- Format: - Headline -- one-sentence summary with source link\\n"
              + "- Prioritize: market-moving > policy/regulation > tech launches > geopolitics.\\n\\n"
              + "RULES: English only. Bullets only (-). No tables. No intro/outro.")
        p2 = ("You are a senior market strategist. " + today
              + "\\nFrom the articles above:\\n\\n### TRENDS\\n"
              + "1-3 dominant narratives with evidence from specific sources.\\n"
              + "For each: What is it? Evidence (name sources). Status: developing / peaking / fading?\\n\\n"
              + "### MARKET SENTIMENT\\nLabel: Bullish/Bearish/Cautious + 2-sentence rationale.\\n\\n"
              + "### RECOMMENDATIONS\\nActionable items for tomorrow: pre-market catalysts, positioning tips, productivity suggestion.\\n\\nRULES: Bullets only. No filler.")
        return [("p1-news", p1), ("p2-trends-recs", p2)]

    def run():
        now      = datetime.now()
        days     = ["Monday", "Tuesday", "Wednesday",
                     "Thursday", "Friday", "Saturday", "Sunday"]
        day_str  = days[now.weekday()]
        month    = str(now.month).zfill(2)
        day_num  = str(now.day).zfill(2)
        year     = str(now.year)
        date_str = month + "/" + day_num + "/" + year

        print("[%s] === Evening Brief --- %s - %s/%s/%s ===" % (
            now.strftime("%H:%M"), day_str, month, day_num, year))
        t0 = time.time()

        # Phase 1: RSS
        print("\\nPhase 1: Fetching RSS...")
        articles = collect_all()
        ent_arts = [a for a in articles if len(a) > 3 and a[3] == "ENT"]

        if not ent_arts:
            print("  No ENT; re-fetching all...")
            raw2 = []
            for n, u, s in RSS_SOURCES:
                fc = rss_fetch(u)
                raw2.extend(fc)
                if fc:
                    print("   +" + n + ":", len(fc))
            articles = raw2[:30]
            ent_arts = [x for x in articles if x[3] == "ENT"]

        text_main = build_text(articles, ent=False)
        print("   %d total, %d ENT" % (len(articles), len(ent_arts)))

        # Phase 2: LLM chains (sequential)
        prompts = get_prompt_list(date_str)
        results = {}
        for pname, ptext in prompts:
            label = "NewsSynth" if pname == "p1" else "TrendsRecs"
            print("\\nChain:", label, "...")
            r       = llm_seq(ptext, text_main, timeout=90)
            results[pname] = r
            print("   len=%d chars" % len(r))

        # Check Ollama alive
        try:
            c  = urllib.request.urlopen(OMLX_HOST + "/v1/models", timeout=5)
            d  = json.loads(c.read())
            ms = [m.get("name", "?") for m in d.get("models", [])]
            print("  Ollama OK:", ", ".join(ms))
        except Exception:
            print("  Ollama DOWN!")

        # Phase 3a: Message 1 - Headlines + Trends
        hdr1 = "\\U0001f4c5\\U0001f30d JARVIS EVENING BRIEF\\n"
        hdr1 += "=" * 50 + "\\n"
        hdr1 += "Today " + date_str + " (" + day_str + ")\\n\\n"
        hdr1 += "**\\U0001f30d KEY HEADLINES**\\n\\n"
        r1     = results.get("p1", "[No data]")[:3000]
        r2     = results.get("p2", "[No data]")[:3000]
        hdr1   += "**\\U0001f4b8 TRENDS & SENTIMENT**\\n\\n"

        msg1    = hdr1 + r1 + "\\n\\n---\\n\\n" + r2

        print("\\nPhase 3a: Msg1 [Headlines+Trends]...")
        send_tg(msg1)
        time.sleep(2.0)

        # Phase 3b: Message 2 - Recommendations + Entertainment
        hdr2 = "\\U0001f4b8 JARVIS EVENING BRIEF -- Part II\\n"
        hdr2 += "=" * 50 + "\\n"
        hdr2 += "Tonight's recommendations:\\n\\n"

        msg2    = hdr2 + "**Recommendations**\\n" + r2[:1500]

        if ent_arts:
            ehdr   = "\\n\\n---\\n\\nNight **Entertainment/Culture Wrap**\\n\\n"
            for i in range(min(5, len(ent_arts))):
                art    = ent_arts[i]
                ehdr  += "- **" + art[0] + "**\\n"
                if art[1]:
                    ehdr  += "    - " + art[1][:200] + "\\n"
            msg2    += ehdr
        else:
            msg2    += "\\nNo entertainment news today."

        print("Phase 3b: Msg2 [Recommendations+Ent]")
        send_tg(msg2)
        time.sleep(1.5)

        # Phase 3c: Entertainment standalone (if >=8 ENT articles)
        if len(ent_arts) >= 8:
            hdr3    = "\\U0001f4b8 NIGHT ENT / CULTURE WRAP\\n"
            hdr3   += "=" * 50 + "\\n"
            hdr3   += date_str + " (" + day_str + ")\\n\\n"
            hdr3   += "Top entertainment tonight:\\n"
            for i in range(min(8, len(ent_arts))):
                art    = ent_arts[i]
                hdr3  += "\\n- **" + art[0] + "**\\n"
                if art[1]:
                    hdr3  += "    - " + art[1][:250]
            print("Phase 3c: Msg3 [Ent standalone]...")
            send_tg(hdr3)

        dur = round(time.time() - t0, 1)
        print("\\n=== Done in %s seconds ===" % str(dur))

    if __name__ == "__main__":
        run()
""")

path = "/Users/nghialam/jarvis-hub/scripts/evening_brief.py"
with open(path, "w", encoding="utf-8") as f:
    f.write(PY)
print("Written %d bytes to %s" % (len(PY), path))
