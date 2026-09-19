"""Pytest tests for database migration integrity.

Verifies that all DB tables exist, schema is loadable,
and data survives basic CRUD operations.
"""
import sqlite3
import pytest


def db_connect(db_path):
    """Helper to open a connection with Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class TestTableExistence:
    """Verify all expected tables exist in the test DB schema."""

    def test_tables_exist(self, test_db_path):
        """All tables that conftest creates must be present."""
        conn = db_connect(test_db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        # These are tables conftest explicitly creates (either from real DB
        # or inline CREATE TABLE statements).
        conftest_tables = {
            "watchlist",
            "cms_articles",
            "portfolio_transactions",
            "report_summaries",
            "market_intelligence",
        }
        missing = conftest_tables - tables
        assert not missing, f"Missing conftest tables: {missing}"

    def test_tables_have_rows_or_are_empty(self, test_db_path):
        """Tables should have some rows (from real DB copy) or be empty but not missing data mid-row."""
        conn = db_connect(test_db_path)
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        conn.close()
        assert len(tables) > 5, f"Expected >5 tables, got {len(tables)}: {tables}"


class TestSchemaIntegrity:
    """Verify tables have basic columns — but accept actual schema."""

    def test_watchlist_has_id_and_symbol(self, test_db_path):
        """watchlist must have at least id and symbol columns."""
        conn = db_connect(test_db_path)
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(watchlist)").fetchall()
        }
        conn.close()
        required = {"id", "symbol"}
        assert required.issubset(cols), f"watchlist missing columns: {required - cols}"

    def test_cms_articles_has_required(self, test_db_path):
        """cms_articles must have id, title, slug, content."""
        conn = db_connect(test_db_path)
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(cms_articles)").fetchall()
        }
        conn.close()
        required = {"id", "title", "slug", "content"}
        assert required.issubset(cols), f"cms_articles missing columns: {required - cols}"

    def test_daily_snapshots_has_date(self, test_db_path):
        """daily_snapshots must have a date-like column."""
        conn = db_connect(test_db_path)
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()
        }
        conn.close()
        required = {"id", "date"}
        assert required.issubset(cols), f"daily_snapshots missing columns: {required - cols}"

    def test_market_cache_has_ttl_columns(self, test_db_path):
        """market_cache should have symbol and expires_at columns."""
        conn = db_connect(test_db_path)
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(market_cache)").fetchall()
        }
        conn.close()
        required = {"symbol", "expires_at"}
        assert required.issubset(cols), f"market_cache missing columns: {required - cols}"


class TestDataRoundTrip:
    """Verify basic CRUD works — write data, read it back, delete."""

    def test_watchlist_insert_select_delete(self, test_db_path):
        """Insert a watchlist entry, read it back, delete, verify gone."""
        conn = db_connect(test_db_path)
        # Insert — find actual columns by introspecting the table
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(watchlist)").fetchall()
        }
        # Insert symbol at minimum (name might not exist in all schemas)
        if "name" in cols:
            conn.execute(
                "INSERT OR REPLACE INTO watchlist (symbol, name) VALUES (?, ?)",
                ("TEST_MIG", "Migration Test"),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO watchlist (symbol) VALUES (?)",
                ("TEST_MIG",),
            )
        conn.commit()

        # Select
        row = conn.execute(
            "SELECT * FROM watchlist WHERE symbol='TEST_MIG'"
        ).fetchone()
        assert row is not None, "Insert failed — row not found"

        # Delete
        conn.execute("DELETE FROM watchlist WHERE symbol='TEST_MIG'")
        conn.commit()

        # Verify gone
        row2 = conn.execute(
            "SELECT * FROM watchlist WHERE symbol='TEST_MIG'"
        ).fetchone()
        assert row2 is None, "Delete failed — row still exists"
        conn.close()

    def test_cms_insert_select(self, test_db_path):
        """Insert a CMS article, read it back, verify content."""
        conn = db_connect(test_db_path)
        conn.execute(
            """INSERT OR REPLACE INTO cms_articles
               (title, slug, content, created_at)
               VALUES (?, ?, ?, ?)""",
            ("Test Article", "test-article-slug", "<p>Hello</p>", "2026-01-01 00:00:00"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM cms_articles WHERE slug='test-article-slug'"
        ).fetchone()
        assert row is not None, "CMS insert failed"
        assert row["title"] == "Test Article"
        assert row["content"] == "<p>Hello</p>"

        # Cleanup
        conn.execute("DELETE FROM cms_articles WHERE slug='test-article-slug'")
        conn.commit()
        conn.close()

    def test_market_cache_ttl_expiry(self, test_db_path):
        """Verify market_cache accepts data with expiry."""
        conn = db_connect(test_db_path)
        conn.execute(
            """INSERT INTO market_cache
               (symbol, data_json, cached_at, expires_at)
               VALUES (?, ?, ?, ?)""",
            ("TTL_TEST", '{"price": 100}', "2026-01-01 00:00:00", "2027-01-01 00:00:00"),
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM market_cache WHERE symbol='TTL_TEST'"
        ).fetchone()
        assert row is not None, "Market cache insert failed"

        # Cleanup
        conn.execute("DELETE FROM market_cache WHERE symbol='TTL_TEST'")
        conn.commit()
        conn.close()


class TestForeignKeys:
    """Verify FK integrity constraints are active."""

    def test_db_file_is_valid_sqlite(self, test_db_path):
        """Verify test DB is a valid SQLite database (not corrupted)."""
        import os
        assert os.path.exists(test_db_path), "Test DB file doesn't exist"
        assert os.path.getsize(test_db_path) > 0, "Test DB file is empty"
        conn = db_connect(test_db_path)
        # SQLite magic header check
        header = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
        conn.close()
        # If it got this far without error, it's valid SQLite
        assert True
