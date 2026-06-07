#!/usr/bin/env python3
"""
Restore app.py signals section from scratch.
Reads current corrupted app.py, extracts everything BEFORE and AFTER the signals block,
then inserts a clean signals section in between with proper Python indentation.
"""

import py_compile
import sys

def read_app():
    with open("/Users/nghialam/jarvis-hub/app.py", "r") as f:
        return f.readlines()

def write_app(lines):
    with open("/Users/nghialam/jarvis-hub/app.py", "w") as f:
        f.writelines(lines)

def get_leading_spaces(line):
    """Count leading spaces in a line of Python code."""
    stripped = line.lstrip()
    return len(line) - len(stripped) if stripped else 0

# Read current (corrupted) app.py
lines = read_app()

# Find boundaries
signals_start_idx = None
alert_feed_start_idx = None
clear_alert_start_idx = None

for i, line in enumerate(lines):
    if "# Unified Signals Feed" in line and signals_start_idx is None:
        signals_start_idx = i
    elif "# Trading Alert Feed" in line and alert_feed_start_idx is None:
        alert_feed_start_idx = i
    elif '"/api/alert-feed/clear"' in line and clear_alert_start_idx is None:
        clear_alert_start_idx = i

if signals_start_idx is None:
    print("ERROR: Could not find signals section")
    sys.exit(1)

if clear_alert_start_idx is None:
    # If clear_alert not found, use alert_feed start - some lines
    clear_alert_start_idx = alert_feed_start_idx + 40 if alert_feed_start_idx else len(lines)

print(f"Signals section: lines {signals_start_idx+1} to {clear_alert_start_idx}")

# Build the clean signals section as Python list of line strings
NEW_SIGNALS_SECTION = []
a = NEW_SIGNALS_SECTION.append

# Header comment
a("# ====================================================================")
a("# Unified Signals Feed - NEW FEATURE (v2.0)")
a("# Merges signals_log and trading_alerts into a single API")
a("# ====================================================================")
a("")
a('')   # blank before decorator

def decorate(func_name):
    """Decorate function to be added."""
    return func_name

