"""Comprehensive API endpoint tests for JH3.0."""
import pytest

class TestHealthAndStatus:
    """Test health, status, and logs endpoints."""

    def test_health(self, client):
        """GET /api/v1/health returns 200 with status."""
        r = client.get('/api/v1/health')
        assert r.status_code == 200
        data = r.get_json()
        assert data['status'] in ['ok', 'degraded', 'error']
        assert 'components' in data

    def test_status(self, client):
        """GET /api/v1/status returns 200."""
        r = client.get('/api/v1/status')
        assert r.status_code == 200
        data = r.get_json()
        assert 'async_queue' in data

    def test_logs(self, client):
        """GET /api/v1/logs returns 200."""
        r = client.get('/api/v1/logs')
        assert r.status_code == 200
        data = r.get_json()
        assert 'logs' in data

class TestNewsEndpoints:
    """Test news API endpoints."""

    def test_news_trending(self, client):
        r = client.get('/api/v1/news/trending')
        assert r.status_code == 200
        data = r.get_json()
        assert 'status' in data
        assert 'articles' in data

    def test_news_categories(self, client):
        r = client.get('/api/v1/news/categories')
        assert r.status_code == 200
        data = r.get_json()
        assert 'categories' in data

    def test_news_search_empty(self, client):
        r = client.get('/api/v1/news/search?q=VCB')
        assert r.status_code == 200
        data = r.get_json()
        assert 'articles' in data

    def test_news_score(self, client):
        r = client.post('/api/v1/news/score', json={})
        assert r.status_code == 200
        data = r.get_json()
        assert 'status' in data

class TestStocksEndpoints:
    """Test stock API endpoints."""

    def test_stocks_watchlist_get(self, client):
        r = client.get('/api/v1/stocks/watchlist')
        assert r.status_code == 200
        data = r.get_json()
        assert 'symbols' in data or 'count' in data

    def test_stocks_watchlist_add(self, client):
        r = client.post('/api/v1/stocks/watchlist/add', json={'symbol': 'ABC'})
        assert r.status_code == 200

    def test_stocks_quotes(self, client):
        r = client.get('/api/v1/stocks/quotes?symbol=VCB')
        assert r.status_code == 200
        data = r.get_json()
        assert 'quotes' in data or 'count' in data

    def test_stocks_symbols_search(self, client):
        r = client.get('/api/v1/stocks/symbols/search?q=VIC')
        assert r.status_code == 200

class TestScreenerEndpoints:
    """Test screener API endpoints."""

    def test_signals(self, client):
        r = client.get('/api/v1/screener/signals')
        assert r.status_code == 200

    def test_alert_feed(self, client):
        r = client.get('/api/v1/screener/alert-feed')
        assert r.status_code == 200

    def test_alert_feed_post(self, client):
        r = client.post('/api/v1/screener/alert', json={
            'symbol': 'TEST', 'price': 100, 'signal_type': 'BUY'
        })
        assert r.status_code == 200

    def test_screener_watchlist(self, client):
        r = client.get('/api/v1/screener/watchlist')
        assert r.status_code == 200

class TestResearchEndpoints:
    """Test research API endpoints."""

    def test_reports(self, client):
        r = client.get('/api/v1/research/reports')
        assert r.status_code == 200
        data = r.get_json()
        assert 'reports' in data

    def test_stats(self, client):
        r = client.get('/api/v1/research/stats')
        assert r.status_code == 200

    def test_crawl(self, client):
        r = client.post('/api/v1/research/crawl', json={})
        assert r.status_code == 200

class TestPortfolioEndpoints:
    """Test portfolio API endpoints."""

    def test_holdings(self, client):
        r = client.get('/api/v1/portfolio/holdings')
        assert r.status_code == 200
        data = r.get_json()
        assert 'holdings' in data

    def test_transactions(self, client):
        r = client.get('/api/v1/portfolio/transactions')
        assert r.status_code == 200
        data = r.get_json()
        assert 'transactions' in data

    def test_pnl(self, client):
        r = client.get('/api/v1/portfolio/pnl')
        assert r.status_code == 200
        data = r.get_json()
        assert 'pnl' in data

    def test_add_transaction(self, client):
        r = client.post('/api/v1/portfolio/add', json={
            'symbol': 'VCB', 'action': 'BUY', 'quantity': 10, 'price': 50
        })
        assert r.status_code == 200

class TestCMSEndpoints:
    """Test CMS API endpoints."""

    def test_get_articles(self, client):
        r = client.get('/api/v1/cms/articles')
        assert r.status_code == 200
        data = r.get_json()
        assert 'articles' in data

    def test_create_article(self, client):
        r = client.post('/api/v1/cms/articles', json={
            'title': 'Test Article', 'content': 'Test content', 'category': 'news'
        })
        assert r.status_code == 200

class TestIntelligenceEndpoints:
    """Test intelligence API endpoints."""

    def test_market_history(self, client):
        r = client.get('/api/v1/intelligence/market/history')
        assert r.status_code == 200

    def test_market_latest(self, client):
        r = client.get('/api/v1/intelligence/market/latest')
        assert r.status_code == 200

    def test_market_sentiment(self, client):
        r = client.get('/api/v1/intelligence/market/latest/sentiment')
        assert r.status_code == 200

    def test_ai_daily_list(self, client):
        r = client.get('/api/v1/intelligence/ai/daily-list')
        assert r.status_code == 200

    def test_market_run(self, client):
        r = client.post('/api/v1/intelligence/market/run', json={})
        assert r.status_code == 200
        data = r.get_json()
        assert 'task_id' in data or 'status' in data

    def test_pipeline_status(self, client):
        r = client.get('/api/v1/intelligence/pipeline/status')
        assert r.status_code == 200

class TestLLMEndpoints:
    """Test LLM API endpoints."""

    def test_llm_health(self, client):
        r = client.get('/api/v1/llm/health')
        assert r.status_code == 200

    def test_llm_stats(self, client):
        r = client.get('/api/v1/llm/stats')
        assert r.status_code == 200

    def test_llm_tasks(self, client):
        r = client.get('/api/v1/llm/tasks')
        assert r.status_code == 200

    def test_llm_submit_task(self, client):
        r = client.post('/api/v1/llm/tasks/submit', json={
            'task_type': 'analyze_stock', 'payload': {'symbol': 'VCB'}
        })
        assert r.status_code == 200
        data = r.get_json()
        assert 'task_id' in data

    def test_llm_circuit_reset(self, client):
        r = client.post('/api/v1/llm/circuit/reset', json={})
        assert r.status_code == 200
