#!/usr/bin/env python3
"""Generate tier_llm_analyst.py from scratch."""

CONTENT = r'''#!/usr/bin/env python3
"""tier_llm_analyst.py - Tier 2: LLM Analysis Pipeline

Reads raw data from jarvis.db, runs deep analysis via Ollama LLM (streaming mode),
saves structured results back to analytical_reports table.
"""
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

for _path in [
     "/Users/nghialam/.hermes/hermes-agent/venv/lib/python3.11/site-packages",
     "/Users/nghialam/jarvis-hub/venv/lib/python3.11/site-packages",
]:
    if Path(_path).exists() and _path not in sys.path:
        sys.path.insert(0, _path)

try:
    import requests as req
except ImportError:
    print("[FATAL] requests not available")
    sys.exit(1)

DB_PATH = str(Path.home() / "jarvis-hub" / "knowledge" / "jarvis.db")
OLLAMA_URL = "http://localhost:11434/api/generate"


def get_conn(db_path=None):
     """Get database connection."""
    if db_path is None:
        db_path = DB_PATH
    p = Path(db_path).expanduser()
    conn = sqlite3.connect(str(p), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_analysis_data(conn):
     """Fetch fresh data from Tier 1 direct DB tables."""
    quote_rows = conn.execute(
         "SELECT * FROM market_quotes WHERE exchange IN ('HOSE','INDEX','GLOBAL',"
         "'CRYPTO','COMMODITY') AND price IS NOT NULL ORDER BY exchange, ticker"
     ).fetchall()
    quotes_data = [dict(r) for r in quote_rows]

    news_rows = conn.execute(
         "SELECT * FROM news_articles ORDER BY published_at DESC LIMIT 20"
     ).fetchall()
    news_data = [dict(r) for r in news_rows]

    if not quotes_data and not news_data:
        print("[Tier 2] No Tier 1 data found. Run tier_data_collector.py first.")
        return None

    return {"quotes": quotes_data, "news": news_data}


def build_analysis_prompt(data):
     """Build prompt for LLM market analysis."""
    quotes = data["quotes"]
    news = data["news"]

    vn_stocks = [q for q in quotes if q.get("exchange") == "HOSE"]
    indices = [q for q in quotes if q.get("exchange") in ("INDEX", "GLOBAL")]
    crypto = [q for q in quotes if q.get("exchange") == "CRYPTO"]
    commodities = [q for q in quotes if q.get("exchange") == "COMMODITY"]

    stock_lines = []
    for s in vn_stocks:
        ticker = s["ticker"]
        name = s.get("name", "")
        price = s["price"]
        stock_lines.append(
             "- %s (%s): %.1f VND" % (ticker, name, price)
         )
    stock_summary = "\n".join(stock_lines)

    index_lines = []
    for idx in indices:
        if "price" in idx and idx["price"]:
            index_lines.append(
                 "- %s: %.2f" % (idx["name"], idx["price"])
             )
    index_summary = "\n".join(index_lines)
    if not index_summary:
        index_summary = "Khong co du lieu."

    news_summaries = [
         "- %s" % n["headline"][:100] for n in news[:5]
     ]
    news_text = "\n".join(news_summaries)
    if not news_text:
        news_text = "Khong co tin tuc."

    sections = []
    sections.append("## DU LIEU THI TRUONG")
    sections.append("")
    sections.append("### VN Stocks (price trong VND):")
    sections.append(stock_summary)
    sections.append("")
    sections.append("### Market Indices:")
    sections.append(index_summary)
    sections.append("")
    sections.append("### Crypto & Commodities:")

    for c in crypto:
        nm = c.get("name", c["ticker"])
        sections.append("- %s: $%.2f" % (nm, c["price"]))
    for cm in commodities:
        nm = cm.get("name", cm["ticker"])
        sections.append("- %s: $%.2f" % (nm, cm["price"]))

    sections.append("")
    sections.append("## TIN TUC (Top 5 gan nhat):")
    sections.append(news_text)
    sections.append("")
    sections.append("## YEU CAU PHAN TICH:")
    sections.append("Phan tich theo cau truc sau (Tieng Viet toi da 80 dong, format markdown):")
    sections.append("")
    sections.append("### 1. Tong quan thi truong (5-10 dong)")
    sections.append("- VN-Index trend (tang/giam/sideways)")
    sections.append("- Diem noi bat cua 3-5 stock lon nhat trong danh sach tren")
    sections.append("")
    sections.append("### 2. Phan tich sector & hot stocks")
    sections.append("- Sector nao co momentum?")
    sections.append("- Stock nao duoc quan tam nhieu nhat?")
    sections.append("")
    sections.append("### 3. Yeu to vi mo & toan cau")
    sections.append("- Anh huong tu US indices, Gold/Oil tren")
    sections.append("- Crypto market sentiment (Bullish/Bearish/Neutral?)")
    sections.append("")
    sections.append("### 4. Tin tuc noi bat anh huong VN")
    sections.append("- Summarize 2-3 news quan trong nhat va muc do anh huong")
    sections.append("")
    sections.append("### 5. Du bao & Khuyen nghi ngan han")
    sections.append("- Bias: Bullish/Bearish/Neutral cho tuan toi + ly do")
    sections.append("- 3 stocks can theo doi voi muc do tin cay (cao/trung binh/thap)")
    sections.append("")
    sections.append("Output format markdown, khong co preamble/greeting, bat dau truc tiep tu ### 1.")

    prompt = "\n".join(sections)
    return prompt


def _clean_reasoning_preamble(text):
     """Remove Qwen3.6 reasoning preamble from streaming output."""
    lines = text.split("\n")
    skip_patterns = [
         "here's a thinking process",
         "let me think about this",
         "i need to analyze",
         "as an ai, i don't have",
         "**Analyze User Input**:",
         "**Role:** Financial",
         "**Data Provided:**",
    ]
    skip_count = 0
    for line in lines:
        lower_line = line.lower().strip()
         # Skip numbered reasoning steps like "1. **Analyze User Input:**"
        if re.match(r"^\s*\d+\.\s+\*\*", line):
            skip_count += 1
        elif any(p in lower_line for p in skip_patterns):
            skip_count += 1
        else:
            break
    result = "\n".join(lines[skip_count:])
    return result.strip() if result.strip() else text


def _ollama_healthcheck():
     """Check if Ollama API is responding."""
    try:
        r = req.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_warmup(model):
     """Quick warm-up to ensure model is loaded."""
    try:
        r = req.post(
            OLLAMA_URL,
            json={
                 "model": model,
                 "prompt": "OK",
                 "stream": False,
                 "options": {"num_predict": 2},
             },
            timeout=120,
         )
        return r.status_code == 200
    except Exception:
        return False


def _ollama_streamed_call(prompt, model, temperature=0.3, num_predict=2048):
     """Call Ollama with streaming mode; accumulate chunks into full response."""
    payload = {
         "model": model,
         "prompt": prompt,
         "stream": True,
         "options": {
             "temperature": temperature,
             "num_predict": num_predict,
             "top_p": 0.9,
              # Qwen3.6 reasons by default - explicitly disable chain-of-thought leaking into response
             "thinking": False,
         },
     }

    try:
        chunks = []
        with req.post(OLLAMA_URL, json=payload, timeout=600, stream=True) as r:
            if r.status_code != 200:
                return None
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                     # Qwen3.6 reasoning models put output in 'thinking', not 'response'
                    token = data.get("thinking", "") or data.get("response", "")
                    if token:
                        chunks.append(token)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        return "".join(chunks)
    except Exception as e:
        print("[Tier 2] Ollama streaming error: %s" % str(e))
        return None


def call_ollama(prompt, model="qwen3.6:35b-a3b-mxfp8"):
     """Call Ollama LLM for analysis using streaming mode."""
    if not _ollama_healthcheck():
        print("[Tier 2] [FAIL] Ollama not responding.")
        return None

    if not _ollama_warmup(model):
        print("[Tier 2] [WARN] Warm-up failed, proceeding anyway...")

    response = _ollama_streamed_call(prompt, model)
    return response


def save_analysis(conn, run_date, analysis_text, model_used="unknown", confidence=0.0):
     """Save LLM analysis result to DB."""
    cursor = conn.execute(
         "INSERT OR REPLACE INTO analytical_reports "
         "(run_date, report_type, title, summary, full_content, status, model_used, created_at) "
         "VALUES (?, ?, ?, ?, ?, 'completed', ?, CURRENT_TIMESTAMP)",
         (run_date, "market_overview",
             "Market Analysis %s" % datetime.now().strftime("%H:%M"),
          analysis_text[:500], analysis_text, model_used),
     )

    conn.execute(
         "INSERT OR REPLACE INTO market_evaluations "
         "(date, evaluation, summary, created_at) VALUES (?, ?, 'Auto-generated', CURRENT_TIMESTAMP)",
         (run_date, analysis_text[:2000]),
     )

    return cursor.lastrowid


def run_analysis(db_path=None, dry_run=False):
     """Execute full Tier 2 LLM analysis pipeline."""
    conn = get_conn(db_path)

    raw_data = fetch_analysis_data(conn)
    if not raw_data:
        return None

    today = datetime.now().strftime("%Y-%m-%d")

    print("\n%s" % ("=" * 60))
    print("[Tier 2] LLM Analysis for run: %s" % today)
    print("         Quotes: %d, News: %d" % (
        len(raw_data["quotes"]), len(raw_data["news"])))
    print("%s\n" % ("=" * 60))

    if dry_run:
        prompt = build_analysis_prompt(raw_data)
        print("# PROMPT (dry run):")
        print(prompt[:2000])
        if len(prompt) > 2000:
            print("\n... (%d more chars)" % (len(prompt) - 2000))
        return prompt

    prompt = build_analysis_prompt(raw_data)
    model = "qwen3.6:35b-a3b-mxfp8"

    print("[Tier 2] Calling %s for market analysis..." % model)
    response = call_ollama(prompt, model=model)

    if not response or len(response.strip()) < 20:
        print("[Tier 2] [FAIL] No meaningful response from Ollama")
        return None

     # Clean reasoning preamble (Qwen3.6 often starts with thinking text)
    cleaned = _clean_reasoning_preamble(response)
    if not cleaned or len(cleaned.strip()) < 20:
        cleaned = response    # fallback to raw

    has_sections = sum([
         "1." in cleaned[:500],
         "2." in cleaned,
         "3." in cleaned,
         "4." in cleaned,
          "Bullish" in cleaned or "Bearish" in cleaned or "Neutral" in cleaned,
     ])
    confidence = min(0.95, 0.4 + has_sections * 0.12)

    report_id = save_analysis(conn, today, cleaned, model, confidence)

    print("[Tier 2] Analysis complete.")
    print("      Report ID: %s" % report_id)
    print("      Model: %s" % model)
    print("      Confidence: %.0f%%" % (confidence * 100))
    print("      Length: %d tokens" % len(cleaned))

    conn.commit()
    return {
         "report_id": report_id,
        "model": model,
          "confidence": confidence,
        "length": len(cleaned),
        "preview": cleaned.strip()[:300],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Jarvis Hub Tier 2: LLM Market Analyst (Ollama)"
      )
    parser.add_argument("--date", help="Override run date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling Ollama")
    args = parser.parse_args()

    result = run_analysis(dry_run=args.dry_run)

    if result:
        print("\n[Tier 2 Summary]")
        print("      Report ID: %s" % result["report_id"])
        print("      Model: %s" % result["model"])
        print("   Confidence: %.0f%%" % (result["confidence"] * 100))
        preview = result.get("preview", "")
        if preview:
            print("      Preview:\n           ---\n%s..." % preview)
    else:
        print("\n[Tier 2] Failed.")
'''

# Write it
path = "/Users/nghialam/jarvis-hub/core/tier_llm_analyst.py"
with open(path, "w") as f:
    f.write(CONTENT)

# Verify syntax
import py_compile
try:
    py_compile.compile(path, doraise=True)
    print("\n[SUCCESS] tier_llm_analyst.py written and syntax valid!")
except py_compile.PyCompileError as e:
    print("\n[BROKEN] %s" % str(e))
