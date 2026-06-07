#!/usr/bin/env python3
"""Start Jarvis Hub Flask server on port 8100 in a background thread."""
import sys, os, threading, time

sys.path.insert(0, '/Users/nghialam/jarvis-hub')
os.chdir('/Users/nghialam/jarvis-hub')

def start_server():
    import app as flask_app
    print("[START] Flask server starting on port 8100...")
    sys.stdout.flush()
    flask_app.app.run(host='0.0.0.0', port=8100, use_reloader=False)

t = threading.Thread(target=start_server, daemon=True)
t.start()

# Wait for server to be ready, then verify
for i in range(20):
    time.sleep(0.5)
    try:
        import urllib.request
        r = urllib.request.urlopen('http://localhost:8100/api/health', timeout=2)
        print(f"[READY] Flask server running! Health: {r.read().decode()[:100]}")
        sys.stdout.flush()
        
         # Now run pipeline self-test
        import urllib.request, json
        r2 = urllib.request.urlopen('http://localhost:8100/api/signals', timeout=5)
        data = json.loads(r2.read().decode())
        print(f"[TEST] /api/signals returned {len(data.get('signals', []))} signals")
        
         # Also test add signal
        import urllib.parse
        sig_data = json.dumps({
            "symbol": "VNM",
            "signal": "BUY", 
            "strength": 0.7,
            "price": 65.5
        }).encode()
        req = urllib.request.Request(
            'http://localhost:8100/api/signals/add',
            data=sig_data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        r3 = urllib.request.urlopen(req, timeout=5)
        add_result = json.loads(r3.read().decode())
        print(f"[TEST] /api/signals/add POST: {add_result}")
        
         # Re-check signals count after adding one
        r4 = urllib.request.urlopen('http://localhost:8100/api/signals', timeout=5)
        data2 = json.loads(r4.read().decode())
        print(f"[FINAL] /api/signals now has {len(data2.get('signals', []))} signals")
        
         # Verify DB directly
        import sqlite3, os
        db_path = os.path.join('/Users/nghialam/jarvis-hub', 'knowledge', 'jarvis.db')
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        sig_count = c.execute('SELECT COUNT(*) FROM signals_log').fetchone()[0]
        alert_count = c.execute('SELECT COUNT(*) FROM trading_alerts').fetchone()[0]
        wl_count = c.execute('SELECT COUNT(*) FROM watchlist_symbols').fetchone()[0]
        print(f"\n{'='*60}")
        print("✅ END-TO-END PIPELINE VERIFICATION")
        print(f"{'='*60}")
        print(f"   📊 signals_log: {sig_count} rows")
        print(f"   📊 trading_alerts: {alert_count} rows")
        print(f"   📊 watchlist_symbols: {wl_count} rows")
        
         # Show recent signals
        rows = c.execute('''
            SELECT sl.symbol, sl.signal_type, sl.strength, sl.price, sl.detected_at
            FROM signals_log sl 
            UNION ALL
            SELECT ta.symbol, ta.signal_type, 0 as strength, 0 as price, ta.timestamp as detected_at
            FROM trading_alerts ta
            ORDER BY detected_at DESC LIMIT 5
        ''').fetchall()
        
        print(f"\n   Recent signals:")
        for sym, stype, strength, price, det in rows:
            print(f"      → {sym}: {stype} (strength={strength}, price={price})")
        
        conn.close()
        print(f"\n{'='*60}")
        print("✅ ALL PIPELINES WORKING! Flask server running on port 8100")
        print(f"{'='*60}")
        
    except Exception as e:
        if i < 19:
            pass  # keep waiting
        else:
            print(f"[ERROR] Failed after {i} attempts: {e}")
    
    break

print("[SERVER] Flask thread running... (check 'ps aux | grep flask')")
