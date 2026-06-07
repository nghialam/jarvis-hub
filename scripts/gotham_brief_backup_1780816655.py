#!/usr/bin/env python3
"""Gotham Brief v2.0 - RSS + LLM intel brief with full kanban tracking."""

import json, os, re, sys, time, traceback
import urllib.request, urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

# Kanban state machine (safe no-op fallback if module missing)
def _noop(*a, **k): pass
try:
    from gotham.kanban import (init as kanban_init,
                               update as kanban_update,
                               complete as kanban_complete)
except ImportError:
    kanban_init = kanban_update = kanban_complete = _noop

# Constants
CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3.6:35b-mlx")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _fetch_all():
    """Fetch all RSS from sources."""
    seen, uniq = set(), []
    for src in RSS_SOURCES:
        for a in fetch_rss(src):
            k = a["title"].strip().lower()
            if k not in seen and len(k) > 10:
                seen.add(k); uniq.append(a)
    return uniq[:25]


def _bot_token():
     """Fetch bot token. Falls back to env/cache."""
    key = "JARVIS_BOT_TOKEN"
    val = os.environ.get(key, "").strip()
    if val: return val
    try:
        c = open(os.path.expanduser("~/.hermes/.jarvis_token_cache"))
             .read().strip()
        if c: return c
    except Exception: pass
    return ""

BOT_TOKEN=_bot_t... # --- Telegram helpers ---

def md2h(text):
     """Convert markdown to HTML for telegram."""
    out = []
    for raw in text.split('\n'):
        l = raw.strip()
        if not l:
            out.append('')
            continue
        if "`" not in l:
            l = re.sub(r'\*(.+?)\*', r'<i>\1</i>', l)
        l = re.sub(r'`(.+?)`', r'<code>\1</code>', l)
        l = re.sub(r'__(.+?)__', r'<b>\1</b>', l)
        l = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', l)
        out.append(l)
    return '\n'.join(out)

def chunk(text, lim=4000):
     """Split text so every part is <= Telegram 4050-safe."""
    ps = []; cur = ''
    for bl in text.split('\n\n'):
        c = (cur+'\n\n'+bl).strip() if cur else bl.strip()
        if len(c) > lim and cur:
            ps.append(cur.strip()); cur = bl
        else: cur = c
    if cur: ps.append(cur.strip())
    out = []
    for p in ps:
        while len(p) > 4050:
            ct = p.rfind(' ', 0, 4000)
            p = p[:ct] if ct > 0 else p[:4000]
        out.append(p)
    return out

def send_tlgrm(text, fmt="HTML"):
     """Send to gotham channel; returns total chunks sent."""
    tok = BOT_TOKEN or _bot_t...()
    if not tok or not CHAT_ID:
        print("(skip) Telegram tokens not set"); return 0
    base = f"https://api.telegram.org/bot{tok}/sendMessage"

     # Single message path
    raw = md2h(text)
    if len(raw) <= 3896:
        pd = json.dumps({"chat_id": CHAT_ID, "text": raw,
                         "parse_mode": fmt}).encode('utf-8')
        try:
            rq = urllib.request.Request(base, data=pd,
                                        headers={"Content-Type": "application/json"})
            rp = urllib.request.urlopen(rq, timeout=15)
            mid = json.loads(rp.read()).get("result", {}).get("message_id", "?")
            print(f"Telegram single sent (msg_id:{mid})"); return 1
        except Exception as e:
            print(f"Telegram single failed: {e}", file=sys.stderr); return 0

     # Chunk path
    outs = chunk(raw)
    cnt = 0
    for idx, ch in enumerate(outs):
        try:
            pd = json.dumps({"chat_id": CHAT_ID, "text": ch,
                             "parse_mode": fmt,
                             "disable_web_page_preview": True}).encode('utf-8')
            rq = urllib.request.Request(base, data=pd,
                                        headers={"Content-Type": "application/json"})
            rp = urllib.request.urlopen(rq, timeout=15)
            mid = json.loads(rp.read()).get("result", {}).get("message_id", "?")
            print(f"Telegram ch {idx+1}/{len(outs)} sent (msg_id:{mid})")
            cnt += 1
        except Exception as e:
            print(f"Telegram ch {idx+1} failed: {e}", file=sys.stderr)
    return cnt


