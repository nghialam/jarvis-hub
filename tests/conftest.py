"""Pytest fixtures for JH3.0 tests — provides a real SQLite DB for test blueprints."""
import sys
import os
import sqlite3
import tempfile

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# ---------- temp-db fixture ----------
@pytest.fixture(scope="session")
def test_db_path():
    """Create a temporary SQLite database with all tables."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)

    # Copy tables from real DB if available, otherwise create minimal schema
    real_db = os.path.join(os.path.dirname(__file__), "..", "data", "jarvis.db")
    if os.path.exists(real_db):
        # Attach real DB and copy all tables
        real = sqlite3.connect(real_db)
        for table in real.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall():
            name = table[0]
            sql = real.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}'").fetchone()[0]
            if sql:
                conn.execute(sql)
            rows = real.execute(f"SELECT * FROM {name}").fetchall()
            for row in rows:
                conn.execute(f"INSERT INTO {name} VALUES ({','.join(['?']*len(row))})", row)
        real.close()
    else:
        # Minimal schema for tests that need writes
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                name TEXT, price REAL, change_pct REAL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cms_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, content TEXT, slug TEXT,
                category TEXT, tags TEXT, published INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS portfolio_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, name TEXT, qty REAL, avg_price REAL
            );
            CREATE TABLE IF NOT EXISTS portfolio_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, action TEXT, qty REAL, price REAL, date TEXT
            );
            CREATE TABLE IF NOT EXISTS report_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, report_type TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS market_intelligence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT, run_period TEXT, status TEXT,
                articles_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS gotham_runs (
                run_id TEXT PRIMARY KEY, status TEXT, mode TEXT,
                date_str TEXT, pipeline_date TEXT, total_articles INTEGER,
                total_sources INTEGER, llm_chain_1_summary TEXT
            );
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT, title TEXT, url TEXT, category TEXT,
                sentiment TEXT, importance REAL, content TEXT,
                publication_date TEXT
            );
            CREATE TABLE IF NOT EXISTS trading_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, signal_type TEXT, severity TEXT,
                timestamp TIMESTAMP, alert_data TEXT, status TEXT
            );
            CREATE TABLE IF NOT EXISTS llm_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT, payload TEXT, status TEXT,
                result TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)

    conn.commit()
    conn.close()
    return tmp.name


@pytest.fixture(autouse=True)
def monkeypatch_db_for_tests(monkeypatch, test_db_path):
    """Inject the test DB path into core.config so the DB module picks it up."""
    import core.config as config_mod
    monkeypatch.setattr(config_mod, "DB_PATH", test_db_path)
    # Also clear the DB module from cache so it re-reads config
    if 'core.db' in sys.modules:
        del sys.modules['core.db']
    if 'core.context' in sys.modules:
        del sys.modules['core.context']


@pytest.fixture
def app():
    """Flask app with blueprints and auto-wired DB."""
    from flask import Flask
    from api import register_blueprints
    app = Flask(__name__)
    app.config['TESTING'] = True
    register_blueprints(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()
