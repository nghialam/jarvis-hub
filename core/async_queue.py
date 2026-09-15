"""
core/async_queue.py - Thread-based task queue with 3 workers

JH3.0: LLM calls run in background threads. Users never wait for LLM.
All LLM-dependent endpoints return immediately with heuristic + task_id.

Features:
- Thread pool with configurable workers (default 3)
- Task submission, status polling, result retrieval
- Task priority (normal/high/urgent)
- Task lifecycle: pending → processing → completed/failed
- Automatic cleanup of old completed tasks
"""

import queue
import threading
import time
import uuid
import json
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

log = None


def _get_logger():
    global log
    if log is None:
        try:
            from core.logging_config import get_logger
            log = get_logger("ASYNC_QUEUE")
        except Exception:
            log = _NullLogger()
    return log


class _NullLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class AsyncTask:
    """Represents a single async task in the queue."""
    
    def __init__(self, task_id: str, task_type: str, payload: Dict,
                 priority: TaskPriority = TaskPriority.NORMAL,
                 callback: Optional[Callable] = None):
        self.task_id = task_id
        self.task_type = task_type
        self.payload = payload
        self.priority = priority
        self.callback = callback
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.started_at = None
        self.completed_at = None
        self.worker_name = None
    
    def to_dict(self) -> Dict:
        """Serialize task to dict for API responses."""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "priority": self.priority.value if isinstance(self.priority, TaskPriority) else self.priority,
            "payload": self.payload,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "worker_name": self.worker_name,
        }


