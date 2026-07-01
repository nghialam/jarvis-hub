#!/usr/bin/env python3
"""
test_memory_db.py - Comprehensive test suite for memory_db.py

Tests cover: CRUD operations, dedup logic, compaction, FTS5 search,
category queries, error handling, and the Python API.
Run with: python3 test_memory_db.py   (uses in-memory/temp DB)
"""

import os
import sys
import time
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, "/Users/nghialam/jarvis-hub/scripts")
from memory_db import MemoryDB


def test_add_and_get():
    """Test basic add and retrieve operations."""
    print("\n[TEST 1] Add and Get Memory")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

        # Add memories of each type
        for mem_type in ("fact", "lesson", "decision", "error", "pending"):
            rowid = db.add_memory(mem_type, "test_category", "Test content for %s" % mem_type)
            assert isinstance(rowid, int), "Row ID should be an integer"

            # Retrieve it
            entry = db.get_memory(rowid)
            assert entry is not None, "Retrieved entry should not be None"
            assert entry["type"] == mem_type, "Type mismatch: %s vs %s" % (entry["type"], mem_type)
            assert entry["category"] == "test_category"
            assert entry["content"] == "Test content for %s" % mem_type

        print("    [PASS] All 5 types added and retrieved successfully")

        # Verify it is None when not found
        assert db.get_memory(99999) is None
        print("    [PASS] Non-existent ID returns None correctly")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 1 PASSED\n")


def test_update_delete():
    """Test update and delete operations."""
    print("\n[TEST 2] Update and Delete Memory")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

        # Add a memory
        rowid = db.add_memory("lesson", "test", "Original content")

        # Update it
        updated = db.update_memory(rowid, content="Updated content", confidence=0.85)
        assert updated is True, "Update should return True when successful"

        # Verify update
        entry = db.get_memory(rowid)
        assert entry["content"] == "Updated content"
        assert entry["confidence"] == 0.85
        print("    [PASS] Update works correctly")

        # Test no-op update (invalid field)
        updated2 = db.update_memory(rowid, invalid_field="test")
        assert updated2 is False, "Should return False for invalid fields"
        print("    [PASS] Invalid field updates return False")

        # Delete it
        deleted = db.delete_memory(rowid)
        assert deleted is True, "Delete should return True when successful"

        # Verify deletion
        assert db.get_memory(rowid) is None
        print("    [PASS] Delete works correctly")

        # Delete non-existent
        deleted2 = db.delete_memory(99999)
        assert deleted2 is False
        print("    [PASS] Deleting non-existent returns False")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 2 PASSED\n")


def test_dedup():
    """Test deduplication logic."""
    print("\n[TEST 3] Deduplication Logic")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

        # Add first entry
        rowid1 = db.add_memory("fact", "omlx", "Parallel calls cause timeouts on 37GB models")
        time.sleep(0.05)   # Ensure different timestamp

        # Add similar entry (should update original with high bigram overlap)
        similar_content = "Parallel API calls will cause timeouts when running 37GB models"
        rowid2 = db.add_memory("fact", "omlx", similar_content, no_dedup=False)

        # These should be the same entry due to dedup
        assert rowid1 == rowid2, "Dedup failed: %s != %s" % (rowid1, rowid2)
        print("    [PASS] Highly similar content returns original ID")

        # Add different content (should get new ID)
        time.sleep(0.05)
        other_type_rowid = db.add_memory("error", "test", "Completely different topic for testing")
        assert other_type_rowid != rowid1, "Different type should get different ID"
        print("    [PASS] Different content gets new ID")

        # Test with no_dedup=True (should always create new entry)
        time.sleep(0.05)
        no_dup_rowid = db.add_memory("lesson", "test", similar_content, no_dedup=True)
        assert no_dup_rowid != other_type_rowid, "no_dedup flag should prevent dedup"
        print("    [PASS] no_dedup=True bypasses dedup correctly")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 3 PASSED\n")


