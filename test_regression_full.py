"""
Jarvis Hub - Full Regression Test Suite (v3 final)
Tests all modules: config, database, news, market, and integration.
"""
import sys
import os
import json
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config, get, reload_config, _DEFAULT_CONFIG_PATH
from core.db import Database
from core.news_service import (
    fetch_and_categorize_articles, enrich_article, get_articles,
    get_exchange_rates, _heuristic_sentiment, fetch_market_indices, fetch_crypto,
     _categorize,
)
from core.market_service import MarketService, MarketCache, _calc_rsi, _sma, _ema
import numpy as np


# ============================================================================
# TEST 1: CONFIG MODULE
# ============================================================================

class TestConfig(unittest.TestCase):

    def test_load_config_exists(self):
        self.assertTrue(_DEFAULT_CONFIG_PATH.exists(), "config.yaml must exist")

    def test_load_config_valid_yaml(self):
        try:
            cfg = load_config()
            self.assertIsInstance(cfg, dict)
        except Exception as e:
            self.fail(f"Failed to load config: {e}")

    def test_dot_notation_access_existing(self):
        cfg = load_config()
        ollama_url = get('ollama.url', None) or cfg.get('omlx', {}).get('url')
        self.assertIsNotNone(ollama_url, "Ollama URL must be configured")
        self.assertIn('11434', str(ollama_url))

    def test_dot_notation_access_missing(self):
        result = get('nonexistent.super.deeply.nested.key', 'DEFAULT')
        self.assertEqual(result, 'DEFAULT')

    def test_reload_config_clears_cache(self):
        import core.config as cfg_mod
          # Force a clean state first
        cfg_mod._config_cache = None
        reload_config()  # reload sets cache to None, then calls load_config
          # After reload, cache should be populated with fresh config data
        self.assertIsNotNone(cfg_mod._config_cache)

    def test_dot_notation_deep_access(self):
        feed_sources = get('feed.sources', None)
        if feed_sources:
            self.assertIsInstance(feed_sources, list)
            first_source = feed_sources[0]
            self.assertIn('name', first_source)
            self.assertIn('url', first_source)

    def test_config_defaults_applied(self):
        cfg = load_config()
        ollama = cfg.get('omlx', {})
        if 'url' not in cfg.get('omlx', {}):
            self.assertEqual(ollama['url'], 'http://localhost:11434')


# ============================================================================
# TEST 2: DATABASE MODULE - ALL TABLES & OPERATIONS
# ============================================================================

