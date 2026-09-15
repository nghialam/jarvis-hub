"""
services/subscription_service.py - Subscription/Alert Service (Phase 3.12)

JH3.0: Manages user subscriptions and alert delivery preferences.
Works without LLM - all alert logic is rule-based.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from core.config import load_config
from core.db import Database

log = logging.getLogger(__name__)


class SubscriptionService:
    """
    Manage user subscriptions and alert delivery.
    
    Supports:
    - Watchlist alerts (price, volume, technical indicators)
    - Daily briefing delivery (email, Telegram, dashboard)
    - News alerts (keyword-based)
    """
    
    def __init__(self, config=None, db=None):
        self.config = config or load_config()
        self.db = db or Database()
    
    def get_subscriptions(self, user_id: str = "default") -> List[Dict]:
        """
        Get all subscriptions for a user.
        
        Args:
            user_id: User identifier (default: "default")
        
        Returns:
            List of subscription dicts
        """
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                """SELECT id, user_id, type, config, created_at, updated_at 
                   FROM subscriptions WHERE user_id = ? ORDER BY type""",
                (user_id,)
            ).fetchall()
            
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "type": row[2],
                    "config": json.loads(row[3]) if row[3] else {},
                    "created_at": row[4],
                    "updated_at": row[5],
                }
                for row in rows
            ]
        except Exception as e:
            log.error("Failed to get subscriptions: %s", e)
            return []
    
    def add_subscription(self, user_id: str, sub_type: str, config: Dict) -> Optional[Dict]:
        """
        Add a new subscription.
        
        Args:
            user_id: User identifier
            sub_type: Subscription type (price_alert, daily_brief, news_alert)
            config: Subscription configuration
        
        Returns:
            Created subscription dict or None
        """
        try:
            conn = self.db.get_connection()
            now = datetime.utcnow().isoformat()
            
            conn.execute(
                """INSERT INTO subscriptions (user_id, type, config, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, sub_type, json.dumps(config), now, now)
            )
            conn.commit()
            
            return {
                "user_id": user_id,
                "type": sub_type,
                "config": config,
                "created_at": now,
                "updated_at": now,
            }
        except Exception as e:
            log.error("Failed to add subscription: %s", e)
            return None
    
    def remove_subscription(self, sub_id: str) -> bool:
        """
        Remove a subscription.
        
        Args:
            sub_id: Subscription ID
        
        Returns:
            True if removed, False otherwise
        """
        try:
            conn = self.db.get_connection()
            conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
            conn.commit()
            return True
        except Exception as e:
            log.error("Failed to remove subscription: %s", e)
            return False
    
    def update_subscription(self, sub_id: str, config: Dict) -> bool:
        """
        Update subscription configuration.
        
        Args:
            sub_id: Subscription ID
            config: New configuration
        
        Returns:
            True if updated, False otherwise
        """
        try:
            conn = self.db.get_connection()
            conn.execute(
                "UPDATE subscriptions SET config = ?, updated_at = ? WHERE id = ?",
                (json.dumps(config), datetime.utcnow().isoformat(), sub_id)
            )
            conn.commit()
            return True
        except Exception as e:
            log.error("Failed to update subscription: %s", e)
            return False
    
    def check_price_alerts(self, watchlist_items: List[Dict]) -> List[Dict]:
        """
        Check if any price alerts have been triggered.
        
        Args:
            watchlist_items: List of watchlist items with current prices
        
        Returns:
            List of triggered alerts
        """
        triggered = []
        
        try:
            conn = self.db.get_connection()
            
            # Get price alert subscriptions
            rows = conn.execute(
                """SELECT s.id, s.config, w.symbol, w.current_price 
                   FROM subscriptions s
                   JOIN watchlist w ON s.user_id = 'default'
                   WHERE s.type = 'price_alert'"""
            ).fetchall()
            
            for row in rows:
                alert_config = json.loads(row[1]) if row[1] else {}
                symbol = row[2]
                current_price = row[3]
                
                # Check price conditions
                target_price = alert_config.get("target_price")
                if target_price and current_price:
                    if (alert_config.get("condition") == "above" and current_price >= target_price) or \
                       (alert_config.get("condition") == "below" and current_price <= target_price):
                        triggered.append({
                            "alert_id": row[0],
                            "symbol": symbol,
                            "current_price": current_price,
                            "target_price": target_price,
                            "condition": alert_config.get("condition"),
                            "message": f"{symbol} is now {'above' if alert_config.get('condition') == 'above' else 'below'} {target_price}",
                        })
        except Exception as e:
            log.error("Price alert check failed: %s", e)
        
        return triggered
    
    def check_volume_alerts(self, watchlist_items: List[Dict]) -> List[Dict]:
        """
        Check if any volume alerts have been triggered.
        
        Args:
            watchlist_items: List of watchlist items with volume data
        
        Returns:
            List of triggered volume alerts
        """
        triggered = []
        
        try:
            for item in watchlist_items:
                volume = item.get("volume", 0)
                avg_volume = item.get("avg_volume", 0)
                
                if avg_volume > 0 and volume > avg_volume * 2:  # 2x average
                    triggered.append({
                        "symbol": item.get("symbol"),
                        "current_volume": volume,
                        "avg_volume": avg_volume,
                        "volume_ratio": volume / avg_volume,
                        "message": f"{item.get('symbol')} volume is {volume/avg_volume:.1f}x average",
                    })
        except Exception as e:
            log.error("Volume alert check failed: %s", e)
        
        return triggered
    
    def get_delivery_channels(self, user_id: str = "default") -> List[str]:
        """
        Get delivery channels for a user.
        
        Returns:
            List of channel names
        """
        channels = ["dashboard"]  # Always include dashboard
        
        try:
            conn = self.db.get_connection()
            rows = conn.execute(
                """SELECT config FROM subscriptions 
                   WHERE user_id = ? AND type = 'delivery_channel'""",
                (user_id,)
            ).fetchall()
            
            for row in rows:
                config = json.loads(row[0]) if row[0] else {}
                channels.extend(config.get("channels", []))
        except Exception as e:
            log.error("Failed to get delivery channels: %s", e)
        
        return list(set(channels))  # Remove duplicates
    
    def clear_subscriptions(self, user_id: str = "default") -> bool:
        """
        Clear all subscriptions for a user.
        
        Args:
            user_id: User identifier
        
        Returns:
            True if cleared, False otherwise
        """
        try:
            conn = self.db.get_connection()
            conn.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
            conn.commit()
            return True
        except Exception as e:
            log.error("Failed to clear subscriptions: %s", e)
            return False
