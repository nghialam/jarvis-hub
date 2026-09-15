"""
api/stocks.py - Stock API blueprints (Phase 3.4, 3.5)

JH3.0: Stock analysis, quotes, and watchlist endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

stocks_bp = Blueprint("stocks", __name__, url_prefix="/api/v1/stocks")


@stocks_bp.route("/analyze", methods=["GET"])
def analyze():
    """Analyze a stock (Phase 3.4 - migrated from app.py)."""
    try:
        symbol = request.args.get("symbol", "").upper().strip()
        if not symbol:
            return jsonify({"error": "Missing symbol parameter"}), 400
        
        # Use heuristic fallback if available
        try:
            from core.fallback_engine import analyze_stock_heuristic
            result = analyze_stock_heuristic(symbol)
            result["generated_by"] = "heuristic"
            return jsonify(result)
        except Exception as e:
            return jsonify({"symbol": symbol, "error": str(e), "generated_by": "error"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stocks_bp.route("/quotes", methods=["GET"])
def quotes():
    """Get quotes for multiple symbols."""
    try:
        symbols = request.args.get("symbols", "").split(",")
        symbols = [s.strip().upper() for s in symbols if s.strip()]
        
        if not symbols:
            return jsonify({"quotes": [], "count": 0})
        
        from core.fallback_engine import analyze_stock_heuristic
        quotes = []
        for sym in symbols[:20]:
            try:
                result = analyze_stock_heuristic(sym)
                quotes.append(result)
            except Exception:
                pass
        
        return jsonify({"quotes": quotes, "count": len(quotes)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stocks_bp.route("/symbols/search", methods=["GET"])
def symbol_search():
    """Search for stock/crypto symbols."""
    try:
        query = request.args.get("q", "").strip().upper()
        if len(query) < 2:
            return jsonify({"matches": [], "error": "Query too short"}), 400
        
        # Return empty matches for now (DB integration pending)
        return jsonify({"matches": [], "count": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stocks_bp.route("/watchlist", methods=["GET"])
def get_watchlist():
    """Get user's watchlist."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"symbols": [], "count": 0})
        watchlist = ctx.db.get_watchlist() if ctx.db else []
        return jsonify({"symbols": watchlist, "count": len(watchlist)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@stocks_bp.route("/watchlist/add", methods=["POST"])
def add_watchlist():
    """Add symbol to watchlist."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        
        if len(symbol) < 2:
            return jsonify({"success": False, "error": "Invalid symbol"}), 400
        
        if hasattr(ctx.db, "add_watchlist"):
            added = ctx.db.add_watchlist(symbol, name)
            return jsonify({"success": True, "added": added})
        
        return jsonify({"success": True, "added": symbol})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@stocks_bp.route("/watchlist/remove", methods=["POST"])
def remove_watchlist():
    """Remove symbol from watchlist."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        
        if len(symbol) < 2:
            return jsonify({"success": False, "error": "Invalid symbol"}), 400
        
        if hasattr(ctx.db, "remove_watchlist"):
            removed = ctx.db.remove_watchlist(symbol)
            return jsonify({"success": True, "removed": removed})
        
        return jsonify({"success": True, "removed": symbol})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
