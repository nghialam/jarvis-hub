#!/usr/bin/env python3
"""
JARVIS Daily Scan Reporter
Runs the full watchlist scan, formats it exactly as the sharp summary format,
and posts it to the Gotham News Telegram channel.

Reads watchlist from watchlist.json (supports updates without code changes).
Loads Telegram token same way as jarvis_intelligence.py.
"""

import sys
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# Ensure modules at the same level are importable
script_dir = os.path.dirname(__file__)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from market_data import fetch_stock_data
    from signal_engine import SignalEngine
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)


# ── Telegram config (same source as jarvis_intelligence.py) ──

_TOKEN_CACHE_FILE = os.path.expanduser("~/.hermes/.jarvis_token_cache")


def load_telegram_token():
    """Load Telegram bot token with fallback chain."""
    # 1. Environment variables (direct cron env or standard .env vars)
    for key in ["JARVIS_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        val = os.environ.get(key, "").strip()
        if val:
            return val

    # 2. Cache file (written by jarvis_regression_test.py or manual setup)
    if os.path.exists(_TOKEN_CACHE_FILE):
        with open(_TOKEN_CACHE_FILE) as f:
            cached = f.read().strip()
            if cached and ":" in cached:
                return cached

    # 3. Load from hermes .env file
    env_path = os.path.join(os.path.expanduser("~"), ".hermes", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "TELEGRAM_BOT_TOKEN" and v.strip():
                    return v.strip()

    # 4. Default placeholder (will fail Telegram API - at least we won't crash)
    return "8733142640:***"


def load_watchlist():
    """Load watchlist from JSON file."""
    watchlist_path = os.path.join(os.path.dirname(__file__), "watchlist.json")
    try:
        with open(watchlist_path) as f:
            data = json.load(f)
            stocks = data.get("stocks", [])
            if stocks:
                return stocks
    except Exception as e:
        print(f"[WARN] Could not load watchlist.json: {e}")
    # Fallback: hardcoded list (should never be hit if watchlist.json exists)
    return ["VCI", "VIC", "VCB", "DGW", "FTS", "TCB", "HCM", "PDR", "NLG", "DXG",
            "BMP", "VGI", "FRT", "VIX", "CTD", "MBB", "FPT", "VHM", "PVS", "EVF"]


TELEGRAM_TOKEN = load_telegram_token()

# Telegram chat ID: env var > cron environment (JARVIS_CHAT_ID) > default (Gotham channel for live market scans)
# Note: Hermes uses plain IDs (1670013239) but direct API may need -100 prefix for channels
_DEFAULT_CHAT_IDS = {
     "scan": "1670013239",       # Gotham news channel — live scan reports
     "private": "3801745265",    # Rex's private chat (briefings, intelligence)
}
CHAT_CATEGORY = os.environ.get("JARVIS_CHAT_CATEGORY", "scan")    # default: scan → gotham
# Allow per-run override via script argument or env var
TELEGRAM_CHAT_ID = (os.environ.get("JARVIS_CHAT_ID", "").strip() 
                    or _DEFAULT_CHAT_IDS.get(CHAT_CATEGORY) 
                    or "1670013239")  # fallback: Gotham channel, plain ID


def post_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        result = json.loads(resp.read())
        if result.get("ok"):
            print(f"[OK] Sent to Telegram (msg_id={result['result'].get('message_id')})")
            return True
        else:
            print(f"[WARN] Telegram API error: {result}")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
        except Exception:
            pass
        print(f"[ERROR] Telegram HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        print(f"[ERROR] Telegram network error: {e.reason}")
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
    return False


def split_message(text, max_chars=3800):
    """Split text into Telegram-safe chunks."""
    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) > max_chars * 0.9 and current:
            parts.append(current.strip())
            current = line
        else:
            current = (current + "\n" + line).strip() if current else line
    if current:
        parts.append(current.strip())
    return parts


def send_telegram_chunked(text):
    """Send text to Telegram, splitting into chunks if needed."""
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        post_to_telegram(chunk)


def _fmt_price(data):
    """Format closing price and change for display."""
    price = data.get("latest_price")
    change = data.get("change_percent")
    if price is None:
        return ""
    if change is not None:
        return f"**{price}** VND ({change:+.2f}%)"
    return f"**{price}** VND"


def run_scan():
    watchlist = load_watchlist()

    engine = SignalEngine()
    results = []

    for sym in watchlist:
        try:
            data = fetch_stock_data(sym)
            signal = engine.analyze_stock(data)
            results.append({"symbol": data["symbol"], "data": data, "signal": signal})
        except Exception as e:
            print(f"[WARN] Failed {sym}: {e}")
            results.append({
                "symbol": sym,
                "data": {"latest_price": "?", "change_percent": None,
                         "rsi_14": None, "histogram": "?"},
                "signal": None
            })

    # === Pocket Pivot Highlight Section ===
    pivots_buy = []
    pivots_sell = []

    for r in results:
        sig = r["signal"]
        pv = sig.get("pivot_info") if sig else None
        if pv and pv.get("is_pocket_pivot"):
            entry = (r["symbol"], r["data"], sig)
            if sig["signal"] == "BUY":
                pivots_buy.append(entry)
            elif sig["signal"] == "SELL":
                pivots_sell.append(entry)

    pivots_buy.sort(key=lambda x: float(x[2]["confidence"]), reverse=True)
    pivots_sell.sort(key=lambda x: float(x[2]["confidence"]), reverse=True)

    # === Group signals ===
    buys = [r for r in results if r["signal"] and r["signal"]["signal"] == "BUY"]
    sells = [r for r in results if r["signal"] and r["signal"]["signal"] == "SELL"]
    holds = [r for r in results if not r["signal"] or r["signal"]["signal"] == "HOLD"]

    buys.sort(key=lambda x: float(x["signal"]["confidence"]) if isinstance(x["signal"]["confidence"], (int, float)) else 0, reverse=True)
    sells.sort(key=lambda x: float(x["signal"]["confidence"]) if isinstance(x["signal"]["confidence"], (int, float)) else 0, reverse=True)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"📊 *JARVIS Daily Scan — {now_str}*",
        "",
        f"*{len(results)} stocks scanned | {len(buys + sells)} active signals*",
        "",
    ]

    # Pocket Pivots
    if pivots_buy or pivots_sell:
        pp_lines = []
        for sym, data, sig in (pivots_buy + pivots_sell):
            pp = sig["pivot_info"]
            price_str = _fmt_price(data)
            emoji = "🟢" if sig["signal"] == "BUY" else "🔴"
            pp_lines.append(
                f"{emoji} *{sym}* {price_str}\n"
                f"    Pivot: {pp['pivot_high']} VND ⮕ breakout +{pp['breakout_pct']:.2f}%\n"
                f"    Vol confirm: {pp['volume_ratio']:.1f}x pivot day\n"
                f"    Confidence: {sig['confidence']}%"
            )
        if pp_lines:
            lines.append("*🚨 POCKET PIVOTS DETECTED*")
            lines.extend(pp_lines)
            lines.append("")

    # STRONG BUY (>=90%)
    strong_buys = [b for b in buys if float(b["signal"]["confidence"]) >= 90]
    if strong_buys:
        lines.append("*🔒 STRONGEST BUY (95%+)*")
        for b in strong_buys:
            s = b["signal"]
            data = b["data"]
            price_info = _fmt_price(data)
            reasons = s["reasons"][0][:60].replace("*", "")
            lines.append(f"• {b['symbol']} {price_info} — {reasons}")

    # HIGH CONFIDENCE (75-89%)
    high_buys = [b for b in buys if 75 <= float(b["signal"]["confidence"]) < 90]
    if high_buys:
        lines.append("")
        lines.append("*🔥 HIGH CONFIDENCE BUY (75%+)*")
        for b in high_buys:
            s = b["signal"]
            data = b["data"]
            price_info = _fmt_price(data)
            reasons = s["reasons"][0][:60].replace("*", "")
            lines.append(f"• {b['symbol']} {price_info} — {reasons}")

    # MODERATE (60-74%)
    mod_buys = [b for b in buys if 60 <= float(b["signal"]["confidence"]) < 75]
    if mod_buys:
        lines.append("")
        lines.append("*⚡ MODERATE BUY (60%+)*")
        for b in mod_buys:
            s = b["signal"]
            data = b["data"]
            price_info = _fmt_price(data)
            reasons = s["reasons"][0][:60].replace("*", "")
            if "overbought" in reasons.lower():
                reasons += " ⚠️"
            lines.append(f"• {b['symbol']} {price_info} — {reasons}")

    # SELL
    high_sells = [s for s in sells if float(s["signal"]["confidence"]) >= 70]
    low_sells = [s for s in sells if float(s["signal"]["confidence"]) < 70]
    if high_sells:
        lines.append("")
        lines.append("*📉 SELL — HIGH CONFIDENCE (70%+)*")
        for s_entry in high_sells:
            rs = s_entry["signal"]
            data = s_entry["data"]
            price_info = _fmt_price(data)
            reasons = rs["reasons"][0][:60].replace("*", "")
            if "overbought" in reasons.lower():
                reasons += " ⚠️⚠️"
            elif "oversold" in reasons.lower():
                reasons += " (potential reversal)"
            lines.append(f"• {s_entry['symbol']} {price_info} 🔴 {rs['confidence']}% — {reasons}")

    if low_sells:
        lines.append("")
        lines.append("*📉 SELL — LOW CONFIDENCE (<70%)*")
        for s_entry in low_sells:
            rs = s_entry["signal"]
            data = s_entry["data"]
            price_info = _fmt_price(data)
            reasons = rs["reasons"][0][:60].replace("*", "")
            lines.append(f"• {s_entry['symbol']} {price_info} 🔴 {rs['confidence']}% — {reasons}")

    # HOLD
    if holds:
        lines.append("")
        lines.append("*⚪ NO SIGNAL (Neutral)*")
        for h in holds:
            data = h["data"]
            rsi = data.get("rsi_14")
            macd = data.get("histogram", "?")
            lines.append(f"• {h['symbol']} — RSI: {rsi} | MACD Hist: {macd}")

    # Key observations
    lines.append("")
    buy_count = len(buys)
    sell_count = len(sells)
    # Safe max — returns None if list is empty (already has default=None, but double-check)
    rsi_buy_candidates = [b for b in buys if b["data"].get("rsi_14") is not None]
    max_rsi_buy = max(rsi_buy_candidates, key=lambda x: x["data"]["rsi_14"]) if rsi_buy_candidates else None
    max_vol_candidate = max(results, key=lambda x: (x["data"].get("volume", 0) or 0), default=None)

    lines.append("*🎯 Key Observations*")
    if buy_count > sell_count:
        lines.append(f"• {buy_count} BUY vs {sell_count} SELL — bullish tilt today")
    elif sell_count > buy_count:
        lines.append(f"• {buy_count} BUY vs {sell_count} SELL — bearish tilt today")
    else:
        lines.append(f"• Balanced: {buy_count} BUY vs {sell_count} SELL")

    if max_rsi_buy and max_rsi_buy["data"].get("rsi_14", 0) >= 80:
        lines.append(f"• ⚠️ {max_rsi_buy['symbol']} at RSI {max_rsi_buy['data']['rsi_14']} — extreme overbought, pullback likely")

    if max_vol_candidate and max_vol_candidate["data"].get("volume", 0) and max_vol_candidate["data"].get("avg_volume_10d"):
        vol_ratio = max_vol_candidate["data"]["volume"] / max_vol_candidate["data"]["avg_volume_10d"]
        if vol_ratio > 3:
            lines.append(f"• {max_vol_candidate['symbol']} volume @ {vol_ratio:.1f}x avg — strong institutional flow")

    lines.append("")
    lines.append("_JARVIS Signal Engine runs daily at 8:00, 13:00, 20:00_")

    print(f"[Scan] Loaded watchlist with {len(watchlist)} stocks")
    return "\n".join(lines)


if __name__ == "__main__":
    print("=== JARVIS DAILY SCAN REPORTER ===")
    report = run_scan()
    print(report)
    print("\n--- Sending to Telegram ---")
    send_telegram_chunked(report)
