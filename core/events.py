"""
Event-driven pipeline: Event sourcing with SQLite backend.
Provides audit trail for all data pipeline ticks (cron/API/manual).
"""

import uuid
import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field, asdict


class EventType(str, Enum):
    """Types of events in the pipeline."""
    # Data ingestion
    TICK_START = "tick_start"
    TICK_COMPLETE = "tick_complete"
    TICK_ERROR = "tick_error"
    
    # Data sources
    RSS_FETCH = "rss_fetch"
    API_FETCH = "api_fetch"
    WEB_SCRAPING = "web_scraping"
    CRON_TRIGGER = "cron_trigger"
    MANUAL_TRIGGER = "manual_trigger"
    
    # Data processing
    DATA_PARSED = "data_parsed"
    DATA_STORED = "data_stored"
    DATA_VALIDATED = "data_validated"
    DATA_INVALID = "data_invalid"
    
    # Semantic layer
    METRIC_PRECOMPUTED = "metric_precomputed"
    VIEW_INVALIDATED = "view_invalidated"
    VIEW_REFRESHED = "view_refreshed"
    
    # Pipeline lifecycle
    PIPELINE_START = "pipeline_start"
    PIPELINE_COMPLETE = "pipeline_complete"
    PIPELINE_ERROR = "pipeline_error"
    
    # Notifications
    ALERT_TRIGGERED = "alert_triggered"
    NOTIFICATION_SENT = "notification_sent"


class EventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass
class Event:
    """Core event data structure."""
    event_id: str
    type: EventType
    status: EventStatus
    source: str  # which module/component triggered it
    payload: dict  # structured data for this event
    timestamp: str  # ISO format
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None  # links related events together
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d
    
    @classmethod
    def create(
        cls,
        event_type: EventType,
        source: str,
        payload: Optional[dict] = None,
        trace_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> "Event":
        """Factory method for creating new events."""
        return cls(
            event_id=str(uuid.uuid4())[:12],
            type=event_type,
            status=EventStatus.PENDING,
            source=source,
            payload=payload or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
            trace_id=trace_id or str(uuid.uuid4())[:8],
            metadata=metadata or {},
        )
    
    @classmethod
    def from_row(cls, row) -> "Event":
        """Reconstruct event from SQLite row."""
        return cls(
            event_id=row[0],
            type=EventType(row[1]),
            status=EventStatus(row[2]),
            source=row[3],
            payload=json.loads(row[4]) if row[4] else {},
            timestamp=row[5],
            duration_ms=row[6],
            error=row[7],
            trace_id=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
        )


class EventStore:
    """SQLite-backed event store for audit trail and event querying."""
    
    def __init__(self, db_path: Optional[str] = None):
        import os
        if db_path is None:
            from flask import current_app
            db_path = current_app.config.get("JH_DB_PATH", 
                os.path.join(os.path.dirname(__file__), "..", "data", "jarvis.db"))
        self.db_path = db_path
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Create events and events_archive tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    source TEXT NOT NULL,
                    payload TEXT,
                    timestamp TEXT NOT NULL,
                    duration_ms REAL,
                    error TEXT,
                    trace_id TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_archive (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload TEXT,
                    timestamp TEXT NOT NULL,
                    duration_ms REAL,
                    error TEXT,
                    trace_id TEXT,
                    metadata TEXT,
                    archived_at TEXT NOT NULL
                )
            """)
            # Indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace ON events(trace_id)")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_type_source_time 
                ON events(event_type, source, timestamp)
            """)
            conn.commit()
        finally:
            conn.close()
    
    def insert(self, event: Event) -> Event:
        """Insert event into store, set to COMPLETED if no error, FAILED if error."""
        if event.error:
            event.status = EventStatus.FAILED
        else:
            event.status = EventStatus.COMPLETED
        
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO events 
                (event_id, event_type, status, source, payload, timestamp, 
                 duration_ms, error, trace_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.type.value,
                event.status.value,
                event.source,
                json.dumps(event.payload),
                event.timestamp,
                event.duration_ms,
                event.error,
                event.trace_id,
                json.dumps(event.metadata),
            ))
            conn.commit()
            return event
        finally:
            conn.close()

    def emit(self, event_type: EventType, source: str, payload: dict,
             trace_id: Optional[str] = None, metadata: Optional[dict] = None) -> str:
        """Create, insert and return event_id for a new event.
        
        Convenience wrapper around Event.create() + insert().
        """
        event = Event.create(
            event_type=event_type,
            source=source,
            payload=payload,
            trace_id=trace_id,
            metadata=metadata or {},
        )
        self.insert(event)
        return event.event_id

    def update(self, event_id: str, status: Optional[EventStatus] = None,
               result: Any = None, error: Optional[str] = None,
               trace: Optional[str] = None, duration_ms: Optional[float] = None,
               metadata: Optional[dict] = None) -> bool:
        """Update an existing event's status, result, error, or metadata."""
        conn = self._get_conn()
        try:
            # Build dynamic update
            updates = []
            params = []

            if status is not None:
                updates.append("status = ?")
                params.append(status.value)
            if result is not None:
                updates.append("payload = ?")
                params.append(json.dumps({**self._get_payload(conn, event_id), **(result if isinstance(result, dict) else {"result": str(result)})}))
            if error is not None:
                updates.append("error = ?")
                params.append(error)
                updates.append("status = ?")
                params.append(EventStatus.FAILED.value)
            if trace is not None:
                updates.append("metadata = ?")
                existing_meta = self._get_payload(conn, event_id)
                existing_meta["trace"] = trace
                updates.append("metadata = ?")
                params.append(json.dumps(existing_meta))
            if duration_ms is not None:
                updates.append("duration_ms = ?")
                params.append(duration_ms)

            if updates:
                updates.append("timestamp = ?")
                params.append(datetime.now(timezone.utc).isoformat())
                params.append(event_id)
                conn.execute(
                    f"UPDATE events SET {', '.join(updates)} WHERE event_id = ?",
                    params,
                )
                conn.commit()
                return True
            return False
        finally:
            conn.close()

    def _get_payload(self, conn, event_id: str) -> dict:
        """Helper: get existing payload for an event."""
        row = conn.execute("SELECT payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if row and row["payload"]:
            try:
                return json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def archive(self, event_id: str) -> bool:
        """Archive an event (move from events to events_archive)."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if not row:
                return False
            
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO events_archive 
                (event_id, event_type, status, source, payload, timestamp,
                 duration_ms, error, trace_id, metadata, archived_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row["event_id"], row["event_type"], row["status"], row["source"],
                row["payload"], row["timestamp"], row["duration_ms"],
                row["error"], row["trace_id"], row["metadata"], now,
            ))
            conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            conn.commit()
            return True
        finally:
            conn.close()
    
    def archive_old(self, days: int = 30) -> int:
        """Archive all events older than N days. Returns count archived."""
        cutoff = (datetime.now(timezone.utc).timestamp() - days * 86400)
        conn = self._get_conn()
        try:
            result = conn.execute(
                "SELECT * FROM events WHERE timestamp < ? AND status = 'completed'",
                (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),)
            ).fetchall()
            now = datetime.now(timezone.utc).isoformat()
            count = 0
            for row in result:
                conn.execute("""
                    INSERT INTO events_archive 
                    (event_id, event_type, status, source, payload, timestamp,
                     duration_ms, error, trace_id, metadata, archived_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["event_id"], row["event_type"], row["status"], row["source"],
                    row["payload"], row["timestamp"], row["duration_ms"],
                    row["error"], row["trace_id"], row["metadata"], now,
                ))
                count += 1
            if count > 0:
                conn.execute(
                    "DELETE FROM events WHERE timestamp < ?",
                    (datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(),)
                )
                conn.commit()
            return count
        finally:
            conn.close()
    
    def query(
        self,
        event_type: Optional[EventType] = None,
        status: Optional[EventStatus] = None,
        source: Optional[str] = None,
        trace_id: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """Query events with filters."""
        conditions = []
        params = []
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type.value)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if trace_id:
            conditions.append("trace_id = ?")
            params.append(trace_id)
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [Event.from_row(r) for r in rows]
        finally:
            conn.close()
    
    def get_trace(self, trace_id: str) -> list:
        """Get all events in a trace (ordered by timestamp)."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM events WHERE trace_id = ? ORDER BY timestamp ASC",
                (trace_id,),
            ).fetchall()
            return [Event.from_row(r) for r in rows]
        finally:
            conn.close()
    
    def get_errors(
        self, limit: int = 50, source: Optional[str] = None
    ) -> list:
        """Get failed events."""
        return self.query(status=EventStatus.FAILED, source=source, limit=limit)
    
    def get_stats(self, hours: int = 24) -> dict:
        """Get event statistics for the last N hours."""
        cutoff = (datetime.now(timezone.utc).timestamp() - hours * 3600)
        time_filter = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        
        conn = self._get_conn()
        try:
            # Count by type
            type_counts = conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM events "
                f"WHERE timestamp >= ? GROUP BY event_type",
                (time_filter,),
            ).fetchall()
            
            # Count by status
            status_counts = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM events "
                f"WHERE timestamp >= ? GROUP BY status",
                (time_filter,),
            ).fetchall()
            
            # Average duration for all events with timing data
            avg_dur = conn.execute(
                "SELECT AVG(duration_ms) as avg_ms, COUNT(*) as cnt FROM events "
                f"WHERE timestamp >= ? AND duration_ms IS NOT NULL",
                (time_filter,),
            ).fetchone()
            
            # Total event count
            total_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM events "
                f"WHERE timestamp >= ?",
                (time_filter,),
            ).fetchone()
            
            # Top error sources
            error_sources = conn.execute(
                "SELECT source, COUNT(*) as cnt, error FROM events "
                f"WHERE timestamp >= ? AND status = 'failed' GROUP BY source ORDER BY cnt DESC LIMIT 5",
                (time_filter,),
            ).fetchall()
            
            return {
                "type_counts": dict((r["event_type"], r["cnt"]) for r in type_counts),
                "status_counts": dict((r["status"], r["cnt"]) for r in status_counts),
                "avg_duration_ms": avg_dur["avg_ms"] if avg_dur and avg_dur["avg_ms"] else 0,
                "total_events": total_row["cnt"] if total_row else 0,
                "top_errors": [
                    {"source": r["source"], "count": r["cnt"], "error": r["error"]}
                    for r in error_sources
                ],
            }
        finally:
            conn.close()
