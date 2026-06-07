#!/usr/bin/env python3
"""
Jarvis Intraday Polling Scanner - Real-time Signal Alerts

Every 15 minutes during market hours (9:15-15:15), scans the watchlist,
detects NEW BUY/SELL signals compared to what was last SENT, and sends
Telegram alerts immediately.

Uses unified_scan.py as the single source of truth — same data pipeline
as scan_reporter so there are no discrepancies between reports.

Pocket Pivot detection on 1-hour candle timeframe.
Schedule: */15 9-15 * * 1-5
"""

import sys
import os
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

# Add script dir to path
script_dir = os.path.dirname(__file__)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from unified_scan import UnifiedScan, SCAN_RESULT_CACHE, _atomic_read, _atomic_write


# -- Telegram config --

def load_telegram_token():
    """Load token the same way as scan_reporter and intelligence."""
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


# -- Telegram Alert --

def send_alert(to: str, chat_id: str, message: str) -> bool:
    """Send one Telegram message (auto-chunks if >3800 chars)."""
    url = f"https://api.telegram.org/bot{to}/sendMessage"
    chunks = []
    current = ""
    blocks = message.split("\n\n")
    for block in blocks:
        if len(current) + len(block) > 3500 and current:
            chunks.append(current.strip())
            current = block
        else:
            current = (current + "\n\n" + block).strip() if current else block
    if current:
        chunks.append(current.strip())

    success_count = 0
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            if result.get("ok"):
                mid = result["result"].get("message_id", "?")
                print(f"[OK] Alert sent ({i+1}/{len(chunks)}, msg_id={mid})")
                success_count += 1
        except Exception as e:
            print(f"[WARN] Telegram chunk {i+1} failed: {e}", file=sys.stderr)
    return success_count > 0


# -- Deduplication Cache --

def load_last_sent():
    """Load the signal states from the last alert that was actually SENT."""
    cached = os.path.expanduser("~/.hermes/jarvis_cache/intraday_last_sent.json")
    if os.path.exists(cached):
        try:
            with open(cached) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_sent(sent_dict):
    """Persist what we just sent so we never resend unchanged signals."""
    cached = os.path.expanduser("~/.hermes/jarvis_cache/intraday_last_sent.json")
    with open(cached, 'w') as f:
        json.dump(sent_dict, f, default=str)


def dedup_against_sent(sent_state, candidate_signals):
    """Filter out signals unchanged since last SENT alert.

    Args:
        sent_state: dict of symbol -> signal from last time we actually sent
        candidate_signals: list of NEW signal dicts to potentially send

    Returns:
        List of signals that have actually changed vs what was last sent.
    """
    filtered = []
    for s in candidate_signals:
        sym = s['symbol']
        last_sent_sig = sent_state.get(sym, {}).get('signal', 'NONE')
        current_sig = s['new_signal']

        if current_sig == last_sent_sig:
            print(f"[DEDUP] {sym}: {current_sig} unchanged vs last send - skipping")
            continue

        filtered.append(s)

    return filtered


# -- Main Polling Function --

