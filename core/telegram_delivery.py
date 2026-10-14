"""
core/telegram_delivery.py - TelegramDeliveryService (Phase 1.13)

Sends market intelligence briefs and alerts to Telegram.
Uses openclaw as primary method, Telegram Bot API as fallback.
JH3.0: Non-blocking, resilient to failures, circuit-breaker aware.
Dead-letter queue with exponential backoff retry logic added.
"""

import os
import json
import time
import socket
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque

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


# ──────────────────────────────────────────────
# Circuit breaker state (module-level)
# ──────────────────────────────────────────────
_telegram_cb_state = "closed"
_telegram_cb_failures = 0
_telegram_cb_last_failure = 0

# ──────────────────────────────────────────────
# Dead-letter queue for failed deliveries
#   Tracks: chat_id, message_text, signal/symbol (if any), retry_count, last_attempt, delivery_type
#   Alert on admin when all retries exhausted (after 3rd failure / 4th total attempt)
# ──────────────────────────────────────────────
_DEAD_LETTER = deque(maxlen=50)  # ring buffer of failed deliveries
_DEATH_ALERT_SENT = set()        # chat_ids for which we already sent death alert in current session


def _dlq_push(chat_id: str, text: str, delivery_type: str, symbol: Optional[str] = None) -> Dict:
    """Push a failed delivery onto the dead-letter queue. Returns the record."""
    record = {
        "chat_id": chat_id,
        "message": text,
        "delivery_type": delivery_type,
        "symbol": symbol,
        "retry_count": 0,
        "last_attempt": datetime.now().isoformat(),
    }
    _DEAD_LETTER.append(record)
    return record


def _dlq_retry(chat_id: str, text: str, delivery_type: str = "unknown", symbol: Optional[str] = None) -> bool:
    """Attempt a retry for a message that has been in the DLQ.

    Exponential backoff delays before retrying:
      1st retry → wait 30s after last failure
      2nd retry → wait 90s after last failure
      3rd (final) retry → wait 5 min after last failure
    After the 3rd retry also fails → alert via DLQ.

    Returns True if a retry attempt was launched (regardless of delivery outcome),
          False if still cooling down for backoff window.
    """
    # Find the most recent entry for this chat_id / type
    best_idx = None
    for i in range(len(_DEAD_LETTER) - 1, -1, -1):
        rec = _DEAD_LETTER[i]
        if rec.get("chat_id") == chat_id and rec.get("delivery_type") == delivery_type:
            best_idx = i
            break

    # If no prior entry or all retries exhausted → alert admin
    if best_idx is None or _DEAD_LETTER[best_idx]["retry_count"] >= 3:
        _alert_admin_dead_letter(chat_id, delivery_type, symbol, text)
        # Mark as exhausted so we don't keep re-alerting the same chat+type combo too often
        key = (chat_id, delivery_type)
        if key not in _DEATH_ALERT_SENT:
            _DEATH_ALERT_SENT.add(key)
        return False  # no more retries available

    rec = _DEAD_LETTER[best_idx]
    last_ts = datetime.fromisoformat(rec["last_attempt"]).timestamp()
    now = time.time()
    elapsed = now - last_ts

    # Exponential backoff: 30s → 90s → 300s (5 min)
    delays = [30, 90, 300]
    attempts_so_far = rec["retry_count"]
    required_wait = delays[min(attempts_so_far, len(delays) - 1)]

    if elapsed < required_wait:
        _get_logger().debug(
            "DLQ backoff: %s/%s retries elapsed %.1fs / need %.0fs",
            rec["retry_count"], 3, elapsed, required_wait,
        )
        return False  # still cooling down

    # Enough time has passed — bump retry count and attempt again
    rec["retry_count"] += 1
    _get_logger().info(
        "DLQ retry: message from %s (%s), attempt #%d after %.0fs wait",
        chat_id, delivery_type, rec["retry_count"], elapsed,
    )
    return True