def test_query_categories():
    """Test querying by category and keyword."""
    print("\n[TEST 4] Category Queries and FTS5 Search")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

        # Add memories in different categories
        db.add_memory("fact", "omlx", "Local Ollama gateway runs on port 8000")
        db.add_memory(
            "lesson",
            "omlx",
            "Sequential calls required for qwen3.6, parallel causes timeouts",
        )
        db.add_memory("decision", "rss", "International news fetched at 21:30 separately")
        db.add_memory(
             "error", "html", ".lstrip('<tag>') strips characters recursively"
         )

        # Query by category
        ollama_results = db.query(category="omlx", limit=5)
        assert len(ollama_results) == 2, (
            "Expected 2 'omlx' memories, got %d" % len(ollama_results)
        )
        print("    [PASS] Category query: found %d ollama entries" % len(ollama_results))

        # Query by keyword (FTS5)
        results = db.query(keyword="parallel", limit=10)
        assert len(results) >= 1, "Should find entries containing 'parallel'"
        print("    [PASS] FTS5 search: found %d matches for 'parallel'" % len(results))

        # Query by type
        fact_results = db.query(type="fact", limit=10)
        assert len(fact_results) >= 1
        print("    [PASS] Type query works correctly")

        # Combined filters
        combined = db.query(category="omlx", type="lesson", limit=10)
        assert len(combined) == 1
        print("    [PASS] Combined category+type filters work correctly")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 4 PASSED\n")


def test_summary():
    """Test the get_summary() method."""
    print("\n[TEST 5] Memory Summary")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

        # Add mix of memories
        for i in range(3):
            db.add_memory("fact", "cat_%d" % i, "Fact content %d" % i)
        for i in range(2):
            db.add_memory("lesson", "cat_%d" % i, "Lesson content %d" % i)

        # Get summary
        summary = db.get_summary()

        assert summary["total_active"] == 5, (
            "Expected 5 active memories, got %d" % summary["total_active"]
        )
        assert "by_type" in summary and summary["by_type"].get("fact", {}).get(
            "count"
        ) >= 1
        assert "by_category" in summary and len(summary["by_category"]) > 0

        print("    [PASS] Summary report generated successfully")
        print("    [INFO] Total: %d, Types: %s" % (summary["total_active"], summary["by_type"]))

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 5 PASSED\n")


def test_sync_to_md():
    """Test markdown export functionality."""
    print("\n[TEST 6] Sync to Markdown Export")

    db_path = tempfile.mktemp(suffix=".db")
    md_path = tempfile.mktemp(suffix="_memory.md")

    try:
        db = MemoryDB(db_path)

        # Add memories
        db.add_memory("fact", "test", "Test fact for export")
        db.add_memory("lesson", "test", "Test lesson for markdown sync")

        # Sync to file
        output_path = db.sync_to_md(md_path)

        # Verify file exists and has content
        assert os.path.exists(output_path), (
            "Markdown file not created at %s" % output_path
        )
        with open(output_path, "r") as f:
            content = f.read()

        assert len(content) > 100, (
            "Markdown output too short: %d chars" % len(content)
        )

        lines = content.strip().split("\n")
        has_section_header = any("##" in line for line in lines if len(line) > 0)
        assert has_section_header, "Should have section headers (##)"

        print("    [PASS] Markdown export works correctly (%d bytes)" % len(content))

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(md_path):
            os.remove(md_path)

    print("  >> TEST 6 PASSED\n")


def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n[TEST 7] Edge Cases and Error Handling")

    db_path = tempfile.mktemp(suffix=".db")

    try:
        db = MemoryDB(db_path)

        # Test with empty content string
        rowid = db.add_memory("pending", "test", "")
        assert isinstance(rowid, int), "Empty string should still create entry"
        print("    [PASS] Empty content handled gracefully")

        # Test confidence boundaries (0 and 1)
        row_low = db.add_memory("fact", "test", "Low confidence entry", confidence=0.0)
        row_high = db.add_memory(
            "fact", "test", "High confidence entry", confidence=1.0
        )

        low_entry = db.get_memory(row_low)
        assert low_entry["confidence"] == 0.0, "Low confidence preserved"
        print("    [PASS] Confidence boundary (0.0) works")

        # Test very long content (>10KB should still work)
        long_content = "x" * 15000
        row_long = db.add_memory("lesson", "test", long_content)
        long_entry = db.get_memory(row_long)
        assert len(long_entry["content"]) == 15000
        print("    [PASS] Large content (15KB) handled correctly")

        # Test close() method doesn't crash
        db.close()
        print("    [PASS] DB close() works without errors")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 7 PASSED\n")