# --- RSS Sources ---
RSS_SOURCES = [
     {"name": "CafeF Doanh Nghiep",   "url": "https://cafef.vn/doanh-nghiep.rss",        "section": "VN"},
     {"name": "VnExpress Kinh Doanh",  "url": "https://vnexpress.net/rss/kinh-doanh.rss",  "section": "VN"},
     {"name": "The Verge AI",         "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml","section":"AI"},
     {"name": "TechCrunch",           "url": "https://techcrunch.com/feed/",               "section": "TECH"},
     {"name": "Ars Technica AI",      "url": "https://feeds.arstechnica.com/arstechnica/technology-labs","section":"AI"},
     {"name": "Bloomberg Markets",    "url": "https://feeds.bloomberg.com/markets/news.rss","section":"INTL"},
     {"name": "Reuters Business",     "url": "https://feeds.reuters.com/reuters/businessNews","section":"INTL"},
     {"name": "BBC News Business",    "url": "http://feeds.bbci.co.uk/business/rss.xml",  "section": "INTL"},
     {"name": "Variety",              "url": "https://variety.com/feed/",                  "section": "ENT"},
     {"name": "Hollywood Reporter",   "url": "https://www.hollywoodreporter.com/feed/",    "section": "ENT"},
     {"name": "BBC Arts",             "url": "http://feeds.bbci.co.uk/arts/rss.xml",       "section": "ENT"},
     {"name": "Deadline Hollywood",   "url": "https://deadline.com/feed/",                 "section": "ENT"},
     {"name": "ESPN News",            "url": "https://www.espn.com/espn/rss/news",         "section": "ENT"},
     {"name": "VnExpress Giai Tri",    "url": "https://vnexpress.net/rss/giai-tri.rss",     "section": "ENT"},
]

def fetch_rss(src):
     """Fetch one RSS; returns article dicts."""
    try:
        import feedparser
        d = feedparser.parse(src["url"])
        out = []
        for e in d.entries[:5]:
            t = (e.get("title") or "").strip()
            s = (e.get("summary") or e.get("description") or "").strip()
            rk = e.get("id", "")
            if isinstance(rk, list): rk = rk[0] if rk else ""
            lk = (e.get("link") or str(rk) or "").strip()
            if not lk or len(t) < 15: continue
            out.append({"title": t, "link": lk, "summary": s[:200],
                         "source": src["name"], "section": src["section"]})
        return out
    except Exception as e:
        print(f"[WARN] {src['name']}: {e}", file=sys.stderr); return []

def build_art_text(arts):
     """Build article text for LLM input."""
    sec = {}
    for a in arts:
        s = a["section"]; sec.setdefault(s, [])
        st = (a.get("summary", "") or "").replace('\n', ' ')
        try: st = st.encode('utf-8', 'ignore').decode('utf-8')
        except Exception: pass
        ls = [f"[{a['source']}] {a['title']} ({a.get('link','')})"]
        if st: ls.append(f"- {st}")
        sec[s].append('\n'.join(ls))
    lbl = {"VN": "\U0001f1fb\U0001f1f3 TIN TRONG NUOC",
           "INTL": "\U0001f30d TIN QUOC TE",
           "AI": "\U0001f927 AI & TECH", "TECH": "\U0001f4bb CONG NGHE"}
    txt = ""
    for k in ["VN","INTL","AI","TECH"]:
        if k in sec:
            txt += f"\n\n{lbl.get(k,k)}:\n\n" + '\n'.join(sec[k])
    return txt.strip()

