#!/usr/bin/env python3
"""JH3.0 Daily Regression Test - Lightweight version.

Tests run in <30s: import checks, config validation, DB schema, API routes.
No server, no conftest — pure unit tests that work in cron.

Usage:
  cd /Users/nghialam/jarvis-hub && python3 scripts/jhrs-regression-tests.py
"""

import os
import sys
import json
import sqlite3
import time
import subprocess

# Setup paths
PROJECT_ROOT = "/Users/nghialam/jarvis-hub"
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)


# -------------------------
# Test 1: Core imports
# -------------------------
def test_core_module_imports():
    """Verify all core modules can be imported without errors."""
    modules = [
        "core.market",
        "core.vn_market",
        "core.market_overview",
        "core.market_service",
        "core.news",
        "core.news_service",
        "core.config",
        "core.db",
        "core.cache_manager",
        "core.events",
        "core.telegram_delivery",
    ]
    for mod in modules:
        __import__(mod)


def test_api_module_imports():
    """Verify all API blueprints load cleanly."""
    modules = [
        "api.news",
        "api.market_brief",
        "api.auth",
        "api.cms",
        "api.intelligence",
        "api.stocks",
        "api.screener",
        "api.research",
        "api.portfolio",
        "api.llm",
        "api.events",
    ]
    for mod in modules:
        __import__(mod)


# -------------------------
# Test 2: Config validation
# -------------------------
def test_config_loads():
    """Verify config.py loads and validates."""
    from core.config import (
        load_config,
        _load_profile,
        _DEFAULT_PROFILES,
        get,
        get_env,
    )
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "db" in cfg or "jarvis_db" in cfg
    # Verify env profiles exist
    for env in ("prod", "staging", "dev"):
        profile = _load_profile(env)
        assert isinstance(profile, dict)
        assert "debug" in profile


def test_config_env_override():
    """Verify JARVIS_ENV env var is respected by _load_profile."""
    import os as _os
    original = _os.environ.get("JARVIS_ENV")
    _os.environ["JARVIS_ENV"] = "prod"
    try:
        from core.config import _load_profile
        profile = _load_profile("prod")
        assert profile["debug"] == False, "prod profile should have debug=False"
        assert profile["testing"] == False, "prod profile should have testing=False"
        assert profile["log_level"] == "WARNING", "prod log_level should be WARNING"
    finally:
        if original:
            _os.environ["JARVIS_ENV"] = original
        elif "JARVIS_ENV" in _os.environ:
            del _os.environ["JARVIS_ENV"]


# -------------------------
# Test 3: DB schema
# -------------------------
def test_db_exists_and_readable():
    """Verify jarvis.db exists and is readable."""
    db_path = os.path.join(PROJECT_ROOT, "data", "jarvis.db")
    assert os.path.exists(db_path), f"jarvis.db not found at {db_path}"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA integrity_check")
    conn.close()