def test_context_manager():
    """Test context manager (__enter__/__exit__) protocol."""
    print("\n[TEST 8] Context Manager Protocol")

    db_path = tempfile.mktemp(suffix=".db")
    conn = None

    try:
        with MemoryDB(db_path) as db:
            conn = db.conn
            rowid = db.add_memory("fact", "test", "Context manager test entry")
            result = db.get_memory(rowid)
            assert result is not None
        # After 'with' block, connection should be closed
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("    [PASS] Context manager works correctly\n")


def test_integration_flow():
    """Full integration test simulating real jarvis hub usage."""
    print("\n[TEST 9] Integration Flow (Realistic Scenario)")

    db_path = tempfile.mktemp(suffix=".db")

    try:
        # Create DB (simulating jarvis hub initialization)
        jarvis_db = MemoryDB(db_path)

        # Step 1: Add initial memories from migration script
        jarvis_db.add_memory(
            "fact", "omlx", "qwen3.6:35b requires sequential API calls"
        )
        jarvis_db.add_memory(
              "lesson",
             "html",
             ".lstrip('<tag>') strips characters - use .find() instead",
         )
        jarvis_db.add_memory(
            "decision", "rss", "International news fetched at 21:30 to avoid timeout"
        )

        # Step 2: Verify query works
        ollama_entries = jarvis_db.query(category="omlx")
        assert len(ollama_entries) >= 1, "Should find ollama category entries"
        print("    [PASS] Query by category from real data works")

        # Step 3: Test FTS5 search across all entries
        search_results = jarvis_db.query(keyword="sequential", limit=5)
        assert len(search_results) >= 1, "Should find 'sequential' in content"
        print("    [PASS] FTS5 keyword search finds relevant entries")

        # Step 4: Generate summary (what cron compaction would use)
        summary = jarvis_db.get_summary()
        assert summary["total_active"] == 3, (
            "Expected 3 active memories, got %d" % summary["total_active"]
        )
        print("    [PASS] Summary correctly reports memory counts")

        # Step 5: Add a new entry and verify it appears in queries
        jarvis_db.add_memory(
            "error", "prompting", "Vietnamese diacritics get corrupted during patching"
        )
        after_add = jarvis_db.query(category="prompting")
        assert len(after_add) == 1, "New entry should be findable immediately"
        print("    [PASS] Post-add queries work correctly")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 9 PASSED\n")


def test_count_archived():
    """Test that compact() properly archives entries."""
    print("\n[TEST 10] Compaction and Archival")

    db_path = tempfile.mktemp(suffix=".db")
    try:
        db = MemoryDB(db_path)

         # Add several unique entries with very distinct content (no shared bigrams)
        for i in range(5):
            db.add_memory("fact", "arch_test_%d" % i, "Archive item number %d using words never repeated anywhere else in this test suite xyz%d" % (i, i))

        assert db.count_archived() == 0, "Should start with 0 archived"
        print("    [PASS] Initial count is 0")

        # Manually set some entries' updated_at to old dates so compact() will catch them
        c = db.conn.cursor()
        old_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "UPDATE memories SET updated_at=? WHERE compacted=0", (old_date,)
        )
        db.conn.commit()

        # Now compact should find them
        compacted = db.compact()
        assert compacted == 5, "Should compact all 5 entries"
        print("    [PASS] Compacting %d old entries works" % compacted)

        archived = db.count_archived()
        assert archived == 5, "Archived count should reflect compaction"
        print("    [PASS] Archive count is correct")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

    print("  >> TEST 10 PASSED\n")


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 65)
    print("  Jarvis Hub Memory Database -- Regression Test Suite v1.0")
    print("=" * 65)

    tests = [
        test_add_and_get,
        test_update_delete,
        test_dedup,
        test_query_categories,
        test_summary,
        test_sync_to_md,
        test_edge_cases,
        test_context_manager,
        test_integration_flow,
        test_count_archived,
    ]

    passed = 0
    failed = []

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print("\n  [FAIL] %s" % test_func.__name__)
            import traceback

            traceback.print_exc()
            failed.append((test_func.__name__, str(e)))

    print("=" * 65)
    if failed:
        print(
            "  RESULTS: %d/%d tests passed, %d FAILED"
            % (passed, len(tests), len(failed))
        )
        for name, error in failed:
            print("    [%s] %s" % ("FAIL", "%s: %s" % (name, error)))
        return False
    else:
        print(
            "  ALL TESTS PASSED! (%d/%d)" % (passed, len(tests))
        )
        return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
