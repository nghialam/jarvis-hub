#!/usr/bin/env python3
"""
AI Signal Monitor v2 - Jarvis Hub Intelligent News & Strategy Assistant

Usage:
    python3 ai_signal_monitor.py brief          # Generate full briefing (text)
    python3 ai_signal_monitor.py dashboard      # Run Flask web dashboard on :8501
"""

import os
import sys
import json
import time
import datetime
import sqlite3
from pathlib import Path

# ─── Lazy imports ──────────────────────────────────────
requests = None
BeautifulSoup = None
DDGS = None

def _ensure_imports():
    global requests, BeautifulSoup, DDGS
    if requests is not None:
        return
    import requests as req_module
    from bs4 import BeautifulSoup as BS_Module
    try:
        from duckduckgo_search import DDGS as DDGS_mod
    except ImportError:
        DDGS_mod = None
        print("[WARN] duckduckgo-search not installed", file=sys.stderr)
    requests = req_module
    BeautifulSoup = BS_Module
    DDGS = DDGS_mod


# ─── Configuration ─────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "signals.db"
OMLX_URL = os.environ.get("OMLX_HOST", "http://localhost:11434")
LLM_MODEL   = os.environ.get("LLM_MODEL", "Qwen3.6-35B-A3B-MLX-8bit")


# ─── 1. Data Collection ────────────────────────────────

def _get(url, timeout=12):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            print(f"  [WARN] fetch {url}: {e}", file=sys.stderr)
    return None


def collect_markets():
    _ensure_imports()
    html = _get("https://finance.yahoo.com/markets/")
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    marks = {}
    for row in soup.select("tr"):
        cells = row.select("td")
        if len(cells) >= 4:
            symbol = cells[0].get_text(strip=True).split("\n")[0]
            price  = cells[2].get_text(strip=True)
            chg    = cells[3].get_text(strip=True)
            marks[symbol[:15]] = {"price": price, "change": chg}
    return marks


def collect_yahoo_headlines():
    _ensure_imports()
    html = _get("https://finance.yahoo.com/news/")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    headlines = []
    seen = set()
    for el in soup.select("h3 a, .stream-item .content, article"):
        t = el.get_text(strip=True)
        if 40 < len(t) < 200 and t not in seen:
            seen.add(t)
            headlines.append(t[:150])
    return headlines[:20]


def collect_ddgs_news():
    _ensure_imports()
    if DDGS is None:
        return []

    topics = [
         "AI breakthrough new model launch",
         "artificial intelligence regulation policy",
         "AI startup funding valuation",
     ]
    results = []
    seen = set()

    for topic in topics:
        try:
            with DDGS() as ddg:
                articles = list(ddg.text(topic, timelimit="d", max_results=6))
                for a in articles:
                    title = a.get("title", "")
                    if title and title.lower() not in seen:
                        seen.add(title.lower())
                        results.append({
                             "title":  title,
                             "source": a.get("href", "").split("//")[1].split("/")[0] if a.get("href") else "",
                             "date":   "",
                             "url":    a.get("href", ""),
                             "body":   a.get("body", "")[:300],
                         })
        except Exception as e:
            print(f"   [WARN] DDG error '{topic}': {e}", file=sys.stderr)

    return results[:15]


def collect_all():
    print("[1/3] Yahoo Finance markets...")
    markets = collect_markets()

    print("[2/3] Yahoo Finance headlines...")
    yahoo_hl  = collect_yahoo_headlines()

    print("[3/3] DuckDuckGo AI news... ")
    ddgs_news = collect_ddgs_news()

    return {
        "collected_at": datetime.datetime.now().isoformat(),
        "markets":      markets,
        "yahoo_headlines": yahoo_hl,
        "ddgs_news":    ddgs_news,
    }


# ─── 2. LLM Analysis Chains ────────────────────────────

def _call_llm(prompt, max_tokens=1024):
    """Call Ollama /v1/chat/completions endpoint."""
    _ensure_imports()
    try:
        resp = requests.post(
            f"{OMLX_URL}/v1/chat/completions",
            json={"model": LLM_MODEL, "messages": [{"role":"user","content":prompt}], "stream": False, "max_tokens": max_tokens},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}", file=sys.stderr)
        return str(e)