def test_db_table_count():
    """Verify jarvis.db has expected number of tables."""
    import sqlite3
    db_path = os.path.join(PROJECT_ROOT, "data", "jarvis.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    count = cur.fetchone()[0]
    # Should have 30+ tables after JH3.0
    assert count >= 30, f"Expected 30+ tables, got {count}"
    conn.close()


def test_market_briefs_schema():
    """Verify market_briefs table has correct columns."""
    import sqlite3
    db_path = os.path.join(PROJECT_ROOT, "data", "jarvis.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(market_briefs)")
    columns = {row[1] for row in cur.fetchall()}
    expected = {"id", "date", "source", "created_at", "formatted_output", "raw_json"}
    assert expected.issubset(columns), f"market_briefs missing: {expected - columns}"
    conn.close()


def test_db_has_data():
    """Verify key tables have data (not just empty schema)."""
    import sqlite3
    db_path = os.path.join(PROJECT_ROOT, "data", "jarvis.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check a few tables that should have data
    cur.execute("SELECT count(*) FROM events")
    events_count = cur.fetchone()[0]
    assert events_count > 0, "events table is empty"

    cur.execute("SELECT count(*) FROM market_briefs")
    briefs_count = cur.fetchone()[0]
    # May be 0 in fresh setup, just make sure it doesn't crash
    assert isinstance(briefs_count, int)

    conn.close()


# -------------------------
# Test 4: Script files
# -------------------------
def test_critical_scripts_syntax():
    """Verify critical scripts have valid Python syntax."""
    scripts = [
        "api/news.py",
        "api/market_brief.py",
        "core/market.py",
        "core/vn_market.py",
        "api/auth.py",
        "api/cms.py",
    ]
    for script in scripts:
        path = os.path.join(PROJECT_ROOT, script)
        assert os.path.exists(path), f"Script not found: {script}"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Syntax error in {script}: {result.stderr}"


# -------------------------
# Test 5: Flask blueprint registration
# -------------------------
def test_blueprint_registration():
    """Verify all blueprints register on a Flask app without errors."""
    from flask import Flask
    from api import register_blueprints

    app = Flask(__name__,
                static_folder=os.path.join(PROJECT_ROOT, "dashboard/static"),
                template_folder=os.path.join(PROJECT_ROOT, "dashboard/templates"))
    app.config["SECRET_KEY"] = "test-secret-key-for-regression"

    with app.app_context():
        report = register_blueprints(app)

    assert isinstance(report, dict)
    assert "registered" in report
    assert len(report["registered"]) >= 10, f"Only {len(report['registered'])} blueprints registered"
    # Check market_brief_bp is in the registered list (case-sensitive check)
    bp_names = [str(b) for b in report["registered"]]
    assert any("market_brief" in b.lower() for b in bp_names), f"market_brief not in {bp_names}"


# -------------------------
# Test 6: Market data functions
# -------------------------
def test_market_module_exports():
    """Verify core.market has expected functions."""
    import core.market as market
    # Check function signatures exist
    funcs = ["analyze_stock", "calculate_technical_indicators",
             "fetch_crypto", "fetch_dxy", "fetch_gold_price", "fetch_oil",
             "generate_technical_summary", "llm_due_diligence", "format_market_cap"]
    for f in funcs:
        assert hasattr(market, f), f"core.market missing: {f}"


def test_market_brief_module_exports():
    """Verify api.market_brief has expected endpoints."""
    import api.market_brief as mb
    funcs = ["list_market_briefs", "get_market_brief",
             "latest_market_brief", "brief_count"]
    for f in funcs:
        assert hasattr(mb, f), f"api.market_brief missing: {f}"


# -------------------------
# Test 7: Cron scripts availability
# -------------------------
def test_cron_scripts_exist():
    """Verify cron scripts referenced in jobs exist."""
    cron_scripts = [
        "/Users/nghialam/.hermes/scripts/daily-brief-data.py",
        "/Users/nghialam/.hermes/scripts/daily-stock-recs-data.py",
        "/Users/nghialam/.hermes/scripts/jarvis-hub-regression-collect.sh",
    ]
    for script in cron_scripts:
        assert os.path.exists(script), f"Cron script not found: {script}"


def test_cron_script_syntax():
    """Verify cron scripts have valid syntax (Python or bash)."""
    cron_scripts = [
        "/Users/nghialam/.hermes/scripts/daily-brief-data.py",
        "/Users/nghialam/.hermes/scripts/daily-stock-recs-data.py",
        "/Users/nghialam/.hermes/scripts/jarvis-hub-regression-collect.sh",
    ]
    for script in cron_scripts:
        with open(script) as f:
            first_line = f.readline().strip()
        # If Python file, compile-check it; if bash, just check exists and is readable
        if "python" in first_line:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"Syntax error in {script}: {result.stderr}"


# -------------------------
# Test 8: Services/modules
# -------------------------
def test_services_imports():
    """Verify services modules load."""
    import services.ai_signal_monitor
    import services.subscription_service
    import services.research_service


def test_core_functions_work():
    """Verify core.market.get_aggregated_data returns valid structure."""
    import core.market as market

    # get_aggregated_data should return dict-like structure
    result = market.get_aggregated_data()
    assert isinstance(result, (dict, list))


def test_market_brief_sqlite_connection():
    """Verify market_brief module can connect to DB."""
    import api.market_brief as mb
    # Just verify the module's DB_PATH is valid
    import os as _os
    assert os.path.exists(mb.DB_PATH), f"Market briefs DB not found: {mb.DB_PATH}"
    # Verify query syntax is valid (no FROM bug)
    import sqlite3
    conn = sqlite3.connect(mb.DB_PATH)
    cur = conn.cursor()
    # Basic count query
    cur.execute("SELECT count(*) FROM market_briefs")
    count = cur.fetchone()[0]
    assert isinstance(count, int)
    conn.close()


# -------------------------
# RUN ALL TESTS (as __main__)
# -------------------------
if __name__ == "__main__":
    test_functions = [
        (test_core_module_imports, "Core module imports"),
        (test_api_module_imports, "API module imports"),
        (test_config_loads, "Config loads"),
        (test_config_env_override, "Config env override"),
        (test_db_exists_and_readable, "DB exists"),
        (test_db_table_count, "DB table count"),
        (test_market_briefs_schema, "Market briefs schema"),
        (test_db_has_data, "DB has data"),
        (test_critical_scripts_syntax, "Script syntax"),
        (test_blueprint_registration, "Blueprint registration"),
        (test_market_module_exports, "Market module exports"),
        (test_market_brief_module_exports, "Market brief module exports"),
        (test_cron_scripts_exist, "Cron scripts exist"),
        (test_cron_script_syntax, "Cron script syntax"),
        (test_services_imports, "Services imports"),
    ]

    failed = []
    total = len(test_functions)
    start = time.time()

    for test_fn, name in test_functions:
        try:
            test_fn()
            print(f"  OK {name}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed.append((name, str(e)))

    elapsed = time.time() - start

    print(f"\n{'='*60}")
    print(f"Results: {total - len(failed)}/{total} passed in {elapsed:.1f}s")

    if failed:
        print("\nFailed tests:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        sys.exit(1)
    else:
        print("All regression tests passed! 🎉")
        sys.exit(0)
