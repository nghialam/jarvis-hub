"""
core/precompute_scheduler.py - Daily precompute job manager

Manages scheduled precompute tasks:
- MA5/10/20/50/200 calculations
- RSI14 calculations
- Volume ratio computations
- Sector ranking updates
- Market breadth aggregation

Uses APScheduler (in-process) for scheduling. No external cron needed.
"""

import threading
import sqlite3
import logging
from datetime import datetime, timedelta, time as dtime
from typing import Callable, Dict, List, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logging.getLogger(__name__).warning("APScheduler not available — precompute_scheduler runs manual mode only")

from core.semantic import MarketView, AggregateCache
from core.events import EventStore, EventType

log = None


def _get_logger():
    global log
    if log is None:
        try:
            from core.logging_config import get_logger
            log = get_logger("PRECOMPUTE")
        except Exception:
            log = _NullLogger()
    return log


class _NullLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class PrecomputeScheduler:
    """Manages daily precompute jobs for the semantic layer.
    
    Schedules:
    - Daily at 06:00 SGT (23:00 UTC previous day): full market precompute
    - On-demand refresh after data ingestion via Event system
    
    Integration: emits events for each precompute tick (start/complete/error).
    """

    def __init__(self, db_path: str, event_store: Optional[EventStore] = None):
        self.db_path = db_path
        self._event_store = event_store
        self._market_view = MarketView(db_path)
        self._agg_cache = AggregateCache(db_path)
        self._scheduler = None
        self._manual_jobs: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._running = False

        # Initialize DB tables
        self._market_view.init_db()
        self._agg_cache.init_db()

        # Register automatic jobs
        self._register_default_jobs()

    def _register_default_jobs(self):
        """Register default precompute jobs."""
        self._manual_jobs["daily_market"] = self._run_daily_market
        self._manual_jobs["market_breadth"] = self._run_market_breadth
        self._manual_jobs["sector_ranking"] = self._run_sector_ranking
        self._manual_jobs["indicators_snapshot"] = self._run_indicators_snapshot

    def start(self):
        """Start the in-process scheduler.
        
        Triggers daily at 23:00 UTC (06:00 SGT) for full precompute.
        """
        if self._running:
            return

        _get_logger()  # Ensure logger is initialized
        log.info("Starting precompute scheduler")
        self._running = True

        if HAS_APSCHEDULER:
            self._scheduler = BackgroundScheduler()
            # Daily full precompute at 06:00 SGT (23:00 UTC previous day)
            self._scheduler.add_job(
                self._run_daily_market,
                CronTrigger(hour=23, minute=0, timezone="UTC"),
                id="daily_market_precompute",
                name="Daily Market Precompute (06:00 SGT)",
                replace_existing=True,
            )
            # Hourly indicators snapshot during trading hours (07:00-16:00 SGT = 00:00-09:00 UTC)
            self._scheduler.add_job(
                self._run_indicators_snapshot,
                CronTrigger(hour="0-9", minute=0, timezone="UTC"),
                id="hourly_indicators_snapshot",
                name="Hourly Indicators Snapshot",
                replace_existing=True,
            )
            self._scheduler.start()
            log.info("Precompute scheduler started — daily at 06:00 SGT")
        else:
            log.warning("APScheduler not installed — use run_manually() to trigger precompute")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            log.info("Precompute scheduler stopped")

    def run_manually(self, job_name: str = "daily_market"):
        """Manually trigger a precompute job (for testing or ad-hoc runs)."""
        job_fn = self._manual_jobs.get(job_name)
        if not job_fn:
            log.warning("Unknown job: %s", job_name)
            return {"status": "error", "error": f"Unknown job: {job_name}"}

        log.info("Running precompute job manually: %s", job_name)
        return job_fn()

    def refresh_on_event(self, event_type: EventType, event_data: dict):
        """Callback for event system — triggers precompute on data ingestion events.
        
        Called automatically when new stock data is stored.
        """
        if event_type in (EventType.DATA_STORED, EventType.TICK_COMPLETE):
            symbol = event_data.get("symbol")
            if symbol:
                log.info("Data stored for %s — triggering indicators refresh", symbol)
                self._run_indicators_snapshot()

    # ---- Individual precompute jobs ----

    def _run_daily_market(self) -> Dict:
        """Full daily market precompute: breadth + top movers + sector ranking + indicators."""
        trace_id = f"daily_{datetime.utcnow().strftime('%Y%m%d')}"
        
        # Emit start event
        if self._event_store:
            self._event_store.emit(
                event_type=EventType.PIPELINE_START,
                source="precompute_scheduler",
                payload={"job": "daily_market", "trace_id": trace_id},
                trace_id=trace_id,
            )

        try:
            # 1. Market breadth
            breadth = self._run_market_breadth()
            
            # 2. Sector ranking
            sector = self._run_sector_ranking()
            
            # 3. Top movers
            movers = self._agg_cache.refresh_all()
            
            # 4. Cache freshness
            self._agg_cache.set_cached("last_precompute", {
                "time": datetime.utcnow().isoformat(),
                "job": "daily_market",
                "breadth_count": len(breadth.get("rows", [])),
                "sector_count": len(sector.get("rows", [])),
            })

            result = {
                "status": "completed",
                "trace_id": trace_id,
                "breadth": breadth,
                "sector_ranking": sector,
                "movers": movers,
            }

            if self._event_store:
                _events = self._event_store.query(
                    source="precompute_scheduler",
                    trace_id=trace_id,
                    limit=1,
                )
                if _events:
                    self._event_store.update(
                        _events[0].event_id,
                        result=result,
                    )

            return result

        except Exception as e:
            if self._event_store:
                self._event_store.emit(
                    event_type=EventType.PIPELINE_ERROR,
                    source="precompute_scheduler",
                    payload={"job": "daily_market", "error": str(e)},
                    trace_id=trace_id,
                )
            return {"status": "error", "error": str(e), "trace_id": trace_id}

    def _run_market_breadth(self) -> Dict:
        """Compute market breadth: advancers/decliners per symbol."""
        from datetime import date, timedelta
        
        trace_id = f"breadth_{datetime.utcnow().strftime('%Y%m%d')}"
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        if self._event_store:
            self._event_store.emit(
                event_type=EventType.METRIC_PRECOMPUTED,
                source="precompute_scheduler",
                payload={"job": "market_breadth", "date": today},
                trace_id=trace_id,
            )

        conn = sqlite3.connect(self.db_path)
        results = []

        try:
            cursor = conn.cursor()
            
            # Use the aggregate_cache table if available
            cursor.execute("""
                INSERT OR REPLACE INTO market_breadth
                SELECT d.date, d.symbol, d.close, p.close,
                       (d.close - p.close) / NULLIF(p.close, 0) * 100,
                       d.volume, s.classification, s.category
                FROM stock_data d
                INNER JOIN stock_data p ON d.symbol = p.symbol AND p.date = ?
                LEFT JOIN (SELECT DISTINCT symbol, classification, category FROM stock_meta) s
                    ON d.symbol = s.symbol
                WHERE d.date = ?
            """, (yesterday, today))
            
            # Count advancers/decliners
            advancers = cursor.execute("""
                SELECT COUNT(*) FROM market_breadth 
                WHERE date = ? AND pct_change > 0
            """, (today,)).fetchone()[0]
            decliners = cursor.execute("""
                SELECT COUNT(*) FROM market_breadth 
                WHERE date = ? AND pct_change < 0
            """, (today,)).fetchone()[0]
            unchanged = cursor.execute("""
                SELECT COUNT(*) FROM market_breadth 
                WHERE date = ? AND pct_change = 0
            """, (today,)).fetchone()[0]

            results = [
                {"label": "advancers", "count": advancers},
                {"label": "decliners", "count": decliners},
                {"label": "unchanged", "count": unchanged},
                {"label": "total", "count": advancers + decliners + unchanged},
            ]

            conn.commit()
            return {"status": "ok", "rows": results, "date": today}

        except Exception as e:
            log.error("Market breadth error: %s", e)
            return {"status": "error", "error": str(e), "date": today}
        finally:
            if conn:
                conn.close()

    def _run_sector_ranking(self) -> Dict:
        """Compute sector volume rankings."""
        from datetime import date

        trace_id = f"sector_{datetime.utcnow().strftime('%Y%m%d')}"
        today = date.today().isoformat()

        if self._event_store:
            self._event_store.emit(
                event_type=EventType.METRIC_PRECOMPUTED,
                source="precompute_scheduler",
                payload={"job": "sector_ranking", "date": today},
                trace_id=trace_id,
            )

        conn = sqlite3.connect(self._db_path)
        results = []

        try:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT classification, COUNT(*) as stock_count,
                       AVG(close) as avg_price, SUM(volume) as total_vol,
                       AVG(pct_change) as avg_pct_change
                FROM market_breadth
                WHERE date = ?
                GROUP BY classification
                ORDER BY total_vol DESC
            """, (today,)).fetchall()

            results = [{"sector": r[0], "count": r[1], "avg_price": r[2],
                       "total_vol": r[3], "avg_pct_change": r[4]} for r in rows]

            self._agg_cache.set_cached(f"sector_rank_{today}", {"rows": results, "date": today})
            return {"status": "ok", "rows": results, "date": today}

        except Exception as e:
            log.error("Sector ranking error: %s", e)
            return {"status": "error", "error": str(e), "date": today}
        finally:
            conn.close()

    def _run_indicators_snapshot(self) -> Dict:
        """Refresh indicator snapshot for watch list symbols."""
        trace_id = f"snapshot_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"

        if self._event_store:
            self._event_store.emit(
                event_type=EventType.METRIC_PRECOMPUTED,
                source="precompute_scheduler",
                payload={"job": "indicators_snapshot", "trace_id": trace_id},
                trace_id=trace_id,
            )

        # Default watch list: common VN stocks
        watch_list = ["VIC", "VCB", "HPG", "VNM", "FMG", "MSN", "GAS", "PLX", "SLM", "TCM"]
        
        try:
            # Get latest indicators
            indicators = self._market_view.get_latest_for_symbols(watch_list)
            
            # Get latest RSI
            rsi_latest = {}
            for sym in watch_list:
                rsi_rows = self._market_view.get_rsi(sym, "2024-01-01", limit=1)
                if rsi_rows:
                    rsi_latest[sym] = rsi_rows[0].get("rsi14")

            result = {
                "status": "ok",
                "indicators": indicators,
                "rsi": rsi_latest,
                "timestamp": datetime.utcnow().isoformat(),
                "symbols_count": len(indicators),
            }

            self._agg_cache.set_cached(f"indicators_snapshot", result)
            return result

        except Exception as e:
            log.error("Indicators snapshot error: %s", e)
            return {"status": "error", "error": str(e)}

    def get_job_status(self) -> Dict:
        """Get current scheduler status and last run times."""
        status = {
            "running": self._running,
            "scheduler": "APScheduler" if HAS_APSCHEDULER and self._scheduler else "manual",
            "jobs_available": list(self._manual_jobs.keys()),
            "cached_entries": 0,
        }

        if self._agg_cache:
            try:
                last = self._agg_cache.get_cached("last_precompute")
                if last:
                    status["last_precompute"] = last
            except Exception:
                pass

        return status


# Singleton instance
_precompute_scheduler_instance = None


def get_precompute_scheduler(db_path: str, event_store: Optional[EventStore] = None) -> PrecomputeScheduler:
    """Get or create PrecomputeScheduler singleton."""
    global _precompute_scheduler_instance
    if _precompute_scheduler_instance is None:
        _precompute_scheduler_instance = PrecomputeScheduler(db_path, event_store=event_store)
    if not _precompute_scheduler_instance._running:
        _precompute_scheduler_instance.start()
    return _precompute_scheduler_instance
