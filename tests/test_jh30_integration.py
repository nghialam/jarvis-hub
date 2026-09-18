#!/usr/bin/env python3
"""
Jarvis Hub 3.0 — Comprehensive Integration Test Suite

Tests all JH3.0 components: context sharing, blueprint wiring, DB access,
async queue, precompute scheduler, security middleware, and API endpoints.

Usage:
    python -m pytest tests/test_jh30_integration.py -v
    python tests/test_jh30_integration.py
"""
import sys
import os
import json
import time
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Test results tracking
results = []
total = 0
passed = 0
failed = 0


def _test(name, func):
    """Decorator to register and run a test."""
    global total, passed, failed
    total += 1
    try:
        start = time.time()
        result = func()
        elapsed = time.time() - start
        passed += 1
        status = "PASS"
        message = "OK"
        results.append({
            "name": name,
            "status": status,
            "message": message,
            "duration_ms": round(elapsed * 1000, 1)
        })
        print(f"  ✅ {name} ({elapsed*1000:.0f}ms)")
    except Exception as e:
        elapsed = time.time() - start
        failed += 1
        status = "FAIL"
        message = str(e)
        tb = traceback.format_exc()
        results.append({
            "name": name,
            "status": status,
            "message": message,
            "duration_ms": round(elapsed * 1000, 1),
            "traceback": tb
        })
        print(f"  ❌ {name}: {e}")