def chain_1_synthesis(data):
    """Chain 1: Global news synthesis + trends."""
    _ensure_imports()
    markets = data.get("markets", {})
    hpairs = "\n".join(f"- {k}: {v['price']} ({v['change']})" for k, v in list(markets.items())[:12])
    headlines = "\n" + "\n".join(f"- {h}" for h in data.get("yahoo_headlines", [])[:10])
    ddgs_news = "\n\n".join(
        f"- **{nd['title']}** ({nd.get('source','')})\n  Body: {nd.get('body','')}"
        for nd in data.get("ddgs_news", [])[:8]
    )

    prompt = f"""You are the Jarvis Intelligence Briefing Assistant. Today is {datetime.date.today().isoformat()}.

GLOBAL MARKETS:
{hpairs}

RECENT HEADLINES (Yahoo):
{headlines}

TOP AI NEWS SOURCES (with bodies):
{ddgs_news}

PROVISIONS: Generate a concise briefing with EXACTLY these 2 sections (bullet points only, no tables):

### SECTION 1: GLOBAL NEWS SYNTHESIS
- Focus on AI breakthroughs first (models, regulation, startups)
- Include other relevant major topics (finance, politics, sports, entertainment) if prominent
- Max ~8 bullets total, extremely concise

### SECTION 2: TREND ANALYSIS  
- Focal point of current news? Correlation between sectors?
- Bullish/Bearish/Neutral with reasoning"""

    return _call_llm(prompt, max_tokens=1500)


def chain_2_recommendations(data):
    """Chain 2: Actionable recommendations."""
    _ensure_imports()
    ddgs_news = data.get("ddgs_news", [])
    top_stories = "\n".join(f"- {nd['title']}" for nd in ddgs_news[:10])

    prompt = f"""You are Jarvis, a strategic AI assistant. Today is {datetime.date.today().isoformat()}.

Recent AI/tech developments:
{top_stories}

PROVISION: Generate EXACTLY this section with bullet points only:

### SECTION 2: ACTIONABLE RECOMMENDATIONS
- Provide 2-3 specific actions for user's work/life optimization using new AI tools
- Focus on HOW to apply them, not just "learn more"
- Keep it practical and immediate"""

    return _call_llm(prompt, max_tokens=800)


def chain_3_tech_lab(data):
    """Chain 4: Tech Lab project proposal."""
    _ensure_imports()
    ddgs_news = data.get("ddgs_news", [])
    top_stories = "\n".join(f"- {nd['title']}" for nd in ddgs_news[:8])

    prompt = f"""You are Jarvis, building AI projects. Today is {datetime.date.today().isoformat()}.

Top developments:
{top_stories}

PROVISION: Generate SECTION 4 - Tech Lab project proposal:

### SECTION 4: TECH LAB PROJECT PROPOSAL
Propose ONE specific AI/tech project we can build immediately:
- Project name & purpose
- Why feasible NOW (current tech available)?
- Practical value it provides
- Implementation approach (what tools/APIs/stack)"""

    return _call_llm(prompt, max_tokens=800)


# ─── 3. Storage ──────────────────────────────────────

def _ensure_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS briefings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        collected_data TEXT,
        section_1 TEXT,
        section_2 TEXT,
        section_3 TEXT,
        section_4 TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()


def save_briefing(data, s1, s2, s3, s4):
    _ensure_db()
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "INSERT INTO briefings (timestamp, collected_data, section_1, section_2, section_3, section_4) VALUES (?,?,?,?,?,?)",
        (datetime.datetime.now().isoformat(), json.dumps(data), s1, s2, s3, s4),
    )
    conn.commit()
    conn.close()


def load_recent_briefings(limit=5):
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM briefings ORDER BY created_at DESC LIMIT ?", (limit,))
    return [dict(r) for r in c.fetchall()]


# ─── 4. Telegram Notification ──────────────────────

def notify_telegram(s1, s2, s3):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        print("[WARN] Telegram tokens not set, skipping delivery")
        return False

    lines = [
        "🤖 **JARVIS INTELLIGENCE BRIEFING**\n📅 " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        "",
        s1[:400] + "..." if len(s1) > 400 else s1,
        "",
        s2[:300] + "..." if len(s2) > 300 else s2,
        "",
        s3[:300] + "..." if len(s3) > 300 else s3,
    ]

    msg = "\n\n".join(lines)
    max_chars = 3800
    if len(msg) > max_chars:
        msg = msg[:max_chars] + "... [truncated]"

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=15,
        )
        if resp.status_code == 200:
            print("  ✓ Telegram notification sent")
            return True
        else:
            print(f"  ✗ Telegram API {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Telegram delivery failed: {e}", file=sys.stderr)
        return False


# ─── 5. Execution Pipeline ────────────────────────

