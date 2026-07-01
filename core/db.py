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

            -- Hub 2.0 tables

            -- Market overview (pre-computed for fast dashboard load)
            CREATE TABLE IF NOT EXISTS market_overview (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE NOT NULL,
                symbol VARCHAR(20) NOT NULL,
                name TEXT,
                asset_type VARCHAR(20),
                price REAL,
                change_pct REAL,
                market_cap REAL,
                volume REAL,
                week_change REAL,
                month_change REAL,
                quarter_change REAL,
                chart_data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- News with enhanced metadata
            CREATE TABLE IF NOT EXISTS news_enhanced (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER,
                title TEXT NOT NULL,
                summary TEXT,
                content TEXT,
                url TEXT NOT NULL,
                source TEXT,
                published_at TIMESTAMP,
                fetched_at TIMESTAMP,
                category TEXT,
                sentiment TEXT,
                sentiment_score REAL,
                importance REAL,
                affected_symbols TEXT,
                is_trending BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Brokerage reports
            CREATE TABLE IF NOT EXISTS brokerage_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broker VARCHAR(10) NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                full_text TEXT,
                pdf_url TEXT,
                report_date DATE NOT NULL,
                crawled_at TIMESTAMP,
                rating INTEGER,
                target_index TEXT,
                sector_focus TEXT,
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Portfolio watchlist
            CREATE TABLE IF NOT EXISTS portfolio_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol VARCHAR(20) NOT NULL,
                name TEXT,
                sector TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                UNIQUE(symbol)
            );

            -- AI Intelligence: run_chains (LLM pipeline runs)
            CREATE TABLE IF NOT EXISTS run_chains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                pipeline_date TEXT NOT NULL,
                llm_chain_1_summary TEXT,
                llm_chain_3_summary TEXT,
                total_articles INTEGER DEFAULT 0,
                total_sources INTEGER DEFAULT 0,
                status TEXT DEFAULT 'complete',
                error_log TEXT,
                chain_started_at TIMESTAMP,
                chain_completed_at TIMESTAMP,
                duration_sec REAL
            );

            -- AI Intelligence: articles (per-crawl articles)
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                published_date TEXT,
                title TEXT NOT NULL,
                summary_raw TEXT,
                category TEXT DEFAULT 'general',
                sentiment TEXT DEFAULT 'TRUNG_LAP',
                sentiment_score REAL DEFAULT 0,
                url TEXT,
                has_image INTEGER DEFAULT 0,
                order_in_run INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- AI Intelligence: articles images
            CREATE TABLE IF NOT EXISTS articles_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER REFERENCES articles(id),
                image_url TEXT NOT NULL,
                caption TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- AI Intelligence: recommendations
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                article_id INTEGER REFERENCES articles(id),
                type TEXT NOT NULL,
                source_topic TEXT DEFAULT '',
                heading TEXT NOT NULL,
                detail_markdown TEXT,
                confidence_hint TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_market_overview_date ON market_overview(date DESC);
            CREATE INDEX IF NOT EXISTS idx_market_overview_symbol ON market_overview(symbol);
            CREATE INDEX IF NOT EXISTS idx_news_enhanced_category ON news_enhanced(category);
            CREATE INDEX IF NOT EXISTS idx_news_enhanced_importance ON news_enhanced(importance DESC);
            CREATE INDEX IF NOT EXISTS idx_news_enhanced_published ON news_enhanced(published_at DESC);
            CREATE INDEX IF NOT EXISTS idx_brokerage_reports_broker ON brokerage_reports(broker);
            CREATE INDEX IF NOT EXISTS idx_brokerage_reports_date ON brokerage_reports(report_date DESC);
            CREATE INDEX IF NOT EXISTS idx_brokerage_reports_broker_date ON brokerage_reports(broker, report_date DESC);
            CREATE INDEX IF NOT EXISTS idx_articles_run_id ON articles(run_id);
            CREATE INDEX IF NOT EXISTS idx_articles_sentiment ON articles(sentiment);
            CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
            CREATE INDEX IF NOT EXISTS idx_arts_img_article ON articles_images(article_id);
            CREATE INDEX IF NOT EXISTS idx_recs_run_id ON recommendations(run_id);
            CREATE INDEX IF NOT EXISTS idx_recs_type ON recommendations(type);
            CREATE INDEX IF NOT EXISTS idx_runs_date ON run_chains(pipeline_date DESC);
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

    # ---- Hub 2.0: Market overview ------------------------------------------------

    def save_market_overview(self, date, symbol, name, asset_type, price, change_pct,
                             market_cap=None, volume=None, week_change=None,
                             month_change=None, quarter_change=None, chart_data=None):
        """Save market overview data for one symbol."""
        with self._db_lock:
            self._c().execute(
                """INSERT INTO market_overview
                   (date, symbol, name, asset_type, price, change_pct, market_cap, volume,
                    week_change, month_change, quarter_change, chart_data)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (date, symbol, name, asset_type, price, change_pct,
                 market_cap, volume, week_change, month_change, quarter_change,
                 json.dumps(chart_data) if chart_data else None))
            self._conn.commit()

    def get_market_overview(self, date=None, symbol=None):
        """Get market overview entries."""
        q = "SELECT * FROM market_overview WHERE 1=1"
        params = []
        if date:
            q += " AND date=?"
            params.append(date)
        if symbol:
            q += " AND symbol=?"
            params.append(symbol)
        q += " ORDER BY updated_at DESC"
        return [dict(r) for r in self._c().execute(q, params).fetchall()]

    def get_latest_overview(self):
        """Get the latest market overview (one entry per symbol)."""
        rows = self._c().execute(
            """SELECT mo.* FROM market_overview mo
               INNER JOIN (
                   SELECT symbol, MAX(updated_at) as max_date FROM market_overview GROUP BY symbol
               ) latest ON mo.symbol = latest.symbol AND mo.updated_at = latest.max_date
               ORDER BY mo.updated_at DESC""").fetchall()
        return [dict(r) for r in rows]

    # ---- Hub 2.0: News enhanced ------------------------------------------------

    def save_news_enhanced(self, title, summary, content, url, source,
                           published_at, category, sentiment, sentiment_score,
                           importance=0, affected_symbols=None, article_id=None):
        """Save an enhanced news entry."""
        with self._db_lock:
            self._c().execute(
                """INSERT INTO news_enhanced
                   (article_id, title, summary, content, url, source, published_at,
                    category, sentiment, sentiment_score, importance, affected_symbols)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (article_id, title, summary, content, url, source, published_at,
                 category, sentiment, sentiment_score, importance,
                 json.dumps(affected_symbols) if affected_symbols else None))
            self._conn.commit()

    def get_news_enhanced(self, category=None, sentiment=None, limit=50, timeframe_days=7):
        """Get enhanced news entries with optional filters."""
        q = """SELECT * FROM news_enhanced WHERE 1=1"""
        params = []
        if category and category != "all":
            q += " AND category=?"
            params.append(category)
        if sentiment and sentiment != "all":
            q += " AND sentiment=?"
            params.append(sentiment)
        q += """ AND published_at >= datetime('now', '-{} days')""".format(timeframe_days)
        q += """ ORDER BY importance DESC, published_at DESC LIMIT ?"""
        params.append(limit)
        return [dict(r) for r in self._c().execute(q, params).fetchall()]

    def get_trending_news(self, limit=10):
        """Get trending (high importance) news."""
        return [dict(r) for r in self._c().execute(
            """SELECT * FROM news_enhanced
               WHERE importance >= 7 AND published_at >= datetime('now', '-7 days')
               ORDER BY importance DESC LIMIT ?""", (limit,)).fetchall()]

    # ---- Hub 2.0: Brokerage reports ------------------------------------------------

    def save_brokerage_report(self, broker, title, summary, full_text, pdf_url,
                              report_date, rating=None, target_index=None,
                              sector_focus=None, source_url=None):
        """Save a brokerage research report."""
        with self._db_lock:
            self._c().execute(
                """INSERT INTO brokerage_reports
                   (broker, title, summary, full_text, pdf_url, report_date, rating,
                    target_index, sector_focus, source_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (broker, title, summary, full_text, pdf_url, report_date,
                 rating, target_index, sector_focus, source_url))
            self._conn.commit()

    def get_brokerage_reports(self, broker=None, period="1m", limit=20):
        """Get brokerage reports with optional broker filter."""
        q = """SELECT * FROM brokerage_reports WHERE 1=1"""
        params = []
        if broker and broker != "all":
            q += " AND broker=?"
            params.append(broker)
        q += """ AND report_date >= datetime('now', '-{}')""".format(period)
        q += """ ORDER BY report_date DESC LIMIT ?"""
        params.append(limit)
        return [dict(r) for r in self._c().execute(q, params).fetchall()]

    def get_brokerage_stats(self):
        """Get report stats per broker."""
        rows = self._c().execute(
            """SELECT broker, COUNT(*) as count, MAX(report_date) as latest
               FROM brokerage_reports GROUP BY broker ORDER BY count DESC""").fetchall()
        return [dict(r) for r in rows]

    # ---- Hub 2.0: Portfolio watchlist ------------------------------------------------

    def add_portfolio_watchlist(self, symbol, name=None, sector=None):
        """Add or update a symbol in portfolio watchlist."""
        with self._db_lock:
            self._c().execute(
                """INSERT INTO portfolio_watchlist (symbol, name, sector)
                   VALUES (?,?,?)
                   ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, sector=excluded.sector, last_checked=CURRENT_TIMESTAMP""",
                (symbol.upper(), name or "", sector or ""))
            self._conn.commit()

    def get_portfolio_watchlist(self):
        """Get portfolio watchlist."""
        return [dict(r) for r in self._c().execute(
            "SELECT * FROM portfolio_watchlist ORDER BY added_at DESC").fetchall()]

    def remove_portfolio_watchlist(self, symbol):
        """Remove from portfolio watchlist."""
        with self._db_lock:
            self._c().execute("DELETE FROM portfolio_watchlist WHERE UPPER(symbol)=UPPER(?)", (symbol,))
            self._conn.commit()

    # ---- AI Intelligence: run_chains ------------------------------------------------

    def save_run_chain(self, run_id, pipeline_date, llm_chain_1_summary=None,
                       llm_chain_3_summary=None, total_articles=0, total_sources=0,
                       status="complete", error_log=None, duration_sec=None):
        """Save LLM pipeline run metadata."""
        with self._db_lock:
            self._c().execute(
                """INSERT OR REPLACE INTO run_chains
                   (run_id, pipeline_date, llm_chain_1_summary, llm_chain_3_summary,
                    total_articles, total_sources, status, error_log, duration_sec)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, pipeline_date, llm_chain_1_summary, llm_chain_3_summary,
                 total_articles, total_sources, status, error_log, duration_sec))
            self._conn.commit()

    def get_run_chains(self, limit=20):
        """Get recent run chains."""
        return [dict(r) for r in self._c().execute(
            "SELECT * FROM run_chains ORDER BY pipeline_date DESC LIMIT ?", (limit,)).fetchall()]

    def get_run_chain(self, run_id):
        """Get a specific run chain."""
        r = self._c().execute("SELECT * FROM run_chains WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    # ---- AI Intelligence: articles ------------------------------------------------

    def save_articles(self, run_id, articles):
        """Bulk save articles from a crawl run."""
        with self._db_lock:
            for i, art in enumerate(articles):
                self._c().execute(
                    """INSERT INTO articles
                       (run_id, published_date, title, summary_raw, category,
                        sentiment, sentiment_score, url, has_image, order_in_run)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, art.get("published_date"), art.get("title", ""),
                     art.get("summary_raw", ""), art.get("category", "general"),
                     art.get("sentiment", "TRUNG_LAP"), art.get("sentiment_score", 0),
                     art.get("url"), 1 if art.get("has_image") else 0, i))
                art_id = self._c().lastrowid
                if art.get("image_urls"):
                    for img_url in art["image_urls"]:
                        self._c().execute(
                            "INSERT INTO articles_images (article_id, image_url) VALUES (?,?)",
                            (art_id, img_url))
            self._conn.commit()

    def get_articles(self, run_id=None, category=None, sentiment=None, limit=50):
        """Get articles with optional filters."""
        q = "SELECT * FROM articles WHERE 1=1"
        params = []
        if run_id:
            q += " AND run_id=?"
            params.append(run_id)
        if category and category != "all":
            q += " AND category=?"
            params.append(category)
        if sentiment and sentiment != "all":
            q += " AND sentiment=?"
            params.append(sentiment)
        q += " ORDER BY order_in_run ASC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._c().execute(q, params).fetchall()]

    # ---- AI Intelligence: recommendations ------------------------------------------------

    def save_recommendations(self, run_id, recs):
        """Bulk save recommendations from LLM output."""
        with self._db_lock:
            for rec in recs:
                self._c().execute(
                    """INSERT INTO recommendations
                       (run_id, article_id, type, source_topic, heading,
                        detail_markdown, confidence_hint)
                       VALUES (?,?,?,?,?,?,?)""",
                    (run_id, rec.get("article_id"), rec.get("type", ""),
                     rec.get("source_topic", ""), rec.get("heading", ""),
                     rec.get("detail_markdown", ""), rec.get("confidence_hint")))
            self._conn.commit()

    def get_recommendations(self, run_id=None, rec_type=None, limit=50):
        """Get recommendations with optional filters."""
        q = "SELECT * FROM recommendations WHERE 1=1"
        params = []
        if run_id:
            q += " AND run_id=?"
            params.append(run_id)
        if rec_type and rec_type != "all":
            q += " AND type=?"
            params.append(rec_type)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._c().execute(q, params).fetchall()]

    # ---- Hub 2.0: News importance scoring ------------------------------------------------

    def update_news_importance(self, article_id, importance, reason):
        """Update importance score for a news article."""
        with self._db_lock:
            self._c().execute(
                """UPDATE news_enhanced
                   SET importance=?, importance_reason=?
                   WHERE id=?""",
                (importance, reason, article_id))
            self._conn.commit()
