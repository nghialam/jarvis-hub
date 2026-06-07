#!/usr/bin/env python3
"""Fix app.py by removing excessive blank lines, then append clean signals/alert sections."""
import py_compile
import re

PATH = "/Users/nghialam/jarvis-hub/app.py"
BACKUP_PATH = PATH + ".bak.restore"

# Step 1: Read corrupted file
with open(PATH, "r") as f:
    lines = f.readlines()

print(f"Original: {len(lines)} lines")

# Step 2: Clean excessive blank lines (keep max 2 consecutive)
cleaned_lines = []
blank_count = 0
for line in lines:
    stripped = line.rstrip("\n\r")
    if not stripped.strip():
        blank_count += 1
        if blank_count <= 2:
            cleaned_lines.append(line)
    else:
        blank_count = 0
        cleaned_lines.append(line)

content = "".join(cleaned_lines)
print(f"Cleaned: {len(cleaned_lines)} lines")
print(f"Difference: Removed {len(lines) - len(cleaned_lines)} blank/existing lines")

# Step 3: Find main block location in cleaned content
lines_c = content.split("\n")
main_idx = None
for i, line in enumerate(lines_c):
    if 'if __name__' in line and '__main__' in line:
        main_idx = i
        break

print(f"Main block at line {main_idx + 1}")

if main_idx is None:
    print("ERROR: Could not find main block!")
    import sys; sys.exit(1)

