"""
workers/alert_monitor.py - Alert Monitor Worker (Phase 3.14)

JH3.0: Watches watchlist for alert conditions using event-driven scheduling.
Works without LLM - all alert logic is rule-based.
Scheduling interval configurable via AUTO_SCAN_INTERVAL env var (default 300s = 5 min).
"""

import json
import logging
import os
import signal
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

try:
    from apscheduler.schedulers.threading import ThreadPoolScheduler  # type: ignore[import-untyped]
    _USE_APSCHEDULER = True
except ImportError:
    _USE_APSCHEDULER = False
    ThreadPoolScheduler = None  # type: ignore[misc,assignment]

from core.config import load_config
from core.db import Database
from core.async_queue import get_async_queue

log = logging.getLogger(__name__)

# Scheduling interval from env var (default 300s = 5 minutes)
_CHECK_INTERVAL = int(os.environ.get("AUTO_SCAN_INTERVAL", "300"))


class AlertMonitor:
    """
    Check watchlist alerts using event-driven scheduling.

    Uses APScheduler if available, otherwise falls back to threading.Timer.
    Interval is configurable via AUTO_SCAN_INTERVAL env var (default 300s / 5 min).
    Handles SIGTERM for graceful shutdown.
    """

    check_interval = _CHECK_INTERVAL  # class-level default, overridable per instance

    def __init__(self, config=None, db=None, check_interval: Optional[int] = None):
        self.config = config or load_config()
        self.db = db or Database()
        self.check_interval = check_interval or self.check_interval
        self._running = False
        self._scheduler: Optional[threading.Timer] = None
        self._apscheduler = None  # type: ignore[assignment]

        # Statistics
        self.stats = {
            "checks_count": 0,
            "alerts_triggered": 0,
            "last_check": None,
            "last_triggered": None,
        }

    def start(self):
        """Start the alert monitor using event-driven scheduling."""
        if self._running:
            return

        self._running = True

        if _USE_APSCHEDULER and ThreadPoolScheduler is not None:  # type: ignore[redundant-expr]
            self._apscheduler = ThreadPoolScheduler()
            self._apscheduler.add_job(
                self.check_alerts,
                'interval',
                seconds=self.check_interval,
                id='alert_check',
                max_instances=1,  # prevent overlapping runs
            )
            self._apscheduler.start()
            log.info("Alert monitor started (APScheduler, interval: %ds)", self.check_interval)
        else:
            # Fallback: schedule first check via threading.Timer
            self._schedule_next_timer()
            log.info("Alert monitor started (Timer fallback, interval: %ds)", self.check_interval)

        # Register SIGTERM/SIGINT handler for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)

    def stop(self):
        """Stop the alert monitor gracefully."""
        self._running = False

        if _USE_APSCHEDULER and self._apscheduler is not None:  # type: ignore[redundant-expr]
            self._apscheduler.shutdown(wait=False)
            log.info("Alert monitor stopped (APScheduler)")
        else:
            if self._scheduler:
                self._scheduler.cancel()
                self._scheduler = None
            log.info("Alert monitor stopped (Timer)")

    def _handle_sigterm(self, signum, frame):
        """Handle SIGTERM/SIGINT: log and trigger graceful shutdown."""
        sig_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        log.info("Received %s — shutting down alert monitor...", sig_name)
        self.stop()

    def _schedule_next_timer(self):
        """Reschedule next check via threading.Timer (fallback mode)."""
        if not self._running:
            return
        self._scheduler = threading.Timer(
            self.check_interval,
            self._run_check
        )
        self._scheduler.daemon = True
        self._scheduler.start()

    def _run_check(self):
        """Execute one alert check and reschedule."""
        if not self._running:
            return
        try:
            self.check_alerts()
            self.stats["checks_count"] += 1
            self.stats["last_check"] = datetime.utcnow().isoformat()
        except Exception as e:
            log.error("Alert check error: %s", e)
        finally:
            if self._running:
                self._schedule_next_timer()

    def check_alerts(self):
        """
        Check all watchlist alerts.
        """
        log.debug("Running alert check...")

        try:
            # Get watchlist items with current prices
            watchlist = self._get_watchlist()
            if not watchlist:
                return

            # Get current market data
            market_data = self._get_current_prices(watchlist)

            # Check price alerts
            price_alerts = self._check_price_alerts(watchlist, market_data)
            if price_alerts:
                self._trigger_alerts(price_alerts)

            # Check volume alerts
            volume_alerts = self._check_volume_alerts(watchlist, market_data)
            if volume_alerts:
                self._trigger_alerts(volume_alerts)

            # Check technical alerts
            tech_alerts = self._check_technical_alerts(watchlist, market_data)
            if tech_alerts:
                self._trigger_alerts(tech_alerts)

        except Exception as e:
            log.error("Alert check failed: %s", e)

    def _get_watchlist(self) -> List[Dict]:
        """Get current watchlist items."""
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                "SELECT id, symbol, name, current_price, avg_volume FROM watchlist"
            ).fetchall()

            return [
                {
                    "id": row[0],
                    "symbol": row[1],
                    "name": row[2],
                    "current_price": float(row[3]) if row[3] else 0,
                    "avg_volume": float(row[4]) if row[4] else 0,
                }
                for row in rows
            ]
        except Exception as e:
            log.error("Failed to get watchlist: %s", e)
            return []

    def _get_current_prices(self, watchlist: List[Dict]) -> Dict[str, Dict]:
        """
        Get current prices for watchlist items.

        Returns:
            Dict mapping symbol to price data
        """
        prices = {}

        try:
            from gateways.market_gateway import MarketGateway
            gateway = MarketGateway(self.config, self.db)

            for item in watchlist:
                price_data = gateway.get_price(item["symbol"], days=1)
                prices[item["symbol"]] = {
                    "price": price_data.get("price") or item["current_price"],
                    "volume": price_data.get("volume") or item["avg_volume"],
                }
        except Exception as e:
            log.error("Failed to get current prices: %s", e)

        return prices

    def _check_price_alerts(self, watchlist: List[Dict], market_data: Dict) -> List[Dict]:
        """Check if any price alerts have been triggered."""
        alerts = []

        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                """SELECT id, symbol, condition, threshold FROM trading_alerts
                   WHERE active = 1 AND type = 'price'"""
            ).fetchall()

            for row in rows:
                symbol = row[1]
                condition = row[2]
                threshold = float(row[3])

                current_price = market_data.get(symbol, {}).get("price", 0)

                if current_price > 0:
                    if (condition == "above" and current_price >= threshold) or \
                       (condition == "below" and current_price <= threshold):
                        alerts.append({
                            "alert_id": row[0],
                            "type": "price",
                            "symbol": symbol,
                            "message": f"{symbol} is now {'above' if condition == 'above' else 'below'} {threshold}",
                            "price": current_price,
                            "threshold": threshold,
                        })
        except Exception as e:
            log.error("Price alert check failed: %s", e)

        return alerts

    def _check_volume_alerts(self, watchlist: List[Dict], market_data: Dict) -> List[Dict]:
        """Check if any volume alerts have been triggered."""
        alerts = []

        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                """SELECT id, symbol, threshold FROM trading_alerts
                   WHERE active = 1 AND type = 'volume'"""
            ).fetchall()

            for row in rows:
                symbol = row[1]
                threshold_multiplier = float(row[2])

                volume_data = market_data.get(symbol, {})
                current_volume = volume_data.get("volume", 0)
                avg_volume = watchlist[0]["avg_volume"] if watchlist else 1

                if avg_volume > 0 and current_volume > avg_volume * threshold_multiplier:
                    alerts.append({
                        "alert_id": row[0],
                        "type": "volume",
                        "symbol": symbol,
                        "message": f"{symbol} volume is {current_volume/avg_volume:.1f}x average",
                        "volume": current_volume,
                        "avg_volume": avg_volume,
                        "ratio": current_volume / avg_volume,
                    })
        except Exception as e:
            log.error("Volume alert check failed: %s", e)

        return alerts

    def _check_technical_alerts(self, watchlist: List[Dict], market_data: Dict) -> List[Dict]:
        """Check if any technical indicator alerts have been triggered."""
        alerts = []

        try:
            from gateways.market_gateway import MarketGateway
            gateway = MarketGateway(self.config, self.db)

            for item in watchlist:
                symbol = item["symbol"]

                # Get technical indicators
                indicators = gateway.get_technical_indicators(symbol, days=90)
                tech = indicators.get("indicators", {})

                # Check RSI levels
                rsi = tech.get("rsi_14", 50)
                if rsi > 70:
                    alerts.append({
                        "type": "technical",
                        "symbol": symbol,
                        "indicator": "RSI",
                        "value": rsi,
                        "message": f"{symbol} RSI is overbought at {rsi:.1f}",
                        "severity": "warning",
                    })
                elif rsi < 30:
                    alerts.append({
                        "type": "technical",
                        "symbol": symbol,
                        "indicator": "RSI",
                        "value": rsi,
                        "message": f"{symbol} RSI is oversold at {rsi:.1f}",
                        "severity": "warning",
                    })

                # Check MA crossover
                sma_20 = tech.get("sma_20", 0)
                sma_50 = tech.get("sma_50", 0)
                current_price = tech.get("price", 0)

                if sma_20 > sma_50 and current_price > sma_20:
                    alerts.append({
                        "type": "technical",
                        "symbol": symbol,
                        "indicator": "MA_CROSS",
                        "value": "bullish",
                        "message": f"{symbol} golden cross: MA20 > MA50",
                        "severity": "info",
                    })
                elif sma_20 < sma_50 and current_price < sma_20:
                    alerts.append({
                        "type": "technical",
                        "symbol": symbol,
                        "indicator": "MA_CROSS",
                        "value": "bearish",
                        "message": f"{symbol} death cross: MA20 < MA50",
                        "severity": "warning",
                    })
        except Exception as e:
            log.error("Technical alert check failed: %s", e)

        return alerts

    def _trigger_alerts(self, alerts: List[Dict]):
        """
        Trigger alert notifications.

        Sends to:
        - Dashboard (stored in DB)
        - Telegram (if configured)
        - Email (if configured)
        """
        if not alerts:
            return

        log.info("Triggered %d alerts", len(alerts))
        self.stats["alerts_triggered"] += len(alerts)
        self.stats["last_triggered"] = datetime.utcnow().isoformat()

        try:
            conn = self.db.get_connection()

            for alert in alerts:
                # Store alert in database
                conn.execute(
                    """INSERT INTO trading_alerts (type, symbol, message, triggered_at, active)
                       VALUES (?, ?, ?, ?, 1)""",
                    (
                        alert["type"],
                        alert["symbol"],
                        alert["message"],
                        datetime.utcnow().isoformat(),
                    )
                )
                conn.commit()

            # Send via Telegram if configured
            self._send_telegram_alerts(alerts)

            # Queue async notifications
            self._queue_notifications(alerts)

        except Exception as e:
            log.error("Failed to trigger alerts: %s", e)

    def _send_telegram_alerts(self, alerts: List[Dict]):
        """Send alerts via Telegram."""
        try:
            from core.telegram_delivery import TelegramDeliveryService

            service = TelegramDeliveryService(self.config)
            for alert in alerts:
                service.send_alert(alert["message"])

            log.info("Sent %d alerts via Telegram", len(alerts))
        except Exception as e:
            log.error("Telegram alert failed: %s", e)

    def _queue_notifications(self, alerts: List[Dict]):
        """Queue async notification tasks."""
        try:
            queue = get_async_queue()

            for alert in alerts:
                queue.submit("send_notification", {
                    "type": alert["type"],
                    "symbol": alert["symbol"],
                    "message": alert["message"],
                })

            log.info("Queued %d notification tasks", len(alerts))
        except Exception as e:
            log.error("Failed to queue notifications: %s", e)

    def get_active_alerts(self) -> List[Dict]:
        """
        Get all active alerts from database.
        """
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                """SELECT id, type, symbol, message, threshold, triggered_at, active
                   FROM trading_alerts WHERE active = 1 ORDER BY triggered_at DESC"""
            ).fetchall()

            return [
                {
                    "id": row[0],
                    "type": row[1],
                    "symbol": row[2],
                    "message": row[3],
                    "threshold": float(row[4]) if row[4] else None,
                    "triggered_at": row[5],
                    "active": bool(row[6]),
                }
                for row in rows
            ]
        except Exception as e:
            log.error("Failed to get active alerts: %s", e)
            return []

    def clear_alert(self, alert_id: str) -> bool:
        """
        Clear a specific alert.
        """
        try:
            conn = self.db.get_connection()
            conn.execute("UPDATE trading_alerts SET active = 0 WHERE id = ?", (alert_id,))
            conn.commit()
            return True
        except Exception as e:
            log.error("Failed to clear alert: %s", e)
            return False

    def get_stats(self) -> Dict:
        """
        Get monitor statistics.
        """
        return {
            **self.stats,
            "running": self._running,
            "check_interval": self.check_interval,
            "using_apscheduler": _USE_APSCHEDULER,
            "os_environ_interval": _CHECK_INTERVAL,
        }
