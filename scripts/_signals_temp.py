# ====================================================================
# Unified Signals Feed - NEW FEATURE (v2.0)
# Merges signals_log and trading_alerts into a single API
# ====================================================================


@app.route("/api/signals", methods=["GET"])
def api_get_signals():
    """Get unified signal feed from both signals_log and trading_alerts tables, merged and deduplicated."""
    if not db:
        return jsonify({"signals": [], "error": "DB not initialized"})

    try:
        # Optional filters
        signal_filter = request.args.get("signal", "").upper()    # BUY / SELL / HOLD
        severity_filter = request.args.get("severity", "").upper()
        symbol_filter = request.args.get("symbol", "").upper()
        only_unread = request.args.get("unread", "false").lower() == "true"

        # Fetch signals from BOTH tables
        all_signals = []
        source_counts = {"signals_log": 0, "trading_alerts": 0}

        try:
            # Table 1: signals_log (from trading bot)
            rows = db._c().execute("""
                SELECT id, symbol, 'TRADING_BOT' as source, signal_type,
                       CAST(strength AS TEXT) as severity, price, details,
                       detected_at as timestamp, delivered as is_delivered, delivery_channel
                FROM signals_log
                WHERE 1=1
            """).fetchall()
            for row in rows:
                r = dict(row)
                # Apply filters
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                all_signals.append(r)
                source_counts["signals_log"] += 1
        except Exception as e:
            print("[SIGNALS] signals_log fetch error (table may not exist yet): %s" % e)

        try:
            # Table 2: trading_alerts (from auto-scan engine)
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
                # Parse JSON alert_data if string
                raw = r.get("alert_data")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        r["alert_parsed"] = _json.loads(raw)
                    except Exception:
                        r["alert_parsed"] = None
                else:
                    r["alert_parsed"] = raw

                del r["alert_data"]    # Clean up raw JSON field

                # Apply filters
                if signal_filter and r["signal_type"] != signal_filter:
                    continue
                if symbol_filter and r["symbol"] != symbol_filter:
                    continue
                if only_unread and r.get("is_delivered"):
                    continue

                all_signals.append(r)
                source_counts["trading_alerts"] += 1
        except Exception as e:
            print("[SIGNALS] trading_alerts fetch error: %s" % e)

        # Sort by timestamp descending (newest first)
        all_signals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Deduplication: keep latest signal per symbol (only non-HOLD/NEUTRAL)
        best_by_symbol = {}
        neutral_kept = []
        for sig in all_signals:
            sym = sig["symbol"]
            stype = sig.get("signal_type", "NEUTRAL")

            # Neutral/HOLD signals: keep as-is (show latest per symbol)
            if stype in ("NEUTRAL", "HOLD"):
                if sym not in [s["symbol"] for s in neutral_kept]:
                    neutral_kept.append(sig)
                continue

            # Buy/Sell signals: keep only the most recent per symbol type
            key = (sym, stype)
            if key not in best_by_symbol or sig.get("timestamp", "") > best_by_symbol[key].get("timestamp", ""):
                if key in best_by_symbol:
                    old = best_by_symbol[sym]
                    if old not in neutral_kept and old["symbol"] not in [s["symbol"] for s in neutral_kept]:
                        neutral_kept.append(old)
                best_by_symbol[key] = sig

        # Remove duplicates from neutral list by symbol
        seen_symbols_neutral = set()
        deduped_neutral = []
        for s in neutral_kept:
            if s["symbol"] not in seen_symbols_neutral:
                seen_symbols_neutral.add(s["symbol"])
                deduped_neutral.append(s)

        # Combine: strong signals first, then neutrals/holds at end
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
    """Get the N most recent signals (for grid overview)."""
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
                del r["details"]    # Clean up raw JSON field
                all_signals.append(r)
        except Exception:
            pass

        # Sort and limit
        all_signals.sort(key=lambda x: x.get("detected_at", ""), reverse=True)
        return jsonify({"signals": all_signals[:limit]})
    except Exception as e:
        return jsonify({"signals": [], "error": str(e)})


@app.route("/api/signals/symbol/<symbol>", methods=["GET"])
def api_signal_for_symbol(symbol):
    """Get all signals for a specific symbol (full history)."""
    if not db:
        return jsonify({"symbol": symbol, "signals": []})

    symbol = str(symbol).upper().strip()
    signals = []

    # From signals_log
    try:
        rows = db._c().execute("""
            SELECT symbol, 'TRADING_BOT', signal_type, CAST(strength AS REAL) as strength,
                   price, details, detected_at, delivered as is_delivered, delivery_channel
            FROM signals_log WHERE UPPER(symbol)=UPPER(?) ORDER BY detected_at DESC
        """, (symbol,)).fetchall()
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
        print("[SIGNALS] signals_log lookup %s error: %s" % (symbol, e))

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
        """, (symbol,)).fetchall()
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
        print("[SIGNALS] trading_alerts lookup %s error: %s" % (symbol, e))

    signals.sort(key=lambda x: x.get("detected_at", "") or x.get("timestamp", ""), reverse=True)
    return jsonify({"symbol": symbol, "signals": signals})


@app.route("/api/signals/add", methods=["POST"])
def api_signal_append():
    """Manual signal entry (via dashboard or API)."""
    if not db:
        return jsonify({"success": False, "error": "DB not initialized"}), 500

    data = request.get_json() or {}
    symbol = str(data.get("symbol", "")).strip().upper()
    signal_type = str(data.get("signal", "")).upper()    # BUY / SELL / HOLD
    strength = float(data.get("strength", 0))    # 0-100

    if not symbol or len(symbol) < 2:
        return jsonify({"success": False, "error": "Invalid symbol"}), 400
    if signal_type and signal_type not in ("BUY", "SELL", "HOLD", "STOP_LOSS", "TAKE_PROFIT", "WATCH", "NEUTRAL"):
        return jsonify({"success": False, "error": "Invalid signal type"}), 400

    details = {k: v for k, v in data.items() if k not in ("symbol", "signal", "strength")}

    # Persist to signals_log table
    try:
        import json as _json
        db._c().execute("""
            INSERT INTO signals_log (symbol, signal_type, strength, price, details, detected_at)
             VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, signal_type if signal_type else "NEUTRAL", strength,
              data.get("price"), _json.dumps(details), _utc_now_iso()))
        db._conn.commit()
        print("[SIGNALS] Manual signal added for %s: %s (%.1f)" % (symbol, signal_type, strength))
        return jsonify({"success": True})
    except sqlite3.Error as e:
        if "no such table" in str(e):
            return jsonify({"success": False, "error": "signals_log table not found - run DB migration"}), 500
        print("[SIGNALS] Insert error: %s" % e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/signals/mark-delivered", methods=["POST"])
def api_signal_mark_delivered():
    """Mark signal as delivered (used by cron delivery)."""
    if not db:
        return jsonify({"success": True})    # Silently OK if no DB

    try:
        rowcount = db._c().execute("""
            UPDATE signals_log SET delivered=1 WHERE id=? AND is_delivered=0
        """, (request.json.get("id"),)).rowcount if request.json else 0
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
