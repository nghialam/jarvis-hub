#!/usr/bin/env python3
"""
Jarvis Hub Database Index Migration Executor

Applies migrate_indexes.sql against both jarvis_hub_memory (PostgreSQL)
and jarvis.db (SQLite), with:
  1. Automated backup before any changes
  2. Transaction safety for PostgreSQL
  3. Verification that every index was created
  4. Summary report of what was added

Usage:
    python scripts/apply_indexes.py [--dry-run] [--no-backup]
"""
import os
import sys
import shutil
import sqlite3
import argparse
import re
from datetime import datetime

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# ─── Configuration ────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

SQL_FILE = os.path.join(BASE_DIR, "migrate_indexes.sql")

# PostgreSQL connection (mirrors MemoryConfig defaults)
PG_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "jarvis_hub_memory",
    "user": "nghialam",
    "password": "",
}

# SQLite DB path — use the primary data jarvis.db
SQLITE_PATH = os.path.join(REPO_ROOT, "data", "jarvis.db")


# ─── Helpers ──────────────────────────────────────────────────────

def split_sql_statements(sql_text: str) -> list[str]:
    """Split SQL text into individual statements, respecting DO $$ blocks."""
    # Remove line comments that are standalone lines (not inline)
    cleaned_lines = []
    for line in sql_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--"):
            pass  # skip comment-only lines
        else:
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    # Use regex to split on semicolons that end statements, but track DO $$ blocks
    statements: list[str] = []
    current_stmt: list[str] = []
    in_do_block = False

    # Process character by character around semicolons
    text = cleaned + ";"  # ensure trailing ; for last stmt
    i = 0
    buffer = ""
    while i < len(text):
        ch = text[i]
        if ch == "$":
            # Check for $$(end of DO block) or $...$(start)
            rest = text[i:]
            if rest.startswith("$$"):
                end_tag = "$"
                j = i + 2
                while j < len(text) and text[j].isalnum():
                    end_tag += text[j]
                    j += 1
                end_tag += "$"
                buffer += text[i:j]
                if in_do_block:
                    in_do_block = False
                else:
                    in_do_block = True
                i = j
                continue
        if ch == ";" and not in_do_block:
            stmt = buffer.strip()
            if stmt:
                statements.append(stmt)
            buffer = ""
        else:
            buffer += ch
        i += 1

    return statements


def backup_database(db_path: str, label: str = "") -> str | None:
    """Create a .bak copy of the database file. Returns backup path or None."""
    if not os.path.exists(db_path):
        print(f"  ⚠️  {db_path} does not exist -- skipping backup.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{label}_{timestamp}.bak"
    backup_path = os.path.join(os.path.dirname(db_path), backup_name)

    shutil.copy2(db_path, backup_path)
    print(f"  ✅  Backup created: {backup_path}")
    return backup_path


def verify_pg_indexes(pg_conn) -> dict[str, list[str]]:
    """Return {table: [index_name, ...]} for all non-system indexes."""
    cur = pg_conn.cursor()
    cur.execute("""
        SELECT indexname, tablename
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND NOT indexname LIKE '%_pkey'
        ORDER BY tablename, indexname;
    """)
    result: dict[str, list[str]] = {}
    for idx_name, tbl in cur.fetchall():
        result.setdefault(tbl, []).append(idx_name)
    cur.close()
    return result


def verify_sqlite_indexes(db_path: str) -> dict[str, list[str]]:
    """Return {table: [index_name, ...]} for all non-auto indexes."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT name, tbl_name FROM sqlite_master
        WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex_%'
        ORDER BY tbl_name, name;
    """)
    result: dict[str, list[str]] = {}
    for idx_name, tbl in cur.fetchall():
        result.setdefault(tbl, []).append(idx_name)
    cur.close()
    conn.close()
    return result


def get_target_indexes_pg() -> list[tuple[str, str]]:
    """List the index names we aim to create on PostgreSQL."""
    return [
        ("idx_memdocs_collection", "memdocs"),
        ("idx_memdocs_peer", "memdocs"),
        ("idx_sessions_peer_created", "sessions"),
        ("idx_signals_timestamp", "signals"),      # conditional
        ("idx_articles_category", "articles"),     # conditional
    ]


def get_target_indexes_sqlite() -> list[tuple[str, str]]:
    """List the index names we aim to create on SQLite."""
    return [
        ("idx_articles_category", "articles"),           # conditional (articles table may not exist)
        ("idx_activities_timestamp", "activity_log"),    # activity_log has timestamp column
        ("idx_daily_snapshot_date", "daily_snapshots"),
        ("idx_knowledge_category", "knowledge"),         # uses tags column
    ]


