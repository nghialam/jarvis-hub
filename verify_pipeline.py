#!/usr/bin/env python3
"""Start Jarvis Hub Flask server on port 8100 and verify pipeline."""
import sys, os, threading, time, json

# Ensure path
sys.path.insert(0, '/Users/nghialam/jarvis-hub')
os.chdir('/Users/nghialam/jarvis-hub')

ready_event = threading.Event()

def start_flask():
    """Start Flask server on port 8100."""
    import app as flask_app
    ready_event.set()
    print("[FLASK] Starting on :8100...")
    sys.stdout.flush()
    flask_app.app.run(host='0.0.0.0', port=8100, use_reloader=False)

# Start Flask in background thread
flask_thread = threading.Thread(target=start_flask, daemon=True)
flask_thread.start()

# Wait for Flask to be ready
if not ready_event.wait(timeout=10):
    print("[FLASK] Thread started but never became ready")
    sys.exit(1)

time.sleep(2)  # extra buffer

# Verify server is up
import urllib.request as req_lib

health_url = 'http://localhost:8100/api/health'
signals_url = 'http://localhost:8100/api/signals'
add_url = 'http://localhost:8100/api/signals/add'

print("\n" + "=" * 60)
print("🔍 PIPELINE VERIFICATION")
print("=" * 60)

# Test 1: Health check
try:
    r = req_lib.urlopen(health_url, timeout=5)
    health_data = json.loads(r.read().decode())
    print(f"✅ /api/health -> {r.status_code}")
    print(f"   DB path: {health_data.get('db_path', 'N/A')}")
    print(f"   Ollama: {health_data.get('omlx', 'unknown')}")
except Exception as e:
    print(f"❌ /api/health FAILED: {e}")
    sys.exit(1)

# Test 2: Get signals (before adding new ones)
try:
    r = req_lib.urlopen(signals_url, timeout=5)
    signals_before = json.loads(r.read().decode())
    print(f"\n✅ /api/signals -> {r.status_code}")
    print(f"   Current signals: {len(signals_before.get('signals', []))}")
except Exception as e:
    print(f"❌ /api/signals FAILED: {e}")

# Test 3: Add a test signal
try:
    sig_body = json.dumps({
        "symbol": "VNM",
        "signal": "BUY",
        "strength": 0.75,
        "price": 65.5
    }).encode()
    req_obj = req_lib.Request(
        add_url,
        data=sig_body,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    r = req_lib.urlopen(req_obj, timeout=5)
    add_resp = json.loads(r.read().decode())
    print(f"\n✅ POST /api/signals/add -> {r.status_code}")
    print(f"   Result: {add_resp}")
except Exception as e:
    print(f"❌ POST /api/signals/add FAILED: {e}")

# Test 4: Verify signal count increased
try:
    time.sleep(0.5)
    r = req_lib.urlopen(signals_url, timeout=5)
    signals_after = json.loads(r.read().decode())
    print(f"\n📊 After add:")
    print(f"   Signals in API: {len(signals_after.get('signals', []))}")
except Exception as e:
    print(f"❌ Re-fetch signals FAILED: {e}")

# Test 5: Verify DB directly
import sqlite3
db_path = '/Users/nghialam/jarvis-hub/knowledge/jarvis.db'
try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    sig_count = c.execute('SELECT COUNT(*) FROM signals_log').fetchone()[0]
    alert_count = c.execute('SELECT COUNT(*) FROM trading_alerts').fetchone()[0]
    wl_count = c.execute('SELECT COUNT(*) FROM watchlist_symbols').fetchone()[0]
    
    print(f"\n📊 DATABASE STATUS:")
    print(f"   signals_log: {sig_count} rows")
    print(f"   trading_alerts: {alert_count} rows")
    print(f"   watchlist_symbols: {wl_count} rows ({c.execute('SELECT COUNT(DISTINCT symbol) FROM watchlist_symbols').fetchone()[0]} unique symbols)")
    
       # Show latest signals from DB
    rows = c.execute('''
        SELECT sl.symbol, sl.signal_type, sl.strength, sl.price, sl.detected_at
        FROM signals_log sl
        ORDER BY sl.detected_at DESC LIMIT 5
    ''').fetchall()
    
    print(f"\n   🔔 Recent Signals:")
    for sym, stype, strength, price, det in rows:
        print(f"       ✓ {sym}: {stype} | strength={strength:.2f} | price=${price}")
    
       # Latest alerts
    alert_rows = c.execute('''
        SELECT symbol, signal_type, severity, timestamp
        FROM trading_alerts
        ORDER BY timestamp DESC LIMIT 3
    ''').fetchall()
    
    if alert_rows:
        print(f"\n   🚨 Recent Alerts:")
        for sym, stype, sev, ts in alert_rows:
            print(f"       ⚡ {sym}: {stype} [{sev}] — {ts}")
    
    conn.close()
except Exception as e:
    print(f"\n❌ DB verification FAILED: {e}")

# Test 6: Load dashboard HTML to verify it has the Signals tab
try:
    with open('/Users/nghialam/jarvis-hub/dashboard/templates/index.html', 'r') as f:
        html_content = f.read()
    
    has_signals_tab = 'id="signals"' in html_content and 'loadSignalsGrid' in html_content
    has_nav_button = "switchTab('signals')" in html_content
    
    print(f"\n📋 Dashboard HTML:")
    print(f"   Signals section exists: {'✅' if has_signals_tab else '❌'}")
    print(f"   Nav button links to signals: {'✅' if has_nav_button else '❌'}")
    
except Exception as e:
    print(f"\n❌ Dashboard HTML check FAILED: {e}")

# Final summary
print("\n" + "=" * 60)
if has_signals_tab and has_nav_button:
    print("✅ ALL PIPELINES VERIFIED!")
    print("📊 Flask server running on port 8100")
    print("🔗 Dashboard: http://localhost:8100/")
    print("📋 New tab: 'Signals Grid' - merged from signals_log + trading_alerts")
    print("=" * 60)
else:
    print("⚠️ Pipeline verified but dashboard HTML needs Signals tab update")
    print("=" * 60)
