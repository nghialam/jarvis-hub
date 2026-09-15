"""
api/screener.py - Screener API blueprints (Phase 3.5)

JH3.0: Screener, alert feed, and signals endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

screener_bp = Blueprint("screener", __name__, url_prefix="/api/v1/screener")


@screener_bp.route("/signals", methods=["GET"])
def get_signals():
    """Get stock screening signals."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"signals": [], "count": 0})
        
        # Get from signals_log or trading_alerts
        signals = []
        try:
            rows = ctx.db._c().execute(
                "SELECT id, symbol, signal_type, CAST(strength AS REAL) as severity, detected_at, delivered as status FROM signals_log ORDER BY detected_at DESC LIMIT 50"
            ).fetchall()
            signals.extend([{"source": "signals_log", **dict(r)} for r in rows])
        except Exception:
            pass
        
        return jsonify({"signals": signals, "count": len(signals)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@screener_bp.route("/alert-feed", methods=["GET"])
def get_alert_feed():
    """Get trading alert feed."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"alerts": [], "count": 0})
        
        alerts = []
        try:
            rows = ctx.db._c().execute(
                "SELECT id, symbol, signal_type, severity, timestamp, status FROM trading_alerts ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
            alerts.extend([{"source": "trading_alerts", **dict(r)} for r in rows])
        except Exception:
            pass
        
        return jsonify({"alerts": alerts, "count": len(alerts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@screener_bp.route("/alert", methods=["POST"])
def add_alert():
    """Add a trading alert."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        signal_type = str(data.get("signal_type", "BUY")).strip()
        price = float(data.get("price", 0))
        
        if len(symbol) < 2:
            return jsonify({"success": False, "error": "Invalid symbol"}), 400
        
        try:
            ctx.db._c().execute(
                "INSERT INTO trading_alerts (symbol, signal_type, severity, alert_data) VALUES (?, ?, ?, ?)",
                (symbol, signal_type, "MEDIUM", f"{{\"price\": {price}}}")
            )
            ctx.db._conn.commit()
            return jsonify({"success": True, "symbol": symbol, "signal": signal_type})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@screener_bp.route("/watchlist", methods=["GET"])
def get_watchlist():
    """Get screener watchlist."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"symbols": [], "count": 0})
        watchlist = ctx.db.get_watchlist() if ctx.db else []
        return jsonify({"symbols": watchlist, "count": len(watchlist)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