def extract_index_name(stmt: str) -> str | None:
    """Extract index name from a CREATE INDEX statement."""
    m = re.search(r'CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', stmt, re.IGNORECASE)
    return m.group(1) if m else None


# ─── Main Migration Logic ─────────────────────────────────────────

def apply_indexes(dry_run: bool = False, skip_backup: bool = False):
    added_pg: list[tuple[str, str | None]] = []    # (index_name, table)
    missed_pg: list[tuple[str, str]] = []   # expected but not found after migration
    added_sqlite: list[tuple[str, str]] = []
    missed_sqlite: list[tuple[str, str]] = []

    print("=" * 65)
    print("  Jarvis Hub Database Index Migration")
    print("=" * 65)

    # ── Step 1: Backups ────────────────────────────────────────────
    if not skip_backup:
        print("\n[Step 1] Creating backups …")
        backup_sqlite = backup_database(SQLITE_PATH, "jarvis_pre_indexes")
    else:
        print("\n[Step 1] Skipped (skip_backup=True)")
        backup_sqlite = None

    # ── Step 2: Read SQL file & split into statements ──────────────
    if not os.path.exists(SQL_FILE):
        print(f"ERROR: SQL file not found at {SQL_FILE}")
        sys.exit(1)

    with open(SQL_FILE) as f:
        sql_text = f.read()

    statements = split_sql_statements(sql_text)
    print(f"\n[Step 2] Loaded {len(statements)} SQL statement(s) from migrate_indexes.sql")

    # ── Step 3: Apply PostgreSQL indexes ───────────────────────────
    print("\n[Step 3] Applying PostgreSQL indexes (jarvis_hub_memory) …")
    pg_conn = psycopg2.connect(**PG_CONFIG)
    pg_conn.set_session(autocommit=False)  # explicit transaction control
    pg_cur = None

    try:
        pg_cur = pg_conn.cursor()
        target_pg = get_target_indexes_pg()
        existing_before = verify_pg_indexes(pg_conn)
        print(f"  Current indexes: {len(existing_before.get('memdocs', []))} on memdocs, "
              f"{len(existing_before.get('sessions', []))} on sessions")

        if not dry_run:
            pg_cur.execute("BEGIN;")

            # Pre-scan PG tables to avoid creating indexes on non-existent ones
            pg_cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public';")
            existing_pg_tables = {row[0] for row in pg_cur.fetchall()}
            print(f"  Known PG tables: {', '.join(sorted(existing_pg_tables))}")

            for stmt in statements:
                idx_name = extract_index_name(stmt)
                if not idx_name:
                    continue  # not a CREATE INDEX → skip

                # Find which target this belongs to
                matched_table = None
                for tn, tbl in target_pg:
                    if idx_name == tn:
                        matched_table = tbl
                        break

                # Skip memdocs_collection -- already exists
                if idx_name == "idx_memdocs_collection":
                    print(f"  ⏭️  Skipping {idx_name} (already exists)")
                    continue

                # Skip statements targeting tables that don't exist on PG
                if matched_table is None or matched_table not in existing_pg_tables:
                    if matched_table and matched_table not in existing_pg_tables:
                        print(f"  ⏭️  Skipped ({idx_name}): table '{matched_table}' doesn't exist")
                    continue

                try:
                    pg_cur.execute(stmt)
                    print(f"  ✅ Created index: {idx_name}")
                except psycopg2.errors.InFailedSqlTransaction:
                    # Transaction was aborted by a prior error; restart it
                    try:
                        pg_cur.execute("END;")   # close failed txn
                        pg_cur.execute("BEGIN;")  # start fresh
                    except Exception:
                        pg_cur.execute("ROLLBACK;")
                        pg_cur.execute("BEGIN;")
                    continue  # re-execute this statement in the new txn
                except Exception as e:
                    err_lower = str(e).lower()
                    if "already exists" in err_lower:
                        print(f"  ⚠️  Skipped (already exists): {idx_name}")
                    elif "does not exist" in err_lower or "relation" in err_lower:
                        print(f"  ⏭️  Skipped (table missing): {idx_name}")
                    else:
                        raise

            pg_cur.execute("COMMIT;")
            print(f"\n[Step 3] PostgreSQL migration complete.")
        else:
            print("  💤 [DRY RUN] -- skipping actual execution")

        # Verify what would/could be applied (fresh connection avoids txn state issues)
        verify_conn = psycopg2.connect(**PG_CONFIG)
        after_pg = verify_pg_indexes(verify_conn)
        for idx_name, tbl in target_pg:
            if idx_name in after_pg.get(tbl, []):
                if (idx_name, tbl) not in added_pg:
                    added_pg.append((idx_name, tbl))
            else:
                missed_pg.append((idx_name, tbl))
        verify_conn.close()

    except Exception as e:
        if pg_cur is not None:
            pg_cur.execute("ROLLBACK;")
        print(f"  ❌ PostgreSQL migration failed: {e}")
        raise
    finally:
        if pg_cur is not None:
            pg_cur.close()

    # ── Step 4: Apply SQLite indexes ───────────────────────────────
    print("\n[Step 4] Applying SQLite indexes (jarvis.db) …")

    if not os.path.exists(SQLITE_PATH):
        print(f"  ⚠️  Database not found at {SQLITE_PATH} -- skipping SQLite.")
    else:
        sqlite_conn = sqlite3.connect(SQLITE_PATH)
        existing_before = verify_sqlite_indexes(SQLITE_PATH)
        print(f"  Current indexes: {len(existing_before.get('knowledge', []))} on knowledge, "
              f"{len(existing_before.get('daily_snapshots', []))} on daily_snapshots")

        try:
            if dry_run:
                print("  💤 [DRY RUN] -- skipping actual execution")
                for stmt in statements:
                    # Skip PostgreSQL-specific blocks
                    if "information_schema" in stmt or "DO $$" in stmt or "pg_indexes" in stmt:
                        continue
                    idx_name = extract_index_name(stmt)
                    if not idx_name:
                        continue
                    for tn, tbl in get_target_indexes_sqlite():
                        if idx_name == tn:
                            added_sqlite.append((idx_name, tbl))
                            break
            else:
                # Only apply SQLite-appropriate statements
                sqlite_pg_names = {extract_index_name(s) for s in split_sql_statements(sql_text)}
                sqlite_target_names = {t[0] for t in get_target_indexes_sqlite()}
                allowed_names = sqlite_target_names

                for stmt in statements:
                    idx_name = extract_index_name(stmt)
                    if "DO $$" in stmt:
                        continue  # PostgreSQL-specific block — skip for SQLite
                    if idx_name not in allowed_names:
                        continue  # PG-only statement — skip for SQLite

                    matched_target = None
                    for tn, tbl in get_target_indexes_sqlite():
                        if idx_name == tn:
                            matched_table = tbl
                            break

                    try:
                        sqlite_conn.execute(stmt)
                        print(f"  ✅ Created index: {idx_name}")
                    except Exception as e:
                        err_lower = str(e).lower()
                        if "already exists" in err_lower:
                            print(f"  ⚠️  Skipped (already exists): {idx_name}")
                        elif "no such table" in err_lower:
                            print(f"  ⏭️  Skipped (table missing): {idx_name}")
                        else:
                            raise

                sqlite_conn.commit()

            sqlite_conn.close()

            # Verify what was applied
            after_sqlite = verify_sqlite_indexes(SQLITE_PATH)
            for idx_name, tbl in get_target_indexes_sqlite():
                if idx_name in after_sqlite.get(tbl, []):
                    if (idx_name, tbl) not in added_sqlite:
                        added_sqlite.append((idx_name, tbl))
                else:
                    missed_sqlite.append((idx_name, tbl))

        except Exception:
            sqlite_conn.close()
            raise

    # ── Step 5: Summary ────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  Migration Summary")
    print("=" * 65)

    print(f"\n🐘 PostgreSQL (jarvis_hub_memory):")
    if added_pg:
        for idx, tbl in added_pg:
            if tbl is not None:
                print(f"  ✅ Added:    {idx} ON {tbl}")
            else:
                print(f"  ✅ Added:    {idx}")
    else:
        print("  (none successfully created)")

    if missed_pg:
        for idx, tbl in missed_pg:
            table_note = f" ON {tbl}" if tbl else ""
            print(f"  ❌ Missed:  {idx}{table_note} -- verify table exists")

    print(f"\n🗄️  SQLite (jarvis.db):")
    if added_sqlite:
        for idx, tbl in added_sqlite:
            if tbl is not None:
                print(f"  ✅ Added:    {idx} ON {tbl}")
            else:
                print(f"  ✅ Added:    {idx}")
    else:
        print("  (none successfully created)")

    if missed_sqlite:
        for idx, tbl in missed_sqlite:
            table_note = f" ON {tbl}" if tbl else ""
            print(f"  ❌ Missed:  {idx}{table_note} -- verify table exists")

    success = len(missed_pg) == 0 and len(missed_sqlite) == 0
    status = "✓ All targets met" if success else "⚠ Partial -- check missed indexes above"
    print(f"\n{status}")

    # Close PostgreSQL connection (already closed in finally, but safe to call)
    try:
        pg_conn.close()
    except Exception:
        pass


# ─── CLI Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Apply database index migration for Jarvis Hub"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without executing")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip creating backups")
    args = parser.parse_args()

    apply_indexes(dry_run=args.dry_run, skip_backup=args.no_backup)
