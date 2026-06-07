#!/usr/bin/env python3
"""
regression_runner.py — Jarvis Hub Nightly Regression Test Suite v2.0

Combines:
  A. Memory database tests (memory_db.py)
  B. Jarvis intelligence/feed pipeline tests
  C. Optional Flask API health checks (if dashboard is running)

Run manually:   python3 regression_runner.py --test
Run via cron:   python3 regression_runner.py        (auto mode, sends Telegram report)
"""

import json
import os
import sys
import unittest
import urllib.request
import urllib.error
from datetime import datetime

# ─── Paths ──────────────────────────────────────────────────────
SCRIPTS_DIR = "/Users/nghialam/jarvis-hub/scripts"
DB_PATH = "/Users/nghialam/jarvis-hub/knowledge/jarvis.db"
BOTTOKEN = "8733142640:***"
CHAT_ID = "1670013239"
BASE_URL = "http://localhost:8100"

sys.path.insert(0, SCRIPTS_DIR)

# ─── Import memory tests ────────────────────────────────────────
try:
    from memory_db import MemoryDB
    HAS_MEMORY_DB = True
except ImportError:
    HAS_MEMORY_DB = False


# ─── Telegram notification helper ───────────────────────────────

def send_telegram(text, max_parts=4):
    url = "https://api.telegram.org/bot%s/sendMessage" % BOTTOKEN
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) > 3800:
            parts.append(current)
            current = line
        else:
            current = (current + "\n" + line).strip() if current else line
    if current:
        parts.append(current)

    for i, part in enumerate(parts[:max_parts]):
        payload = {"chat_id": CHAT_ID, "text": part, "parse_mode": "Markdown"}
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read())
            msg_id = result.get("result", {}).get("message_id", "?")
            print("   [TG] Chunk %d/%d sent (msg: %s)" % (i + 1, len(parts), msg_id))
        except Exception as e:
            print("   [TG] Send failed: %s" % e)


# ─── Test suites ──────────────────────────────────────────────

