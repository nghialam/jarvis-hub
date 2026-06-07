#!/usr/bin/env python3
"""
JARVIS Trading Signal Engine - Telegram Sender Module
Sends trading signals and results to Telegram channel (Gotham News).

Message format uses bullet points, no tables for better readability on Telegram.
"""

import json
import urllib.request


try:
    from config import BOT_TOKEN, TELEGRAM_CHAT_ID, SIGNAL_EMOJIS
except ImportError:
    BOT_TOKEN = "8733142640:AAHs32LJp2bdJhbjYlVCaOYWwMl0ERZ0rQk"
    TELEGRAM_CHAT_ID = "-1003801745265"
    SIGNAL_EMOJIS = {"BUY": "🟢", "SELL": "🔴", "HOLD": "⚪"}


class TelegramSender:
    """Send signals and results to Telegram channel."""

    def __init__(self):
        self.token = BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _post(self, text):
        """Send message to Telegram (Markdown format)."""
        url = f"{self.base_url}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=req_data, headers={"Content-Type": "application/json"}
        )

        try:
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            if result.get("ok"):
                msg_id = result["result"].get("message_id", "?")
                print(f"[TELEGRAM] Sent (msg_id={msg_id})")
                return True
            else:
                desc = result.get("description", "unknown error")
                print(f"[TELEGRAM] Error: {desc}")
                return False
        except Exception as e:
            print(f"[TELEGRAM] Failed: {e}")
            return False

    def send_signal(self, signal_data):
        """Send Buy/Sell signal to Telegram."""
        symbol = signal_data["symbol"]
        signal_type = signal_data["signal"]
        confidence = signal_data.get("confidence", 0)
        emoji = SIGNAL_EMOJIS.get(signal_type, "⚪")

        lines = [
            f"***{emoji} JARVIS SIGNAL - {symbol.upper()}***",
            "",
            f"*Type:* **{signal_type}**",
            f"*Price:* {signal_data.get('latest_price', 'N/A')} VND",
            f"*Confidence:* {confidence:.1f}%",
            "",
            "*Reasons:*",
        ]

        for reason in signal_data.get("reasons", []):
            lines.append(f"- {reason}")

        stop_loss = signal_data.get("stop_loss")
        take_profit = signal_data.get("take_profit")

        if stop_loss:
            lines.append(f"*Stop Loss:* **{stop_loss}** VND")
        if take_profit:
            lines.append(f"*Take Profit:* **{take_profit}** VND")

        rsi = signal_data.get("rsi")
        if rsi is not None:
            lines.append(f"*RSI(14):* {rsi:.2f}")

        macd = signal_data.get("macd")
        if macd is not None:
            lines.append(f"*MACD:* {macd:.4f}")

        text = "\n".join(lines) + "\n"
        self._post(text)

    def send_risk_notice(self, message):
        """Send risk/warning notice to Telegram (circuit breaker, position close)."""
        lines = [
            "*JARVIS RISK MANAGER*",
            "",
            f"{message}",
        ]
        self._post("\n".join(lines))

    def send_daily_summary(self, signals_sent, accuracy_report=None):
        """Send daily summary report to Telegram."""
        lines = [
            "*JARVIS - Daily Trading Summary*",
            "",
            f"*Signals sent:* {signals_sent}",
        ]

        if accuracy_report:
            acc = accuracy_report.get("overall_accuracy", 0)
            lines.append(f"*Overall accuracy:* {acc:.1%}")
        else:
            lines.append("*No data yet*")

        by_symbol = accuracy_report.get("accuracy_by_symbol", {}) if accuracy_report else {}
        if by_symbol:
            lines.append("")
            lines.append("*Accuracy by symbol:*")
            for sym, stats in by_symbol.items():
                acc = stats["wins"] / max(stats["total"], 1)
                lines.append(f"- **{sym}**: {acc:.0%} ({stats['wins']}/{stats['total']})")

        self._post("\n".join(lines))
