#!/usr/bin/env python3
"""Gotham Brief - Fast standalone briefing generator.

Uses fast_briefing.py for RSS+LLM collection, then formats output into
4-section English brief delivered to gotham channel.

Usage:
    python3 gotham_fast_brief.py afternoon|morning|noon|evening
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime


# --- Config ---
CHAT_ID = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "-1003801745265")  # gotham channel

def get_bot_token():
    for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    try:
        path = os.path.expanduser("~/.hermes/.jarvis_token_cache")
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return ""

BOT_TOKEN = get_bot_token()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# --- Telegram helpers ---

def send_telegram(text, parse_mode="HTML"):
    """Send message to Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[WARN] Telegram tokens not set, skipping delivery")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Split long messages (>4096 chars for Telegram Bot API)
    max_len = 3800
    parts = []
    current = ""
    for block in text.split("\n\n"):
        chunk = (current + "\n\n" + block).strip() if current else block.strip()
        if len(chunk) > max_len and current:
            parts.append(current[:max_len])
            current = block.strip()
        else:
            current = chunk

    if current.strip():
        parts.append(current.strip())

    for i, part in enumerate(parts):
        # Convert markdown -> Telegram HTML
        html = _markdown_to_html(part)

        payload = json.dumps({
            "chat_id": CHAT_ID,
            "text": html,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            mid = result.get("result", {}).get("message_id", "?")
            print(f"Telegram sent (msg_id:{mid})")
        except Exception as e:
            print(f"Telegram failed ({i+1}): {e}", file=sys.stderr)

    return True


def _markdown_to_html(text):
    """Convert markdown to Telegram-compatible HTML."""
    line = text.strip()

    # Bold
    line = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
    line = re.sub(r'__(.+?)__', r'<b>\1</b>', line)

    # Italic (only if no backtick on same line)
    if '`' not in line:
        line = re.sub(r'\*(.+?)\*', r'<i>\1</i>', line)

    # Code
    line = re.sub(r'`(.+?)`', r'<code>\1</code>', line)

    # Links [name](url) -> <a href=url>name</a>
    line = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', line
    )

    return line


# --- Core pipeline ---

def run_fast_briefing():
    """Run fast_briefing.py and capture ALL output."""
    try:
        proc = subprocess.run(
            ["python3", os.path.join(SCRIPT_DIR, "fast_briefing.py")],
            capture_output=True, text=True, timeout=600
        )
        # Combine stdout+stderr since jarvis scripts print to stderr
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return combined + "\n\n=== RAW OUTPUT START ===\n" + combined
    except subprocess.TimeoutExpired:
        print("[WARN] fast_briefing.py timed out")
        return ""
    except FileNotFoundError:
        print(f"[ERROR] Script not found: "
              f"{os.path.join(SCRIPT_DIR, 'fast_briefing.py')}")
        return ""


def generate_english_brief(raw_output, mode):
    """Generate formatted 4-section English brief from LLM output."""

    now = datetime.now()
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                  "Friday", "Saturday", "Sunday"]
    date_str = now.strftime('%d/%m/%Y')
    day_name = day_names[now.weekday()]

    # Check if we got LLM results
    has_ai = "PHAN-AI" in raw_output or "Running LLM analysis" in raw_output
    has_trend = "PHAN-XUHUONG" in raw_output
    has_recs = "PHAN-KHENHNGHI" in raw_output

    header = (
        f"JARVIS INTELLIGENCE BRIEFING\n"
        f"\u1f4c5 {date_str} ({day_name})\n"
        f"\u23f0 {mode.title()} Edition\n"
        f"{'=' * 40}\n\n"
    )

    msg = header

    # Section 1: News Synthesis (AI Priority)
    if has_ai:
        ai_match = re.search(
            r'PHAN-AI\s*\n(.*?)($|PHAN-ECON)', raw_output, re.DOTALL
        )
        if ai_match:
            msg += "\u1f30d **GLOBAL NEWS SYNTHESIS (AI Priority)**\n\n"
            for line in ai_match.group(1).strip().split('\n')[:6]:
                line = line.strip()
                if line and not line.startswith('#'):
                    clean = re.sub(r'^[\s*\-*]+', '', line)
                    msg += f"- {clean}\n"
        else:
            msg += (
                "\u1f30d **GLOBAL NEWS SYNTHESIS (AI Priority)**\n\n"
                "- Unable to extract AI/Tech news from pipeline.\n\n"
            )
    else:
        msg += (
            "\u1f30d **GLOBAL NEWS SYNTHESIS**\n\n"
            "\u26a0 Pipeline completed but no LLM content captured. "
            + "Check raw output.\n\n"
        )

    # Section 2: Trend Analysis
    if has_trend:
        trend_match = re.search(
            r'PHAN-XUHUONG\s*\n(.*?)($|PHAN-KHENHNGHI)',
            raw_output, re.DOTALL
        )
        if trend_match:
            msg += "\n\u1f50d **TREND ANALYSIS**\n\n"
            for line in trend_match.group(1).strip().split('\n')[:5]:
                line = line.strip()
                if line and not line.startswith('#'):
                    clean = re.sub(r'^[\s*\-*]+', '', line)
                    msg += f"- {clean}\n"
        else:
            msg += (
                "\n\u1f50d **TREND ANALYSIS**\n\n"
                "- Pipeline ran but trend extraction failed.\n\n"
            )
    else:
        msg += (
            "\n\u1f50d **TREND ANALYSIS**\n\n"
            "\u26a0 No trend data captured from pipeline.\n\n"
        )

    # Section 3: Actionable Recommendations
    if has_recs:
        rec_match = re.search(
            r'PHAN-KHENHNGHI\s*\n(.*?)$', raw_output, re.DOTALL
        )
        if rec_match:
            msg += "\n\ud83d\udca1 **ACTIONABLE RECOMMENDATIONS**\n\n"
            for line in rec_match.group(1).strip().split('\n')[:3]:
                line = line.strip()
                if line and not line.startswith('#'):
                    clean = re.sub(r'^[\s*\-*]+', '', line)
                    msg += f"- {clean}\n"

    msg += (
        "\ud83d\udca1 **ACTIONABLE RECOMMENDATIONS**\n\n"
        "- Deploy AI Triage Protocol for email/notes processing\n"
        "- Weekly Context Synthesis routine using Gemini\n"
        "- Automate repetitive workflows with Notion/Airtable scripts\n\n"
    )

    # Section 4: Tech Lab Proposal (static template)
    msg += (
        "\ud83e\uddea **TECH LAB PROPOSAL**\n\n"
        "- **Project**: Personal AI Knowledge Hub - ingest saved "
        "articles/notes via Unstructured.io, embed with Ollama API, "
        "query via RAG pipeline\n"
        "- **Why now**: Multimodal models can process PDFs/images/audio "
        "in one pass. LangGraph/CrewAI mature for cyclic agent workflows.\n"
        "- **Value**: Instant strategic insight from unstructured data - "
        "no more manual note organization.\n"
    )

    return msg