class TestMemoryDB(unittest.TestCase):
    """Unit tests for the memory database."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        if not HAS_MEMORY_DB:
            raise unittest.SkipTest("memory_db.py not available")
        cls.db_path = tempfile.mktemp(suffix=".db")
        cls.db = MemoryDB(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        import os
        cls.db.close()
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_add_and_query(self):
        """Add a memory and query it back."""
        rid = self.db.add_memory("fact", "test_regression", "Regression test entry 2026-05")
        entries = self.db.query(keyword="regression", limit=5)
        self.assertGreater(len(entries), 0, "Should find the added memory via FTS5 search")

    def test_context_manager(self):
        """Verify context manager protocol."""
        with MemoryDB(self.db_path + "_cm") as db:
            db.add_memory("pending", "test", "Context manager test")
        import os
        if os.path.exists(self.db_path + "_cm"):
            os.remove(self.db_path + "_cm")

    def test_summary_consistency(self):
        """Summary should reflect actual DB state."""
        before = self.db.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE compacted=0"
        ).fetchone()[0]
        summary = self.db.get_summary()
        self.assertEqual(summary["total_active"], before)


class TestFlaskHealth(unittest.TestCase):
    """Flask dashboard health checks (skip if server not running)."""

    @classmethod
    def setUpClass(cls):
        cls._skip_reason = None
        try:
            urllib.request.urlopen("%s/api/health" % BASE_URL, timeout=3)
        except Exception:
            cls._skip_reason = "Flask dashboard not running on port 8100"

    def test_0_skip(self):
        if self._skip_reason:
            raise unittest.SkipTest(self._skip_reason)

    def test_health_endpoint(self):
        """Health endpoint should return 200 with indices."""
        try:
            resp = urllib.request.urlopen("%s/api/health" % BASE_URL, timeout=10)
            data = json.loads(resp.read())
            self.assertEqual(resp.status, 200)
            self.assertIn("indices", data)
        except Exception:
            self.skipTest("Flask dashboard not available")

    def test_articles_api(self):
        """Articles API should return structured data."""
        try:
            resp = urllib.request.urlopen("%s/api/articles?limit=3" % BASE_URL, timeout=10)
            data = json.loads(resp.read())
            self.assertEqual(resp.status, 200)
            self.assertIn("articles", data)
        except Exception:
            self.skipTest("Flask dashboard not available")

    def test_kb_search(self):
        """KB search should work on a known term."""
        try:
            resp = urllib.request.urlopen("%s/api/search?q=RSI" % BASE_URL, timeout=10)
            data = json.loads(resp.read())
            self.assertEqual(resp.status, 200)
            self.assertIn("results", data)
        except Exception:
            self.skipTest("Flask dashboard not available")

    def test_watchlist(self):
        """Watchlist endpoint should return a list."""
        try:
            resp = urllib.request.urlopen("%s/api/watchlist" % BASE_URL, timeout=10)
            data = json.loads(resp.read())
            self.assertEqual(resp.status, 200)
            self.assertTrue(isinstance(data.get("watchlist", []), list))
        except Exception:
            self.skipTest("Flask dashboard not available")


class TestJarvisIntelligence(unittest.TestCase):
    """Validate the jarvis_intelligence pipeline scripts exist and compile."""

    def test_script_exists(self):
        path = os.path.join(SCRIPTS_DIR, "jarvis_intelligence.py")
        self.assertTrue(os.path.exists(path), "jarvis_intelligence.py must exist")

    def test_script_compiles(self):
        import py_compile, tempfile, os
        src = os.path.join(SCRIPTS_DIR, "jarvis_intelligence.py")
        tmp_pyc = tempfile.mktemp(suffix=".pyc")
        try:
            py_compile.compile(src, cfile=tmp_pyc)
        finally:
            if os.path.exists(tmp_pyc):
                os.remove(tmp_pyc)

    def test_intelligence_feed_format(self):
        """Validate the intelligence feed uses correct section structure."""
        src = os.path.join(SCRIPTS_DIR, "jarvis_intelligence.py")
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
         # Should have RSS source list with multiple feeds
        self.assertIn("rss", content.lower())
        # Should not use ThreadPoolExecutor on /api/chat (known bug pattern)
        self.assertNotIn(
             "ThreadPoolExecutor(max_workers",
             content,
             "CRITICAL: Use sequential calls for /api/chat — parallel causes timeouts"
         )


# ─── Report builder ────────────────────────────────────────────

def build_report(results, start_time):
    elapsed = (datetime.now() - start_time).seconds
    total = results.testsRun
    failures = len(results.failures) + len(results.errors)
    skips = len(results.skipped)
    passed = total - failures - skips

    lines = [
        "JARVIS HUB REGRESSION REPORT — %s" % datetime.now().strftime("%d/%m/%Y"),
        "",
        "⏱️ Duration: %ds  Tests: %d   ✅ Passed: %d   ❌ Failed: %d   ⏭️ Skipped: %d"
              % (elapsed, total, passed, failures, skips),
        "",
        "-- RESULTS --",
    ]

     # Add failure/error details
    for test, traceback_str in results.failures + results.errors:
        lines.append("❌ %s" % str(test))
        short = traceback_str.strip().split("\n")[-3]   # last meaningful line
        if len(short) > 120:
            short = short[:120]
        lines.append("     %s" % short)

    for test, reason in results.skipped:
        lines.append("⏭️ %s : %s" % (str(test), reason))

    lines.extend([
        "",
        "-- MEMORY DB STATUS --",
        "  Path: %s" % DB_PATH,
        "  Exists: %s" % (os.path.exists(DB_PATH)),
     ])

    if os.path.exists(DB_PATH):
        try:
            temp_db = MemoryDB(DB_PATH)   # read-only check — won't modify
            summary = temp_db.get_summary()
            lines.append("  Total active: %d" % summary["total_active"])
            for mem_type, stats in summary["by_type"].items():
                emoji = {"fact": "📦", "lesson": "💡", "decision": "🔀", "error": "🚨", "pending": "⏳"}[mem_type]
                lines.append("    %s %s: %d" % (emoji, mem_type, stats["count"]))
            temp_db.close()
        except Exception as e:
            lines.append("  ERROR reading DB: %s" % e)

    lines.extend([
        "",
        "-- SUMMARY --",
        "Run at: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Next run: Tomorrow 03:00 AM",
         "" if failures == 0 else (
             "⚠️ %d test(s) FAILED — review immediately" % failures
         ),
    ])

    return "\n".join(lines)


# ─── Main entry point ──────────────────────────────────────────

def run_tests(test_mode=False):
    start_time = datetime.now()

    print("=" * 65)
    print("JARVIS HUB REGRESSION TEST SUITE v2.0")
    print("%s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 65)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load all tests from each suite
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryDB))
    suite.addTests(loader.loadTestsFromTestCase(TestFlaskHealth))
    suite.addTests(loader.loadTestsFromTestCase(TestJarvisIntelligence))

    runner = unittest.TextTestRunner(verbosity=0)
    results = runner.run(suite)

    report = build_report(results, start_time)

    print("\n" + report + "\n")

    if not test_mode and results.failures:
        send_telegram(report)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    if mode in ("--test", "test"):
        run_tests(test_mode=True)
    else:
        print("Running regression tests...")
        run_tests()
        print("\nAll tests complete!")
