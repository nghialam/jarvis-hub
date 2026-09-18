"""Pytest fixtures for JH3.0 tests — provides a real SQLite DB for test blueprints."""
import sys
import os
import sqlite3
import tempfile
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope="session")
def test_db_path():
    """Create a temporary SQLite database with all tables, copied from the real DB."""
    real_db = os.path.join(os.path.dirname(__file__), '..', 'data', 'jarvis.db')

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.execute("PRAGMA foreign_keys = ON")

    if os.path.exists(real_db):
        real = sqlite3.connect(real_db)
        real.row_factory = sqlite3.Row

        tables = [
            row[0] for row in real.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '%_fts%'"
            ).fetchall()
        ]

        for name in tables:
            sql = real.execute(
                f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{name}'"
            ).fetchone()
            if sql and sql[0]:
                try:
                    conn.execute(sql[0])
                except sqlite3.OperationalError:
                    pass

            try:
                rows = real.execute(f"SELECT * FROM {name}").fetchall()
                for row in rows:
                    placeholders = ','.join(['?'] * len(row))
                    conn.execute(
                        f"INSERT OR IGNORE INTO {name} VALUES ({placeholders})",
                        list(row)
                    )
            except sqlite3.OperationalError:
                pass

        real.close()
    else:
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
                title TEXT, report_type TEXT, content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS market_intelligence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT, run_period TEXT, status TEXT,
                articles_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

    conn.commit()
    conn.close()
    return tmp.name


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db(test_db_path):
    """Install test DB into core.context so blueprints pick it up."""
    from core.db import Database
    from core.context import init_context

    # Create the real DB instance pointing to our test DB
    test_db = Database(test_db_path)

    # Inject a minimal config (tests don't need full YAML config)
    test_config = {
        "db_path": test_db_path,
        "debug": True,
        "testing": True,
        "log_level": "DEBUG",
        "ollama": {"url": "http://localhost:11434", "model": "test"},
    }

    # Register it in the shared context
    init_context(test_db, test_config)

    # Ensure CMS table exists (it's in the real schema but may not be in data/jarvis.db)
    test_db.init_cms_table()

    # Clear any cached modules that might have loaded the real DB
    for mod in list(sys.modules.keys()):
        if mod.startswith('core.') and mod not in ('core.config', 'core.context'):
            del sys.modules[mod]


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
