#!/usr/bin/env python3
"""
memory_db.py — Persistent memory store for Jarvis Hub.

SQLite-backed with FTS5 search, auto-compaction, version history, and
structured categorization (facts, lessons, decisions, errors, pending).

Usage:
    from memory_db import MemoryDB

    db = MemoryDB("/path/to/jarvis.db")
    db.add_memory("lesson", "ollama", "qwen3.6 needs sequential API calls, not parallel.")
    results = db.query(category="ollama")
    db.compact()  # runs automatically when entries get stale
"""

import sqlite3
import os
import json
import shutil
from datetime import datetime, timedelta
from typing import Optional


DB_PATH_DEFAULT = "/Users/nghialam/jarvis-hub/knowledge/jarvis.db"
COMPACT_THRESHOLD_DAYS = 14  # age before entry gets archived
MAX_ACTIVE_MEMORIES = 200      # trigger compaction when exceeded


class MemoryDB:
    """SQLite-backed persistent memory store with FTS5 search and auto-compaction."""

    def __init__(self, db_path: str = DB_PATH_DEFAULT):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    # ─── Schema ──────────────────────────────────────────────────────

    def _init_db(self):
        c = self.conn.cursor()

        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('fact','lesson','decision','error','pending')),
                category TEXT,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 1.0 CHECK(confidence BETWEEN 0 AND 1),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                compacted INTEGER DEFAULT 0 NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_compacted ON memories(compacted);

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, category,
                content=memories,
                content_rowid=id
            );

            -- Keep FTS5 in sync with main table
            CREATE TRIGGER IF NOT EXISTS mem_fts_insert AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
            END;
            CREATE TRIGGER IF NOT EXISTS mem_fts_delete AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category);
            END;
            CREATE TRIGGER IF NOT EXISTS mem_fts_update AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category) VALUES('delete', old.id, old.content, old.category);
                INSERT INTO memories_fts(rowid, content, category) VALUES (new.id, new.content, new.category);
            END;

            -- Archive table for compacted entries (preserved for reference)
            CREATE TABLE IF NOT EXISTS memories_archive (
                id INTEGER PRIMARY KEY,
                type TEXT,
                category TEXT,
                content TEXT,
                confidence REAL,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                compacted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Session counter: how many items added total (for dedup tracking)
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.commit()

    # ─── CRUD ────────────────────────────────────────────────────────

    def add_memory(
        self,
        memory_type: str,
        category: str,
        content: str,
        confidence: float = 1.0,
        no_dedup: bool = False,
    ) -> int:
        """Add a memory entry. Returns the row id.

        Checks for duplicate content within same type+category and warns
        if found (doesn't block). Set `no_dedup=True` to skip the check.
        """
        assert memory_type in ("fact", "lesson", "decision", "error", "pending")
        assert 0 <= confidence <= 1

        c = self.conn.cursor()

        # Basic dedup: same type + category + similar content (hash first 80 chars)
        if not no_dedup:
            content_hash = hash(content[:80] + memory_type + category)
            c.execute(
                "SELECT id FROM memories WHERE compacted=0 AND type=? AND category=?",
                (memory_type, category),
            )
            for row in c.fetchall():
                existing = self.get_memory(row[0])
                if existing and len(existing.get("content", "")) > 10:
                    # Simple Jaccard similarity on character bigrams (fast approximation)
                    a, b = content[:80], existing['content'][:80]
                    bigrams = lambda s: set(s[i:i+2].lower() for i in range(len(s)-1)) if len(s) > 1 else set()
                    intersection = bigrams(a) & bigrams(b)
                    union = bigrams(a) | bigrams(b)
                    if len(union) > 0 and len(intersection) / len(union) > 0.4:
                        c.execute(
                            "UPDATE memories SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                            (row[0],),
                        )
                        self.conn.commit()
                        return row[0]  # update in place

        c.execute(
            """INSERT INTO memories (type, category, content, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (memory_type, category, content, confidence),
        )
        rowid = c.lastrowid

        # Auto-compaction if threshold exceeded
        c.execute("SELECT COUNT(*) FROM memories WHERE compacted=0")
        if c.fetchone()[0] > MAX_ACTIVE_MEMORIES:
            self.compact()

        self.conn.commit()
        return rowid

    def get_memory(self, memory_id: int) -> Optional[dict]:
        """Return a single memory as dict, or None."""
        c = self.conn.cursor()
        c.execute("SELECT * FROM memories WHERE id=?", (memory_id,))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "type": row[1], "category": row[2],
            "content": row[3], "confidence": row[4],
            "created_at": row[5], "updated_at": row[6], "compacted": row[7],
        }

    def update_memory(self, memory_id: int, **fields) -> bool:
        """Update one or more fields. Returns True if updated."""
        valid = {"type", "category", "content", "confidence", "compacted"}
        fields = {k: v for k, v in fields.items() if k in valid}
        if not fields:
            return False

        c = self.conn.cursor()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [memory_id]

        # Also update updated_at timestamp
        set_clause += ", updated_at=CURRENT_TIMESTAMP"
        c.execute(f"UPDATE memories SET {set_clause} WHERE id=?", params)
        self.conn.commit()
        return c.rowcount > 0

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory. Returns True if deleted."""
        c = self.conn.cursor()
        c.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        self.conn.commit()
        return c.rowcount > 0

    def query(
        self,
        type: str = None,
        category: str = None,
        keyword: str = None,
        limit: int = 20,
        active_only: bool = True,
    ) -> list[dict]:
        """Query memories with optional filters.

        Uses FTS5 for keyword search (relevance-ranked) and SQL filters
        for type/category.
        """
        c = self.conn.cursor()
        conditions = []
        params = []

        if active_only:
            conditions.append("compacted=0")
        if type:
            conditions.append(f"type=?")
            params.append(type)
        if category:
            conditions.append(f"category LIKE ?")
            params.append(f"%{category}%")

        where = " AND ".join(conditions) if conditions else "1=1"

        entries = []
        if keyword:
             # FTS5 search (relevance-ranked via bm25)
            c.execute(
                f"""SELECT memories.*, memories_fts.rank
                    FROM memories_fts
                    JOIN memories ON memories.id = memories_fts.rowid
                    WHERE memories_fts MATCH ? AND {where}
                    ORDER BY rank ASC LIMIT ?""",
                (keyword, limit),
             )
        else:
            c.execute(
                f"""SELECT *, 0.0
                    FROM memories
                    WHERE {where}
                    ORDER BY updated_at DESC LIMIT ?""",
                params + [limit],
            )

        for row in c.fetchall():
            entry = {
                "id": row[0], "type": row[1], "category": row[2],
                "content": row[3], "confidence": row[4],
                "created_at": row[5], "updated_at": row[6], "compacted": row[7],
            }
            if len(row) > 8:
                entry["rank"] = row[8]  # FTS5 relevance score
            entries.append(entry)

        return entries

    def get_summary(self) -> dict:
        """Get a structured overview of all memory."""
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM memories WHERE compacted=0")
        total = c.fetchone()[0]

        stats = {}
        for mem_type in ("fact", "lesson", "decision", "error", "pending"):
            c.execute(
                "SELECT COUNT(*), MAX(updated_at) FROM memories WHERE compacted=0 AND type=?",
                (mem_type,),
            )
            count, latest = c.fetchone()
            stats[mem_type] = {"count": count, "last_updated": latest}

        # Category distribution
        c.execute("""SELECT category, COUNT(*) FROM memories
                     WHERE compacted=0 AND category IS NOT NULL
                     GROUP BY category ORDER BY COUNT(*) DESC""")
        categories = {row[0]: row[1] for row in c.fetchall()}

        return {
            "total_active": total,
            "by_type": stats,
            "by_category": categories,
            "oldest": self._get_oldest().get("updated_at") if self._get_oldest() else None,
        }

    def _get_oldest(self) -> Optional[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM memories WHERE compacted=0 ORDER BY updated_at ASC LIMIT 1")
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "updated_at": row[6]
        }

    # ─── Compaction & archival ───────────────────────────────────────

    def compact(self) -> int:
        """Archive entries older than COMPACT_THRESHOLD_DAYS days.

        Moves them to `memories_archive` and soft-deletes from main table.
        Returns count of archived entries.
        """
        c = self.conn.cursor()
        cutoff = (datetime.now() - timedelta(days=COMPACT_THRESHOLD_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        # Archive active entries older than threshold
        c.execute("""INSERT INTO memories_archive (id, type, category, content, confidence, created_at, updated_at)
                     SELECT id, type, category, content, confidence, created_at, updated_at
                     FROM memories WHERE compacted=0 AND updated_at < ?""",
                   (cutoff,))

        # Soft delete from main table
        c.execute("UPDATE memories SET compacted=1 WHERE compacted=0 AND updated_at < ?", (cutoff,))

        self.conn.commit()
        return c.rowcount

    def count_archived(self) -> int:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM memories_archive")
        return c.fetchone()[0]

    # ─── Utility ─────────────────────────────────────────────────────

    def get_by_type(self, memory_type: str, limit: int = 50) -> list[dict]:
        """Get all active entries of a given type."""
        return self.query(type=memory_type, limit=limit)

    def sync_to_md(self, md_path: str) -> str:
        """Sync database contents to a markdown file (readable format).

        Used as a snapshot/dump for backup or human review.
        Returns the path written to.
        """
        lines = [f"# Jarvis Hub Memory Dump", "", f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

        for mem_type in ("fact", "lesson", "decision", "error", "pending"):
            entries = self.get_by_type(mem_type)
            if not entries:
                continue
            emoji = {"fact": "📦", "lesson": "💡", "decision": "🔀", "error": "🚨", "pending": "⏳"}[mem_type]
            lines.append(f"## {emoji} {mem_type.upper()} ({len(entries)} entries)")
            lines.append("")

            for e in entries:
                cat = f"[{e['category']}]" if e.get('category') else ""
                conf_marker = " ⚠️ low confidence" if e.get('confidence', 1.0) < 0.7 else ""
                lines.append(f"- **{cat}** {e['content']}{conf_marker}")

            lines.append("")

        with open(md_path, 'w') as f:
            f.write('\n'.join(lines))

        return md_path

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── CLI convenience ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    db = MemoryDB(DB_PATH_DEFAULT)

    if len(sys.argv) < 2:
        # Default: show summary
        summary = db.get_summary()
        print(f"=== Jarvis Hub Memory Summary ===")
        print(f"Total active memories: {summary['total_active']}")
        for mem_type, stats in summary["by_type"].items():
            emoji = {"fact":"📦","lesson":"💡","decision":"🔀","error":"🚨","pending":"⏳"}[mem_type]
            print(f"  {emoji} {mem_type}: {stats['count']} (last: {stats['last_updated'] or 'never'})")
        if summary.get("by_category"):
            print(f"\nCategories:")
            for cat, count in summary["by_category"].items():
                print(f"  {cat}: {count}")
    else:
        cmd = sys.argv[1]
        if cmd == "add":
            if len(sys.argv) < 5:
                print("Usage: memory_db.py add <type> <category> '<content>'")
            else:
                rowid = db.add_memory(sys.argv[2], sys.argv[3], sys.argv[4])
                print(f"Added memory (id={rowid})")

        elif cmd == "query":
            keyword = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
            results = db.query(keyword=keyword, limit=10)
            print(f"\nFound {len(results)} matches:\n")
            for r in results:
                cat = f"[{r['category']}]" if r.get('category') else ""
                print(f"  {r['type']} {cat}: {r['content'][:120]}...")

        elif cmd == "compact":
            count = db.compact()
            print(f"Compacted {count} entries to archive")

        elif cmd == "sync-md":
            path = db.sync_to_md("/Users/nghialam/jarvis-hub/memory_snapshot.md")
            print(f"Synced to {path}")

        elif cmd == "summary":
            summary = db.get_summary()
            for k, v in summary.items():
                print(f"{k}: {v}")
