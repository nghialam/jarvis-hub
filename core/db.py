"""
db.py -- SQLite database for Jarvis Hub (Knowledge Base, Activity Log)

All datetime stored as ISO strings. Uses WAL journal mode for perf.
Thread-safe via _db_lock on all write operations.
"""
import json
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from threading import Lock, Thread
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

         # Thread safety: use check_same_thread=False since we have _db_lock for write serialization
        self._db_lock = Lock()
        self._conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")   # Wait up to 5s for locks
        self._conn.execute("PRAGMA foreign_keys=ON")
        
        # Auto-recovery: check integrity on startup, attempt repair if needed
        self._attempt_recovery()
        self.init_db()
        # Bind orphan methods (indent broken in this file) so they act as instance methods
        _bind_orphans(self)

    def _attempt_recovery(self):
        """Check DB integrity and attempt auto-recovery if corrupted."""
        try:
            c = self._conn.cursor()
            c.execute("PRAGMA integrity_check")
            result = c.fetchone()[0]
            
            if result != "ok":
                print("[DB] WARNING: Database integrity check failed (%s)" % result)
                # Attempt basic recovery
                backup_path = str(self.db_path) + ".bak." + datetime.now().strftime("%Y%m%d%H%M%S")
                try:
                    import shutil
                    if os.path.exists(str(self.db_path)):
                        shutil.copy2(str(self.db_path), backup_path)
                        print("[DB] Backup created at %s" % backup_path)
                except Exception:
                    pass
                
                # Try VACUUM first (often fixes corruption)
                try:
                    c.execute("VACUUM")
                    c.execute("REINDEX")
                    print("[DB] Auto-recovery succeeded with VACUUM REINDEX")
                except sqlite3.Error as e2:
                    print("[DB] WARN: Auto-recovery failed, continuing but DB may be unstable", file=sys.stderr)
        except Exception as e:
            print("[DB] WARN: Could not check integrity on startup: %s" % str(e), file=sys.stderr)

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


            CREATE TABLE IF NOT EXISTS market_evaluations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                date          TEXT UNIQUE NOT NULL,
                evaluation    TEXT NOT NULL,
                summary       TEXT DEFAULT '',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               );

            CREATE TABLE IF NOT EXISTS trading_alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT     NOT NULL COLLATE NOCASE,
                signal_type  TEXT     NOT NULL DEFAULT 'NEUTRAL',          -- STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL
                severity     TEXT     NOT NULL DEFAULT 'LOW',             -- LOW / MEDIUM / HIGH / CRITICAL
                alert_data   TEXT,                                        -- JSON blob: {price, change_pct, rsi, sma_20, macd_histogram, signal_reason}
                status       TEXT     NOT NULL DEFAULT 'unread',          -- unread / read
                timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               );

            CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON trading_alerts(symbol);
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON trading_alerts(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_alerts_status   ON trading_alerts(status);
            CREATE TABLE IF NOT EXISTS market_intelligence (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date       TEXT    NOT NULL,
                run_period     TEXT    NOT NULL DEFAULT 'daily',  -- daily / weekly
                articles_json  TEXT    NOT NULL,                 -- JSON array of processed articles
                market_brief   TEXT,                             -- synthesized market brief content
                status         TEXT  NOT NULL DEFAULT 'Notification Ready',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_mi_run_date ON market_intelligence(run_date DESC);
            CREATE INDEX IF NOT EXISTS idx_mi_created_at ON market_intelligence(created_at DESC);           """)
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
        with self._db_lock:
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
        """Search knowledge base with relevance scoring based on term/content matches."""
        cleaned = query.strip().lower()
        if not cleaned or len(cleaned) < 2:
            return []

         # Filter out noise words
        stop_words = {'la', 'va', 'hoac', 'trong', 'cua', 'de', 'du', 'co',
                       'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                       'will', 'would', 'could', 'should', 'may', 'might', 'must',
                       'can', 'a', 'an', 'the', 'at', 'to', 'for', 'of', 'in',
                       'on', 'with', 'by', 'from', 'about'}
        meaningful_words = [w for w in cleaned.split() if len(w) >= 3 and w not in stop_words]

        if not meaningful_words:
            meaningful_words = cleaned.split()[:2]

        results = {}

         # Phase 1: Term column search (HIGH PRIORITY)
        for word in meaningful_words[:3]:
            r = self._c().execute(
                 "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(term) LIKE ?",
                 ('%' + word + '%',)).fetchall()

            for row in r:
                d = dict(row)
                term_lower = d['term'].lower()
                score = 0

                 # Exact query-to-term match is strongest signal
                if term_lower == cleaned or term_lower.startswith(cleaned):
                    score += 30

                 # Word-by-word scoring with order bonus
                term_words_list = term_lower.split()
                matched_count = 0
                word_order_correct = True
                last_term_idx = -1

                for qi, qword in enumerate(meaningful_words[:2]):
                    if qword in term_words_list:
                        matched_count += 1
                        tpos = term_words_list.index(qword)
                        if tpos < last_term_idx and matched_count > 1:
                            word_order_correct = False
                        last_term_idx = tpos

                if matched_count >= 2 and word_order_correct:
                    score += 50    # Words match IN ORDER - strongest relevance signal
                elif matched_count >= 2:
                    score += 35    # Both words found but order uncertain
                elif matched_count == 1:
                    score += 20    # One word matched

                if not any(ww in term_lower for ww in meaningful_words[:2]):
                    score += 5     # Weak partial match

                existing = results.get(d['term'])
                if existing is None or score > existing[0]:
                    results[d['term']] = (score, d)

         # Phase 2: Content match fallback (only if no strong term match found)
        filtered_results = {k: v for k, v in results.items() if v[0] >= 20}

        if not filtered_results:
            for i in range(len(meaningful_words)):
                pattern1 = '%' + meaningful_words[i] + '%'
                if i + 1 < len(meaningful_words):
                    pattern2 = '%' + meaningful_words[i + 1] + '%'
                    r = self._c().execute(
                         "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(content) LIKE ? AND LOWER(content) LIKE ?",
                         (pattern1, pattern2)).fetchall()

                    for row in r:
                        d = dict(row)
                        if d['term'] not in results:
                            content_lower = d['content'].lower()
                            pos1 = content_lower.find(pattern1.replace('%', ''))
                            pos2 = content_lower.find(pattern2.replace('%', ''))
                            score = 10
                            if pos1 >= 0 and pos2 >= 0 and pos1 < pos2:
                                score = 25    # Words in correct order in content

                            results[d['term']] = (score, d)
                else:
                    r = self._c().execute(
                         "SELECT id, term, content, tags, updated_at FROM knowledge WHERE LOWER(content) LIKE ?",
                         (pattern1,)).fetchall()
                    for row in r:
                        d = dict(row)
                        if d['term'] not in results:
                            results[d['term']] = (5, d)

         # Phase 3: Sort by score and return
        sorted_results = sorted(results.items(), key=lambda x: x[0], reverse=True)
        return [item[1] for item in sorted_results[:limit]] if sorted_results else []

    def get_all_terms(self):
        """Get all terms with update timestamps."""
        return [dict(r) for r in self._c().execute(
              "SELECT term, updated_at FROM knowledge ORDER BY updated_at DESC").fetchall()]

     # ---- activity log -------------------------------------------------------

    def log_activity(self, command, args="", status="ok", summary=None, duration_ms=None):
        """Log activity to the database (thread-safe)."""
        with self._db_lock:
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
        """Save or update a daily snapshot (thread-safe)."""
        with self._db_lock:
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
        """Add a symbol to watchlist (thread-safe)."""
        with self._db_lock:
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
        with self._db_lock:
            c = self._c()
            c.execute("DELETE FROM watchlist WHERE UPPER(symbol)=UPPER(?)", (symbol,))
            self._conn.commit()
            return c.rowcount > 0

     # ---- market cache -------------------------------------------------------

    def save_market_data(self, symbol, data, ttl_minutes=60):
        """Save cached market data for a symbol (thread-safe)."""
        with self._db_lock:
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

      # ---- market evaluations -------------------------------------------------

    def save_market_evaluation(self, date, evaluation, summary=""):
        """Save a daily market evaluation (thread-safe)."""
        with self._db_lock:
            c = self._c()
            try:
                c.execute(
                       """INSERT INTO market_evaluations (date, evaluation, summary) VALUES (?, ?, ?)
                        ON CONFLICT(date) DO UPDATE SET evaluation=excluded.evaluation, summary=excluded.summary""",
                        (date, evaluation, summary))
                self._conn.commit()
            except sqlite3.Error:
                pass

    def get_all_evaluations(self):
        return [dict(r) for r in self._c().execute(
               "SELECT * FROM market_evaluations ORDER BY date DESC").fetchall()]

    def get_today_evaluation(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return dict(self._c().execute("SELECT * FROM market_evaluations WHERE date=?", (today,)).fetchone()) or None

    # ---- trading alerts ----------------------------------------------------

    def get_alerts(self, signal=None, severity=None, symbol=None):
        """Get trading alerts with optional filters. Sorted by timestamp DESC."""
        conditions = ["1=1"]
        params = []
        if signal:
            conditions.append("signal_type = ?")
            params.append(signal.upper())
        if severity:
            conditions.append("severity = ?")
            params.append(severity.upper())
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol.upper())
        where = " AND ".join(conditions)
        rows = self._c().execute(
            f"SELECT * FROM trading_alerts WHERE {where} ORDER BY timestamp DESC LIMIT 100",
            params,
        ).fetchall()
        alerts = [dict(r) for r in rows]
        # Parse JSON alert_data
        import json as _json
        for a in alerts:
            raw = a.get("alert_data")
            if isinstance(raw, str):
                try:
                    a["alert_data"] = _json.loads(raw)
                except Exception:
                    pass
        return alerts

    def mark_alerts_as_read(self):
        """Mark all alerts as read."""
        with self._db_lock:
            self._c().execute("UPDATE trading_alerts SET status = 'read'")
            self._conn.commit()
            return True

    def get_unread_count(self):
        """Count unread alerts."""
        r = self._c().execute(
            "SELECT COUNT(*) AS cnt FROM trading_alerts WHERE status = 'unread'"
        ).fetchone()
        return r["cnt"] if r else 0

    # ---- Market Intelligence Agent (v2.0) ------------------------------------

    def save_market_intelligence(self, run_date, run_period, articles_json, market_brief, status="Notification Ready"):
        """Save a complete market intelligence run to DB."""
        with self._db_lock:
            c = self._c()
            try:
                c.execute(
                    """INSERT INTO market_intelligence
                       (run_date, run_period, articles_json, market_brief, status)
                      VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT(run_date, run_period) DO UPDATE SET
                        articles_json=excluded.articles_json,
                        market_brief=excluded.market_brief,
                        status=excluded.status,
                        created_at=CURRENT_TIMESTAMP""",
                    (run_date, run_period, articles_json, market_brief, status))
                self._conn.commit()
                return c.lastrowid
            except sqlite3.Error:
                return 0

    def get_latest_market_intelligence(self):
        """Get the most recent market intelligence run."""
        r = self._c().execute(
            "SELECT * FROM market_intelligence ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if r:
            d = dict(r)
            try:
                d["articles"] = json.loads(d.get("articles_json", "[]"))
            except Exception:
                d["articles"] = []
            return d
        return None

    def get_market_intelligence_history(self, limit=10, period=None):
        """List past runs with optional period filter."""
        if period:
            rows = self._c().execute(
                "SELECT id, run_date, run_period, status, created_at, articles_json, market_brief "
                "FROM market_intelligence WHERE run_period=? ORDER BY created_at DESC LIMIT ?",
                (period, limit)
            ).fetchall()
        else:
            rows = self._c().execute(
                "SELECT id, run_date, run_period, status, created_at, articles_json, market_brief "
                "FROM market_intelligence ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                articles = json.loads(d.get("articles_json", "[]"))
                sentiments = [a.get("sentiment", "Neutral") for a in articles if isinstance(a, dict)]
                bull = sentiments.count("Bullish")
                bear = sentiments.count("Bearish")
                neu = sentiments.count("Neutral")
                d["article_count"] = len(articles)
                d["sentiment_summary"] = {"bullish": bull, "bearish": bear, "neutral": neu}
            except Exception:
                d["article_count"] = 0
                d["sentiment_summary"] = {"bullish": 0, "bearish": 0, "neutral": 0}
            result.append(d)
        return result

    def get_market_intelligence_by_id(self, run_id):
        """Get specific run by ID."""
        r = self._c().execute(
            "SELECT * FROM market_intelligence WHERE id=?", (run_id,)
        ).fetchone()
        if r:
            d = dict(r)
            try:
                d["articles"] = json.loads(d.get("articles_json", "[]"))
            except Exception:
                d["articles"] = []
            return d
        return None

    def delete_market_intelligence(self, run_id):
        """Delete a specific run."""
        with self._db_lock:
            c = self._c()
            c.execute("DELETE FROM market_intelligence WHERE id=?", (run_id,))
            self._conn.commit()
            return c.rowcount > 0

    def get_sentiment_distribution(self):
        """Get Bullish/Bearish/Neutral counts across all articles."""
        rows = self._c().execute(
            "SELECT articles_json FROM market_intelligence"
        ).fetchall()
        totals = {"Bullish": 0, "Bearish": 0, "Neutral": 0}
        total_articles = 0
        for r in rows:
            try:
                articles = json.loads(r["articles_json"])
                for a in articles:
                    if isinstance(a, dict) and "sentiment" in a:
                        s = a["sentiment"]
                        if s in totals:
                            totals[s] += 1
                        total_articles += 1
            except Exception:
                pass
        totals["total"] = total_articles
        return totals

     # ---- CMS / Manual Articles ----------------------------------------------

    def init_cms_table(self):
        """Create articles table if it does not already exist."""
        with self._db_lock:
            self._c().executescript("""
                CREATE TABLE IF NOT EXISTS cms_articles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT    NOT NULL,
                    slug        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                    content     TEXT    NOT NULL DEFAULT '',
                    category    TEXT    NOT NULL DEFAULT 'general',
                    featured_image TEXT DEFAULT '',
                    tags        TEXT    DEFAULT '',
                    status      TEXT    NOT NULL DEFAULT 'published',   -- published | draft
                    view_count  INTEGER NOT NULL DEFAULT 0,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self._conn.commit()

    def save_article(self, slug, title, content, category='general', featured_image='', tags=None, article_id=None):
        """Create or update a CMS article. Returns the article id."""
        with self._db_lock:
            c = self._c()
            now = _utc_now_iso()
            tags_json = json.dumps(tags or [])
            if article_id:
                c.execute("""
                    UPDATE cms_articles SET
                        title=?, content=?, category=?, featured_image=?,
                        tags=?, updated_at=? WHERE id=?
                """, (title, content, category, featured_image, tags_json, now, int(article_id)))
                return int(article_id)
            # New article
            c.execute("""
                INSERT INTO cms_articles (slug, title, content, category, featured_image, tags, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?)
            """, (slug, title, content, category, featured_image, tags_json, now, now))
            return c.lastrowid

    def get_all_published_articles(self):
        """Return all published articles ordered by created_at desc."""
        return [dict(r) for r in self._c().execute(
            "SELECT id, slug, title, category, featured_image, tags, status, view_count, updated_at FROM cms_articles WHERE status='published' ORDER BY updated_at DESC"
        ).fetchall()]

    def get_article_by_slug(self, slug):
        """Return a single published article by slug, incrementing view_count."""
        c = self._c()
        r = c.execute(
            "SELECT * FROM cms_articles WHERE slug=? AND status='published'", (slug,)
        ).fetchone()
        if r:
            c.execute("UPDATE cms_articles SET view_count=view_count+1 WHERE id=?", (r['id'],))
            self._conn.commit()
            d = dict(r)
            try:
                d['tags'] = json.loads(d.get('tags', '[]'))
            except Exception:
                d['tags'] = []
            return d
        return None

    def get_article_by_id(self, article_id):
        """Return a single CMS article by ID (any status)."""
        r = self._c().execute(
            "SELECT * FROM cms_articles WHERE id=?", (int(article_id),)
        ).fetchone()
        if r:
            d = dict(r)
            try:
                d['tags'] = json.loads(d.get('tags', '[]'))
            except Exception:
                d['tags'] = []
            return d
        return None

    def update_article_status(self, article_id, status):
        """Update the status (published/draft) of an article."""
        if status not in ('published', 'draft'):
            return False
        with self._db_lock:
            c = self._c()
            now = _utc_now_iso()
            c.execute("UPDATE cms_articles SET status=?, updated_at=? WHERE id=?", (status, now, int(article_id)))
            self._conn.commit()
            return c.rowcount > 0

    def delete_article(self, article_id):
        """Delete an article by ID."""
        with self._db_lock:
            c = self._c()
            c.execute("DELETE FROM cms_articles WHERE id=?", (int(article_id),))
            self._conn.commit()
            return c.rowcount > 0


# -- Orphan method binder (fixes indent-broken methods further down) --
# Binds module-level orphan functions into Database instance methods via MethodType

def _bind_orphans(db_instance):
    mod = sys.modules[__name__]
    orphan_names = [
         'init_research_tables',
         'save_research_item',
         'get_research_items',
         'get_research_item_by_url',
         'delete_research_item',
         'add_backlog_task',
         'get_backlog_tasks',
         'in_progress',
         'update_backlog_task',
         'complete_backlog_task',
         'delete_backlog_task',
         'add_portfolio_transaction',
         'get_portfolio_transactions',
         'get_portfolio_holdings',
         'delete_portfolio_transaction',
     ]
    from types import MethodType
    for name in orphan_names:
        fn = getattr(mod, name, None)
        if fn is not None:
            setattr(db_instance, name, MethodType(fn, db_instance))
    if hasattr(db_instance, 'init_research_tables'):
        db_instance.init_research_tables()


# ---- Research Intelligence --------------------------------------------------

def init_research_tables(self):
    """Create research_items and backlog_tasks tables if they do not exist."""
    with self._db_lock:
        self._c().executescript("""
            CREATE TABLE IF NOT EXISTS research_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url   TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                title        TEXT    NOT NULL,
                summary      TEXT    NOT NULL DEFAULT '',
                content      TEXT    NOT NULL DEFAULT '',
                author       TEXT    DEFAULT '',
                published_at TEXT    DEFAULT '',
                research_date TEXT   NOT NULL,
                tags         TEXT    DEFAULT '[]',
                status       TEXT    NOT NULL DEFAULT 'processed',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_research_date ON research_items(research_date DESC);
            CREATE INDEX IF NOT EXISTS idx_research_url  ON research_items(source_url);

            CREATE TABLE IF NOT EXISTS backlog_tasks (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                research_item_id INTEGER DEFAULT NULL REFERENCES research_items(id),
                title          TEXT    NOT NULL,
                description    TEXT    NOT NULL DEFAULT '',
                priority       TEXT    NOT NULL DEFAULT 'MEDIUM',
                status         TEXT    NOT NULL DEFAULT 'pending',
                estimated_hours REAL   DEFAULT 0,
                notes          TEXT    DEFAULT '',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at   TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
             );

            CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog_tasks(status);
            CREATE INDEX IF NOT EXISTS idx_backlog_priority ON backlog_tasks(priority);
            CREATE INDEX IF NOT EXISTS idx_backlight_research ON backlog_tasks(research_item_id);

            CREATE TABLE IF NOT EXISTS portfolio_transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol     TEXT    NOT NULL COLLATE NOCASE,
                name       TEXT    DEFAULT '',
                action     TEXT    NOT NULL DEFAULT 'buy',  -- buy / sell
                quantity   REAL    NOT NULL,
                price      REAL    NOT NULL,               -- VND per share (x1000 applied)
                txn_date   TEXT    NOT NULL DEFAULT (date('now')),
                note       TEXT    DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
             );

            CREATE INDEX IF NOT EXISTS idx_portfolio_symbol ON portfolio_transactions(symbol);
            CREATE INDEX IF NOT EXISTS idx_portfolio_date   ON portfolio_transactions(txn_date DESC);
         """)
        self._conn.commit()


def save_research_item(self, url, title, summary='', content='', author='', tags=None, published_at=''):
    """Save or update a research item by URL (upsert, thread-safe)."""
    with self._db_lock:
        c = self._c()
        now = _utc_now_iso()
        tags_json = json.dumps(tags or [])
        try:
            c.execute("""
                INSERT INTO research_items
                    (source_url, title, summary, content, author, published_at, research_date, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_url) DO UPDATE SET
                    title=excluded.title,
                    summary=excluded.summary,
                    content=excluded.content,
                    author=excluded.author,
                    published_at=excluded.published_at,
                    tags=excluded.tags,
                    updated_at=?
            """, (url, title, summary, content, author, published_at, now, tags_json, now))
            self._conn.commit()
            return c.lastrowid
        except sqlite3.Error:
            return 0


def get_research_items(self, limit=20, status=None):
    """Query research items with optional filters."""
    conditions = ['1=1']
    params = []
    if status:
        conditions.append('status = ?')
        params.append(status.upper())
    where = ' AND '.join(conditions)
    rows = self._c().execute(
        f'SELECT * FROM research_items WHERE {where} ORDER BY research_date DESC LIMIT ?',
        params + [limit]
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d['tags'] = json.loads(d.get('tags', '[]'))
        except Exception:
            d['tags'] = []
        result.append(d)
    return result


def get_research_item_by_url(self, url):
    """Get a single research item by source URL."""
    r = self._c().execute('SELECT * FROM research_items WHERE source_url=?', (url,)).fetchone()
    if r:
        d = dict(r)
        try:
            d['tags'] = json.loads(d.get('tags', '[]'))
        except Exception:
            d['tags'] = []
        return d
    return None


def delete_research_item(self, item_id):
    """Delete a research item."""
    with self._db_lock:
        c = self._c()
        c.execute('DELETE FROM backlog_tasks WHERE research_item_id=?', (int(item_id),))
        c.execute('DELETE FROM research_items WHERE id=?', (int(item_id),))
        self._conn.commit()
        return True


# ---- Backlog Tasks ----------------------------------------------------------

def add_backlog_task(self, title, description='', priority='MEDIUM', research_item_id=None, estimated_hours=0, notes=''):
    """Add a task to backlog (thread-safe). Returns task id."""
    with self._db_lock:
        c = self._c()
        try:
            c.execute("""
                INSERT INTO backlog_tasks
                    (research_item_id, title, description, priority, estimated_hours, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (research_item_id, title, description, priority.upper(), estimated_hours, notes))
            self._conn.commit()
            return c.lastrowid
        except sqlite3.Error:
            return 0


def get_backlog_tasks(self, research_item_id=None, status=None, limit=20):
    """Get backlog tasks with optional filters."""
    conditions = ['1=1']
    params = []
    if research_item_id is not None:
        conditions.append('research_item_id = ?')
        params.append(int(research_item_id))
    if status:
        conditions.append('status = ?')
        params.append(status.upper())
    where = ' AND '.join(conditions)
    rows = self._c().execute(
        f'SELECT * FROM backlog_tasks WHERE {where} ORDER BY '
        "CASE priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END, "
        'created_at DESC LIMIT ?',
        params + [limit]
    ).fetchall()
    return [dict(r) for r in rows]


def in_progress(self):
    """Get tasks currently in_progress."""
    return self.get_backlog_tasks(status='in_progress')


def update_backlog_task(self, task_id, **kwargs):
    """Update backlog task fields. Returns True if updated."""
    if not kwargs:
        return False
    with self._db_lock:
        c = self._c()
        set_parts = []
        params = []
        for k, v in kwargs.items():
            if k in ('title', 'description', 'priority', 'estimated_hours', 'notes', 'status'):
                set_parts.append(f'{k}=?')
                params.append(v)
        if 'status' in kwargs and kwargs['status'] == 'done':
            set_parts.append('completed_at=?')
            params.append(_utc_now_iso())
        set_parts.append('updated_at=?')
        params.append(_utc_now_iso())
        params.append(int(task_id))
        c.execute(f"UPDATE backlog_tasks SET {', '.join(set_parts)} WHERE id=?", params)
        self._conn.commit()
        return c.rowcount > 0


def complete_backlog_task(self, task_id):
    """Mark a backlog task as done with timestamp."""
    return self.update_backlog_task(task_id, status='done')


def delete_backlog_task(self, task_id):
    """Delete a backlog task."""
    with self._db_lock:
        self._c().execute('DELETE FROM backlog_tasks WHERE id=?', (int(task_id),))
        self._conn.commit()
        return True

# ---- Portfolio Transactions -------------------------------------------------------

def add_portfolio_transaction(self, symbol, action='buy', quantity=0, price=0, name='', txn_date=None, note=''):
    """Add a buy/sell transaction. Returns transaction id."""
    with self._db_lock:
        c = self._c()
        d = txn_date or datetime.utcnow().strftime('%Y-%m-%d')
        c.execute(
            "INSERT INTO portfolio_transactions (symbol, name, action, quantity, price, txn_date, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol.upper(), name, action.lower(), float(quantity), float(price), d, note)
        )
        self._conn.commit()
        return c.lastrowid

def get_portfolio_transactions(self, symbol=None, limit=100):
    """Get transaction history, optionally filtered by symbol."""
    conditions = []
    params = []
    if symbol:
        conditions.append('symbol = ?')
        params.append(symbol.upper())
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    rows = self._c().execute(
        f'SELECT * FROM portfolio_transactions{where} ORDER BY txn_date DESC, id DESC LIMIT ?',
        params + [limit]
    ).fetchall()
    return [dict(r) for r in rows]

def get_portfolio_holdings(self):
    """Calculate current holdings: net quantity per symbol, avg buy cost, total invested."""
    rows = self._c().execute("""
        SELECT
            symbol,
            MAX(name) AS name,
            SUM(CASE WHEN action='buy'  THEN quantity ELSE -quantity END) AS net_quantity,
            ROUND(
                SUM(CASE WHEN action='buy'  THEN quantity * price ELSE 0 END) /
                NULLIF(ABS(SUM(CASE WHEN action='buy' THEN quantity ELSE 0 END)), 0),
                2
            ) AS avg_cost,
            ROUND(SUM(CASE WHEN action='buy'  THEN quantity * price ELSE 0 END), 2) AS total_bought,
            ROUND(SUM(CASE WHEN action='sell' THEN quantity * price ELSE 0 END), 2) AS total_sold
        FROM portfolio_transactions
        GROUP BY symbol
        HAVING net_quantity > 0
        ORDER BY symbol
    """).fetchall()
    return [dict(r) for r in rows]

def delete_portfolio_transaction(self, txn_id):
    """Delete a single transaction by ID."""
    with self._db_lock:
        self._c().execute('DELETE FROM portfolio_transactions WHERE id=?', (int(txn_id),))
        self._conn.commit()
        return True

# ---- End of file ---
