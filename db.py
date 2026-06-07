"""
db.py -- SQLite database for Jarvis Hub (Knowledge Base, Activity Log)

All datetime stored as ISO strings. Uses WAL journal mode for perf.
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import core.config as cfg


def _utc_now_iso():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    DATABASE_PATH_KEY = "db_path"
    DEFAULT_DB_NAME = Path.home() / "jarvis-hub" / "knowledge" / "jarvis.db"

    def __init__(self, db_path=None):
        self.db_path = Path(db_path).expanduser() if db_path else Path(self.DEFAULT_DB_NAME)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.init_db()

    def init_db(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                term TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                content TEXT NOT NULL,
                tags TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
             );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(term, content, tags);

            CREATE TRIGGER IF NOT EXISTS kn_ai AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts (rowid, term, content, tags) VALUES (new.id, new.term, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS kn_au AFTER UPDATE ON knowledge BEGIN
                UPDATE knowledge_fts SET term=new.term, content=new.content, tags=new.tags WHERE rowid=old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS kn_ad AFTER DELETE ON knowledge BEGIN
                DELETE FROM knowledge_fts WHERE rowid=old.id;
            END;

            CREATE TABLE IF NOT EXISTS activity_log (
                id     INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                command TEXT NOT NULL,
                args  TEXT DEFAULT '',
                status TEXT DEFAULT 'ok',
                summary TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT UNIQUE NOT NULL,
                briefing_content TEXT,
                summary          TEXT,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol   TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                name     TEXT DEFAULT '',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS market_cache (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL COLLATE NOCASE,
                data_json   TEXT    NOT NULL,
                cached_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at  TIMESTAMP,
                UNIQUE(symbol, cached_at)
            );

            DELETE FROM market_cache
                 WHERE datetime(expires_at) < datetime('now');

            CREATE TABLE IF NOT EXISTS trading_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT    NOT NULL COLLATE NOCASE,
                signal_type  TEXT    NOT NULL,    -- BUY / SELL / HOLD / STRONG_BUY / NEUTRAL
                severity     TEXT    DEFAULT 'LOW', -- LOW / MEDIUM / HIGH / CRITICAL
                alert_data   TEXT    DEFAULT '{}', -- JSON blob with price/RSI/MACD details
                status       TEXT    DEFAULT 'unread', -- unread / read
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              );

            CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON trading_alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_alerts_status ON trading_alerts(status);

            CREATE TABLE IF NOT EXISTS market_evaluation (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                date           TEXT    UNIQUE NOT NULL,
                evaluation     TEXT    NOT NULL,
                summary        TEXT    DEFAULT '',
                generated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
              );

          """)
        self._conn.commit()
        print("[DB] Initialized %s" % self.db_path)

    # -- helpers ---------------------------------------------------------------

    def _c(self):
        """Return a cursor from the persistent connection."""
        c = self._conn.cursor()
        return c

    # ---- knowledge base ----------------------------------------------------

    def save_term(self, term, content, tags=""):
        """Save or update a knowledge base entry."""
        c = self._c()
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            c.execute(
                """INSERT INTO knowledge (term, content, tags, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(term) DO UPDATE SET content=excluded.content, tags=excluded.tags, updated_at=?""",
                (term.lower(), content, tags, now, now))
            self._conn.commit()
            return c.lastrowid
        except sqlite3.Error:
            return 0

    def search_knowledge(self, query, limit=10):
        """Search knowledge base. Tries FTS5 first, falls back to LIKE."""
        # Try FTS5 - need to escape quotes and handle special chars
        try:
            # Remove problematic FTS5 operators: + - AND OR NOT "
            cleaned = query.strip().replace('+', '').replace('-', '').replace('"', '')
            
            # If it's a phrase with spaces, search for each word individually
            words = [w for w in cleaned.split() if len(w) > 1]
            if not words:
                return []
            
            # Build OR query to match any word
            conditions = " OR ".join(["term LIKE ? OR content LIKE ?", ] * min(len(words), 3))
            params = [("%" + w + "%",) * 2 for w in words[:3]]
            params = [p for wp in params for p in wp] + [limit]
            
            r = self._c().execute(
                "SELECT id, term, content, tags, updated_at FROM knowledge WHERE %s ORDER BY updated_at DESC LIMIT ?" % conditions,
                params).fetchall()
            return [dict(row) for row in r] if r else []
        except sqlite3.Error:
            return []

    def get_all_terms(self):
        """Get all terms with update timestamps."""
        return [dict(r) for r in self._c().execute(
             "SELECT term, updated_at FROM knowledge ORDER BY updated_at DESC").fetchall()]

    # ---- activity log -------------------------------------------------------

    def log_activity(self, command, args="", status="ok", summary=None, duration_ms=None):
        c = self._c()
        c.execute(
             """INSERT INTO activity_log (command, args, status, summary, duration_ms)
               VALUES (?, ?, ?, ?, ?)""",
             (command, str(args), status, summary or "", duration_ms if duration_ms else 0))
        self._conn.commit()

    def get_activities(self, limit=20):
        return [dict(r) for r in self._c().execute(
             "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()]

    # ---- daily snapshots ---------------------------------------------------

    def save_daily_snapshot(self, date, briefing_content, summary=""):
        c = self._c()
        try:
            c.execute(
                """INSERT INTO daily_snapshots (date, briefing_content, summary) VALUES (?, ?, ?)
                   ON CONFLICT(date) DO UPDATE SET briefing_content=excluded.briefing_content""",
                (date, briefing_content, summary))
            self._conn.commit()
        except sqlite3.Error:
            pass

    def get_daily_snapshot(self, date):
        c = self._c()
        r = c.execute("SELECT * FROM daily_snapshots WHERE date=?", (date,)).fetchone()
        return dict(r) if r else None

    def get_all_dates(self):
        c = self._c()
        return [r["date"] for r in c.execute(
             "SELECT DISTINCT date FROM daily_snapshots ORDER BY date DESC").fetchall()]

    # ---- watchlist ----------------------------------------------------------

    def add_watchlist(self, symbol, name=""):
        c = self._c()
        try:
            c.execute("""INSERT INTO watchlist (symbol, name) VALUES (?, ?)
                          ON CONFLICT(symbol) DO UPDATE SET name=excluded.name""",
                        (symbol.upper(), name))
            self._conn.commit()
            return c.lastrowid
        except sqlite3.Error:
            return 0

    def get_watchlist(self):
        return [dict(r) for r in self._c().execute(
             "SELECT * FROM watchlist ORDER BY added_at DESC").fetchall()]

    def remove_watchlist(self, symbol):
        c = self._c()
        c.execute("DELETE FROM watchlist WHERE UPPER(symbol)=UPPER(?)", (symbol,))
        self._conn.commit()
        return c.rowcount > 0

    # ---- market cache -------------------------------------------------------

    def save_market_data(self, symbol, data, ttl_minutes=60):
        ts = _utc_now_iso()
        exp = (datetime.utcnow() + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            self._c().execute(
                 "INSERT INTO market_cache (symbol, data_json, cached_at, expires_at) VALUES (?,?,?,?)",
                 (symbol.upper(), json.dumps(data), ts, exp))
            self._conn.commit()
        except sqlite3.Error:
            pass

    def get_cached_market_data(self, symbol):
        c = self._c()
        r = c.execute(
              """SELECT data_json FROM market_cache WHERE symbol=? AND datetime(expires_at) > datetime('now')
               ORDER BY cached_at DESC LIMIT 1""", (symbol.upper(),)).fetchone()
        if r:
            return json.loads(r["data_json"])
        return None

     # ---- trading alerts -----------------------------------------------------

    def mark_alerts_as_read(self):
        c = self._c()
        c.execute("UPDATE trading_alerts SET status='read' WHERE status='unread'")
        self._conn.commit()
        return c.rowcount

    def get_evaluation_by_date(self, date):
        r = self._c().execute(
                "SELECT * FROM market_evaluation WHERE date=?", (date,)).fetchone()
        return dict(r) if r else None

    def save_market_evaluation(self, date, evaluation, summary=""):
        try:
            self._c().execute(
                 """INSERT INTO market_evaluation (date, evaluation, summary)
                   VALUES (?, ?, ?)
                   ON CONFLICT(date) DO UPDATE SET evaluation=excluded.evaluation, 
                                                   summary=excluded.summary,
                                                   generated_at=CURRENT_TIMESTAMP""",
                 (date, evaluation, summary),
             )
            self._conn.commit()
            return True
        except sqlite3.Error:
            return False

    def get_all_evaluations(self):
        return [dict(r) for r in self._c().execute(
                "SELECT * FROM market_evaluation ORDER BY date DESC").fetchall()]