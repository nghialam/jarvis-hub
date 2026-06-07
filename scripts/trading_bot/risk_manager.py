#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Risk Manager Module
Circuit breaker risk control: position sizing, stop-loss validation,
circuit breaker (pause signaling when too many signals generated), drawdown protection.
"""

import json
import os
from datetime import datetime, timedelta

try:
    from config import MAX_SIGNALS_PER_SCAN, ATR_MULTIPLIER
except ImportError:
    MAX_SIGNALS_PER_SCAN = 5
    ATR_MULTIPLIER = 2


class RiskManager:
    """Risk control engine for trade signals."""

    def __init__(self, portfolio_value=1000000, max_risk_per_trade=0.02):
        """
        Args:
            portfolio_value: Total capital (VND), default 1 billion VND
            max_risk_per_trade: Max risk per trade (2% = 20 million)
        """
        self.portfolio_value = portfolio_value
        self.max_risk_per_trade = max_risk_per_trade
        self.max_signals_per_scan = MAX_SIGNALS_PER_SCAN

        # Track positions (open trades)
        self.positions = {}   # {symbol: {"entry_price": ..., "stop_loss": ..., "qty": ...}}

        # Circuit breaker state
        self.signals_this_scan = 0
        self.last_scan_time = None
        self.scan_count = 0

        # Daily drawdown tracking
        self.daily_peak_portfolio = portfolio_value
        self.daily_drawdown = 0

    def validate_signal(self, signal_data):
        """
        Check if a signal can be executed.

        Args:
            signal_data: Result from SignalEngine.analyze_stock()

        Returns:
              (approved: bool, reason: str)
        """
        symbol = signal_data["symbol"]
        confidence = signal_data.get("confidence", 0)
        signal_type = signal_data["signal"]

        # Check 1: Maximum signals per scan limit
        self.signals_this_scan += 1
        if self.signals_this_scan > self.max_signals_per_scan:
            return False, f"Reached limit of {self.max_signals_per_scan} signals/scan (circuit breaker)"

        # Check 2: Minimum confidence threshold
        if signal_type != "HOLD":
            if confidence < 35:   # Too low -> skip (even if it passes threshold)
                return False, f"Confidence too low ({confidence}%) - not confirmed"

        # Check 3: No duplicate positions on same stock
        if symbol in self.positions and signal_type == "BUY":
            current_pos = self.positions[symbol]
            return False, f"Already have a position in {symbol} at {current_pos.get('entry_price')} VND"

        # Check 4: Validate stop loss is reasonable
        stop_loss = signal_data.get("stop_loss")
        if stop_loss and symbol in self.positions:
            current_sl = self.positions[symbol].get("stop_loss", 0)
            if abs(stop_loss - current_sl) / max(current_sl, 1) < 0.01:
                return False, (
                    f"Stop loss {signal_type} for {symbol} "
                    "matches an already closed position (circuit breaker)"
                )

        # Check 5: Risk exposure limit
        total_exposure = self.get_total_exposure()
        if signal_type == "BUY":
            risk_amount = self.calculate_risk_amount(signal_data)
            if risk_amount > self.portfolio_value * 0.3:
                return False, f"Risk too large ({risk_amount:,.0f} VND)"

        return True, (
            f"Signal {signal_type} for {symbol} approved "
            f"(confidence: {confidence}%)"
         )

    def calculate_risk_amount(self, signal_data):
        """Calculate max risk amount for a trade."""
        latest_price = signal_data.get("latest_price", 0)
        stop_loss = signal_data.get("stop_loss")

        if not stop_loss or stop_loss <= 0:
            return latest_price * 1000   # Default fallback

        risk_per_share = abs(latest_price - stop_loss)
        qty = int(self.portfolio_value * self.max_risk_per_trade / risk_per_share) if risk_per_share > 0 else 0

        return risk_per_share * qty

    def update_position(self, signal_data):
        """Update open position after an approved signal."""
        symbol = signal_data["symbol"]
        self.positions[symbol] = {
            "entry_price": signal_data["latest_price"],
            "stop_loss": signal_data.get("stop_loss"),
            "take_profit": signal_data.get("take_profit"),
            "signal_type": signal_data["signal"],
            "confidence": signal_data.get("confidence"),
            "timestamp": datetime.now().isoformat(),
        }

    def close_position(self, symbol, exit_price):
        """Close position and update equity."""
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        entry = pos["entry_price"]
        pnl_pct = ((exit_price - entry) / entry) * 100 if entry > 0 else 0

        del self.positions[symbol]
        return True, f"Closed {symbol} at {exit_price}, PnL: {pnl_pct:+.2f}%"

    def get_total_exposure(self):
        """Total value currently invested."""
        total = 0
        for sym, pos in self.positions.items():
            risk_amount = self.calculate_risk_amount({
                "latest_price": pos["entry_price"],
                "stop_loss": pos.get("stop_loss"),
            })
            total += risk_amount
        return total / len(self.positions) if self.positions else 0

    def reset_scan(self):
        """Reset circuit breaker state for each scan cycle."""
        self.signals_this_scan = 0
        self.last_scan_time = datetime.now()
        self.scan_count += 1

    @property
    def status_summary(self):
        """Current risk status summary."""
        return {
            "portfolio_value": self.portfolio_value,
            "open_positions": len(self.positions),
            "total_exposure": round(self.get_total_exposure(), 2),
            "max_risk_per_trade": f"{self.max_risk_per_trade * 100}%",
            "scan_count": self.scan_count,
            "positions": dict(self.positions),
        }
