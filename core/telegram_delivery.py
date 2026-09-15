"""
core/telegram_delivery.py - TelegramDeliveryService (Phase 1.13)

Sends market intelligence briefs and alerts to Telegram.
Uses openclaw as primary method, Telegram Bot API as fallback.
JH3.0: Non-blocking, resilient to failures, circuit-breaker aware.
"""

import os
import json
import time
import socket
from datetime import datetime
from typing import Dict, List, Optional

log = None


def _get_logger():
    global log
    if log is None:
        try:
            from core.logging_config import get_logger
            log = get_logger("TELEGRAM")
        except Exception:
            log = _NullLogger()
    return log


class _NullLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


# Circuit breaker state for Telegram delivery
_telegram_cb_state = "closed"
_telegram_cb_failures = 0
_telegram_cb_last_failure = 0


class TelegramDeliveryService:
    """Service for sending messages to Telegram."""
    
    def __init__(self, chat_id: Optional[str] = None, bot_token: Optional[str] = None):
        self.chat_id = chat_id or os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "16700013239")
        self.bot_token = bot_token or os.environ.get("JARVIS_BOT_TOKEN", "")
        self.openclaw_path = os.environ.get("OPENCLAW_PATH", "/opt/homebrew/bin/openclaw")
        self.use_bot_api = self.bot_token is not None and len(self.bot_token) > 10
        self.delivered_count = 0
        self.failed_count = 0
    
    def send_brief(self, market_brief: str, sentiment_dist: Dict, articles: List[Dict]) -> bool:
        """Send a market intelligence brief to Telegram."""
        _get_logger().info("Sending Telegram brief to %s", self.chat_id)
        
        # Circuit breaker check
        if self._is_circuit_breaker_open():
            _get_logger().warning("Telegram circuit breaker open, skipping delivery")
            return False
        
        try:
            msg = self._build_brief_message(market_brief, sentiment_dist, articles)
            return self._send_message(msg)
        except Exception as e:
            _get_logger().error("Telegram brief delivery failed: %s", e)
            self._record_failure()
            return False
    
    def send_alert(self, symbol: str, signal: str, reason: str, price: float = None) -> bool:
        """Send a trading alert to Telegram."""
        _get_logger().info("Sending Telegram alert: %s %s", symbol, signal)
        
        if self._is_circuit_breaker_open():
            return False
        
        try:
            emoji = {"STRONG_BUY": "🟢", "BUY": "🟩", "HOLD": "⬜", 
                     "SELL": "🟧", "STRONG_SELL": "🔴"}.get(signal, "⚠️")
            
            msg = (
                f"*{emoji} TRADING ALERT*\n"
                f"*Symbol:* {symbol}\n"
                f"*Signal:* {signal}\n"
            )
            if price:
                msg += f"*Price:* {price:,.2f}\n"
            msg += f"*Reason:* {reason}\n"
            msg += f"*Time:* {datetime.now().strftime('%H:%M:%S')} SGT"
            
            return self._send_message(msg)
        except Exception as e:
            _get_logger().error("Telegram alert delivery failed: %s", e)
            self._record_failure()
            return False
    
    def send_error(self, error_type: str, message: str) -> bool:
        """Send an error notification to Telegram."""
        msg = (
            f"*⚠️ JARVIS HUB ERROR*\n"
            f"*Type:* {error_type}\n"
            f"*Message:* {message}\n"
            f"*Time:* {datetime.now().strftime('%H:%M:%S')} SGT"
        )
        return self._send_message(msg)
    
    def _build_brief_message(self, brief: str, sentiment: Dict, articles: List[Dict]) -> str:
        """Build Telegram message from market intelligence data."""
        bull = sentiment.get("Bullish", 0)
        bear = sentiment.get("Bearish", 0)
        neu = sentiment.get("Neutral", 0)
        total = sentiment.get("total", bull + bear + neu)
        
        msg = f"*📊 MARKET INTELLIGENCE BRIEF*\n"
        msg += f"*Period:* {datetime.now().strftime('%Y-%m-%d %H:%M')} SGT\n\n"
        msg += f"*Sentiment:*\n"
        msg += f"🟢 Bullish: {bull}\n"
        msg += f"🔴 Bearish: {bear}\n"
        msg += f"⚪ Neutral: {neu}\n"
        msg += f"📈 Total: {total}\n\n"
        
        # Add brief (truncated for Telegram's 4096 char limit)
        msg += f"*Brief:*\n\n{brief[:2000]}"
        
        # Top signals
        bullish = [a for a in articles if a.get("sentiment") == "Bullish"][:3]
        bearish = [a for a in articles if a.get("sentiment") == "Bearish"][:3]
        
        if bullish:
            msg += "\n\n*🟢 Top Bullish:*\n"
            msg += "\n".join(f"• {a.get('title', '?')[:80]}" for a in bullish)
        
        if bearish:
            msg += "\n\n*🔴 Top Bearish:*\n"
            msg += "\n".join(f"• {a.get('title', '?')[:80]}" for a in bearish)
        
        return msg[:4000]  # Telegram limit
    
    def _send_message(self, text: str) -> bool:
        """Send message via openclaw or Telegram Bot API."""
        # Method 1: openclaw
        try:
            import subprocess
            cmd = [self.openclaw_path, "send", "--chat-id", self.chat_id, "--text", text]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                self._record_success()
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Method 2: Telegram Bot API
        if self.use_bot_api:
            try:
                import requests
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"},
                    timeout=15
                )
                if resp.status_code == 200:
                    self._record_success()
                    return True
            except Exception as e:
                _get_logger().error("Telegram Bot API failed: %s", e)
        
        self._record_failure()
        return False
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker should block requests."""
        global _telegram_cb_state, _telegram_cb_failures, _telegram_cb_last_failure
        
        now = time.time()
        
        if _telegram_cb_state == "closed":
            if _telegram_cb_failures >= 5:
                _telegram_cb_state = "open"
                _telegram_cb_last_failure = now
                _get_logger().error("Telegram circuit breaker OPENED (5 failures)")
                return False  # Allow one more try
        
        elif _telegram_cb_state == "open":
            if now - _telegram_cb_last_failure < 300:  # 5 min cooldown
                return True
            else:
                _telegram_cb_state = "half-open"
                _get_logger().info("Telegram circuit breaker HALF-OPEN")
        
        elif _telegram_cb_state == "half-open":
            _telegram_cb_state = "closed"
            _telegram_cb_failures = 0
            _get_logger().info("Telegram circuit breaker CLOSED (recovered)")
        
        return False
    
    def _record_success(self):
        global _telegram_cb_state, _telegram_cb_failures
        _telegram_cb_state = "closed"
        _telegram_cb_failures = 0
        self.delivered_count += 1
    
    def _record_failure(self):
        global _telegram_cb_failures
        _telegram_cb_failures += 1
        self.failed_count += 1
    
    def get_stats(self) -> Dict:
        """Get service statistics."""
        return {
            "delivered": self.delivered_count,
            "failed": self.failed_count,
            "chat_id": self.chat_id,
            "using_bot_api": self.use_bot_api
        }


# Singleton instance
_telegram_service = None


def get_telegram_service() -> TelegramDeliveryService:
    """Get or create TelegramDeliveryService singleton."""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramDeliveryService()
    return _telegram_service