def run_all_tests():
    """Run all integration tests."""
    print("=" * 70)
    print("Jarvis Hub 3.0 — Integration Test Suite")
    print("=" * 70)

    # Phase 1: Core Context Tests
    print("\n[Phase 1] Core Context & Shared State")
    _test("Core context module exists", lambda: __import__("core.context"))
    
    def test_context_singleton():
        from core.context import get_context, init_context, _AppContext
        ctx = get_context()
        assert isinstance(ctx, _AppContext), "Context should be _AppContext instance"
        assert ctx.db is None, "Context should start with db=None"
        assert ctx.config == {}, "Context should start with empty config"
    _test("Context singleton pattern", test_context_singleton)
    
    def test_context_init():
        from core.context import init_context, get_context
        class MockDB:
            def _c(self): return None
        init_context(MockDB(), {"test": "value"})
        ctx = get_context()
        assert ctx.db is not None, "DB should be set after init"
        assert ctx.config.get("test") == "value", "Config should be set"
    _test("Context init with DB + config", test_context_init)
    
    # Phase 2: Blueprint Imports
    print("\n[Phase 2] Blueprint Module Imports")
    def test_blueprint_imports():
        import api.llm
        import api.news
        import api.main
        import api.stocks
        import api.screener
        import api.research
        import api.portfolio
        import api.cms
        import api.intelligence
        import api.auth
        import api
    _test("All blueprint modules import", test_blueprint_imports)
    
    def test_blueprint_registration():
        from flask import Flask
        from api import register_blueprints
        app = Flask(__name__)
        result = register_blueprints(app)
        assert "registered" in result, "Should return registration result"
        assert len(result["registered"]) > 0, "At least one blueprint should register"
        print(f"  Registered {len(result['registered'])} blueprints, {len(result.get('failed', []))} failed")
    _test("Blueprint registration works", test_blueprint_registration)
    
    # Phase 3: Database Context Integration
    print("\n[Phase 3] Database + Context Integration")
    def test_db_auto_registers_context():
        import core.db
        from core.context import get_context
        # Create a test DB
        db = core.db.Database(":memory:")
        ctx = get_context()
        assert ctx.db is not None, "DB should auto-register with context"
    _test("DB auto-registers with context", test_db_auto_registers_context)
    
    def test_db_query_via_context():
        import core.db
        from core.context import get_context
        db = core.db.Database(":memory:")
        ctx = get_context()
        # Create test table
        ctx.db._c().execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        ctx.db._c().execute("INSERT INTO test (name) VALUES ('hello')")
        ctx.db._conn.commit()
        # Query via context
        rows = ctx.db._c().execute("SELECT * FROM test").fetchall()
        assert len(rows) == 1, f"Should have 1 row, got {len(rows)}"
        assert rows[0]["name"] == "hello", "Query should return correct data"
    _test("DB queries via context work", test_db_query_via_context)
    
    # Phase 4: API Blueprint Endpoint Tests
    print("\n[Phase 4] API Blueprint Endpoint Tests")
    def test_health_endpoint():
        from flask import Flask
        from api.main import main_bp
        from core.context import init_context
        class MockDB:
            def _c(self): return None
        init_context(MockDB(), {})
        
        app = Flask(__name__)
        app.register_blueprint(main_bp)
        with app.test_client() as client:
            response = client.get("/api/v1/health")
            assert response.status_code == 200, f"Health should return 200, got {response.status_code}"
            data = response.get_json()
            assert "status" in data, "Response should have status"
    _test("Health endpoint works", test_health_endpoint)
    
    def test_llm_task_submit():
        from flask import Flask
        from api.llm import llm_bp
        from core.async_queue import get_async_queue
        
        app = Flask(__name__)
        app.register_blueprint(llm_bp)
        queue = get_async_queue()
        queue.start()
        
        with app.test_client() as client:
            response = client.post("/api/v1/llm/tasks",
                                  json={"task_type": "test", "payload": {"key": "value"}})
            assert response.status_code == 200, f"Submit should return 200, got {response.status_code}"
            data = response.get_json()
            assert data["status"] == "ok", "Submit should succeed"
            assert "task_id" in data, "Response should have task_id"
    _test("LLM task submit works", test_llm_task_submit)
    
    def test_news_search():
        from flask import Flask
        from api.news import news_bp
        from core.context import init_context
        import core.db
        
        db = core.db.Database(":memory:")
        db._c().execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, content TEXT, publication_date TEXT)")
        db._c().execute("INSERT INTO articles (title, content, publication_date) VALUES ('Test Article', 'Test content', '2026-09-12')")
        db._conn.commit()
        init_context(db, {})
        
        app = Flask(__name__)
        app.register_blueprint(news_bp)
        with app.test_client() as client:
            response = client.get("/api/v1/news/search?q=Test")
            assert response.status_code == 200, f"Search should return 200, got {response.status_code}"
            data = response.get_json()
            assert data["status"] == "ok", "Search should succeed"
    _test("News search endpoint works", test_news_search)
    
    # Phase 5: Portfolio Endpoint Tests
    print("\n[Phase 5] Portfolio Endpoint Tests")
    def test_portfolio_holdings():
        from flask import Flask
        from api.portfolio import portfolio_bp
        from core.context import init_context
        import core.db
        
        db = core.db.Database(":memory:")
        db._c().execute("""CREATE TABLE portfolio_watchlist (
            id INTEGER PRIMARY KEY, symbol TEXT, quantity INTEGER,
            avg_price REAL, current_price REAL, total_cost REAL, current_value REAL
        )""")
        db._c().execute("INSERT INTO portfolio_watchlist (symbol, quantity, avg_price, current_price, total_cost, current_value) VALUES ('VCB', 100, 50, 60, 5000, 6000)")
        db._conn.commit()
        init_context(db, {})
        
        app = Flask(__name__)
        app.register_blueprint(portfolio_bp)
        with app.test_client() as client:
            response = client.get("/api/v1/portfolio/holdings")
            assert response.status_code == 200, f"Holdings should return 200, got {response.status_code}"
            data = response.get_json()
            assert data["count"] >= 1, f"Should have at least 1 holding, got {data['count']}"
    _test("Portfolio holdings endpoint works", test_portfolio_holdings)
    
    def test_portfolio_pnl():
        from flask import Flask
        from api.portfolio import portfolio_bp
        from core.context import init_context
        import core.db
        
        db = core.db.Database(":memory:")
        db._c().execute("""CREATE TABLE portfolio_watchlist (
            id INTEGER PRIMARY KEY, symbol TEXT, quantity INTEGER,
            avg_price REAL, current_price REAL, total_cost REAL, current_value REAL
        )""")
        db._c().execute("INSERT INTO portfolio_watchlist (symbol, quantity, avg_price, current_price, total_cost, current_value) VALUES ('VCB', 100, 50, 60, 5000, 6000)")
        db._conn.commit()
        init_context(db, {})
        
        app = Flask(__name__)
        app.register_blueprint(portfolio_bp)
        with app.test_client() as client:
            response = client.get("/api/v1/portfolio/pnl")
            assert response.status_code == 200, f"PnL should return 200, got {response.status_code}"
            data = response.get_json()
            assert "pnl" in data, "Response should have pnl"
            assert data["pnl"]["total"] == 1000, f"PnL should be 1000, got {data['pnl']['total']}"
    _test("Portfolio PnL endpoint works", test_portfolio_pnl)
    
    def test_portfolio_add_transaction():
        from flask import Flask
        from api.portfolio import portfolio_bp
        from core.context import init_context
        import core.db
        
        db = core.db.Database(":memory:")
        db._c().execute("CREATE TABLE portfolio_transactions (id INTEGER PRIMARY KEY, symbol TEXT, action TEXT, quantity INTEGER, price REAL, total REAL, status TEXT)")
        init_context(db, {})
        
        app = Flask(__name__)
        app.register_blueprint(portfolio_bp)
        with app.test_client() as client:
            response = client.post("/api/v1/portfolio/add",
                                  json={"symbol": "VCB", "action": "BUY", "quantity": 100, "price": 50})
            assert response.status_code == 200, f"Add txn should return 200, got {response.status_code}"
            data = response.get_json()
            assert data["success"] is True, "Transaction should succeed"
            assert data["total"] == 5000, f"Total should be 5000, got {data['total']}"
    _test("Portfolio add transaction endpoint works", test_portfolio_add_transaction)
    
    # Phase 6: Async Queue Tests
    print("\n[Phase 6] Async Queue Tests")
    def test_async_queue_basic():
        from core.async_queue import AsyncQueue, TaskPriority
        
        queue = AsyncQueue(num_workers=1)
        queue.start()
        try:
            task_id = queue.submit("test_task", {"key": "value"}, priority=TaskPriority.NORMAL)
            assert task_id is not None, "Should return task_id"
            
            status = queue.get_status(task_id)
            assert status is not None, "Should get status"
            assert status["status"] in ("completed", "failed"), f"Task should complete or fail, got {status['status']}"
        finally:
            queue.stop()
    _test("Async queue basic operations", test_async_queue_basic)
    
    def test_async_queue_singleton():
        from core.async_queue import get_async_queue
        
        queue1 = get_async_queue(num_workers=1)
        queue1.start()
        try:
            queue2 = get_async_queue(num_workers=1)
            assert queue1 is queue2, "Should be singleton"
        finally:
            queue1.stop()
    _test("Async queue singleton pattern", test_async_queue_singleton)
    
    # Phase 7: Security Middleware Tests
    print("\n[Phase 7] Security Middleware Tests")
    def test_security_module_imports():
        import core.security
    _test("Security module imports", test_security_module_imports)
    
    def test_rate_limiter():
        from core.security import RateLimiter
        
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        # First 5 requests should pass
        for i in range(5):
            assert limiter.is_allowed("test_ip"), f"Request {i+1} should be allowed"
        
        # 6th request should be blocked
        assert not limiter.is_allowed("test_ip"), "6th request should be blocked"
    _test("Rate limiter works", test_rate_limiter)
    
    # Phase 8: Configuration Tests
    print("\n[Phase 8] Configuration Tests")
    def test_config_loader():
        import core.config
        cfg = core.config.load_config()
        assert isinstance(cfg, dict), "Config should be dict"
        assert "db" in cfg, "Config should have db section"
        assert "db_path" in cfg, "Config should have db_path"
    _test("Config loader works", test_config_loader)
    
    # Phase 9: Documentation Verification
    print("\n[Phase 9] Documentation & Code Structure")
    def test_jh30_status_doc():
        path = Path(__file__).parent.parent / "JH3.0_IMPLEMENTATION_STATUS.md"
        assert path.exists(), "Status doc should exist"
        content = path.read_text()
        assert "2026-09-10" in content, "Status doc should have latest update"
    _test("JH3.0 status doc exists and updated", test_jh30_status_doc)
    
    def test_blueprint_count():
        from flask import Flask
        from api import register_blueprints
        
        app = Flask(__name__)
        result = register_blueprints(app)
        assert len(result["registered"]) == 10, f"Should register 10 blueprints, got {len(result['registered'])}"
    _test("All 10 blueprints register", test_blueprint_count)
    
    def test_no_database_imports_in_blueprints():
        """Verify no blueprint files import Database() directly."""
        api_dir = Path(__file__).parent.parent / "api"
        for py_file in api_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text()
            assert "from core.db import Database" not in content, \
                f"{py_file.name} should not import Database directly"
    _test("No Database() imports in blueprints", test_no_database_imports_in_blueprints)


if __name__ == "__main__":
    run_all_tests()
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Total:  {total}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print("=" * 70)
    
    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  - {r['name']}: {r['message']}")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed! JH3.0 is ready.")
        sys.exit(0)
