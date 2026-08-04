"""
delivery.py - Stage 5: Delivery

Persist results to DB and trigger notifications (Telegram/dashboard).
"""

import json
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _utc_now():
    """Return current UTC as a naive datetime for display."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def save_to_db(run_date, run_period, articles_json, market_brief):
    """Save a complete market intelligence run to DB.

    Args:
        run_date: ISO date string (YYYY-MM-DD)
        run_period: Period identifier (morning/afternoon/evening/night)
        articles_json: JSON string of analyzed articles
        market_brief: Synthesized Market Brief text

    Returns:
        run_id (int) on success, 0 on failure
    """
    try:
        from core.db import Database
        db = Database()

        run_id = db.save_market_intelligence(
            run_date=run_date,
            run_period=run_period,
            articles_json=articles_json,
            market_brief=market_brief,
            status="Notification Ready"
        )

        if run_id:
            log.info(f"[MI] Saved to DB: run_id={run_id}, period={run_period}")
            return run_id
        else:
            log.error("[MI] Failed to save to DB")
            return 0

    except Exception as e:
        log.error(f"[MI] DB save failed: {e}", exc_info=True)
        return 0


def notify_telegram(market_brief, sentiment_dist, articles):
    """Send Market Brief to Telegram.

    Args:
        market_brief: Synthesized brief text
        sentiment_dist: Dict with Bullish/Bearish/Neutral counts
        articles: List of analyzed articles
    """
    try:
        # Build Telegram message
        bull = sentiment_dist.get("Bullish", 0)
        bear = sentiment_dist.get("Bearish", 0)
        neu = sentiment_dist.get("Neutral", 0)
        total = sentiment_dist.get("total", bull + bear + neu)

        # Format message with markdown
        msg = f"*\U0001f4ca MARKET INTELLIGENCE BRIEF*\n"
        msg += f"*Period:* {_utc_now().strftime('%Y-%m-%d %H:%M')} SGT\n\n"
        msg += f"*Sentiment Distribution:*\n"
        msg += f"\U0001f7e2 Bullish: {bull}\n"
        msg += f"\U0001f534 Bearish: {bear}\n"
        msg += f"\u26aa Neutral: {neu}\n"
        msg += f"\U0001f4c8 Total Articles: {total}\n\n"
        msg += f"*Market Brief:*\n\n{market_brief[:1000]}\n\n"

        # Add top 3 bullish articles
        bullish = [a for a in articles if a.get("sentiment") == "Bullish"][:3]
        if bullish:
            msg += "*Top Bullish Signals:*\n"
            for a in bullish:
                msg += f"\u2022 {a.get('title', 'Untitled')}\n"
            msg += "\n"

        # Add top 3 bearish articles
        bearish = [a for a in articles if a.get("sentiment") == "Bearish"][:3]
        if bearish:
            msg += "*Top Bearish Signals:*\n"
            for a in bearish:
                msg += f"\u2022 {a.get('title', 'Untitled')}\n"
            msg += "\n"

        # Send via Telegram API or openclaw
        _send_telegram_message(msg)
        log.info("[MI] Telegram notification sent")

    except Exception as e:
        log.error(f"[MI] Telegram notification failed: {e}", exc_info=True)


def _send_telegram_message(text):
    """Send message to Telegram via configured method."""
    # Try openclaw first (preferred method per config)
    openclaw_path = os.environ.get("OPENCLAW_PATH", "/opt/homebrew/bin/openclaw")

    try:
        # Check if openclaw is available
        import subprocess
        result = subprocess.run(
            [openclaw_path, "send", "--chat-id", "1670013239", "--text", text],
            capture_output=True,
            timeout=30
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: direct Telegram API
    try:
        import requests

        # Get bot token from env or config
        bot_token = os.environ.get("JARVIS_BOT_TOKEN", "")
        if not bot_token:
            try:
                from core.config import load_config
                cfg = load_config()
                bot_token = cfg.get("telegram", {}).get("bot_token", "")
            except Exception:
                pass

        if not bot_token:
            log.warning("[MI] No Telegram bot token configured")
            return False

        chat_id = os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "1670013239")

        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=15
        )

        if resp.status_code != 200:
            log.warning(f"[MI] Telegram API returned {resp.status_code}: {resp.text}")

    except Exception as e:
        log.error(f"[MI] Telegram API call failed: {e}")


def update_dashboard(run_id):
    """Log activity and update dashboard cache.

    Args:
        run_id: The run ID from DB save
    """
    try:
        from core.db import Database
        db = Database()

        # Log to activity_log
        db.log_activity(
            command="market_intelligence_pipeline",
            args=json.dumps({"run_id": run_id, "status": "complete"}),
            status="ok",
            summary=f"Market Intelligence pipeline completed (run {run_id})"
        )

        log.info(f"[MI] Dashboard updated for run {run_id}")

    except Exception as e:
        log.error(f"[MI] Dashboard update failed: {e}")


def get_sentiment_distribution():
    """Get sentiment distribution across all articles.

    Returns:
        Dict with Bullish/Bearish/Neutral counts and total
    """
    try:
        from core.db import Database
        db = Database()
        return db.get_sentiment_distribution()

    except Exception as e:
        log.error(f"[MI] Sentiment distribution fetch failed: {e}")
        return {"Bullish": 0, "Bearish": 0, "Neutral": 0, "total": 0}


def trigger_notifications(run_id, market_brief, articles):
    """Trigger all notification channels.

    Args:
        run_id: Run ID from DB
        market_brief: Synthesized brief text
        articles: List of analyzed articles
    """
    log.info(f"[MI] Triggering notifications for run {run_id}...")

    # Get sentiment distribution
    sentiment_dist = get_sentiment_distribution()

    # Send to Telegram
    notify_telegram(market_brief, sentiment_dist, articles)

    # Update dashboard
    update_dashboard(run_id)

    log.info(f"[MI] All notifications triggered for run {run_id}")