class AsyncQueue:
    """
    Thread-based async task queue.
    
    Usage:
        queue = AsyncQueue(num_workers=3)
        queue.start()
        
        # Submit a task
        task_id = queue.submit("analyze", {"symbol": "VCB"})
        
        # Check status
        status = queue.get_status(task_id)
        
        # Wait for result
        result = queue.get_result(task_id, timeout=300)
    """
    
    def __init__(self, num_workers: int = 3, max_queue_size: int = 100):
        self.num_workers = num_workers
        self.max_queue_size = max_queue_size
        self._task_queue = queue.Queue(maxsize=max_queue_size)
        self._tasks: Dict[str, AsyncTask] = {}
        self._lock = threading.Lock()
        self._workers: List[threading.Thread] = []
        self._running = False
        self._cleanup_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.stats = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "processing": 0,
            "pending": 0,
        }
    
    def start(self):
        """Start worker threads."""
        if self._running:
            return
        
        self._running = True
        _get_logger()  # Ensure logger is initialized
        log.info("Starting async queue with %d workers", self.num_workers)
        
        # Start worker threads
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"async-worker-{i}",
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        # Start cleanup thread (runs every 5 minutes)
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="async-cleanup",
            daemon=True
        )
        self._cleanup_thread.start()
    
    def stop(self):
        """Stop worker threads gracefully."""
        self._running = False
        for worker in self._workers:
            worker.join(timeout=10)
        self._workers.clear()
        log.info("Async queue stopped")
    
    def submit(self, task_type: str, payload: Dict,
               priority: TaskPriority = TaskPriority.NORMAL,
               callback: Optional[Callable] = None) -> str:
        """
        Submit a task to the queue.
        
        Returns:
            task_id: Unique identifier for the submitted task
        """
        task_id = str(uuid.uuid4())[:12]
        task = AsyncTask(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            callback=callback
        )
        
        with self._lock:
            self._tasks[task_id] = task
            self.stats["submitted"] += 1
            self.stats["pending"] += 1
        
        try:
            self._task_queue.put_nowait(task)
            log.info("Task submitted: %s (%s, priority=%s)", task_id, task_type, priority.value)
        except queue.Full:
            log.error("Queue full, rejecting task: %s", task_id)
            with self._lock:
                self.stats["pending"] -= 1
                self.stats["failed"] += 1
                task.status = TaskStatus.FAILED
                task.error = "Queue full"
        
        return task_id
    
    def get_status(self, task_id: str) -> Optional[Dict]:
        """Get task status by ID."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return task.to_dict()
        return None
    
    def get_result(self, task_id: str, timeout: float = 300) -> Optional[Dict]:
        """
        Wait for task result with timeout.
        
        Returns:
            Task dict with result, or None if timeout/failed
        """
        deadline = time.time() + timeout
        
        while time.time() < deadline:
            status = self.get_status(task_id)
            if status and status["status"] in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                return status
            
            time.sleep(0.5)
        
        return self.get_status(task_id)
    
    def list_tasks(self, task_type: str = None, status: str = None,
                   limit: int = 50) -> List[Dict]:
        """List tasks with optional filters."""
        with self._lock:
            tasks = list(self._tasks.values())
        
        # Filter
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        if status:
            tasks = [t for t in tasks if (t.status.value if isinstance(t.status, TaskStatus) else t.status) == status]
        
        # Sort by created_at desc, limit
        tasks.sort(key=lambda t: t.created_at or datetime.min, reverse=True)
        
        return [t.to_dict() for t in tasks[:limit]]
    
    def get_stats(self) -> Dict:
        """Get queue statistics."""
        with self._lock:
            self.stats["processing"] = sum(
                1 for t in self._tasks.values()
                if isinstance(t.status, TaskStatus) and t.status == TaskStatus.PROCESSING
            )
            self.stats["pending"] = sum(
                1 for t in self._tasks.values()
                if isinstance(t.status, TaskStatus) and t.status == TaskStatus.PENDING
            )
            return dict(self.stats)
    
    def _worker_loop(self):
        """Main loop for worker threads."""
        worker_name = threading.current_thread().name
        
        while self._running:
            try:
                # Get task from queue (block with timeout)
                try:
                    task = self._task_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Process task
                self._process_task(task, worker_name)
                
                # Mark task as done in queue
                self._task_queue.task_done()
                
            except Exception as e:
                log.error("Worker %s error: %s", worker_name, e)
    
    def _process_task(self, task: AsyncTask, worker_name: str):
        """Process a single task."""
        task.worker_name = worker_name
        task.started_at = datetime.utcnow()
        
        with self._lock:
            task.status = TaskStatus.PROCESSING
            self.stats["pending"] = max(0, self.stats["pending"] - 1)
            self.stats["processing"] += 1
        
        log.info("Processing task %s (%s) on %s", task.task_id, task.task_type, worker_name)
        
        try:
            # Execute task based on type
            result = self._execute_task(task)
            
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.utcnow()
            
            with self._lock:
                self.stats["completed"] += 1
                self.stats["processing"] -= 1
            
            log.info("Task %s completed successfully", task.task_id)
            
            # Call callback if provided
            if task.callback:
                try:
                    task.callback(task.task_id, result)
                except Exception as cb_error:
                    log.error("Task callback error: %s", cb_error)
                    
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.utcnow()
            
            with self._lock:
                self.stats["failed"] += 1
                self.stats["processing"] -= 1
            
            log.error("Task %s failed: %s", task.task_id, e)
            log.error(traceback.format_exc())
    
    def _execute_task(self, task: AsyncTask) -> Any:
        """Execute task based on its type."""
        # Task type handlers
        handlers = {
            "analyze_stock": self._handle_analyze_stock,
            "market_evaluation": self._handle_market_evaluation,
            "news_score": self._handle_news_score,
            "market_intelligence": self._handle_market_intelligence,
        }
        
        handler = handlers.get(task.task_type)
        if handler:
            return handler(task.payload)
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")
    
    def _handle_analyze_stock(self, payload: Dict) -> Dict:
        """Handle stock analysis task."""
        from core.fallback_engine import analyze_stock_heuristic
        symbol = payload.get("symbol", "")
        return analyze_stock_heuristic(symbol, payload.get("market_data", {}))
    
    def _handle_market_evaluation(self, payload: Dict) -> Dict:
        """Handle market evaluation task."""
        from core.fallback_engine import generate_market_evaluation_heuristic
        return generate_market_evaluation_heuristic(payload)
    
    def _handle_news_score(self, payload: Dict) -> Dict:
        """Handle news scoring task."""
        from core.fallback_engine import score_news_heuristic
        return score_news_heuristic(
            payload.get("title", ""),
            payload.get("summary", ""),
            payload.get("category", "")
        )
    
    def _handle_market_intelligence(self, payload: Dict) -> Dict:
        """Handle market intelligence pipeline task."""
        try:
            from core.market_intelligence import run_pipeline
            return run_pipeline()
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _cleanup_loop(self):
        """Periodically clean up old completed tasks."""
        while self._running:
            try:
                time.sleep(300)  # Every 5 minutes
                self._cleanup_old_tasks()
            except Exception as e:
                log.error("Cleanup error: %s", e)
    
    def _cleanup_old_tasks(self):
        """Remove tasks older than 24 hours."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        removed = 0
        
        with self._lock:
            tasks_to_remove = [
                tid for tid, task in self._tasks.items()
                if task.created_at and task.created_at < cutoff
            ]
            for tid in tasks_to_remove:
                del self._tasks[tid]
                removed += 1
        
        if removed > 0:
            log.info("Cleaned up %d old tasks", removed)


# Singleton instance
_async_queue_instance = None


def get_async_queue(num_workers: int = 3) -> AsyncQueue:
    """Get or create AsyncQueue singleton."""
    global _async_queue_instance
    if _async_queue_instance is None:
        _async_queue_instance = AsyncQueue(num_workers=num_workers)
    if not _async_queue_instance._running:
        _get_logger()  # Ensure logger is initialized before start()
        _async_queue_instance.start()
    return _async_queue_instance
