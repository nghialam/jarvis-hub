#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Learning Engine Module
Learn from past signals to improve accuracy.

- Record signal history + outcomes (buy/sell/hold)
- Calculate accuracy per indicator type (RSI, MACD, MA Cross, Volume)
- Auto-adjust thresholds daily based on performance
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np


try:
    from config import SIGNAL_HISTORY_FILE
except ImportError:
    SIGNAL_HISTORY_FILE = "/Users/nghialam/jarvis-hub/scripts/trading_bot/signal_history.json"


class LearningEngine:
    """Learn and self-improve from past signals."""

    def __init__(self, history_file=SIGNAL_HISTORY_FILE):
        self.history_file = history_file
        self.signal_history = self._load_history()
        self.rsi_adjustments = {"overbought": 0, "oversold": 0}

    def _load_history(self):
        """Load signal history from JSON file."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("signals", [])
            except (json.JSONDecodeError, IOError):
                pass
        return []

    def _save_history(self):
        """Persist signal history to JSON file."""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump({"signals": self.signal_history}, f, ensure_ascii=False, indent=2)

    def record_signal(self, symbol, signal_data, outcome=None):
        """
        Record a signal + result (if available).

        Args:
            symbol: Stock ticker symbol
            signal_data: Result from SignalEngine.analyze_stock()
            outcome: "win"/"loss"/"neutral"/None
                   (None = signal just created, result not yet known)
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol.upper(),
            "signal_type": signal_data["signal"],
            "confidence": signal_data.get("confidence", 0),
            "price": signal_data.get("latest_price"),
            "rsi": signal_data.get("rsi"),
            "macd": signal_data.get("macd"),
            "stop_loss": signal_data.get("stop_loss"),
            "take_profit": signal_data.get("take_profit"),
            "directions": signal_data.get("directions", []),
            "reasons": signal_data.get("reasons", []),
            "outcome": outcome,
        }

        self.signal_history.append(record)

        # Limit history to last 30 days to avoid bloat
        cutoff = datetime.now() - timedelta(days=30)
        self.signal_history = [
            s for s in self.signal_history
            if datetime.fromisoformat(s["timestamp"]).replace(tzinfo=None) > cutoff
        ]

        # Evaluate and potentially optimize thresholds periodically
        if len(self.signal_history) % 5 == 0:
            self.evaluate_and_optimize()

        self._save_history()

    def evaluate_and_optimize(self):
        """
        Evaluate past signal effectiveness to suggest threshold adjustments.

        Uses last 7 days of data to calculate accuracy per indicator type.
        Adjusts RSI thresholds if consistently wrong signals are being generated.
        """
        cutoff = datetime.now() - timedelta(days=7)

        recent_signals = [
            s for s in self.signal_history
            if datetime.fromisoformat(s["timestamp"]).replace(tzinfo=None) > cutoff
            and s.get("outcome") is not None
        ]

        if len(recent_signals) < 3:
            print("[LEARN] Insufficient data to adjust thresholds.")
            return

        # Calculate accuracy per indicator type
        indicators = ["RSI", "MACD", "MA Cross", "Volume Spike"]
        indicator_stats = {ind: {"total": 0, "correct": 0} for ind in indicators}

        for sig in recent_signals:
            directions = sig.get("directions", [])
            outcome = sig["outcome"]

            if outcome == "win" and len(directions) > 0:
                for d in directions:
                    if "RSI" in d or "rsi" in d.lower():
                        indicator_stats["RSI"]["correct"] += 1
                        indicator_stats["RSI"]["total"] += 1
                    elif "MACD" in d or "macd" in d.lower():
                        indicator_stats["MACD"]["correct"] += 1
                        indicator_stats["MACD"]["total"] += 1
                    else:
                        indicator_stats["MA Cross"]["correct"] += 1
                        indicator_stats["MA Cross"]["total"] += 1

        overall_accuracy = (
            sum(s["correct"] for s in indicator_stats.values())
               / max(sum(s["total"] for s in indicator_stats.values()), 1)
         )

        print(f"[LEARN] Total accuracy: {overall_accuracy:.1%} ({len(recent_signals)} signals)")

        if overall_accuracy < 0.4:
            self.rsi_adjustments["overbought"] -= 2
            self.rsi_adjustments["oversold"] += 2
            print("[LEARN] Low accuracy -> adjusting RSI thresholds")
        elif overall_accuracy > 0.65:
            self.rsi_adjustments["overbought"] += 1
            self.rsi_adjustments["oversold"] -= 1
            print("[LEARN] High accuracy -> tightening RSI thresholds")

    def get_accuracy_report(self):
        """System accuracy report."""
        completed = [s for s in self.signal_history if s.get("outcome")]

        wins = sum(1 for s in completed if s["outcome"] == "win")
        loses = sum(1 for s in completed if s["outcome"] == "loss")
        neutrals = sum(1 for s in completed if s["outcome"] == "neutral")

        by_symbol = {}
        for sig in completed:
            sym = sig["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = {"total": 0, "wins": 0}
            by_symbol[sym]["total"] += 1
            if sig["outcome"] == "win":
                by_symbol[sym]["wins"] += 1

        return {
            "total_signals": len(completed),
            "overall_accuracy": wins / max(len(completed), 1),
            "wins": wins,
            "loses": loses,
            "neutrals": neutrals,
            "accuracy_by_symbol": by_symbol,
            "rsi_adjustments": self.rsi_adjustments,
        }

    def get_recent_signals(self, limit=20):
        """Return last N signals for review."""
        return self.signal_history[-limit:] if self.signal_history else []
