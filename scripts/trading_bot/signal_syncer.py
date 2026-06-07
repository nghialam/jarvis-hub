#!/usr/bin/env python3
"""
signal_syncer.py — Jarvis Hub Signal Sync Engine

Syncs trading signals from internal web API (/api/signals) into local SQLite database.
Also triggers auto-scan of watchlist symbols when DB is empty or stale.

Usage:
    python3 signal_syncer.py sync          # Sync from API to DB (primary use)
    python3 signal_syncer.py scan          # Run full auto-scan + persist to DB
    python3 signal_syncer.py status        # Show current DB state
"""

import json
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# --- Config ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JARVIS_HUB = os.path.dirname(os.path.dirname(BASE_DIR))
DB_PATH = os.path.join(JARVIS_HUB, "knowledge", "jarvis.db")
FLASK_API_BASE = "http://localhost:8100"  # Flask app default port

# Watchlist symbols to scan
WATCHLIST_SYMBOls = [
    "VCB", "VPB", "HDB", "MBB", "ACB", "TPB", "SBV", "CTG",
    "PVN", "GAS", "POW", "HCM", "FPT", "VIC", "HPG", "MSN",
    "MCC", "STB", "BRE", "TCH", "VNM", "MWG", "TCB", "SHB",
    "EIB", "TPC", "MSN", "NVL", "PDR"
]


def get_conn():
    """Get database connection."""
    if not os.path.exists(DB_PATH):
        print(f"[SYNC] ERROR: DB not found at {DB_PATH}")
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(conn):
    """Ensure signals_log and trading_alerts tables exist with proper schema."""
    cursor = conn.cursor()
    
    # signals_log table - stores signals from scanning bot
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals_log (
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
         )
     """)
    
    # trading_alerts table - stores alerts from auto-scan pipeline
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            source TEXT DEFAULT 'AUTO_SYNC',
            signal_type TEXT NOT NULL,
            severity TEXT DEFAULT 'MEDIUM',
            alert_data TEXT,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            delivery_channel TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    # Create index for faster symbol lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_symbol 
        ON signals_log(symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerts_symbol 
        ON trading_alerts(symbol)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signals_detected 
        ON signals_log(detected_at DESC)
    """)
    
    conn.commit()