def run_pipeline(verbose=True):
    """Execute full pipeline: scrape → LLM chains → storage → notify."""
    start = time.time()

    if verbose:
        print("\n" + "=" * 60)
        print("JARVIS AI INTELLIGENCE BRIEFING SYSTEM")
        print(f"Start: {datetime.datetime.now().isoformat()}")

    # Phase 1: Collect data
    data = collect_all()
    if verbose:
        print(f"\nData: {len(data['ddgs_news'])} DDGS news, "
              f"{len(data.get('yahoo_headlines',[]))} Yahoo headlines, "
              f"{len(data.get('markets',{}))} market indices")

    # Phase 2: LLM chains (sequential - CRITICAL for qwen3.6)
    if verbose:
        print("\n[Chain 1/3] News synthesis...")
    s1 = chain_1_synthesis(data)

    print("[Chain 2/3] Recommendations...")
    time.sleep(10)
    s2 = chain_2_recommendations(data)

    print("[Chain 3/3] Tech Lab proposal...")
    time.sleep(10)
    s3 = chain_3_tech_lab(data)

    # Add section 4 as empty since chain naming was 1-2-3 but we want 4 sections total
    s4 = "Tech Lab data embedded in Chain 3 above." if verbose else ""

    # Phase 3: Store
    print("\n[Phase 3] Saving briefing to DB...")
    save_briefing(data, s1, s2, s3, s4)

    # Phase 4: Telegram delivery
    print("[Phase 4] Sending to Telegram...")
    notify_telegram(s1, s2, s3)

    elapsed = round(time.time() - start, 1)
    print(f"\nBRIEFING COMPLETE in {elapsed}s\n")


# ─── Flask Dashboard ──────────────────────────────

def create_flask_app():
    from flask import Flask, render_template_string, jsonify
    
    TEMPLATES = """
<html><head>
<title>Jarvis AI Signal Monitor</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#111; color:#EEE; padding:2rem; }
  h1 { font-size:2rem; margin-bottom:1rem; color:#FF3747; }
  .section { background:#1a1a1a; border-radius:8px; padding:1.5rem; margin-bottom:1rem; }
  .section h2 { color:#00F4B0; margin-bottom:.8rem; font-size:1.2rem; }
  .meta { color:#999; font-size:.85rem; margin-bottom:.5rem; }
  pre { white-space:pre-wrap; line-height:1.6; font-size:.95rem; }
  .btn { display:inline-block; background:#333;color:#EEE;padding:.7rem 1.2rem;border-radius:4px;text-decoration:none;margin:.5rem .5rem .5rem 0;cursor:pointer;border:1px solid #555; }
  .btn:hover { background:#444; }
  .btn-primary { background:#0066ff; border-color:#0066ff; }
  .status { color:#FF3747; }
</style>
<script>
function refreshData(){window.location.reload();}
function runPipeline(){fetch('/api/scrape').then(r=>r.json()).then(d=>{alert(JSON.stringify(d,null,2));window.location.reload();});}
setInterval(refreshData, 30000); // Auto-refresh every 30s
</script>
</head><body>
<h1>Jarvis AI Signal Monitor</h1>
<p class="meta">Last updated: {{ timestamp }} | Source count: {{ briefings|length }}</p>

<div style="margin:.5rem 0;">
  <a href="/api/scrape" class="btn btn-primary">Run Pipeline Now</a>
  <button class="btn" onclick="runPipeline()">Refresh</button>
</div>

{% for b in briefings %}
<div class="section">
  <h2>Briefing #{{ loop.revindex }} - {{ b.timestamp }}</h2>
  <div>{{ b.section_1 | replace('\n', '<br>') | safe }}</div>
  <hr style="margin:1rem 0;opacity:.2">
  <div>{{ b.section_2 | replace('\n', '<br>') | safe }}</div>
</div>
{% endfor %}

<p class="meta">{{ briefings|length }} briefing(s) collected</p>
</body></html>
"""

    app = Flask(__name__, template_string=TEMPLATES)

    @app.route("/")
    def index():
        briefings = load_recent_briefings()
        return render_template_string(
            TEMPLATES,
            timestamp=datetime.datetime.now().isoformat(),
            briefings=briefings,
        )

    @app.route("/api/scrape")
    def api_scrape():
        try:
            run_pipeline(verbose=True)
            return jsonify({"status": "success", "message": "Pipeline triggered"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/latest")
    def api_latest():
        briefings = load_recent_briefings(1)
        if not briefings:
            return jsonify({"error": "No briefings yet. Run pipeline first."}), 404
        return jsonify(briefings[0])

    @app.route("/api/history")
    def api_history():
        return jsonify(load_recent_briefings(20))

    return app


# ─── Entry Point ──────────────────────────────

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Jarvis AI Signal Monitor")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("brief", help="Run one briefing pipeline (text output)")
    sub.add_parser("dashboard", help="Start Flask web dashboard (port 8501)")

    args = parser.parse_args()

    if not args.command or args.command == "brief":
        run_pipeline(verbose=True)
        sys.exit(0)

    elif args.command == "dashboard":
        app = create_flask_app()
        print("Starting Jarvis AI Signal Dashboard on http://localhost:8501")
        app.run(host="0.0.0.0", port=8501, debug=False)