def _alert_admin_dead_letter(chat_id: str, delivery_type: str, symbol: Optional[str], text: str):
    """Build an admin alert for a delivery that exhausted all retries.

    Sends via a dedicated admin channel (JARVIS_TELEGRAM_ADMIN_CHAT_ID) or falls
    back to the regular chat ID. If no admin channel is configured the alert goes
    to the normal output logger at ERROR level so it isn't lost.

    Avoids duplicate alerts per session by tracking _DEATH_ALERT_SENT set keyed on
    (chat_id, delivery_type).
    """
    # Prevent repeated alerts in same session
    key = (chat_id, delivery_type)
    if key in _DEATH_ALERT_SENT:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert_text = f"*🚨 DEAD LETTER — ALL RETRIES EXHAUSTED*\\n" \
                 f"*Chat:* `{chat_id}`\\n" \
                 f"*Type:* {delivery_type}"
    if symbol:
        alert_text += f"\\n*Symbol:* {symbol}\\n"
    alert_text += f"\\n*Failed at:* {now_str} SGT\\n" \
                  f"*Message preview:* `{text[:150]}`...\\n" \
                  f"*See DLQ:* call get_delivery_stats() for full details"

    admin_id = os.environ.get("JARVIS_TELEGRAM_ADMIN_CHAT_ID", "")
    if admin_id and len(admin_id) > 5:
        _get_logger().warning(
            "Dead-letter alert → admin chat %s: %s retries exhausted",
            admin_id, delivery_type,
        )
        # Attempt to deliver via the same service targeting admin channel
        tmp_svc = TelegramDeliveryService(chat_id=admin_id)
        tmp_svc._send_message(alert_text)
    else:
        _get_logger().error(
            "DEAD LETTER — %s retries exhausted for chat %s [%s]:\n%s",
            3, chat_id, delivery_type, text[:500],
        )

    _DEATH_ALERT_SENT.add(key)


# ──────────────────────────────────────────────
# Exponential backoff helpers
# ──────────────────────────────────────────────

def _apply_backoff(retry_index: int):
    """Sleep for exponential-backoff delay based on retry attempt number (0-based).

    Delays: 30s, 90s, 5min — corresponding to first/second/third retry.
    """
    delays = [30, 90, 300]
    idx = min(retry_index, len(delays) - 1)
    _get_logger().info("Backoff sleep: %.0fs (attempt #%d)", delays[idx], retry_index + 1)
    time.sleep(delays[idx])


# ──────────────────────────────────────────────
# TelegramDeliveryService
# ──────────────────────────────────────────────