def sync_from_api(conn):
    """Fetch signals from Flask API endpoint and persist to DB."""
    url = f"{FLASK_API_BASE}/api/signals"
    
    try:
        req = Request(url)
        req.add_header("Accept", "application/json")
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        print(f"[SYNC] API fetch failed: {e}")
        print(f"[SYNC] Ensure Flask app is running on port 8100")
        return {"api_signals": 0, "db_inserted": 0}
    except Exception as e:
        print(f"[SYNC] Unexpected error: {e}")
        return {"api_signals": 0, "db_inserted": 0}
    
    signals = data.get("signals", [])
    if not signals:
        print("[SYNC] No signals returned from API")
        return {"api_signals": 0, "db_inserted": 0}
    
    print(f"[SYNC] Received {len(signals)} signals from API")
    
    inserted = 0
    updated = 0
    cursor = conn.cursor()
    
    for sig in signals:
        symbol = (sig.get("symbol") or "").upper().strip()
        signal_type = (sig.get("signal_type") or "NEUTRAL").upper()
        strength = float(sig.get("strength", 0) or 0)
        price = float(sig.get("price", 0) or 0) if sig.get("price") else None
        details = sig.get("details_parsed") or sig.get("details") or {}
        timestamp = sig.get("timestamp") or sig.get("detected_at") or datetime.now().isoformat()
        source = sig.get("source", "AUTO_SYNC")
        delivered = 1 if (sig.get("is_delivered")) else 0
        
        # Avoid duplicate: skip if same symbol + signal_type exists within last 2 hours
        try:
            existing = cursor.execute(
                """SELECT id FROM signals_log 
                  WHERE symbol = ? AND signal_type = ? 
                  AND detected_at > datetime('now', '-2 hours')
                  LIMIT 1""",
                (symbol, signal_type)
            ).fetchone()
            
            if existing:
                # Update existing record with latest data
                cursor.execute(
                    """UPDATE signals_log 
                      SET strength = ?, price = ?, details = ?, detected_at = ?, delivered = ?
                      WHERE id = ?""",
                    (strength, price, json.dumps(details), timestamp, delivered, existing["id"])
                )
                updated += 1
            else:
                # Insert new signal
                cursor.execute(
                    """INSERT INTO signals_log 
                       (symbol, asset_type, signal_type, strength, price, details, detected_at, delivered)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol, "stock", signal_type, strength, price, json.dumps(details), timestamp, delivered)
                )
                inserted += 1
                
        except Exception as e:
            print(f"[SYNC] Error inserting {symbol}: {e}")
            continue
    
    conn.commit()
    
    # Also persist to trading_alerts for cross-reference (non-duplicate entries only)
    for sig in signals:
        symbol = (sig.get("symbol") or "").upper().strip()
        signal_type = (sig.get("signal_type") or "NEUTRAL").upper()
        severity = (sig.get("severity") or "MEDIUM").upper()
        det = sig.get("details_parsed") or sig.get("details") or {}
        
        if isinstance(det, dict):
            alert_json = json.dumps(det)
        else:
            alert_json = json.dumps({"raw": str(det)}) if det else "{}"
        
        timestamp = sig.get("timestamp") or sig.get("detected_at") or datetime.now().isoformat()
        delivered_count = 1 if (sig.get("is_delivered")) else 0
        
        try:
            # Only insert non-neutral into trading_alerts
            if signal_type not in ("NEUTRAL", "HOLD"):
                # Check duplicate within last 6 hours
                existing = cursor.execute(
                    """SELECT id FROM trading_alerts 
                       WHERE symbol = ? AND signal_type = ?
                       AND timestamp > datetime('now', '-6 hours')
                       LIMIT 1""",
                    (symbol, signal_type)
                ).fetchone()
                
                if not existing:
                    cursor.execute(
                        """INSERT INTO trading_alerts 
                           (symbol, source, signal_type, severity, alert_data, timestamp, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (symbol, "AUTO_SYNC", signal_type, severity, alert_json, timestamp, "pending")
                    )
        except Exception as e:
            pass
    
    conn.commit()
    
    return {"api_signals": len(signals), "db_inserted": inserted, "db_updated": updated}


def run_auto_scan(conn):
    """Run full auto-scan of watchlist symbols and persist signals to DB."""
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    
    # Check if watchlist is populated
    try:
        count = conn.cursor().execute("SELECT COUNT(*) as cnt FROM watchlist_symbols").fetchone()["cnt"]
        if count == 0:
            print("[SCAN] Watchlist empty! Use API or CLI to add symbols first.")
            return {"scanned": 0, "alerts": 0}
    except Exception:
        pass
    
    # Determine symbols: from watchlist_symbols table if available, else fallback
    try:
        symbols = [row[0] for row in conn.cursor().execute(
            "SELECT symbol FROM watchlist_symbols LIMIT 100"
        ).fetchall()]
    except Exception:
        symbols = []
    
    if not symbols:
        symbols = WATCHLIST_SYMBOls[:10]  # fallback to hardcoded list
    
    print(f"[SCAN] Scanning {len(symbols)} symbols from watchlist...")
    
    scanned = 0
    alerts_created = 0
    
    for symbol in symbols:
        symbol = symbol.upper().strip()
        if not symbol or len(symbol) < 2:
            continue
        
        # Call /api/analyze to get technical analysis
        try:
            url = f"{FLASK_API_BASE}/api/analyze?symbol={symbol}"
            req = Request(url)
            resp = urlopen(req, timeout=15)
            data = json.loads(resp.read().decode("utf-8"))
            
            if "error" in data:
                continue
                
            scanned += 1
            
            price = float(data.get("price", 0) or 0)
            change_pct = float(data.get("change_pct", 0) or 0)
            technical = data.get("technical", {}) or {}
            
            # Extract key indicators
            rsi = (technical.get("rsi_14") or technical.get("RSI_14") or 
                   technical.get("RSI") or 50)
            sma20 = technical.get("sma_20") or technical.get("SMA_20")
            macd_hist = technical.get("macd_histogram") or 0
            
            # Generate signal based on analysis
            rsi_num = float(rsi) if rsi else 50
            
            signal_type = "NEUTRAL"
            strength = 0.3
            reasons = []
            
            if rsi_num <= 30:
                signal_type = "BUY"
                strength = 0.6
                reasons.append(f"RSI oversold ({rsi_num:.1f})")
            elif rsi_num >= 70:
                signal_type = "SELL"
                strength = 0.6
                reasons.append(f"RSI overbought ({rsi_num:.1f})")
            
            if sma20 and price and price < sma20 * 0.95:
                reasons.append(f"Price below SMA20 ({sma20:.2f})")
                if signal_type == "NEUTRAL":
                    signal_type = "SELL"
                    strength = 0.5
            
            macd_val = float(macd_hist) if macd_hist else 0
            if macd_val < -0.5:
                reasons.append("MACD momentum bearish")
                if signal_type == "NEUTRAL":
                    signal_type = "SELL"
                    strength = 0.4
            elif macd_val > 0.5:
                reasons.append("MACD momentum bullish")
                if signal_type == "NEUTRAL":
                    signal_type = "BUY"
                    strength = 0.4
            
            if len(reasons) >= 3 and signal_type in ("BUY", "SELL"):
                signal_type = f"STRONG_{signal_type}"
                strength = 0.85
            
            # Persist to signals_log
            try:
                existing = conn.cursor().execute(
                    """SELECT id FROM signals_log 
                       WHERE symbol=? AND signal_type=? 
                       AND detected_at > datetime('now', '-4 hours')
                       LIMIT 1""",
                    (symbol, signal_type)
                ).fetchone()
                
                reason_str = "; ".join(reasons) if reasons else "No strong signal"
                details = {"price": price, "change_pct": change_pct, 
                          "rsi_14": rsi_num, "sma_20": sma20,
                          "macd_histogram": macd_val, "signal_reason": reason_str}
                
                if not existing:
                    conn.cursor().execute(
                         """INSERT INTO signals_log 
                           (symbol, asset_type, signal_type, strength, price, details, detected_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (symbol, "stock", signal_type, strength, price,
                         json.dumps(details), datetime.now().isoformat())
                     )
                    
                    # Non-neutral signals also go to trading_alerts  
                    if signal_type not in ("NEUTRAL", "HOLD"):
                        severity = "LOW"
                        if strength >= 0.7:
                            severity = "HIGH"
                        elif strength >= 0.5:
                            severity = "MEDIUM"
                        
                        conn.cursor().execute(
                             """INSERT INTO trading_alerts 
                                (symbol, signal_type, severity, alert_data, timestamp, status)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                             (symbol, signal_type, severity,
                             json.dumps(details), datetime.now().isoformat(), "pending")
                         )
                        alerts_created += 1
                        
            except Exception as e:
                print(f"[SCAN] Error persisting {symbol}: {e}")
        
        except (URLError, HTTPError) as e:
            print(f"[SCAN] Failed to analyze {symbol}: {e}")
            # Could be Flask app not running - note it but continue with other symbols
            if "Connection refused" in str(e):
                print("[SCAN] WARNING: Flask app may not be running on port 8100")
                break
        except Exception as e:
            print(f"[SCAN] Unexpected error for {symbol}: {e}")
    
    conn.commit()
    
    return {"scanned": scanned, "alerts_created": alerts_created}


def show_status(conn):
    """Display current DB state."""
    cursor = conn.cursor()
    
    tables = ["signals_log", "trading_alerts", "watchlist_symbols"]
    print("\n=== JARVIS HUB — Signal Sync Status ===\n")
    
    for table in tables:
        try:
            # Get table info
            cols = [d[1] for d in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            
            print(f"📊 {table}: {count} rows")
            if count > 0 and table != "watchlist_symbols":
                # Show latest 3 entries
                col1 = cols[1] if len(cols) > 1 else "symbol"
                col2 = cols[3] if len(cols) > 3 else "signal_type"
                col3 = cols[5] if len(cols) > 5 else "detected_at"
                
                rows = cursor.execute(
                    f"SELECT {col1}, {col2}, {col3} FROM {table} ORDER BY {col3} DESC LIMIT 3"
                ).fetchall()
                
                for row in rows:
                    symbol, stype, ts = row[0], row[1], row[2]
                    print(f"   → {symbol}: {stype} ({ts})")
            elif table == "watchlist_symbols":
                wl_count = count
                unique_syms = cursor.execute("SELECT COUNT(DISTINCT symbol) FROM watchlist_symbols").fetchone()[0]
                print(f"   ({unique_syms} unique symbols)")
            
            print()
        except Exception as e:
            print(f"  {table}: ERROR — {e}")
    
    print("=" * 45)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sync"
    
    conn = get_conn()
    if not conn:
        sys.exit(1)
    
    ensure_tables(conn)
    
    if cmd == "sync":
        result = sync_from_api(conn)
        print(f"[SYNC] Complete: {result}")
        
    elif cmd == "scan":
        result = run_auto_scan(conn)
        print(f"[SCAN] Complete: {result}")
        
    elif cmd == "status":
        show_status(conn)
        
    else:
        print(f"Usage: python3 signal_syncer.py [sync|scan|status]")
        sys.exit(1)
    
    conn.close()


if __name__ == "__main__":
    main()
