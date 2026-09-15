"""
core/precompute_scheduler.py - Pre-compute LLM results on schedule (Phase 2.12)

JH3.0: LLM tasks are queued on data refresh, not on user request.
This ensures LLM analysis is always up-to-date when users visit.

Scheduler runs:
- Every 5 minutes: Refresh market data + queue LLM tasks
- Every 6 hours: Full market intelligence pipeline
- On demand: Queue specific analysis tasks
"""

import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

log = logging.getLogger(__name__)


class PrecomputeScheduler:
    """
    Scheduler that pre-computes LLM results on a schedule.
    
    Usage:
        scheduler = PrecomputeScheduler()
        scheduler.start()
    """
    
    def __init__(self, data_refresh_interval: int = 300, intelligence_interval: int = 21600,
                 data_refresh: Optional[Callable[[], Any]] = None):
        self.data_refresh_interval = data_refresh_interval  # 5 minutes default
        self.intelligence_interval = intelligence_interval  # 6 hours default
        # Phase 2.12: optional callback (e.g. app._refresh_data) so the
        # 5-minute loop refreshes real market data, not just LLM queues.
        self.data_refresh = data_refresh
        self._running = False
        self._data_thread: Optional[threading.Thread] = None
        self._intelligence_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            "data_refresh_count": 0,
            "intelligence_run_count": 0,
            "last_data_refresh": None,
            "last_intelligence_run": None,
        }
    
    def start(self):
        """Start all scheduler threads."""
        if self._running:
            return
        
        self._running = True
        
        # Start data refresh thread
        self._data_thread = threading.Thread(
            target=self._data_refresh_loop,
            name="precompute-data",
            daemon=True
        )
        self._data_thread.start()
        log.info("Precompute scheduler started (data refresh: %ds, intelligence: %ds)",
                 self.data_refresh_interval, self.intelligence_interval)
    
    def stop(self):
        """Stop all scheduler threads."""
        self._running = False
        if self._data_thread:
            self._data_thread.join(timeout=10)
        if self._intelligence_thread:
            self._intelligence_thread.join(timeout=10)
        log.info("Precompute scheduler stopped")
    
    def _data_refresh_loop(self):
        """Loop that refreshes data and queues LLM tasks periodically."""
        while self._running:
            try:
                self._refresh_data_and_queue_llm()
                self.stats["last_data_refresh"] = datetime.utcnow().isoformat()
                self.stats["data_refresh_count"] += 1
            except Exception as e:
                log.error("Data refresh error: %s", e)
            
            time.sleep(self.data_refresh_interval)
    
    def _intelligence_loop(self):
        """Loop that runs full MI pipeline periodically."""
        while self._running:
            try:
                self._run_intelligence_pipeline()
                self.stats["last_intelligence_run"] = datetime.utcnow().isoformat()
                self.stats["intelligence_run_count"] += 1
            except Exception as e:
                log.error("Intelligence pipeline error: %s", e)
            
            time.sleep(self.intelligence_interval)
    
    def _refresh_data_and_queue_llm(self):
        """Refresh market data and queue LLM analysis tasks."""
        log.info("Refreshing market data and queuing LLM tasks...")
        
        # Phase 2.12: actually refresh market data if a callback is wired
        if self.data_refresh is not None:
            try:
                self.data_refresh()
            except Exception as e:
                log.error("Data refresh callback error: %s", e)
        
        try:
            from core.async_queue import get_async_queue
            queue = get_async_queue()
            
            # Queue LLM tasks for key stocks
            stocks_to_analyze = ["VCB", "VPB", "MBB", "BIDV", "HDB"]  # Configurable
            for symbol in stocks_to_analyze:
                queue.submit("analyze_stock", {"symbol": symbol})
            
            # Queue market evaluation
            queue.submit("market_evaluation", {})
            
            log.info("Queued %d LLM tasks for data refresh", len(stocks_to_analyze) + 1)
            
        except Exception as e:
            log.error("Failed to queue LLM tasks: %s", e)
    
    def _run_intelligence_pipeline(self):
        """Run full market intelligence pipeline."""
        log.info("Running market intelligence pipeline...")
        
        try:
            from core.async_queue import get_async_queue
            queue = get_async_queue()
            queue.submit("market_intelligence", {})
            log.info("MI pipeline queued")
        except Exception as e:
            log.error("Failed to queue MI pipeline: %s", e)
    
    def get_stats(self) -> Dict:
        """Get scheduler statistics."""
        return {
            **self.stats,
            "running": self._running
        }
    
    def force_refresh(self):
        """Force immediate data refresh and LLM task queuing."""
        log.info("Forcing immediate data refresh...")
        self._refresh_data_and_queue_llm()
    
    def force_intelligence(self):
        """Force immediate intelligence pipeline run."""
        log.info("Forcing immediate intelligence pipeline...")
        self._run_intelligence_pipeline()


# Singleton instance
_precompute_scheduler = None


def get_precompute_scheduler() -> PrecomputeScheduler:
    """Get or create PrecomputeScheduler singleton."""
    global _precompute_scheduler
    if _precompute_scheduler is None:
        _precompute_scheduler = PrecomputeScheduler()
        _precompute_scheduler.start()
    return _precompute_scheduler