class TelegramDeliveryService:
    """Service for sending messages to Telegram."""

    # Circuit breaker thresholds — increase to 5 so brief TG outages don't trip cascading failures.
    FAILURE_THRESHOLD = 5       # failures before circuit opens
    RECOVERY_WINDOW = 60        # seconds between half-open probe (circuit breaker cooldown)

    def __init__(self, chat_id: Optional[str] = None, bot_token: Optional[str] = None):
        self.chat_id = chat_id or os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "16700013239")
        self.bot_token = bot_token or os.environ.get("JARVIS_BOT_TOKEN", "")
        self.openclaw_path = os.environ.get("OPENCLAW_PATH", "/opt/homebrew/bin/openclaw")
        self.use_bot_api = self.bot_token is not None and len(self.bot_token) > 10
        self.delivered_count = 0
        self.failed_count = 0

    # ── Public API (signatures unchanged) ────────────

    def send_brief(self, market_brief: str, sentiment_dist: Dict, articles: List[Dict]) -> bool:
        """Send a market intelligence brief to Telegram."""
        _get_logger().info("Sending Telegram brief to %s", self.chat_id)

        if self._is_circuit_breaker_open():
            _get_logger().warning("Telegram circuit breaker open, skipping delivery")
            return False

        try:
            msg = self._build_brief_message(market_brief, sentiment_dist, articles)
            success = self._deliver_with_retry(msg, delivery_type="brief", symbol=None)
            if not success:
                _get_logger().error("Telegram brief delivery failed")
                self._record_failure()
            return success
        except Exception as e:
            _get_logger().error("Telegram brief delivery exception: %s", e)
            self._record_failure()
            return False

    def send_alert(self, symbol: str, signal: str, reason: str, price: float = None) -> bool:
        """Send a trading alert to Telegram."""
        _get_logger().info("Sending Telegram alert: %s %s", symbol, signal)

        if self._is_circuit_breaker_open():
            return False

        try:
            emoji = {
                "STRONG_BUY": "🟢", "BUY": "🟩", "HOLD": "⬜",
                "SELL": "🟧", "STRONG_SELL": "🔴",
            }.get(signal, "⚠️")

            msg = (
                f"*{emoji} TRADING ALERT*\n"
                f"*Symbol:* {symbol}\n"
                f"*Signal:* {signal}\n"
            )
            if price:
                msg += f"*Price:* {price:,.2f}\n"
            msg += f"*Reason:* {reason}\n"
            msg += f"*Time:* {datetime.now().strftime('%H:%M:%S')} SGT"

            success = self._deliver_with_retry(msg, delivery_type="alert", symbol=symbol)
            if not success:
                _get_logger().error("Telegram alert delivery failed")
                self._record_failure()
            return success
        except Exception as e:
            _get_logger().error("Telegram alert delivery exception: %s", e)
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
        success = self._deliver_with_retry(msg, delivery_type="error", symbol=None)
        if not success:
            _get_logger().error("Telegram error delivery failed")
            self._record_failure()
        return success

    # ── Internal helpers ─────────────────────────────

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

    def _deliver_with_retry(self, text: str, delivery_type: str = "unknown", symbol: Optional[str] = None) -> bool:
        """Send message with exponential backoff retry logic.

        - Initial attempt + up to 3 retries (5 min backoff on final).
        - After 3rd retry also fails → push to dead-letter queue & alert admin.
        - Uses openclaw first, Telegram Bot API as fallback within each attempt.
        """
        max_retries = 3

        for attempt in range(max_retries + 1):
            if attempt > 0:
                _apply_backoff(attempt - 1)
                _get_logger().info("Retry attempt %d/%d for delivery_type=%s", attempt, max_retries, delivery_type)

            success = self._send_message(text)

            if success:
                return True

            # Record the failure (for circuit breaker + DLQ tracking)
            self.failed_count += 1
            _get_logger().warning(
                "Delivery attempt %d/%d failed for %s", attempt + 1, max_retries + 1, delivery_type,
            )

        # All retries exhausted → dead-letter
        _dlq_push(self.chat_id, text, delivery_type, symbol)
        _alert_admin_dead_letter(self.chat_id, delivery_type, symbol, text)
        return False

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
                    timeout=15,
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
            if _telegram_cb_failures >= self.FAILURE_THRESHOLD:
                _telegram_cb_state = "open"
                _telegram_cb_last_failure = now
                _get_logger().error("Telegram circuit breaker OPENED (%d failures)", self.FAILURE_THRESHOLD)
                return False  # Allow one more try

        elif _telegram_cb_state == "open":
            if now - _telegram_cb_last_failure < self.RECOVERY_WINDOW:
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

    # ── Stats / DLQ queries ────────────────────────

    def delivery_stats(self) -> Dict:
        """Return delivery statistics with success/failure counts and recent failures.

        Returns keys: delivered, failed, chat_id, using_bot_api, circuit_breaker_state,
                      dlq_count, dlq_recent (list of last 10 dead-letter entries).
        """
        return {
            "delivered": self.delivered_count,
            "failed": self.failed_count,
            "chat_id": self.chat_id,
            "using_bot_api": self.use_bot_api,
            "circuit_breaker_state": _telegram_cb_state,
            "circuit_breaker_failures": _telegram_cb_failures,
            "dlq_count": len(_DEAD_LETTER),
            "dlq_recent": list(_DEAD_LETTER)[-10:],  # last 10 entries
        }

    def get_stats(self) -> Dict:
        """Legacy alias for delivery_stats() — preserved for backward compatibility."""
        return self.delivery_stats()


# ──────────────────────────────────────────────
# Module-level convenience
# ──────────────────────────────────────────────

# Singleton instance
_telegram_service = None


def get_telegram_service() -> TelegramDeliveryService:
    """Get or create TelegramDeliveryService singleton."""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramDeliveryService()
    return _telegram_service