def build_ent_text(arts):
     """Build entertainment/culture/sports text for wrap-up."""
    sec = {}
    for a in arts:
        if a["section"] != "ENT": continue
        sec.setdefault("ENT", [])
        st = (a.get("summary", "") or "").replace('\n', ' ')
        try: st = st.encode('utf-8', 'ignore').decode('utf-8')
        except Exception: pass
        ls = [f"[{a['source']}] {a['title']} ({a.get('link','')})"]
        if st: ls.append(f"- {st}")
        sec["ENT"].append('\n'.join(ls))
    if "ENT" in sec:
        return f"\n\n\U0001f3ad TIN GIAI TRI:\n\n" + '\n'.join(sec["ENT"])
    return ""

def get_llm(system_prompt, articles_text, timeout=300):
     """Call Ollama /api/chat; strip thinking preamble."""
    pl = {"model": LLM_MODEL, "messages": [
              {"role":"system","content":system_prompt},
              {"role":"user","content":articles_text[:8000]},
          ], "stream": False,
          "options": {"temperature": 0.3, "num_predict": 16384}}
    rq = json.dumps(pl).encode('utf-8')
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat", data=rq,
            headers={"Content-Type":"application/json"})
        rs = urllib.request.urlopen(req, timeout=timeout)
        rt = json.loads(rs.read())
        ms = rt.get("message", {})
        th = (ms.get("thinking") or "").strip()
        ct = (ms.get("content") or "").strip()
        r = ""
        if th:
            m = th.find("###")
            r = th[m:].strip() if 0 < m < len(th)//2 else th.lstrip('\n\n').strip()
        elif ct:
            r = ct.strip()
        pf = ('Here','I would','Let me','The answer','Based on','Sure')
        while (r and any(r.startswith(p) for p in pf)):
            ix = next((i+1 for i,ch in enumerate(r[:100]) if ch == '\n'), 0)
            r = r[ix:].strip() if ix > 0 else ""
            if not ix: break
        return (r if len(r) > 50 else "[No useful analysis returned]")
    except Exception as e:
        print(f"[LLM ERR] {type(e).__name__}: {e}", file=sys.stderr)
        if "11434" in str(e): return "Ollama not running - start ollama serve"
        return f"[LLM Error: {type(e).__name__}]"

def _build_prompts(ds, art_text):
     """Build LLM prompts for this briefing."""
    t = f"Today is {ds}."
    p1 = (f"""You are Jarvis, an intelligence analyst. {t}
Analyze these articles and output:
### NEWS SYNTHESIS (AI First)
Up to 5 AI news items: - title + summary [Source](url). Bullets only.
### TREND ANALYSIS
Top 3 market trends + drivers. Bullish/Bearish/Neutral with reasoning.
""")
    p2 = (f"""You are an experienced market analyst. {t}
Based on these articles provide:
### KEY TRENDS + REC
Top narratives daily, market sentiment (Bullish/Bearish/Cautious), and why.
2-3 specific actions based on outlook. Bullets only."""
     )
    return [("AI & Tech Priority", p1), ("Trend + Recs Deep", p2)]

