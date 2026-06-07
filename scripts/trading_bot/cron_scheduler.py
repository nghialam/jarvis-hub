#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Cron Scheduler
Tự động chạy trading bot trong các khung giờ cố định.

Usage:
    python3 cron_scheduler.py              # Chay mot lan (single scan)  
    python3 cron_scheduler.py --list       # Xem watchlist
    python3 cron_scheduler.py --add VCI    # Them code vao watchlist
"""

import subprocess
import sys
import os
from datetime import datetime, timedelta

BASE_DIR = "/Users/nghialam/jarvis-hub/scripts/trading_bot"
BOT_SCRIPT = os.path.join(BASE_DIR, "trading_bot.py")

TRADING_HOURS_VN = {
     "open": 8,       # 8:00 AM
     "close": 14.5,   # 14:30 PM (2:30 PM)
 }

# VN Weekdays: Mon-Fri (0-4), skip Saturday/Sunday
def is_trading_time():
    now = datetime.now()
    
    if now.weekday() >= 5:   # Weekend
        return False
    
    current_hour = now.hour + now.minute / 60.0  
    return TRADING_HOURS_VN["open"] <= current_hour < TRADING_HOURS_VN["close"]

def run_signal_scan():
    """Chay mot lan quet signal."""
    print(f"[CRON] {datetime.now().isoformat()} - Running signal scan...")
    
    result = subprocess.run(
        [sys.executable, BOT_SCRIPT, "--single-scan"],
         cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=300   # 5 minutes max per scan
    )
    
    if result.returncode != 0:
        print(f"[CRON] Error: {result.stderr}")
        
     # Print key info from stdout for reporting
    for line in result.stdout.split("\n"):
         if "active signals" in line or "JARVIS" in line or "Scan" in line:
             print(f"[CRON]   {line.strip()}")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    
    # CLI commands (pass to trading_bot.py)
    if cmd == "--list":
        subprocess.run([sys.executable, BOT_SCRIPT, "--list"])
    elif cmd == "--add" and len(sys.argv) >= 3:
        subprocess.run([sys.executable, BOT_SCRIPT, "--add", sys.argv[2].upper()])
    elif cmd == "--remove" and len(sys.argv) >= 3:
        subprocess.run([sys.executable, BOT_SCRIPT, "--remove", sys.argv[2].upper()])
    else:
        # Default behavior: check if trading hours, then scan
         if is_trading_time():
            run_signal_scan()
         else:
            print("[CRON] Outside VN trading hours (8:00-14:30 Mon-Fri). Skipping scan.")

if __name__ == "__main__":
    main()
