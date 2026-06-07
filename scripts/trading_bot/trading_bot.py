#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Main Orchestrator Module

Chay lien tuc trong gio giao dich, quet danh sach theo doi,
phan tich indicators, phat hien tin hieu Buy/Sell va gui ve Telegram.

Workflow:
1. Khoi dong -> load watchlist
2. Trong Gio GD (8:00-14:30): scan each 5 minutes
3. Get real-time data from VNStock for all symbols
4. Calculate indicators -> generate signals
5. Risk manager validates and accepts/rejects signals
6. If approved -> send to Telegram + log it
7. Next day: Learning engine auto-adjusts thresholds

Usage: python3 trading_bot.py [--dry-run] [--single-scan]
"""

import time
import sys
from datetime import datetime, timedelta


try:
    from config import (
        TRADING_HOURS_OPEN,
        TRADING_HOURS_CLOSE,
        SCANNER_INTERVAL,
        MIN_CONFIDENCE_THRESHOLD,
        MAX_SIGNALS_PER_SCAN,
        WATCHLIST_FILE,
    )
except ImportError:
    TRADING_HOURS_OPEN = 8
    TRADING_HOURS_CLOSE = 14.5
    SCANNER_INTERVAL = 300

from watchlist_mgr import load_watchlist, add_stock, remove_stock, list_stocks
from market_data import fetch_stock_data
from signal_engine import SignalEngine
from risk_manager import RiskManager
from learning_engine import LearningEngine
from telegram_sender import TelegramSender


class TradingBot:
    """Orchestrator chinh cho he thong signal engine."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run

        # Initialize components
        print("[JARVIS] Loading watchlist...")
        self.watchlist_data = load_watchlist()
        self.watchlist_symbols = [s.upper().strip() for s in self.watchlist_data["stocks"]]

        if not self.watchlist_symbols:
            print("[JARVIS] Watchlist rong. Hay them danh sach vao watchlist.json.")
            sys.exit(1)

        self.signal_engine = SignalEngine()
        self.risk_mgr = RiskManager()
        self.telegram = TelegramSender()

        if not dry_run:
            self.learning = LearningEngine()
        else:
            self.learning = None   # Don't learn in dry-run mode

    def _is_trading_hours(self):
        """Kiem tra co phai Gio giao dich khong (Gio VN)."""
        now = datetime.now()
        current_hour = now.hour + now.minute / 60.0
        return TRADING_HOURS_OPEN <= current_hour < TRADING_HOURS_CLOSE

    def run(self, loop=True):
        """Chay he thong (loop hoac chay mot lan)."""
        print("[JARVIS] === STARTING JARVIS TRADING SIGNAL ENGINE ===")
        print(f"[JARVIS] Watchlist: {', '.join(self.watchlist_symbols)} ({len(self.watchlist_symbols)} symbols)")
        print(f"[JARVIS] Trading hours: {int(TRADING_HOURS_OPEN):02d}:00 - {int(TRADING_HOURS_CLOSE):02d}:30")

        if not self._is_trading_hours():
            if loop:
                print("[JARVIS] Khong phai Gio giao dich. Waiting for next trading session.")

            # Scan once anyway to prep data for next scan
            self.run_once()

        while loop:
            time.sleep(5)   # Brief wait before checking hours

            if not self._is_trading_hours():
                continue   # Skip non-trading hours

            print(f"[JARVIS] === SCAN {datetime.now().strftime('%H:%M')} ===")
            scanned_count = self.run_once()

            await_time = SCANNER_INTERVAL - int((datetime.now().timestamp() % SCANNER_INTERVAL))
            if await_time < 0:
                await_time = SCANNER_INTERVAL - 60

            print(f"[JARVIS] Next scan in {await_time}s...")
            time.sleep(await_time)

    def run_once(self):
        """Chay mot lan quet duy nhat."""
        # Reset per-scan state for Risk Manager
        self.risk_mgr.reset_scan()

        results = []
        skipped = 0

        for symbol in self.watchlist_symbols:
            try:
                print(f"    [{symbol}]", end=" ", flush=True)

                # Fetch real-time data
                data = fetch_stock_data(symbol)

                if not data or data["status"] == "error":
                    print(f"FAILED - {data.get('status_msg', 'unknown')}")
                    skipped += 1
                    continue

                if data["status"] == "partial":
                    print("PARTIAL data only")

                # Analyze for signals
                signal = self.signal_engine.analyze_stock(data)

                if signal and signal["signal"] != "HOLD":
                    # Risk manager validation
                    approved, message = self.risk_mgr.validate_signal(signal)

                    if approved:
                        print(f"-> {message}")
                        results.append(signal)

                        # Record in learning engine
                        if self.learning and not self.dry_run:
                            self.learning.record_signal(symbol, signal)

                        # Send to Telegram
                        try:
                            if signal.get("signal") == "WATCH":
                                print("    Watch signal - monitor only")
                            else:
                                self.telegram.send_signal(signal)
                                print(f"    {signal['signal']} sent to Telegram!")
                        except Exception as e:
                            print(f"  Telegram failed: {e}")
                    else:
                        print(f"SKIPPED - {message}")
                        skipped += 1
                else:
                    print("No actionable signal")

            except Exception as e:
                print(f"ERROR: {e}")
                continue

        if results:
            print(f"\n[JARVIS] {len(results)} active signals detected!")
        else:
            print("\n[JARVIS] No actionable signals this scan.")

        return len(results)


