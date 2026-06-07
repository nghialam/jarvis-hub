#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gotham.kanban — SQLite-backed state machine for Gotham Brief audit trail.

Provides a lightweight persistent Kanban tracker at gotham/kanban/gotham_kanban.db
with states: IDLE → TRIAGE → PROCESSING → DELIVERED/FAILED.

All functions are safe to call before DB init (auto-initializes on first write).
Designed for cron execution: no external deps beyond stdlib sqlite3 + os.time.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone

# ─── Constants ──────────────────────────────────────────────
# These must match gotham/__init__.py exactly to keep DB path consistent.

_KANBAN_DIR = os.path.join(os.path.dirname(__file__), "kanban")
_KANBAN_DB  = os.path.join(_KANBAN_DIR, "gotham_kanban.db")

_STATE_TRANSITIONS = frozenset((
    "IDLE", "TRIAGE", "PROCESSING", "DELIVERING",
    "DELIVERED", "FAILED",
))

# ─── Internal Helpers ──────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """Open a connection and ensure the gotham_runs table exists."""
    os.makedirs(_KANBAN_DIR, exist_ok=True)
    conn = sqlite3.connect(_KANBAN_DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gotham_runs (
            run_id          TEXT PRIMARY KEY,
            state           TEXT   NOT NULL DEFAULT 'IDLE',
            mode            TEXT,
            date_str        TEXT,
            day_name        TEXT,
            rss_count_main  INTEGER DEFAULT -1,
            rss_count_ent   INTEGER DEFAULT -1,
            ent_sources_loaded INTEGER DEFAULT 0,
            prompts_fired   INTEGER DEFAULT 0,
            llm_success_count INTEGER DEFAULT 0,
            llm_results     TEXT,
            telegram_sent   INTEGER DEFAULT 0,
            telegram_msg_ids TEXT,
            errors          TEXT,
            started_at      TEXT,
            completed_at    TEXT,
            duration_sec    REAL
        );
    """)
    conn.commit()
    return conn


# ─── Public API ──────────────────────────────────────────────

def init(run_id: str, mode: str = "auto", date_str: str = "",
         day_name: str = "") -> None:
    """Mark a run ID as started (state → TRIAGE). Creates table if needed.

    Call once at the very top of each pipeline cron invocation.
    """
    conn = _conn()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        conn.execute(
            "INSERT OR REPLACE INTO gotham_runs "
            "(run_id, state, mode, date_str, day_name, started_at) "
            "VALUES (?, 'TRIAGE', ?, ?, ?, ?)",
            (run_id, mode, date_str, day_name, now),
        )
        conn.commit()
    finally:
        conn.close()


def update(run_id: str, **fields) -> None:
    """Update arbitrary column(s) for a run ID. Safe to call anytime.

    Allowed keys (besides common ones): state, mode, date_str, day_name,
    rss_count_main, rss_count_ent, ent_sources_loaded, prompts_fired,
    llm_success_count, llm_results, telegram_sent, telegram_msg_ids,
    errors, started_at, completed_at, duration_sec.

    Example: update(run_id, state="PROCESSING", llm_success_count=2)
    """
    if not fields:
        return
    conn = _conn()
    try:
        cols_vals = ", ".join(f"{k} = ?" for k in fields)
        vals      = list(fields.values()) + [run_id]
        conn.execute(
            f"UPDATE gotham_runs SET {cols_vals} WHERE run_id = ?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def read(run_id: str) -> dict | None:
    """Return row as dict, or None if not found."""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT * FROM gotham_runs WHERE run_id = ?", (run_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        keys = [desc[0] for desc in cur.description]
        return dict(zip(keys, row))
    finally:
        conn.close()


def list_recent(limit: int = 10) -> list[dict]:
    """Return most recent runs ordered by completed_at DESC.

    Returns list of dicts (empty if nothing in DB yet).
    """
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT * FROM gotham_runs ORDER BY completed_at DESC LIMIT ?",
            (limit,),
        )
        return [
            dict(zip([desc[0] for desc in cur.description], row))
            for row in cur.fetchall()
        ]
    finally:
        conn.close()


def complete(run_id: str, state: str = "DELIVERED", duration_sec: float = 0.0,
             **extra_fields) -> None:
    """Mark a run as finished with final state + timing.

    Final states should be DELIVERED or FAILED (enforced by callers).
    """
    extrafields = {**{"state": state, "completed_at":
                      datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                      "duration_sec": duration_sec}, **extra_fields}
    update(run_id, **extrafields)


# ─── Convenience Utilities ──────────────────────────────────

def snapshot_run(run_id: str) -> dict | None:
    """Read run state, useful for logging/reporting before send."""
    return read(run_id)


def summarize_recent(limit: int = 5) -> str:
    """Return a short text summary of recent runs. For cron health checks."""
    rows = list_recent(limit)
    lines = []
    for r in rows:
        sid   = r.get("run_id", "?")
        state = r.get("state", "?")
        mode  = r.get("mode", "?")
        date  = r.get("date_str", "?")
        d_sec = f'{r.get("duration_sec", 0):.0f}s' if r.get("duration_sec") else "N/A"
        errors = f' ERR={r["errors"][:80]}' if r.get("errors") else ""
        lines.append(f"{sid}: {state:12s} mode={mode:8s} date={date} dur={d_sec}{errors}")
    return "\n".join(lines) if lines else "(no runs in DB yet)"