def run_poll():
    """Execute one polling cycle: scan all symbols -> detect changes vs sent -> send alerts."""
    now = datetime.now()
    print(f"[Poll] {now.strftime('%H:%M')} scanning with unified pipeline...")

    # Use unified_scan — SAME pipeline as scan_reporter, single source of truth
    unified = UnifiedScan()
    results = unified.full_scan()

    if not results:
        print("[Poll] No data returned from scan engine.")
        return []
    # Build current scan state dict (matching old format)
    current_scan = {}
    for sym, signal_data in results.items():
        if signal_data:
            current_scan[sym] = {
                'signal': signal_data.get('signal', 'NONE'),
                'data': {
                    'latest_price': signal_data.get('latest_price'),
                    'change_percent': None,   # not directly available from signal engine
                    'rsi_14': signal_data.get('rsi'),
                },
                'pivot_info': signal_data.get('pivot_info'),
            }
        else:
            current_scan[sym] = {'signal': 'NONE', 'data': {}, 'pivot_info': None}

    # Detect signals that changed vs last SCAN
    last_scan_cache = _atomic_read(SCAN_RESULT_CACHE)
    new_signals = []

    for sym in results:
        curr_sig = results.get(sym, {}).get('signal', 'NONE') if results.get(sym) else 'NONE'
        last_sig = 'NONE'
        if last_scan_cache and sym in last_scan_cache and last_scan_cache[sym]:
            last_sig = last_scan_cache[sym].get('signal', 'NONE')

        if curr_sig == 'NONE' and last_sig == 'NONE':
            continue
        if curr_sig != last_sig:
            # Build signal dict similar to old format for dedup logic
            curr_data = results.get(sym, {})
            new_signals.append({
                'symbol': sym,
                'old_signal': last_sig,
                'new_signal': curr_sig,
                'data': {
                    'latest_price': curr_data.get('latest_price'),
                    'change_percent': None,
                    'rsi_14': curr_data.get('rsi'),
                },
                'pivot_info': curr_data.get('pivot_info'),
            })

    if not new_signals:
        print("[Poll] No signal changes detected vs. last scan.")
        return []

    # DEDUPLICATION: filter against what was LAST SENT to user
    sent_state = load_last_sent()
    deduped = dedup_against_sent(sent_state, new_signals)

    if not deduped:
        print("[Poll] Signal changes detected but all unchanged since last send - no duplicates.")
        return []

    # Build alert message(s) for deduplicated signals only
    alerts = []
    for s in deduped:
        sym = s['symbol']
        signal_emoji = "\U0001f7e2" if s['new_signal'] == 'BUY' else "\U0001f534"
        old = s['old_signal']
        new_sig = s['new_signal']

        # Header: bold with emoji and signal change info
        if old != 'NONE':
            header_tag = f"{old} \u2192 {new_sig}"
        else:
            header_tag = new_sig
        lines = [f"<b>{signal_emoji} {sym}: {header_tag}</b>"]

        # Price line
        latest_price = s['data'].get('latest_price')
        if latest_price is not None:
            lines.append(f"{signal_emoji} <b>Price:</b> {round(latest_price, 1)} VND")

        # RSI line
        rsi_val = s['data'].get('rsi_14')
        if rsi_val is not None:
            rsi_label = "\u26a0\ufe0f OB" if rsi_val > 70 else "\u2705 OS" if rsi_val < 30 else "\u2014"
            lines.append(f"{signal_emoji} <b>RSI(14):</b> {round(rsi_val, 1)} {rsi_label}")

        # Signal change/detail line
        if old != 'NONE':
            lines.append(f"<b>\u26a1 Change:</b> {old} \u2192 <b>{new_sig}</b>")
        else:
            first = "\U0001f195 First signal detected"
            lines.append(f"{first}: <b>{new_sig}</b>")

        # Pocket Pivot section
        pp = s.get('pivot_info')
        if pp is not None and pp.get('is_pocket_pivot'):
            lines.append("")
            bull_emoji = "\U0001f402"
            bear_emoji = "\U0001f43b"
            pp_dir = "BULLISH " + bull_emoji if pp['pivot_direction'] == 'BUY' else "BEARISH " + bear_emoji
            breakout_val = abs(pp['breakout_pct'])
            break_label = "above resistance" if pp['pivot_direction'] == 'BUY' else "below support"

            lines.append(f"<b>\U0001f6a8 Pocket Pivot 1H \u26a1 {pp_dir}</b>")
            lines.append(f"Breakout: <i>{round(breakout_val, 2)}%</i> ({break_label})")
            lines.append(f"Pivot level: <i>{round(pp['pivot_high'], 1)} VND</i>")
            lines.append(f"Volume: <b>{pp['volume_ratio']:.1f}x</b> avg (last 3 candles)")

        alerts.append("\n".join(lines))

    # Send single combined message — but only if we have something to report
    tg_token = load_telegram_token()
    chat_id = os.environ.get("JARVIS_CHAT_ID", "-1003801745265").strip() or "-1003801745265"

    if not alerts:
        print("[Alert] No non-duplicate alerts after filtering - skipping send.")
        return []

    final_msg = "\n---\n".join(alerts)
    print(f"[Alert] Sending {len(deduped)} unique signal change(s) to Telegram...")

    ok = send_alert(tg_token, chat_id, final_msg)
    if ok:
        # Save what we just sent for dedup comparison next time
        sent_state_for_save = {}
        for s in deduped:
            sym = s['symbol']
            data_entry = {
                'signal': s['new_signal'],
                'latest_price': s['data'].get('latest_price'),
                'rsi_14': s['data'].get('rsi_14'),
            }
            if pp := s.get('pivot_info'):
                data_entry['pivot'] = pp
            sent_state_for_save[sym] = data_entry

        save_sent(sent_state_for_save)
        print("[Alert] Delivered & saved to dedup cache")

    return deduped


# -- Entry Point --

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "poll"

    if arg == "--test":
        print("=== INTRADAY POLL TEST (dry run, sends alerts) ===")
        signals = run_poll()
        print(f"\nResult: {len(signals)} unique signal change(s)", file=sys.stderr)
    elif arg == "--watch":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 900
        print(f"=== STARTED -- polling every {interval}s ===")
        try:
            while True:
                signals = run_poll()
                if signals:
                    print(f"[Watch] {len(signals)} unique alert(s) sent!", file=sys.stderr)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[Watch] Stopped.")
    else:
        print("=== JARVIS INTRADAY SCANNER ===")
        new = run_poll()
        if new:
            print(f"[Done] {len(new)} unique alert(s)", file=sys.stderr)