# --- api_get_signals (lines 1-240 approx) ---
a("@app.route(\"/api/signals\", methods=[\"GET\"])")
a("def api_get_signals():")
a('    """Get unified signal feed from both signals_log and trading_alerts tables, merged and deduplicated."""')
a("    if not db:")
a('        return jsonify({"signals": [], "error": "DB not initialized"})')
a("")
a("    try:")
a("         # Optional filters")
a('        signal_filter = request.args.get("signal", "").upper()     # BUY / SELL / HOLD')
a('        severity_filter = request.args.get("severity", "").upper()')
a('        symbol_filter = request.args.get("symbol", "").upper()')
a('        only_unread = request.args.get("unread", "false").lower() == "true"')
a("")
a("         # Fetch signals from BOTH tables")
a("        all_signals = []")
a('        source_counts = {"signals_log": 0, "trading_alerts": 0}')
a("")
a("        try:")
a("             # Table 1: signals_log (from trading bot)")
a('            rows = db._c().execute("""')
a("                SELECT id, symbol, 'TRADING_BOT' as source, signal_type,")
a("                       CAST(strength AS TEXT) as severity, price, details,")
a("                       detected_at as timestamp, delivered as is_delivered, delivery_channel")
a("                FROM signals_log")
a("                WHERE 1=1")
a('            """).fetchall()')
a("            for row in rows:")
a("                r = dict(row)")
a("                 # Apply filters")
a('                if signal_filter and r["signal_type"] != signal_filter:')
a("                    continue")
a('                if symbol_filter and r["symbol"] != symbol_filter:')
a("                    continue")
a("                all_signals.append(r)")
a('                source_counts["signals_log"] += 1')
a("        except Exception as e:")
a('            print("[SIGNALS] signals_log fetch error (table may not exist yet): %s" % e)')
a("")
a("        try:")
a("             # Table 2: trading_alerts from auto-scan engine")
a('            rows = db._c().execute("""')
a("                SELECT id, symbol, 'AUTO_SCAN' as source, signal_type,")
a("                       severity AS severity,")
a("                       CAST(alert_data->>'price' AS REAL) as price,")
a("                       alert_data,")
a("                       timestamp as detected_at,")
a("                       CASE WHEN status='read' THEN 1 ELSE 0 END as is_delivered,")
a("                       delivery_channel")
a("                FROM trading_alerts")
a('            """).fetchall()')
a("            for row in rows:")
a("                r = dict(row)")
a("                 # Parse JSON alert_data if string")
a('                raw = r.get("alert_data")')
a("                if isinstance(raw, str):")
a("                    try:")
a("                        import json as _json")
a('                        r["alert_parsed"] = _json.loads(raw)')
a("                    except Exception:")
a('                        r["alert_parsed"] = None')
a("                else:")
a('                    r["alert_parsed"] = raw')
a("")
a('                del r["alert_data"]     # Clean up raw JSON field')
a("")
a("                 # Apply filters")
a('                if signal_filter and r["signal_type"] != signal_filter:')
a("                    continue")
a('                if symbol_filter and r["symbol"] != symbol_filter:')
a("                    continue")
a('                if only_unread and r.get("is_delivered"):')
a("                    continue")
a("")
a("                all_signals.append(r)")
a('                source_counts["trading_alerts"] += 1')
a("        except Exception as e:")
a('            print("[SIGNALS] trading_alerts fetch error: %s" % e)')
a("")
a("         # Sort by timestamp descending (newest first)")
a('        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)')
a("")
a("         # Deduplication: keep latest signal per symbol")
a("        best_by_symbol = {}")
a("        neutral_kept = []")
a("        for sig in all_signals:")
a('            sym = sig["symbol"]')
a('            stype = sig.get("signal_type", "NEUTRAL")')
a("")
a("             # Neutral/HOLD signals: keep latest per symbol")
a('            if stype in ("NEUTRAL", "HOLD"):')
a('                if sym not in [s["symbol"] for s in neutral_kept]:')
a("                    neutral_kept.append(sig)")
a("                continue")
a("")
a("             # Buy/Sell signals: keep only most recent per symbol/type")
a("            key = (sym, stype)")
a('            if key not in best_by_symbol or sig.get("timestamp", "") > best_by_symbol[key].get("timestamp", ""):')
a("                if key in best_by_symbol:")
a("                    old = best_by_symbol[sym]")
a('                    if old not in neutral_kept and old["symbol"] not in [s["symbol"] for s in neutral_kept]:')
a("                        neutral_kept.append(old)")
a("                best_by_symbol[key] = sig")
a("")
a("         # Remove duplicates from neutral list by symbol")
a("        seen_symbols_neutral = set()")
a("        deduped_neutral = []")
a("        for s in neutral_kept:")
a('            if s["symbol"] not in seen_symbols_neutral:')
a('                seen_symbols_neutral.add(s["symbol"])')
a("                deduped_neutral.append(s)")
a("")
a("         # Combine: strong signals first, then neutrals/holds at end")
a("        final_signals = list(best_by_symbol.values()) + deduped_neutral")
a("")
a("        return jsonify({")
a('             "signals": final_signals,')
a('             "counts": {')
a('                 "total": len(final_signals),')
a('                 "by_source": source_counts,')
a("             },")
a("         })")
a("    except Exception as e:")
a('        print("[SIGNALS] Error: %s" % str(e))')
a('        return jsonify({"signals": [], "error": str(e)}, 500)')
a("")
a("")