# --- Main ---

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "afternoon"

    print(f"[Gotham Fast Briefing] Running {mode} edition...")

    # Step 1: Run fast_briefing.py (5 sources, faster than 14-source jarvis)
    print("[Step 1/2] Collecting RSS feeds and running LLM analysis...")

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                   "Friday", "Saturday", "Sunday"]

    raw_output = run_fast_briefing()

    if not raw_output or \
        ("Could not fetch RSS" in raw_output or "No data available" in raw_output):
        msg = (
            f"\u26a0\ufe0f JARVIS INTELLIGENCE BRIEFING\n"
            f"\u1f4c5 {datetime.now().strftime('%d/%m/%Y')} "
            f"({day_names[datetime.now().weekday()]})\n"
          + "\u23f0 {} Edition\n".format(mode.title())
             + "{}\n\nRSS feed unavailable. Check network.".format("=" * 40)
        )
        print(msg)
        send_telegram(msg)
        return

    # Step 2: Format into 4-section English brief
    print("[Step 2/2] Formatting brief...")
    brief = generate_english_brief(raw_output, mode)

    # Send to gotham channel
    print(f"Sending Telegram message ({len(brief)} chars)...")
    send_telegram(brief)

    print("\n\ud83d\udc4d Briefing delivered!")


if __name__ == "__main__":
    main()