# ==========================================
# CLI Entry Point
# ==========================================

def main():
    """Parse CLI args and start the trading bot."""
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Trading Signal Engine")
    args, remaining = parser.parse_known_args()

    # Check if running with arguments for adding/removing symbols
    if "--add" in sys.argv:
        symbol_idx = sys.argv.index("--add") + 1
        symbol = sys.argv[symbol_idx].upper()
        if add_stock(symbol):
            print(f"Successfully added {symbol}")

    elif "--remove" in sys.argv:
        sym_idx = sys.argv.index("--remove") + 1
        symbol = sys.argv[sym_idx].upper()
        remove_stock(symbol)

    elif "--list" in sys.argv:
        print(list_stocks())

    elif "--clear" in sys.argv:
        print("Clearing watchlist? (Cannot be undone)")
        from watchlist_mgr import clear_watchlist
        # Uncomment when ready: clear_watchlist()
        sys.exit(0)

    elif "--test-telegram" in sys.argv:
        tg = TelegramSender()   # Test sending message to Telegram channel
        tg.send_signal({
            "symbol": "TEST",
            "latest_price": 100.0,
            "signal": "BUY",
            "confidence": 85.0,
            "reasons": ["Test signal - system is operational"],
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "rsi": 55.0,
            "macd": 0.123,
        })
        sys.exit(0)

    elif "--history" in sys.argv:
        le = LearningEngine()
        print("=== Recent Signals ===")
        signals = le.get_recent_signals(limit=20)
        for sig in signals:
            emoji = "GREEN_CIRCLE" if sig["signal_type"] == "BUY" else ("RED_CIRCLE" if sig["signal_type"] == "SELL" else "WHITE_CIRCLE")
            print(f"{emoji} {sig['symbol']} | {sig['signal_type']} | Conf: {sig.get('confidence', 0):.1f}% | {sig.get('outcome', 'pending')} | {sig['timestamp'][:19]}")
        sys.exit(0)

    elif "--accuracy" in sys.argv:
        le = LearningEngine()
        report = le.get_accuracy_report()
        print("=== Accuracy Report ===")
        for k, v in report.items():
            if k != "accuracy_by_symbol":
                print(f"    {k}: {v}")
        sys.exit(0)

    else:
        # Default: run the trading bot
        dry_run = "--dry-run" in sys.argv
        single_scan = "--single-scan" in sys.argv

        bot = TradingBot(dry_run=dry_run)

        if single_scan:
            bot.run_once()      # Single scan only
        else:
            bot.run(loop=True)    # Continuous loop


if __name__ == "__main__":
    main()