# --- api_latest_signals (lines ~241-340 approx)---
a('@app.route("/api/signals/latest", methods=["GET"])')
a("def api_latest_signals():")
a('    """Get the N most recent signals for grid overview."""')
a('    limit = min(int(request.args.get("limit", "20")), 100)')
a("    if not db:")
a('        return jsonify({"signals": []})')
a("")
a("    try:")
a("        all_signals = []")
a("")
a("         # From signals_log")
a("        try:")
a('            rows = db._c().execute("""')
a("                SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,")
a("                       price, details, detected_at, delivered as is_delivered, delivery_channel")
a("                FROM signals_log ORDER BY detected_at DESC LIMIT 50")
a('            """).fetchall()')
a("            for row in rows:")
a("                r = dict(row)")
a('                if isinstance(r.get("details"), str):')
a("                    try:")
a("                        import json as _json")
a('                        r["details_parsed"] = _json.loads(r["details"])')
a("                    except Exception:")
a("                        pass")
a("                all_signals.append(r)")
a("        except Exception:")
a("            pass")
a("")
a("         # From trading_alerts")
a("        try:")
a('            rows = db._c().execute("""')
a("                SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,")
a("                       CAST(alert_data->>'price' AS REAL) as price,")
a("                       alert_data as details,")
a("                       timestamp as detected_at,")
a("                       CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,")
a("                       delivery_channel")
a("                FROM trading_alerts ORDER BY timestamp DESC LIMIT 50")
a('            """).fetchall()')
a("            for row in rows:")
a("                r = dict(row)")
a('                raw = r.get("details")')
a("                if isinstance(raw, str):")
a("                    try:")
a("                        import json as _json")
a('                        r["details_parsed"] = _json.loads(raw)')
a("                    except Exception:")
a('                        r["details_parsed"] = None')
a("                else:")
a('                    r["details_parsed"] = raw')
a('                del r["details"]    # Clean up raw JSON field')
a("                all_signals.append(r)")
a("        except Exception:")
a("            pass")
a("")
a("         # Sort and limit")
a('        all_signals.sort(key=lambda x: x.get("detected_at", ""), reverse=True)')
a('        return jsonify({"signals": all_signals[:limit]})')
a("    except Exception as e:")
a('        return jsonify({"signals": [], "error": str(e)})')
a("")
a("")

# --- api_signal_for_symbol (lines ~341-420 approx)---
a('@app.route("/api/signals/symbol/<symbol>", methods=["GET"])')
a("def api_signal_for_symbol(symbol):")
a('    """Get all signals for a specific symbol full history."""')
a("    if not db:")
a('        return jsonify({"symbol": symbol, "signals": []})')
a("")
a("    symbol = str(symbol).upper().strip()")
a("    signals = []")
a("")
a("     # From signals_log")
a("    try:")
a('        rows = db._c().execute"""')
            a("            SELECT symbol, 'TRADING_BOT' , signal_type, CAST(strength AS REAL) as strength,")
a("                   price, details, detected_at, delivered as is_delivered, delivery_channel")
a("            FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC")
a('        """, (symbol,)).fetchall()')
a("        for row in rows:")
a("            r = dict(row)")
a('            if isinstance(r.get("details"), str):')
a("                try:")
a("                    import json as _json")
a('                    r["details_parsed"] = _json.loads(r["details"])')
a("                except Exception:")
a("                    pass")
a("            signals.append(r)")
a("    except Exception as e:")
a('        print("[SIGNALS] signals_log lookup %s error: %s" % (symbol, e))')
a("")
a("     # From trading_alerts ")
a("    try:")
a('        rows = db._c().execute("""')
a("            SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,")
a("                   CAST(alert_data->>'price' AS REAL) as price,")
a("                   alert_data as details,")
a("                   timestamp as detected_at,")
a("                   CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,")
a("                   delivery_channel")
a("            FROM trading_alerts WHERE UPPER(symbol)=UPPER(?) ORDER BY timestamp DESC")
a('        """, (symbol,)).fetchall()')
a("        for row in rows:")
a("            r = dict(row)")
a('            raw = r.get("details")')
a("            if isinstance(raw, str):")
a("                try:")
a("                    import json as _json")
a('                    r["details_parsed"] = _json.loads(raw)')
a("                except Exception:")
a("                    pass")
a("            signals.append(r)")
a("    except Exception as e:")
a('        print("[SIGNALS] trading_alerts lookup %s error: %s" % (symbol, e))')
a("")
a('    signals.sort(key=lambda x: x.get("detected_at", "") or x.get("timestamp", ""), reverse=True)')
a('    return jsonify({"symbol": symbol, "signals": signals})')
a("")
a("")