# =====================================================================
# Full pipeline with kanban tracking at every boundary
# =====================================================================
def run_pipeline(mode="afternoon"):
     """Full briefing pipeline with state machine tracking."""
    start = time.time()
    now = datetime.now()
    dn = ["Monday","Tuesday","Wednesday","Thursday",
          "Friday","Saturday","Sunday"][now.weekday()]
    ds = now.strftime('%d/%m/%Y')

      # Kanban START
    rid = f"gotham_{mode}_{ds.replace('/','')}"
    kanban_init(rid, mode=mode, date_str=ds, day_name=dn)
    print(f"\n[{now.strftime('%H:%M')}] Gotham {dn}, {ds} ({mode})")

    try:
          # -- PHASE 1: Collect RSS --
        print('\nPhase 1: Fetching RSS feeds...')
        main_s = [s for s in RSS_SOURCES if s["section"] != 'ENT']
        ent_s  = [s for s in RSS_SOURCES if s["section"] == 'ENT']

        mm, ee = [], []
        for src in main_s + ent_s:
            fx = fetch_rss(src)
            if fx:
                tg = " (ENT)" if src["section"] == "ENT" else ""
                print(f"    {src['name']}:{len(fx)} articles{tg}")

          # Deduplicate
          sm, um = set(), []
        for a in sorted(mm, key=lambda x: "VNINTLAI TECHNOENT".find(x["section"])):
            k = a['title'].strip().lower()
            if k not in sm and len(k) > 10: sm.add(k); um.append(a)

          # Kanban after RSS
        kanban_update(rid, state='RSS_DONE', rss_count_main=len(um),
                      rss_count_ent=len(ee))
        print(f"   Main: {len(um)}, ENT: {len(ee)}")

          # -- PHASE 2: LLM analysis (sequential + retry) --
        art = build_art_text(um[:30])
        print('\nPhase 2: Running LLM prompts...')
        pl = _build_prompts(ds, art)
        res = {}
        for sn, prompt in pl:
            t_out = 400 if "Recs" in sn else 200
            print(f"\n   [{sn}] (tout:{t_out}s)...")
            result = None
            for att in range(3):
                try:
                    result = get_llm(prompt, art, timeout=t_out)
                    if result and len(result) > 50 and "[LLM Error]" not in result[:20]: break
                except Exception as e:
                    print(f"    retry {att+1}... {e}"); time.sleep(10)
            res[sn] = (result if result and len(result) > 50
                       else "[No data - LLM returned empty]")
            print(f"      [{sn}] len={len(res[sn])}")

          # Kanban after LLM phase
        lk = sum(1 for v in res.values() if "[LLM Error]" not in str(v))
        kanban_update(rid, state='LLM_DONE', llm_success_count=lk,
                      llm_results=json.dumps(res))

          # -- PHASE 3: Format & send main brief --
        print('\nPhase 3: Formatting and sending brief...')
        at = res.get("AI & Tech Priority", "")[:2500]
        tr = res.get("Trend + Recs Deep", "")[:3000]
        hdr = (f"JARVIS INTELLIGENCE BRIEFING\n\U0001f4c5 {ds} ({dn})\n"
               f"\u23f0 {mode.title()} Edition\n{'=' * 40}\n\n")
        ft = (f"{hdr}**News Synthesis (AI Priority)** \n\n{at}"
              f"\n\n{'-'*40}\n"
              f"**Trends + Recommendations**\n\n{tr}")

         # Send chunks
        ps = chunk(ft); cs = 0
        for _i, p in enumerate(ps):
            if send_tlgrm(p, fmt="HTML"): cs += 1
            time.sleep(2)

          # -- PHASE 3b: Entertainment wrap-up --
        print('\nPhase 3b: Sending entertainment/culture/wrap-up...')
        if ee:
            et = build_ent_text(ee)
            eh = f"\U0001f3ad TIN GIAI TRI / VAN HOA / THE THAO\n{ds} -- {dn}\n\n"
            fe = eh + et; ep = chunk(fe)
            for _i, p in enumerate(ep):
                send_tlgrm(p, fmt="HTML")
                if _i < len(ep)-1: time.sleep(2)
        else:
            print("   No ENT articles -- skipping wrap-up")

          # -- FINAL: mark DELIVERED + duration --
        dur = time.time() - start
        kanban_complete(rid, state='DELIVERED', telegram_sent=cs,
                       completed_at=datetime.now().isoformat(),
                       duration_sec=round(dur, 2))
        print(f"\nTotal pipeline duration: {dur:.1f}s")
        print(f"Kanban: run_id={rid} -> DELIVERED ✅")

    except KeyboardInterrupt:
        dur = time.time() - start
        kanban_complete(rid, state='FAILED', errors="Interrupted",
                       completed_at=datetime.now().isoformat(),
                       duration_sec=round(dur, 2))
        print(f"\n[ABORT] Pipeline interrupted (user)")

    except Exception as e:
        dur = time.time() - start
        em = f"{type(e).__name__}: {e}"
        kanban_complete(rid, state='FAILED', errors=em,
                       completed_at=datetime.now().isoformat(),
                       duration_sec=round(dur, 2), run_id=rid)
        print(f"\n[FATAL ERROR] {em}")
        traceback.print_exc()


# =====================================================================
# CLI entry point (mode: morning|noon|afternoon|evening)
# =====================================================================
if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    run_pipeline(mode)
