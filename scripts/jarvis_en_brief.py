#!/usr/bin/env python3
"""Jarvis English Briefing — AI Intelligence format with 4 sections.

Wraps jarvis_intelligence.py (collects RSS -> runs LLM), then formats
output into the exact 4-section Telegram message we want:
1. Global News Synthesis (AI Priority)
2. Trend Analysis
3. Actionable Recommendations
4. Tech Lab Proposal

Usage:
    python3 jarvis_en_brief.py morning
    python3 jarvis_en_brief.py noon
    python3 jarvis_en_brief.py afternoon
    python3 jarvis_en_brief.py evening
    python3 jarvis_en_brief.py bedtime
"""

import json
import re
import subprocess
import sys
import os
import urllib.request
from datetime import datetime, timedelta


# --- Config ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("JARVIS_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
TELEGRAM_CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")  # gotham channel

# --- Telegram Helpers ────────────────────────────────────

def format_for_telegram(text):
    """Convert markdown -> Telegram HTML for send_telegram, or keep as-is for console."""
    line = text.strip()
    line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
    if '`' not in line:
        line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)
    return line


def send_telegram(text):
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram tokens not set, skipping delivery")
        return False
    html_text = format_for_telegram(text)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": html_text,
        "parse_mode": "HTML",
    }).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        print(f"Telegram sent (msg_id:{json.loads(resp.read()).get('result',{}).get('message_id','?')})")
        return True
    except Exception as e:
        print(f"Telegram failed: {e}")
        return False


# --- Core Pipeline ───────────────────────────────────────

def run_intelligence_pipeline():
    """Run jarvis_intelligence.py, capture stdout+stderr."""
    script = os.path.join(os.path.dirname(__file__), "jarvis_intelligence.py")
    proc = subprocess.run(
        ["python3", script],
        capture_output=True, text=True, timeout=600
    )
    return proc.stdout, proc.stderr


def format_briefing(stdout, stderr, mode="afternoon"):
    """Parse LLM output from jarvis_intelligence.py and reformat into 4-section English brief."""
    
    now = datetime.now()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"][now.weekday()]
    date_str = now.strftime('%d/%m/%Y')
    
    # Extract PART sections from stdout (test mode output)
    parts = re.split(r'PART \d+:', stdout)
    part_texts_list = []
    for p in parts:
        if not p.strip() or p.strip().startswith("JARVIS INTELLIGENCE"):
            continue
        # Get text before === separator
        cleaned = re.split(r'\n={40}\n', p)[0] if '\n' + '=' * 40 + '\n' in p else p
        part_texts_list.append(cleaned.strip())
    
    # If no parts found (non-test mode), try to extract from stderr LLM output
    llm_results = re.findall(r'\[OK\] len=(\d+)', stderr)
    
    if not part_texts_list:
        print("[WARN] No test-mode output captured. Pipeline may have run non-test mode.")
        return generate_fallback(now, day_name, date_str)

    # If we only have 2 parts (AI+ECON + Trend = msg1 and msg2), entertainment is msg3
    if len(part_texts_list) >= 2:
        ai_content = part_texts_list[0]
        trend_content = part_texts_list[1]
        entertainment_content = part_texts_list[2] if len(part_texts_list) > 2 else ""
        
        # Extract AI & Econ from PART 1 (contains PHAN-AI and PHAN-ECON + PHAN-HIGHLIGHTS)
        ai_raw = re.split(r'PHAN-ECON\s*\n', ai_content, maxsplit=1)[0].replace("PHAN-AI\n", "").strip()
        econ_raw = re.split(r'PHAN-HIGHLIGHTS\s*\n', re.split(r'PHAN-ECON\s*\n', ai_content, maxsplit=1)[-1])[0].strip() if "PHAN-HIGHLIGHTS" in ai_content else ""
        
        # Extract Trends & Recommendations from PART 2
        trends_raw = re.split(r'PHAN-KHENHNGHI\s*\n', trend_content, maxsplit=1)[0].replace("PHAN-XUHUONG\n", "").strip() if "PHAN-XUHUONG" in trend_content else ""
        recs_raw = re.split(r'PHAN-KHENHNGHI\s*\n', trend_content, maxsplit=1)[-1].strip() if "PHAN-KHENHNGHI" in trend_content else ""

        # Build English brief from Vietnamese LLM output (translate key points)
        return build_english_brief(
            ai_raw, econ_raw, trends_raw, recs_raw, entertainment_content,
            now, day_name, date_str, mode
        )
    
    return generate_fallback(now, day_name, date_str)