# --- api_signal_append (lines ~421-480 approx)---
a('@app.route("/api/signals/add", methods=["POST"])')
a("def api_signal_append():")
a('    """Manual signal entry via dashboard or API."""')
a("    if not db:")
a('        return jsonify({"success": False, "error": "DB not initialized"}), 500')
a("")
a('    data = request.get_json() or {}')
a('    symbol = str(data.get("symbol", "")).strip().upper()')
a('    signal_type = str(data.get("signal", "")).upper()     # BUY / SELL / HOLD')
a('    strength = float(data.get("strength", 0))     # 0-100')
a("")
a("    if not symbol or len(symbol) < 2:")
a('        return jsonify({"success": False, "error": "Invalid symbol"}), 400')
a('    if signal_type and signal_type not in ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL"):')
a('        return jsonify({"success": False, "error": "Invalid signal type"}), 400')
a("")
a('    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}')
a("")
a("     # Persist to signals_log table")
a("    try:")
a("        import json as _json")
a('        db._c().execute("""')
a('            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)')
a('             VALUES (?, ?, ?, ?, ?, ?)')
a('        """, (symbol, signal_type if signal_type else "NEUTRAL", strength,')
a('             data.get("price"), _json.dumps(details), _utc_now_iso()))')
a("        db._conn.commit()")
a('        print("[SIGNALS] Manual signal added for %s: %s (%.1f)" % (symbol, signal_type, strength))')
a('        return jsonify({"success": True})')
a("    except sqlite3.Error as e:")
a('        if "no such table" in str(e):')
a('            return jsonify({"success": False, "error": "signals_log table not found - run DB migration"}), 500')
a('        print("[SIGNALS] Insert error: %s" % e)')
a('        return jsonify({"success": False, "error": str(e)}), 500')
a("")
a("")

# --- api_signal_mark_delivered (lines ~481-500 approx)---
a('@app.route("/api/signals/mark-delivered", methods=["POST"])')
a("def api_signal_mark_delivered():")
a('    """Mark signal as delivered for cron delivery."""')
a("    if not db:")
a('        return jsonify({"success": True})     # Silently OK if no DB')
a("")
a("    try:")
a('        rowcount = db._c().execute("""')
a('            UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0')
a('        """, (request.json.get("id"),)).rowcount if request.json else 0')
a("        db._conn.commit()")
a('        return jsonify({"success": True, "marked": rowcount})')
a("    except Exception as e:")
a('        print("[SIGNALS] Mark delivered error: %s" % e)')
a('        return jsonify({"success": False, "error": str(e)})')


# Count lines in new section
print(f"Built {len(NEW_SIGNALS_SECTION)} lines for signals section")

# Now build the complete file
before_section = lines[:signals_start_idx]  
after_section = []

# Find where to cut - look for "@app.route("/api/alert-feed/clear""
for i in range(clear_alert_start_idx, len(lines)):
    if '/api/alert-feed/clear' in lines[i]:
        # Keep this function and everything after
        after_section = lines[i:]
        print(f"Cut here: keeping alert-clear section from line {i+1}")
        break

if not after_section:
    print("WARNING: Could not find end marker, appending empty")

# Assemble final file
new_lines = before_section + NEW_SIGNALS_SECTION + ["\n"] * 2 + after_section

# Verify indentation of key lines before writing
print("\nKey line indentation check:")
for i, line in enumerate(NEW_SIGNALS_SECTION[:30]):
    stripped = line.lstrip()
    spaces = len(line) - len(stripped) if stripped else 0
    if stripped:
        print(f"  L{i+1} ({spaces:>2} sp): {stripped[:60]}")

# Write the new file 
with open("/Users/nghialam/jarvis-hub/app.py", "w") as f:
    f.writelines(new_lines)

print(f"\nWritten {len(new_lines)} lines (was {len(lines)})")

# Verify syntax
try:
    py_compile.compile("/Users/nghialam/jarvis-hub/app.py", doraise=True)
    print("\nOK! Syntax check PASSED!\n")
except SyntaxError as e:
    print(f"\nSYNTAX ERROR at line {e.lineno}: {e.msg}")
    ctx = new_lines
    for i in range(max(0, e.lineno-5), min(len(ctx), e.lineno+6)):
        marker = "***" if i+1 == e.lineno else "   "
        print(f"{marker} L{i+1}: {ctx[i][:80]}")
    sys.exit(1)
