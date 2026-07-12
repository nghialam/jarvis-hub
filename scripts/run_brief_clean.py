#!/usr/bin/env python3
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("LLM_MODEL", "qwen3.6:35b-a3b-mxfp8")
TG_CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")
TG_BOT_TOKEN = os.environ.get("JARVIS_BOT_TOKEN", "").strip() or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

if not TG_BOT_TOKEN:
    print("FATAL: tg_bot not set"); sys.exit(1)
if not TG_CHAT_ID:
    print("FATAL: tg_chat not set"); sys.exit(1)


def fetch_articles():
    import feedparser
    sources = [
         {"name": "Verge", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "sec": "AI"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/", "sec": "TECH"},
        {"name": "Bloomberg", " url": "https://feeds.bloomberg.com/markets/news.rss", "sec": "INTL"},
         {"name": "CafeF", "url": "https://cafef.vn/doanh-nghiep.rss", "sec": "VN"},
    ]
    all = []
    for s in sources:
        try:
            parsed = feedparser.parse(s["url"])
            arts = []
            for entry in parsed.entries[:5]:
                t = str(entry.get("title") or "").strip()
                sm = str(entry.get("summary", "")).strip()
                ln = str(entry.get("link") or "")
                if ln and len(t) > 14:
                    arts.append({"t": t, "l": ln, "s": sm[:200], "n": s["name"], "sec": s["sec"]})
            all.extend(arts)
        except Exception as ex:
            print(f"[WARN] {s['n']}: {ex}")
    
    seen = set(); uniq = []
    for a in sorted(all, key=lambda x: "AI TECHNOINTL VN".find(x["sec"])):
        k = (a["t"] or "").strip().lower()
        if k not in seen and len(k) > 10:
            seen.add(k); uniq.append(a)
    ai = [a for a in uniq if a["sec"] in ("AI","TECH")]
    others = [a for a in uniq if a["sec"] not in ("AI","TECH")]
    return ai[:12] + others[:13]


def build_text(articles):
    fmt = {}
    for a in articles:
        sec = a["sec"]; fmt.setdefault(sec, [])
        arts_fmt = f"   [{a['n']}] {a['t']} ({a['l']})"
        if a.get("s"): arts_fmt += "\n      " + a["s"][:300]
        fmt[sec].append(arts_fmt)
    
    txt = ""
    for sec in ["AI","TECH","INTL","VN"]:
        if sec in fmt:
            txt += "\n\n" + sec.upper() + ":\n\n" + "\n".join(fmt[sec])
    return txt[:5000]


def llm_call(sys_prompt, user_text, timeout=420):
    payload = json.dumps({
        "model": MODEL_NAME,
        "messages": [{"role":"system","content":sys_prompt},{"role":"user","content":user_text[:4500]}],
        "stream": False, "options": {"temperature":0.3,"num_predict":3000}
    }).encode()
    
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{OLLAMA_HOST}/v1/chat/completions", data=payload,
                headers={"Content-Type":"application/json"})
            resp = urllib.request.urlopen(req, timeout=timeout)
            r = json.loads(resp.read())
            text = r.get("message",{}).get("content","").strip()
            if len(text) > 100: return text
        except Exception as e:
            pass
    return "[LLM error]"


def send_tg(msg):
     url=f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
     max_len = 4096
     parts = [msg[i:i+max_len] for i in range(0,len(msg),max_len)]
     print(f"\nSending {len(parts)} chunks...")
     for chunk in parts:
         pl = json.dumps({"chat_id":TG_CHAT_ID,"text":chunk}).encode()
         try:
            resp=urllib.request.urlopen(urllib.request.Request(url,data=pl),15)
            r=json.loads(resp.read()); mid=r.get("result",{}).get("message_id","?")
            print(f" OK msg:{mid}")
         except Exception as e:
             print(f"ERR {e}")


def run():
    now=datetime.now()
    date_str=now.strftime("%d/%m/%Y")
    days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    day_name=days[now.weekday()]
    
    print(f"\n[{now.strftime('%H:%M')}] Jarvis Intelligence {date_str} ({day_name})")
    
    # Phase 1: RSS
    articles=fetch_articles(); article_text=build_text(articles)
    print(f"Got {len(articles)} articles, {len(article_text)} chars\n")
    
    if len(article_text)<500:
        print("ERROR: Too few"); return
    
    # Phase 2: LLM chains (sequential)
    prompts=[
        ("NEWS","You are Jarvis AI analyst.","Top 5 AI news with impact analysis:"),
        ("TREND","Market analyst.","Trend analysis of current news flow:"),
        ("RECS","AI strategy advisor.","Actionable recommendations for optimization:"),
        ("TECH","Tech architect.","Concrete project proposal using available tech:"),
    ]
    
    sections={}
    for name,sp,uc in prompts:
        t0=time.time()
        print(f"[{name}] -> LLM...")
        result=llm_call(sp,(article_text+"\n\n"+uc)[:600],timeout=420)
        elapsed=time.time()-t0
        sections[name]=result[:3000]
        print(f"  {len(sections[name])} chars ({elapsed:.1f}s)\n")
    
    # Phase 3: Send brief to Telegram
    header=f"Jarvis Intelligence Brief | {date_str} | {day_name}\n"+("="*50)
    full=header+"\n\n"
    full+="\n".join([f"{k}: {v}" for k,v in sections.items()])
    
    print("Phase 3: Sending to Telegram...")
    send_tg(full)
    print("\nDone! Jarvis brief delivered.\n")


if __name__=="__main__": run()