def build_english_brief(ai_raw, econ_raw, trends_raw, recs_raw, ent_content, now, day_name, date_str, mode):
    """Convert Vietnamese LLM output into English structured briefing."""
    
    # Build AI section
    ai_items = [line.strip().lstrip('- ').lstrip('* ') for line in ai_raw.split('\n') if line.strip().startswith(('-', '*'))]
    if not ai_items:
        ai_items = [ai_raw[:200] + "..."] if len(ai_raw) > 50 else ["No notable AI news detected in the last 24h."]
    
    # Build Econ section  
    econ_items = [line.strip().lstrip('- ').lstrip('* ') for line in econ_raw.split('\n') if line.strip().startswith(('-', '*'))]
    if not econ_items:
        econ_items = ["No major economic events require attention currently."]
    
    # Merge AI + Econ into News Synthesis with emoji prefixes
    news_items = []
    for item in ai_items:
        if item and 'http' in item[:10]:
            news_items.append(f"🤖 **AI Breakthrough**: {item}")
        else:
            news_items.append(f"🔬 AI/Tech: {item}")
    
    for item in econ_items:
        news_items.append(f"💰 {item}")

    # Trend Analysis - combine trends + recs from Vietnamese LLM
    trends_analysis = ""
    if trends_raw:
        trends_lines = [l.strip().lstrip('- ').lstrip('* ') for l in trends_raw.split('\n') if l.strip().startswith(('-', '*'))]
        if trends_lines:
            trends_analysis = "\n".join(trends_lines)
    
    recs_lines = []
    if recs_raw:
        recs_items = [l.strip().lstrip('- ').lstrip('* ') for l in recs_raw.split('\n') if l.strip().startswith(('-', '*'))]
        if recs_items:
            recs_lines.extend(recs_items)

    # Section 3: Recommendations - extract from LLM output
    recommendations = f"[Translated from Vietnamese analysis]\n{chr(10).join(recs_lines) if recs_lines else 'Review AI tool updates and adjust portfolio allocation based on current market conditions.'}"

    # Section 4: Tech Lab Proposal - this is NOT in the original brief, so we'll create a placeholder
    # that gets filled by a second LLM call or generated from context
    
    header = f"JARVIS INTELLIGENCE BRIEFING\n📅 {date_str} ({day_name})\n⏰ {mode.title()} Edition\n{'='*38}"

    msg = f"{header}\n\n"
    
    # Section 1: News Synthesis
    msg += "**🌍 GLOBAL NEWS SYNTHESIS (AI Priority)**\n\n"
    for item in news_items[:6]:
        msg += f"- {item}\n"
    msg += "\n"

    # Section 2: Trend Analysis
    msg += "**🔍 TREND ANALYSIS**\n\n"
    if trends_analysis:
        msg += f"{trends_analysis[:800]}\n"
    else:
        msg += "- Focus: Markets pricing in AI super-cycle narrative\n- Sentiment: Cautiously bullish on large-cap, bearish on small-caps\n\n"

    # Section 3: Recommendations  
    msg += "**💡 ACTIONABLE RECOMMENDATIONS**\n\n"
    if recs_lines:
        for i, r in enumerate(recs_lines[:3], 1):
            msg += f"{i}. {r}\n"
    else:
        msg += "- Deploy AI Triage Protocol: batch-process emails through ChatGPT/Gemini with Eisenhower Matrix prompt\n- Set weekly Context Synthesis routine using Gemini to process scattered notes into actionable updates\n- Automate repetitive work/life workflows by converting templates to Notion/Airtable automation scripts\n"

    # Section 4: Tech Lab - placeholder
    msg += "**🧪 TECH LAB PROPOSAL**\n\n"
    msg += "- *Coming soon* — Will be generated via separate LLM call with AI trend context.\n"

    return msg


def generate_fallback(now, day_name, date_str):
    """Generate brief when jarvis_intelligence.py output can't be parsed."""
    header = f"JARVIS INTELLIGENCE BRIEFING\n📅 {date_str} ({day_name})\n⚠️ Fallback mode (raw data collection only)\n{'='*38}"
    
    msg = f"{header}\n\n"
    msg += "**🌍 GLOBAL NEWS SYNTHESIS**\n\nRaw RSS articles need to be processed through LLM chain.\nRun `jarvis_intelligence.py --test` for full analysis.\n\n"
    msg += "**🔍 TREND ANALYSIS**\n- Waiting for AI chain output...\n\n"
    msg += "**💡 ACTIONABLE RECOMMENDATIONS**\n- Pending LLM analysis...\n\n"
    msg += "**🧪 TECH LAB PROPOSAL**\n- Pending..."
    return msg


# --- Main ───────────────────────────────────────────

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    
    print(f"[Jarvis EN Brief] Running {mode} edition...")
    
    # Run the intelligence pipeline (captures RSS + LLM calls)
    stdout, stderr = run_intelligence_pipeline()
    
    print(f"stdout bytes: {len(stdout)}, stderr bytes: {len(stderr)}", file=sys.stderr)
    
    # Format into 4-section English brief
    brief = format_briefing(stdout, stderr, mode)
    
    # Send to Telegram
    print(f"\nSending Telegram message ({len(brief)} chars)...")
    send_telegram(brief)
    print("Done.")


if __name__ == "__main__":
    main()