# Step 4: Build the signals + alert feed section
signals_section = '''
# ====================================================================
# Unified Signals Feed - NEW FEATURE (v2.0)
# Merges signals_log and trading_alerts into a single API
# ====================================================================


@app.route("/api/signals", methods=["GET"])
def api_get_signals():
    """Get unified signal feed from both tables, merged and deduplicated."""
    if not db:
        return jsonify({"signals": [], "error": "DB not initialized"})

    try:
        # Optional filters
        signal_filter = request.args.get("signal", "").upper()
        severity_filter = request.args.get("severity", "").upper()
        symbol_filter = request.args.get("symbol", "").upper()
        only_unread = request.args.get("unread", "false").lower() == "true"

        # Fetch signals from BOTH tables
        all_signals = []
        source_counts = {"signals_log": 0, "trading_alerts": 0}

        # Table 1: signals_log (from trading bot)
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'TRADING_BOT' as source, signal_type,
                       CAST(strength AS TEXT) as severity, price, details,
                       detected_at as timestamp, delivered as is_delivered, delivery_channel
                FROM signals_log WHERE 1=1
            """).fetchall()
            for row in rows:
                r = dict(row)
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                all_signals.append(r)
                source_counts["signals_log"] += 1
        except Exception as e:
            print("[SIGNALS] signals_log error: %s" % e)

        # Table 2: trading_alerts (from auto-scan engine)
        try:
            rows = db._c().execute("""
                SELECT id, symbol, 'AUTO_SCAN' as source, signal_type,
                       severity AS severity,
                       CAST(alert_data->>'price' AS REAL) as price,
                       alert_data,
                       timestamp as detected_at,
                       CASE WHEN status='read' THEN 1 ELSE 0 END as is_delivered,
                       delivery_channel
                FROM trading_alerts
            """).fetchall()
            for row in rows:
                r = dict(row)
                raw = r.get("alert_data")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        r["alert_parsed"] = _json.loads(raw)
                    except Exception:
                        r["alert_parsed"] = None
                else:
                    r["alert_parsed"] = raw
                del r["alert_data"]

                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                if only_unread and r.get("is_delivered"):
                    continue

                all_signals.append(r)
                source_counts["trading_alerts"] += 1
        except Exception as e:
            print("[SIGNALS] trading_alerts error: %s" % e)

        # Sort by timestamp descending (newest first)
        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplication: keep latest signal per symbol
        best_by_symbol = {}
        neutral_kept = []
        for sig in all_signals:
            sym = sig["symbol"]
            stype = sig.get("signal_type", "NEUTRAL")

            if stype in ("NEUTRAL", "HOLD"):
                if sym not in [s["symbol"] for s in neutral_kept]:
                    neutral_kept.append(sig)
                continue

            key = (sym, stype)
            if key not in best_by_symbol or sig.get("timestamp", "") > best_by_symbol[key].get("timestamp", ""):
                if key in best_by_symbol:
                    old = best_by_symbol[sym]
                    if old not in neutral_kept and old["symbol"] not in [s["symbol"] for s in neutral_kept]:
                        neutral_kept.append(old)
                best_by_symbol[key] = sig

        seen_symbols_neutral = set()
        deduped_neutral = []
        for s in neutral_kept:
            if s["symbol"] not in seen_symbols_neutral:
                seen_symbols_neutral.add(s["symbol"])
                deduped_neutral.append(s)

        final_signals = list(best_by_symbol.values()) + deduped_neutral

        return jsonify({
            "signals": final_signals,
            "counts": {
                "total": len(final_signals),
                "by_source": source_counts,
            },
        })
    except Exception as e:
        print("[SIGNALS] Error: %s" % str(e))
        return jsonify({"signals": [], "error": str(e)}, 500)


@app.route("/api/signals/latest", methods=["GET"])
def api_latest_signals():
    """Get the N most recent signals for grid overview."""
    limit = min(int(request.args.get("limit", "20")), 100)
    if not db:
        return jsonify({"signals": []})

    try:
        all_signals = []

        # From signals_log
        try:
            rows = db._c().execute("""
                SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,
                       price, details, detected_at, delivered as is_delivered, delivery_channel
                FROM signals_log ORDER BY detected_at DESC LIMIT 50
            """).fetchall()
            for row in rows:
                r = dict(row)
                if isinstance(r.get("details"), str):
                    try:
                        import json as _json
                        r["details_parsed"] = _json.loads(r["details"])
                    except Exception:
                        pass
                all_signals.append(r)
        except Exception:
            pass

        # From trading_alerts
        try:
            rows = db._c().execute("""
                SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,
                       CAST(alert_data->>'price' AS REAL) as price,
                       alert_data as details,
                       timestamp as detected_at,
                       CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,
                       delivery_channel
                FROM trading_alerts ORDER BY timestamp DESC LIMIT 50
            """).fetchall()
            for row in rows:
                r = dict(row)
                raw = r.get("details")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        r["details_parsed"] = _json.loads(raw)
                    except Exception:
                        r["details_parsed"] = None
                else:
                    r["details_parsed"] = raw
                del r["details"]
                all_signals.append(r)
        except Exception:
            pass

        all_signals.sort(key=lambda x: x.get("detected_at", ""), reverse=True)
        return jsonify({"signals": all_signals[:limit]})
    except Exception as e:
        return jsonify({"signals": [], "error": str(e)})


@app.route("/api/signals/symbol/<symbol>", methods=["GET"])
def api_signal_for_symbol(symbol):
    """Get all signals for a specific symbol full history."""
    if not db:
        return jsonify({"symbol": symbol, "signals": []})

    sym = str(symbol).upper().strip()
    signals = []

    # From signals_log
    try:
        rows = db._c().execute("""
            SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,
                   price, details, detected_at, delivered as is_delivered, delivery_channel
            FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC
        """, (sym,)).fetchall()
        for row in rows:
            r = dict(row)
            if isinstance(r.get("details"), str):
                try:
                    import json as _json
                    r["details_parsed"] = _json.loads(r["details"])
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] signals_log lookup %s error: %s" % (sym, e))

    # From trading_alerts  
    try:
        rows = db._c().execute("""
            SELECT symbol, 'AUTO_SCAN', signal_type, severity as strength,
                   CAST(alert_data->>'price' AS REAL) as price,
                   alert_data as details,
                   timestamp as detected_at,
                   CASE WHEN status='read' THEN 1 ELSE 0 END AS is_delivered,
                   delivery_channel
            FROM trading_alerts WHERE UPPER(symbol)=UPPER(?) ORDER BY timestamp DESC
        """, (sym,)).fetchall()
        for row in rows:
            r = dict(row)
            raw = r.get("details")
            if isinstance(raw, str):
                try:
                    import json as _json
                    r["details_parsed"] = _json.loads(raw)
                except Exception:
                    pass
            signals.append(r)
    except Exception as e:
        print("[SIGNALS] trading_alerts lookup %s error: %s" % (sym, e))

    signals.sort(key=lambda x: (x.get("detected_at", "") or x.get("timestamp", "")), reverse=True)
    return jsonify({"symbol": sym, "signals": signals})


@app.route("/api/signals/add", methods=["POST"])
def api_signal_append():
    """Manual signal entry via dashboard or API."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}
    sym = str(data.get("symbol", "")).strip().upper()
    signal_type = str(data.get("signal", "")).upper()
    strength = float(data.get("strength", 0))

    if not sym or len(sym) < 2:
        return jsonify({"success": False, "error": "Invalid symbol"}), 400
    valid_types = ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL")
    if signal_type and signal_type not in valid_types:
        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    try:
        import json as _json
        db._c().execute("""
            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (sym, signal_type if signal_type else "NEUTRAL", strength,
              data.get("price"), _json.dumps(details), _utc_now_iso()))
        db._conn.commit()
        print("[SIGNALS] Added %s: %s (%.1f)" % (sym, signal_type, strength))
        return jsonify({"success": True})
    except sqlite3.Error as e:
        if "no such table" in str(e):
            return jsonify({"success": False, "error": "signals_log not found"}), 500
        print("[SIGNALS] Insert error: %s" % e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/mark-delivered", methods=["POST"])
def api_signal_mark_delivered():
    """Mark signal as delivered for cron delivery."""
    if not db:
        return jsonify({"success": True})

    try:
        rowcount = 0
        if request.json:
            rowcount = (db._c().execute(
                "UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0", 
                (request.json.get("id"),)).rowcount)
        db._conn.commit()
        return jsonify({"success": True, "marked": rowcount})
    except Exception as e:
        print("[SIGNALS] Mark delivered error: %s" % e)
        return jsonify({"success": False, "error": str(e)})


# ====================================================================
# Trading Alert Feed - NEW FEATURE
# ====================================================================


@app.route("/api/alert-feed", methods=["GET"])
def api_get_alert_feed():
    """Get trading alerts sorted by recency."""
    if not db:
        return jsonify({"alerts": [], "filters_applied": []})

    signal = request.args.get("signal", "").upper()
    severity = request.args.get("severity", "").upper()
    symbol_filter = request.args.get("symbol", "").upper()

    try:
        filters_applied = []
        conditions = ["1=1"]
        params = []

        if signal:
            conditions.append("signal_type = ?")
            params.append(signal)
            filters_applied.append("signal=" + signal)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)
            filters_applied.append("severity=" + severity)
        if symbol_filter:
            conditions.append("symbol = ?")
            params.append(symbol_filter)
            filters_applied.append("symbol=" + symbol_filter)

        where_clause = " AND ".join(conditions)
        rows = db._c().execute(
            "SELECT * FROM trading_alerts WHERE %s ORDER BY timestamp DESC LIMIT 100" % where_clause,
            params,
        ).fetchall()

        alerts = [dict(r) for r in rows]
        for a in alerts:
            raw = a.get("alert_data")
            if isinstance(raw, str):
                import json as _json
                try:
                    a["alert_data"] = _json.loads(raw)
                except Exception:
                    pass
        return jsonify({"alerts": alerts, "filters_applied": filters_applied})
    except Exception as e:
        print("[ALERT-FEED] Error: %s" % e)
        return jsonify({"alerts": [], "errors": [str(e)]})


@app.route("/api/alert-feed/auto-scan", methods=["GET"])
def api_auto_scan():
    """Trigger auto-scan of watchlist for trading signals."""
    if not db or not config:
        return jsonify({"scanned": 0, "new_alerts": 0, "error": "DB/Config not init"})

    try:
        watchlist = db.get_watchlist()
        if not watchlist:
            return jsonify({"scanned": 0, "new_alerts": 0, "message": "Watchlist empty"})

        results = {"scanned": 0, "new_alerts": 0}
        for item in watchlist:
            sym = item["symbol"]
            try:
                result = analyze_stock(sym)
                if result and "error" not in result and result.get("price"):
                    results["scanned"] += 1

                    tech = result.get("technical", {}) or {}
                    rsi_val = tech.get("rsi") or tech.get("RSI") or tech.get("RSI_14", 50)
                    sma20 = tech.get("sma_20")
                    macd_hist = tech.get("macd_histogram") if tech else None

                    llm_rec = ""
                    if result.get("llm_report"):
                        rec_match = re.search(
                            r'(?:KHUYEN NGH[YIA]|RECOMMENDATION|ACTION)[\\s]*([^\\n]+)',
                            result["llm_report"]
                        )
                        if rec_match:
                            llm_rec = rec_match.group(1).strip().upper()

                    signal_type = "NEUTRAL"
                    reason_parts = []

                    rsi_num = float(rsi_val) if rsi_val else 50
                    change_pct = float(result.get("change_pct", 0))

                    if rsi_num <= 30:
                        reason_parts.append("RSI oversold (%.1f)" % rsi_num)
                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type
                    elif rsi_num >= 70:
                        reason_parts.append("RSI overbought (%.1f)" % rsi_num)
                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    price_num = float(result.get("price", 0))
                    if sma20 and price_num:
                        if price_num < sma20 * 0.95:    # 5% below SMA
                            reason_parts.append("Price below SMA20 (%.2f)" % sma20)
                            signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type

                    if macd_hist is not None and float(macd_hist) < -0.5:
                        reason_parts.append("MACD momentum bearish")
                        signal_type = "SELL" if signal_type in ("NEUTRAL", "BUY") else signal_type
                    elif macd_hist is not None and float(macd_hist) > 0.5:
                        reason_parts.append("MACD momentum bullish")
                        signal_type = "BUY" if signal_type in ("NEUTRAL", "SELL") else signal_type

                    if change_pct <= -5:
                        reason_parts.append("Sharp drop (-%.1f%%)" % abs(change_pct))
                        signal_type = "SELL" if signal_type == "NEUTRAL" else signal_type
                    elif change_pct >= 5:
                        reason_parts.append("Strong rally (+%.1f%%)" % change_pct)
                        signal_type = "BUY" if signal_type == "NEUTRAL" else signal_type

                    if len(reason_parts) >= 3 and signal_type in ("BUY", "SELL"):
                        signal_type = "STRONG_" + signal_type
                    elif len(reason_parts) == 0:
                        signal_type = "NEUTRAL"

                    reason_str = "; ".join(reason_parts) if reason_parts else "No strong signal detected"

                    is_neutral = signal_type == "NEUTRAL"

                    existing = db._c().execute(
                        "SELECT id FROM trading_alerts WHERE symbol=? AND timestamp > datetime('now', '-6 hours') LIMIT 1",
                        (sym,),
                    ).fetchone()

                    if not existing and not is_neutral:
                        trigger_alert(sym, signal_type, {
                            "price": result.get("price"),
                            "change_pct": change_pct,
                            "rsi_14": rsi_val,
                            "sma_20": sma20,
                            "macd_histogram": macd_hist,
                            "signal_reason": reason_str,
                        })
                        results["new_alerts"] += 1

                    elif is_neutral and not existing:
                        recent = db._c().execute(
                            "SELECT id FROM trading_alerts WHERE symbol=? AND signal_type='NEUTRAL' AND timestamp > datetime('now', '-24 hours') LIMIT 1",
                            (sym,),
                        ).fetchone()
                        if not recent:
                            trigger_alert(sym, "NEUTRAL", {
                                "price": result.get("price"),
                                "change_pct": change_pct,
                                "rsi_14": rsi_val,
                                "sma_20": sma20,
                                "macd_histogram": macd_hist,
                                "signal_reason": reason_str,
                            })
                            results["new_alerts"] += 1

            except Exception as e:
                print("[AUTO-SCAN] Error scanning %s: %s" % (sym, e))

        return jsonify({
            "scanned": results["scanned"],
            "new_alerts": results["new_alerts"],
            "watchlist_count": len(watchlist),
        })
    except Exception as e:
        print("[AUTO-SCAN] Auto-scan failed: %s" % e)
        return jsonify({"scanned": 0, "new_alerts": 0, "error": str(e)})


@app.route("/api/alert-feed/clear", methods=["POST"])
def api_clear_alert_feed():
    """Mark all alerts as read."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"})
    try:
        db.mark_alerts_as_read()
        return jsonify({"success": True})

'''

