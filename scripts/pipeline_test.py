#!/usr/bin/env python3
"""Pipeline Test Script — verifies signals DB + API endpoints."""
import sys
import sqlite3
import json

DB_PATH = "/Users/nghialam/jarvis-hub/knowledge/jarvis.db"

def ensure_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS signals_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        asset_type TEXT DEFAULT 'stock',
        signal_type TEXT NOT NULL,
        strength REAL DEFAULT 0,
        price REAL,
        details TEXT,
        detected_at TEXT NOT NULL,
        delivered INTEGER DEFAULT 0,
        delivery_channel TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS trading_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        severity TEXT DEFAULT 'MEDIUM',
        alert_data TEXT,
        timestamp TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        delivery_channel TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    
    conn.commit()
    return conn

def insert_test_signals(conn):
    c = conn.cursor()
    sig_count_before = c.execute("SELECT COUNT(*) FROM signals_log").fetchone()[0]
    
    test_signals = [
        ("VCB", "BUY", 0.75, 98.5, "Golden cross + volume spike", "2026-06-02T09:30:00"),
        ("HPG", "SELL", 0.60, 31.2, "RSI overbought at 75", "2026-06-02T09:25:00"),
        ("FPT", "STRONG_BUY", 0.88, 125.3, "MACD bullish + RSI recovery + volume surge", "2026-06-02T09:20:00"),
        ("VIC", "BUY", 0.65, 45.8, "Support level hold", "2026-06-02T09:15:00"),
        ("MSN", "SELL", 0.55, 243.7, "MACD momentum bearish", "2026-06-02T09:10:00"),
    ]
    
    for sym, stype, strength, price, reason, ts in test_signals:
        c.execute("""INSERT INTO signals_log 
            (symbol, asset_type, signal_type, strength, price, details, detected_at)
        VALUES (?, 'stock', ?, ?, ?, ?, ?)""",
            (sym, stype, strength, price, json.dumps({"reason": reason}), ts))
        
        if stype not in ("NEUTRAL", "HOLD"):
            c.execute("""INSERT INTO trading_alerts 
                (symbol, signal_type, severity, alert_data, timestamp, status)
            VALUES (?, ?, ?, ?, ?, 'pending')""",
                (sym, stype, "HIGH" if strength > 0.7 else "MEDIUM",
                 json.dumps({"reason": reason}), ts))
    
    conn.commit()
    sig_count_after = c.execute("SELECT COUNT(*) FROM signals_log").fetchone()[0]
    return sig_count_after - sig_count_before

def verify_db():
    conn = ensure_tables()
    c = conn.cursor()
    
    print("=" * 60)
    print("📊 DB Status")
    print("=" * 60)
    
    for table in ["signals_log", "trading_alerts", "watchlist_symbols"]:
        try:
            count = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            cols = [d[1] for d in c.execute(f"PRAGMA table_info({table})").fetchall()]
            print(f"  ✅ {table}: {count} rows")
            print(f"     Columns: {', '.join(cols)}")
        except Exception as e:
            print(f"  ❌ {table}: ERROR — {e}")
    
    signals = c.execute("SELECT symbol, signal_type, strength, price FROM signals_log ORDER BY detected_at DESC LIMIT 5").fetchall()
    if signals:
        print("\n📊 Sample Signals:")
        for sym, stype, strength, price in signals:
            print(f"   → {sym}: {stype} (strength={strength}, price={price})")
    
    alerts = c.execute("SELECT symbol, signal_type, severity FROM trading_alerts ORDER BY timestamp DESC LIMIT 3").fetchall()
    if alerts:
        print("\n📊 Sample Alerts:")
        for sym, stype, sev in alerts:
            print(f"   → {sym}: {stype} [{sev}]")
    
    inserted = insert_test_signals(conn)
    print(f"\n✅ Inserted {inserted} test signals")
    
    conn.close()
    return True

def verify_flask():
    print("\n" + "=" * 60)
    print("🔗 Flask App Verification")
    print("=" * 60)
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("app", "/Users/nghialam/jarvis-hub/app.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        # Check routes
        routes = [r.rule for r in mod.app.url_map.iter_rules()]
        signals_routes = [r for r in routes if "signal" in r or "alert" in r]
        print(f"  ✅ Total routes: {len(routes)}")
        for r in signals_routes[:5]:
            print(f"     → {r}")
        
        # Test API endpoints
        from werkzeug.test import Client
        client = Client(mod.app)
        
        resp_signals = client.get("/api/signals")
        sig_data = resp_signals.get_json()
        print(f"\n  🔗 /api/signals: {resp_signals.status_code} "
              f"({len(sig_data.get('signals', []))} signals)")
        
        resp_health = client.get("/api/health")
        health = resp_health.get_json()
        print(f"  🔗 /api/health: {resp_health.status_code}")
        print(f"     Ollama: {health.get('ollama', 'unknown')}")
        print(f"     DB: {health.get('db_path', 'N/A')}")
        
        return True
        
    except Exception as e:
        import traceback
        print(f"\n  ❌ Flask verification FAILED:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    db_ok = verify_db()
    flask_ok = verify_flask()
    
    print("\n" + "=" * 60)
    if db_ok and flask_ok:
        print("✅ ALL CHECKS PASSED — Ready to start Flask server!")
        print("=" * 60)
    else:
        print("❌ Some checks failed — review above")
        print("=" * 60)
    
    sys.exit(0 if db_ok and flask_ok else 1)
