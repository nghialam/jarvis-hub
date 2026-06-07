#!/usr/bin/env python3
"""Market evaluation reporter.

Calls Jarvis Hub /api/market-evaluation, formats the LLM output, and sends
a clean HTML-formatted message to the Gotham News Telegram channel.

Scheduled: weekdays 08:30 (before VN market open at 9:00).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

TELEGRAM_CHAT_ID = "-1003801745265"    # private chat
JARVIS_HUB_URL = os.environ.get("JARVIS_HUB_URL", "http://localhost:8100")


def load_telegram_token():
    """Load token from env -> cache -> .env."""
    for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    cache_file = os.path.expanduser("~/.hermes/.jarvis_token_cache")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cached = f.read().strip()
            if cached and ":" in cached:
                return cached
    try:
        env_path = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "TELEGRAM_BOT_TOKEN" and v.strip():
                    return v.strip()
    except Exception:
        pass
    return "8733142640:***"


def send_telegram(token, message):
    """Send one Telegram message in HTML parse mode."""
    chat_id = TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": message.strip(),
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json"
    })
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode())
        if result.get("ok"):
            return True, result["result"]["message_id"]
        desc = result.get("description", "unknown telegram error")
        return False, desc
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"HTTP {e.code}: {body[:200]}"
    except Exception as ex:
        return False, f"Network error: {ex}"


def fetch_market_evaluation(force=False):
    """Call /api/market-evaluation and return parsed JSON.

    Default (force=False) reads from cached DB entry — fast and reliable.
    Set force=True only when no evaluation exists for today, to trigger
    a full Ollama refresh. If Ollama hangs, we fall back gracefully.
    """
    suffix = "?force=true" if force else ""
    url = f"{JARVIS_HUB_URL}/api/market-evaluation{suffix}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode())
        return data
    except urllib.error.HTTPError as e:
        raw = e.read().decode()[:500] if e.fp else ""
        return {"status": "error", "error": f"HTTP {e.code}: {raw}"}
    except Exception as ex:
        # On timeout (20+ seconds), log it but don't block the reporter
        if "timed out" in str(ex).lower() or "timeout" in str(ex).lower():
            return {"status": "error", "error": f"Ollama/api timeout — using cached data"}
        return {"status": "error", "error": str(ex)[:500]}


def fetch_health():
    """Check Jarvis Hub health. Returns dict with 'ok' key on success."""
    url = f"{JARVIS_HUB_URL}/api/health"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get("status") == "ok":
            data["ok"] = True
        return data
    except Exception as ex:
        return {"error": str(ex)}


def format_evaluation(text):
    """Format LLM evaluation text for Telegram HTML delivery."""
    if not text:
        return "\u26a0\ufe0f Market evaluation unavailable \u2014 Ollama timeout?"

    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### ") or stripped.startswith("**TỔ QUAN"):
            clean = stripped.lstrip("#* ").rstrip("*")
            lines.append(f"<b>\u2592 {clean}</b>")
        elif stripped.startswith("## "):
            lines.append(f"<i>{stripped[3:].strip()}</i>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            lines.append(f"\u2022 {stripped[2:].strip()}")
        elif stripped and stripped[0].isdigit() and "." in stripped[:3]:
            lines.append(f"<b>{stripped}</b>")
        else:
            lines.append(stripped)
    return "\n\n".join(lines)


def main():
    print("[EVAL-RPT] Starting market evaluation report...")

    # Step 1: Verify Jarvis Hub health
    health = fetch_health()
    if "ok" not in health and "error" in health:
        today_str = datetime.now().strftime("%d/%m/%Y")
        msg = (
            "<b>\U0001f6a8 JARVIS HUB MARKET EVALUATION</b>\n"
            f"<i>{today_str}</i>\n\n"
            "\u26a0\ufe0f Jarvis Hub dashboard is unavailable.\n"
            f"Health error: {health.get('error', 'unknown')}\n\n"
            "Please ensure Flask dashboard is running on :8100."
        )
        ok, mid = send_telegram(load_telegram_token(), msg)
        print(f"[EVAL-RPT] Alert sent (ok={ok}, msg_id={mid})")
        return

    # Step 2: Fetch evaluation
    data = fetch_market_evaluation()
    status = data.get("status", "unknown")
    
    date_str = data.get("date", "")
    if not date_str:
        date_str = datetime.now().strftime("%d/%m/%Y")
    
    evaluation = (data.get("evaluation", "") or "").strip()

    # Step 3: Build message based on status
    if status == "error":
        msg = (
            "<b>\U0001f6a8 JARVIS HUB MARKET EVALUATION</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"\u274c Error: {data.get('error', 'unknown')}\n\n"
            "Check Jarvis Hub logs or Ollama status."
        )
    elif status == "pending":
        msg = (
             "<b>\U0001f4cb JARVIS HUB MARKET EVALUATION</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"{data.get('message', 'No evaluation generated yet.')}")
    elif evaluation:
        formatted = format_evaluation(evaluation)
        msg = (
            "<b>\U0001f4ca JARVIS HUB MARKET EVALUATION\ud83c\uddfb\ud83c\uddf3</b>\n"
            f"<i>{date_str}</i>\n\n"
            f"{formatted}"
        )
    else:
        msg = (
            "<b>\U0001f4ca JARVIS HUB MARKET EVALUATION</b>\n"
            f"<i>{date_str}</i>\n\n"
            "\u26a0\ufe0f No evaluation generated. Check Ollama connectivity."
        )

    # Step 4: Deliver
    ok, mid = send_telegram(load_telegram_token(), msg)
    print(f"[EVAL-RPT] Delivered (ok={ok}, msg_id={mid})")


if __name__ == "__main__":
    main()
