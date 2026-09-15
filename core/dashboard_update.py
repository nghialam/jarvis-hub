"""
core/dashboard_update.py - DashboardUpdateService (Phase 1.14)

Updates the dashboard with latest brief, alerts, and system status.
JH3.0: Reads from consolidated DB, writes to cache, non-blocking.
"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional

log = None


def _get_logger():
    global log
    if log is None:
        try:
            from core.logging_config import get_logger
            log = get_logger("DASHBOARD")
        except Exception:
            log = _NullLogger()
    return log


class _NullLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class DashboardUpdateService:
    """Service for updating dashboard state and cache."""
    
    def __init__(self, db=None):
        self.db = db
        self._cache = {}
        self._lock = threading.Lock()
        self.update_count = 0
        self.error_count = 0
    
    def update_from_intelligence_run(self, run_id: int, brief: str, articles: List[Dict], sentiment: Dict) -> bool:
        """Update dashboard after a Market Intelligence run completes."""
        log.info("Dashboard update from MI run %d", run_id)
        
        try:
            with self._lock:
                # Store in memory cache for fast API reads
                self._cache["latest_brief"] = {
                    "run_id": run_id,
                    "brief": brief,
                    "sentiment": sentiment,
                    "articles_count": len(articles),
                    "updated_at": datetime.now().isoformat()
                }
                
                # Log to DB
                if self.db:
                    try:
                        self.db.log_activity(
                            command="dashboard_update",
                            args=json.dumps({"run_id": run_id, "type": "market_intelligence"}),
                            status="ok",
                            summary=f"Dashboard updated for MI run {run_id}"
                        )
                    except Exception:
                        pass  # Non-critical
                
                self.update_count += 1
                log.info("Dashboard updated (total: %d)", self.update_count)
                return True
                
        except Exception as e:
            log.error("Dashboard update failed: %s", e)
            self.error_count += 1
            return False
    
    def update_market_data(self, fresh_data: Dict) -> bool:
        """Update dashboard with fresh market data."""
        try:
            with self._lock:
                self._cache["market_data"] = {
                    "vn_indices": fresh_data.get("vn_indices", {}),
                    "global_indices": fresh_data.get("global_indices", {}),
                    "rates": fresh_data.get("rates", {}),
                    "crypto": {k: v for k, v in fresh_data.items() if k.startswith("crypto_")},
                    "gold": fresh_data.get("gold"),
                    "dxy": fresh_data.get("dxy"),
                    "oil": fresh_data.get("oil"),
                    "updated_at": datetime.now().isoformat()
                }
                self.update_count += 1
                return True
        except Exception as e:
            log.error("Market data dashboard update failed: %s", e)
            self.error_count += 1
            return False
    
    def update_alerts(self, alerts: List[Dict]) -> bool:
        """Update dashboard with latest alerts."""
        try:
            with self._lock:
                self._cache["alerts"] = {
                    "alerts": alerts[:50],  # Last 50 alerts
                    "updated_at": datetime.now().isoformat()
                }
                self.update_count += 1
                return True
        except Exception as e:
            log.error("Alerts dashboard update failed: %s", e)
            self.error_count += 1
            return False
    
    def update_health(self, health_data: Dict) -> bool:
        """Update dashboard with system health status."""
        try:
            with self._lock:
                self._cache["health"] = {
                    **health_data,
                    "updated_at": datetime.now().isoformat()
                }
                return True
        except Exception as e:
            log.error("Health dashboard update failed: %s", e)
            return False
    
    def get_latest_brief(self) -> Optional[Dict]:
        """Get the latest market intelligence brief from cache."""
        return self._cache.get("latest_brief")
    
    def get_dashboard_state(self) -> Dict:
        """Get complete dashboard state for API response."""
        with self._lock:
            state = {
                "latest_brief": self._cache.get("latest_brief"),
                "market_data": self._cache.get("market_data"),
                "alerts": self._cache.get("alerts"),
                "health": self._cache.get("health"),
                "cache_age_seconds": datetime.now().timestamp() - (
                    self._cache.get("market_data", {}).get("updated_at", 0)
                    if self._cache.get("market_data") else 0
                ) if isinstance(self._cache.get("market_data", {}).get("updated_at"), (int, float)) else 0
            }
            return state
    
    def get_stats(self) -> Dict:
        """Get service statistics."""
        return {
            "update_count": self.update_count,
            "error_count": self.error_count,
            "cache_keys": len(self._cache),
            "has_latest_brief": "latest_brief" in self._cache
        }


# Singleton instance
_dashboard_service = None


def get_dashboard_service(db=None) -> DashboardUpdateService:
    """Get or create DashboardUpdateService singleton."""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardUpdateService(db=db)
    return _dashboard_service