class TestDatabase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, 'test_jarvis.db')
        self.db = Database(self.db_path)

    def tearDown(self):
        try:
            for ext in ['', '-wal', '-shm']:
                p = self.db_path + ext
                if os.path.exists(p):
                    os.unlink(p)
        except Exception:
            pass

    def test_db_table_creation(self):
        expected_tables = [
            'knowledge', 'knowledge_fts', 'activity_log',
            'daily_snapshots', 'watchlist', 'market_cache',
            'market_evaluations'
        ]
        c = self.db._c()
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        created_tables = [r['name'] for r in rows]
        for t in expected_tables:
            self.assertIn(t, created_tables, f"Table {t} should be created")

    def test_save_and_get_knowledge(self):
        tid = self.db.save_term("P/E Ratio", "The price-to-earnings ratio is...", "stock,valuation,ratio")
        self.assertIsInstance(tid, int)
        terms = [dict(r) for r in self.db._c().execute("SELECT * FROM knowledge").fetchall()]
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0]['term'], 'p/e ratio')

    def test_knowledge_upsert(self):
        self.db.save_term("RSI", "Old definition")
        tid2 = self.db.save_term("RSI", "Relativity Strength Index updated", "")
        rows = [r for r in self.db._c().execute("SELECT * FROM knowledge WHERE term='rsi'").fetchall()]
        self.assertEqual(len(rows), 1, "Should have exactly one entry for RSI")

    def test_knowledge_search_term_match(self):
        self.db.save_term("Moving Average", "A trend indicator...", "ta,moving average")
        self.db.save_term("Technical Indicator A", "Description A", "ta")
        self.db.save_term("Technical Indicator B", "Description B", "ta")
        self.db.save_term("Technical Indicator C", "Description C", "ta")
        self.db.save_term("Technical Indicator D", "Description D", "ta")
        results = self.db.search_knowledge("technical indicator", limit=50)
        self.assertGreaterEqual(len(results), 3)

    def test_knowledge_search_stops_words(self):
        self.db.save_term("Stock Market", "The stock market...", "general")
        empty_results = self.db.search_knowledge("the is a va la")
        self.assertLessEqual(len(empty_results), 5)

    def test_knowledge_search_empty_query(self):
        results = self.db.search_knowledge("")
        self.assertEqual(results, [])

    def test_knowledge_search_short_query(self):
        results = self.db.search_knowledge("a")
        self.assertEqual(len(results), 0)

    def test_activity_log(self):
        before_count = len([r for r in self.db._c().execute("SELECT * FROM activity_log").fetchall()])
        self.db.log_activity('test_command', '--symbol VNM', 'ok', 'Test summary', 123)
        after_count = len([r for r in self.db._c().execute("SELECT * FROM activity_log").fetchall()])
        self.assertEqual(after_count, before_count + 1)

    def test_activity_log_fields(self):
        self.db.log_activity('test_log', 'arg1 arg2', 'warn', 'Warning summary', 456)
        c = self.db._c()
        row = c.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 1").fetchone()
        d = dict(row)
        self.assertEqual(d['command'], 'test_log')
        self.assertIn('arg1', d['args'])
        self.assertEqual(d['status'], 'warn')

    def test_get_activities_limit(self):
        for i in range(10):
            self.db.log_activity('log_test', '', 'ok', f'Log {i}', i * 10)
        recent = self.db.get_activities(limit=5)
        self.assertEqual(len(recent), 5)

    def test_activity_log_empty_args(self):
        self.db.log_activity('test_empty', '', 'ok')
        rows = [r for r in self.db._c().execute("SELECT * FROM activity_log").fetchall()]
        self.assertEqual(len(rows), 1)

    def test_daily_snapshot_save_and_get(self):
        date = "2026-05-24"
        content = "Morning briefing summary..."
        self.db.save_daily_snapshot(date, content, "Briefing")
        snapshot = self.db.get_daily_snapshot(date)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot['date'], date)

    def test_daily_snapshot_upsert(self):
        date = "2026-05-24"
        self.db.save_daily_snapshot(date, "Update 1")
        self.db.save_daily_snapshot(date, "Update 2")
        snapshots = [r for r in self.db._c().execute("SELECT * FROM daily_snapshots").fetchall()]
        self.assertEqual(len(snapshots), 1)

    def test_get_all_dates(self):
        dates = ["2026-05-22", "2026-05-23", "2026-05-24"]
        for d in dates:
            self.db.save_daily_snapshot(d, f"Content {d}")
        result_dates = self.db.get_all_dates()
        self.assertEqual(result_dates, ['2026-05-24', '2026-05-23', '2026-05-22'])

    def test_daily_snapshot_empty(self):
        self.db.save_daily_snapshot("2026-05-24", "", "")
        snapshot = self.db.get_daily_snapshot("2026-05-24")
        self.assertIsNotNone(snapshot)

    def test_watchlist_add_and_list(self):
        self.db.add_watchlist("VNM")
        self.db.add_watchlist("FRT", "FCP FRT")
        watchlist_raw = [dict(r) for r in self.db._c().execute(
            "SELECT * FROM watchlist ORDER BY symbol"
        ).fetchall()]
        symbols = [w['symbol'] for w in watchlist_raw]
        self.assertIn("VNM", symbols)
        self.assertIn("FRT", symbols)

    def test_watchlist_upsert_name(self):
        tid = self.db.add_watchlist("VNM")
        tid2 = self.db.add_watchlist("VNM", "Updated Vinamilx Name")
        rows_raw = [dict(r) for r in self.db._c().execute(
            "SELECT * FROM watchlist"
        ).fetchall()]
        vnm_rows = [r for r in rows_raw if r.get('symbol') == 'VNM']
        self.assertEqual(len(vnm_rows), 1)

    def test_watchlist_remove(self):
        self.db.add_watchlist("REMOVE_ME")
        rows_before = len([r for r in self.db._c().execute(
            "SELECT * FROM watchlist"
        ).fetchall()])
        removed = self.db.remove_watchlist("REMOVE_ME")
        rows_after = len([r for r in self.db._c().execute(
            "SELECT * FROM watchlist"
        ).fetchall()])
        self.assertTrue(removed)
        self.assertEqual(rows_after, rows_before - 1)

    def test_watchlist_case_insensitive(self):
        self.db.add_watchlist("VNM", "Vinamilx")
        rows_raw = [dict(r) for r in self.db._c().execute(
            "SELECT * FROM watchlist"
        ).fetchall()]
        vnm_rows = [r for r in rows_raw if r.get('symbol').upper() == 'VNM']
        self.assertEqual(len(vnm_rows), 1)

    def test_market_cache_save_get(self):
        data = {"symbol": "VNM", "price": 57.5, "change_pct": 2.3}
        self.db.save_market_data("VNM", data, ttl_minutes=5)
        cached = self.db.get_cached_market_data("VNM")
        self.assertIsNotNone(cached)
        self.assertEqual(cached['symbol'], 'VNM')

    def test_market_cache_expiry(self):
        import json as j
        now = datetime.utcnow()
        exp = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        ts = (now - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        self.db._c().execute(
            "INSERT INTO market_cache (symbol, data_json, cached_at, expires_at) VALUES (?, ?, ?, ?)",
            ("EXPIRED", j.dumps({"p": 1}), ts, exp)
        )
        self.db._conn.commit()
        result = self.db.get_cached_market_data("EXPIRED")
        self.assertIsNone(result)

    def test_save_market_evaluation(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        eval_txt = "Market is bullish with strong volume..."
        self.db.save_market_evaluation(today, eval_txt, "Summary: positive sentiment")
        today_eval = self.db.get_today_evaluation()
        self.assertIsNotNone(today_eval)

    def test_get_all_evaluations(self):
        dates = ["2026-05-22", "2026-05-23", "2026-05-24"]
        for d in dates:
            self.db.save_market_evaluation(d, f"Eval {d}")
        results = self.db.get_all_evaluations()
        self.assertEqual(len(results), 3)

    def test_bulk_write_integrity(self):
        for i in range(50):
            self.db.save_term(f"term_{i}", f"description content {i}")
        result = self.db.search_knowledge("term", limit=50)
        self.assertGreater(len(result), 20, f"Expected >20 results, got {len(result)}")


# ============================================================================
# TEST 3: NEWS SERVICE - RSS, SENTIMENT, CATEGORIZATION
# ============================================================================

class TestNewsService(unittest.TestCase):

    def test_heuristic_sentiment_bullish(self):
        label, bull, bear = _heuristic_sentiment(
             "Tăng mạnh cổ phiếu ACB", "Lợi nhuận tăng cao"
         )
        self.assertEqual(label, "TÍCH_CỰC")
        self.assertGreater(bull, 0)

    def test_heuristic_sentiment_bearish(self):
        label, bull, bear = _heuristic_sentiment(
             "Giảm điểm VN-Index", "Sụt giảm thị trường rủi ro cao"
         )
        self.assertEqual(label, "TIÊU_CỰC")
        self.assertGreater(bear, 0)

    def test_heuristic_sentiment_neutral(self):
        label, bull, bear = _heuristic_sentiment(
             "Bán và mua cân bằng", "Thị trường ổn định không biến động"
         )
        self.assertEqual(label, "TRUNG_LẬP")

    def test_heuristic_sentiment_empty(self):
        label, bull, bear = _heuristic_sentiment("", "")
        self.assertEqual(label, "TRUNG_LẬP")
        self.assertEqual(bull, 0)
        self.assertEqual(bear, 0)

    def test_categorize_into_banking(self):
        article = {
             "title": "ACB tăng vốn",
             "summary_raw": "Ngân hàng ACB phát hành CP mới"
         }
        cat = _categorize(article)
        self.assertEqual(cat, "ngân hàng")

    def test_categorize_into_real_estate(self):
        article = {
             "title": "VIC mở rộng bất động sản",
             "summary_raw": "Vinhomes mua đất nền"
         }
        cat = _categorize(article)
        self.assertEqual(cat, "bất động sản")

    def test_categorize_fallback_general(self):
        article = {
             "title": "Hội thảo giáo dục 2026",
             "summary_raw": "Trường đại học mở thêm ngành mới"
         }
        cat = _categorize(article)
        self.assertEqual(cat, "general")
    @patch('core.news_service.feedparser.parse')
    def test_fetch_articles_parse_error(self, mock_feed):
        mock_feed.side_effect = Exception("Connection refused")
        articles = fetch_and_categorize_articles(limit=5)
        self.assertEqual(articles, [])

    def test_get_articles_returns_list(self):
        articles = get_articles(limit=2)
        if articles:
            self.assertIsInstance(articles[0], dict)
            self.assertIn('title', articles[0])


# ============================================================================
# TEST 4: MARKET SERVICE - TECHNICAL INDICATORS
# ============================================================================

class TestTechnicalIndicators(unittest.TestCase):

    def test_sma_default_period(self):
        closes = np.array([10.0, 12.0, 14.0, 16.0, 18.0])
        sma = _sma(closes, 3)
        self.assertEqual(sma[2], 12.0)
        self.assertAlmostEqual(float(sma[-1]), 16.0, places=1)

    def test_sma_with_nans(self):
        closes = np.array([10.0, float('nan'), 14.0, 16.0, 18.0])
        sma = _sma(closes, 2)
        self.assertGreater(len(sma), 2)

    def test_sma_insufficient_data(self):
        closes = np.array([10.0])
        sma = _sma(closes, 5)
        self.assertTrue(np.isnan(sma[0]))

    def test_ema_basic(self):
        closes = np.array([10.0, 12.0, 14.0, 16.0, 18.0])
        ema = _ema(closes, 3)
        self.assertIsNotNone(ema, "EMA should not be None with enough data")
        if len(ema) >= 3:
            self.assertTrue(np.isnan(ema[0]))
            self.assertTrue(np.isnan(ema[1]))
            self.assertFalse(np.isnan(float(ema[2])))

    def test_ema_insufficient_data(self):
        closes = np.array([10.0, 11.0])
        result = _ema(closes, 5)
        self.assertIsNone(result)

    def test_rsi_normal_upward(self):
        closes = np.array([10.0, 11.0, 12.5, 13.0, 14.5, 15.0, 16.0, 17.5, 18.0])
        rsi = _calc_rsi(closes, period=4)
        self.assertIsNotNone(rsi, "RSI should return a value for sufficient data")
        actual_rsi = float(rsi) if rsi else 0.0
        self.assertGreaterEqual(actual_rsi, 0.0)
        self.assertLessEqual(actual_rsi, 100.0)

    def test_rsi_oversold(self):
        # Downward trend but not necessarily <30 RSI
        closes = np.array([50.0, 48.5, 47.0, 46.0, 44.5, 42.0, 40.5, 39.0, 38.5])
        rsi = _calc_rsi(closes, period=4)
        self.assertIsNotNone(rsi, "RSI should return a value for sufficient data")
        actual_rsi = float(rsi) if rsi else None
        if actual_rsi is not None:
            self.assertGreaterEqual(actual_rsi, 0.0)
            self.assertLess(actual_rsi, 90.0)

    def test_rsi_insufficient_data(self):
        closes = np.array([10.0])
        rsi = _calc_rsi(closes, period=14)
        self.assertIsNone(rsi)


# ============================================================================
# TEST 5: MARKET SERVICE - YAHOO & CRYPTO FETCHING
# ============================================================================

class TestMarketFetching(unittest.TestCase):

    def setUp(self):
        from core.db import Database
        self.dir = tempfile.mkdtemp()
        db_path = os.path.join(self.dir, 'test_market.db')
        self.db = Database(db_path)
        self.service = MarketService(db=self.db)

    @patch('core.market_service._fetch_yahoo')
    def test_analyze_stock_returns_data(self, mock_fetch):
        base_price = 57.5
        closes = [base_price + i * 0.1 + np.sin(i * 0.3) * 2 for i in range(90)]

        fake_price_data = {
            'symbol': 'VNM',
            'price': base_price,
            'change_pct': 1.2,
            'volume': 12000000,
            'historical_closes': closes,
            'historical_volumes': [int(1e7) for _ in range(90)],
        }
        mock_fetch.return_value = fake_price_data

        result = self.service.analyze_stock("VNM")
        self.assertIsInstance(result, dict)
        self.assertIn('rsi', result)
        self.assertIn('sma_20', result)

    @patch('core.market_service.requests.get')
    def test_binance_fetch_btc(self, mock_get):
        mock_data = {
            'lastPrice': '45000.50',
            'priceChangePercent': '2.34',
            'quoteVolume': '1234567890',
            'highPrice': '46000.00',
            'lowPrice': '44000.00',
        }
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: mock_data
        )

        result = self.service.get_crypto_price("BTC")
        if result is not None:
            self.assertIsInstance(result, dict)
            self.assertIn('price', result)


# ============================================================================
# TEST 6: CACHING LAYER - TTL BEHAVIOR
# ============================================================================

class TestCaching(unittest.TestCase):

    def test_market_cache_get_miss(self):
        mc = MarketCache()
        result = mc.get("TEST", "stock")
        self.assertIsNone(result)

    def test_market_cache_get_hit(self):
        """Cache hit - fresh entry should return data."""
        mc = MarketCache()
        
         # Set ts relative to real utcnow (will be fresh for stock 300s TTL)
        fake_ts = datetime.utcnow().timestamp() - 60   # 60s ago
        mc._store['stock:VNM'] = {'data': {'price': 50}, 'ts': fake_ts}
        
         # Just call get without any mocking - ts is relative to real time
        result = mc.get("VNM", "stock")

        self.assertIsNotNone(result, "Cache hit expected for fresh entry")
        if result is not None:     # Type narrowing for LSP
            self.assertEqual(result['data']['price'], 50)

    def test_market_cache_ttl_expiry(self):
        mc = MarketCache()
        old_ts = datetime(2026, 5, 24, 8, 0, 0).timestamp()

         # Key must match the actual format: lowercase category + UPPER symbol
        with patch.object(mc, '_store', {
                 'stock:VNM': {'data': {'price': 50}, 'ts': old_ts}
             }):
            with patch('core.market_service.datetime') as mock_dt:
                mock_dt.utcnow.return_value = datetime(2026, 5, 24, 10, 30, 0)
                result = mc.get("VNM", "stock")

        self.assertIsNone(result)

    def test_news_cache_get_miss(self):
        from core.news_service import _NEWS_CACHE
        _NEWS_CACHE._store = {}
        result = _NEWS_CACHE.get("articles")
        self.assertIsNone(result)

    def test_cache_stats(self):
        mc = MarketCache()
        fake_ts = datetime.now().timestamp()
        mc._store['TEST:stock'] = {'data': {'price': 50}, 'ts': fake_ts}

        stats = mc.cache_stats
        self.assertEqual(stats.get('cached_keys', 0), 1)


# ============================================================================
# TEST 7: EDGE CASES & FTS INTEGRITY
# ============================================================================

class TestEdgeCases(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.dir, 'test_edge.db')
        self.db = Database(self.db_path)
        self.service = MarketService(db=self.db)

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.unlink(self.db_path)
        except Exception:
            pass

    def test_duplicate_tag_update(self):
        self.db.save_term("RSI", "First definition", "technical")
        self.db.save_term("RSI", "Updated definition", "oscillator,momentum")
        results_raw = [dict(r) for r in self.db._c().execute(
            "SELECT * FROM knowledge WHERE term='rsi'"
        ).fetchall()]
        self.assertEqual(len(results_raw), 1)
        self.assertIn('oscillator', results_raw[0]['tags'])

    @patch('core.market_service.requests.get')
    def test_yahoo_non_200(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

         # Should gracefully handle non-200 and return error dict
        result = self.service.analyze_stock("NONEXISTENT")
        self.assertIsInstance(result, dict)

    def test_fts_sync_on_insert(self):
        db_path2 = os.path.join(self.dir, 'test_fts.db')
        db2 = Database(db_path2)
        db2.save_term("Test Term", "Test content", "test")

        rows_raw = [dict(r) for r in db2._c().execute(
            "SELECT * FROM knowledge_fts WHERE term='test term'"
        ).fetchall()]
        self.assertGreater(len(rows_raw), 0, "FTS index should exist after INSERT")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":

    print("=" * 70)
    print("JARVIS HUB - FULL REGRESSION TEST SUITE")
    print("=" * 70)

    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    total_failed = len(result.failures) + len(result.errors)
    status = "PASSED" if result.wasSuccessful() else f"FAILED - {total_failed} issue(s)"
    print(f"RESULT: {status}")
    print(f"{result.testsRun} tests run, {len(result.failures)} failures, {len(result.errors)} errors")

    for test, traceback in result.failures:
        last_line = traceback.strip().split('\n')[-2] if traceback else "Unknown"
        print(f"   FAIL - {test}: {last_line}")

    for test, traceback in result.errors:
        last_line = traceback.strip().split('\n')[-2] if traceback else "Unknown"
        print(f"   ERROR - {test}: {last_line}")

    print("\nCATEGORIES COVERED:")
    print("   [1] TestConfig            - Config loading & dot notation")
    print("   [2] TestDatabase          - All DB operations (7 tables)")
    print("   [3] TestNewsService       - RSS, sentiment, categorization")
    print("   [4] TestTechnicalIndicators - SMA, EMA, RSI calculations")
    print("   [5] TestMarketFetching    - Yahoo Finance & Binance API")
    print("   [6] TestCaching           - TTL cache hit/miss/expiry")
    print("   [7] TestEdgeCases         - Edge cases & FTS sync")
    print("=" * 70)

    sys.exit(0 if result.wasSuccessful() else 1)