# Step 5: Build final content
before_main = "\n".join(lines_c[:main_idx])
after_main = "\n".join(lines_c[main_idx:])

full_content = before_main + signals_section + "\n\n" + after_main

# Step 6: Write backup first (Golden Rule - backup before write)
with open(BACKUP_PATH, "w") as f:
    f.write(content)
print(f"Backup saved to {BACKUP_PATH}")

# Step 7: Write new file
with open(PATH, "w") as f:
    f.write(full_content)

print(f"\nWritten {len(full_content.split(chr(10)))} lines total")

# Step 8: Verify syntax
try:
    py_compile.compile(PATH, doraise=True)
    print("OK! Syntax check PASSED!")
    
    # List all route decorators
    import re
    routes = re.findall(r'@app.route\("([^"]+)"', full_content)
    print("\nRegistered routes:")
    for r in sorted(routes):
        print(f"  {r}")
        
except SyntaxError as e:
    print(f"\nSYNTAX ERROR at line {e.lineno}: {e.msg}")
    ctx = full_content.split("\n")
    start = max(0, e.lineno - 10)
    for i in range(start, min(len(ctx), e.lineno + 8)):
        marker = "***" if i+1 == e.lineno else "      "
        print("%s L%d: %s" % (marker, i+1, ctx[i][:90]))
