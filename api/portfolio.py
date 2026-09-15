"""
api/portfolio.py - Portfolio API blueprints (Phase 3.7)

JH3.0: Portfolio holdings, transactions, and PnL endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/api/v1/portfolio")


@portfolio_bp.route("/holdings", methods=["GET"])
def get_holdings():
    """Get portfolio holdings."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"holdings": [], "count": 0})
        
        holdings = []
        try:
            rows = ctx.db._c().execute(
                """SELECT symbol, name, quantity, avg_price, current_price, 
                       total_cost, current_value, pnl, pnl_pct
                  FROM portfolio_watchlist ORDER BY symbol"""
            ).fetchall()
            holdings = [dict(r) for r in rows]
        except Exception:
            # Fallback: read from watchlist table
            try:
                rows = ctx.db._c().execute(
                    "SELECT symbol, name FROM watchlist ORDER BY symbol"
                ).fetchall()
                holdings = [{"symbol": r[0], "name": r[1]} for r in rows]
            except Exception:
                holdings = []
        
        return jsonify({"holdings": holdings, "count": len(holdings)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portfolio_bp.route("/transactions", methods=["GET"])
def get_transactions():
    """Get portfolio transactions."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"transactions": [], "count": 0})
        
        limit = int(request.args.get("limit", "50"))
        
        transactions = []
        try:
            rows = ctx.db._c().execute(
                """SELECT id, symbol, action, quantity, price, total, date, notes, status
                   FROM portfolio_transactions
                   ORDER BY date DESC LIMIT ?""", (limit,)
            ).fetchall()
            transactions = [dict(r) for r in rows]
        except Exception:
            transactions = []
        
        return jsonify({"transactions": transactions, "count": len(transactions)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portfolio_bp.route("/pnl", methods=["GET"])
def get_pnl():
    """Get portfolio P&L from holdings."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"pnl": {"total": 0, "realized": 0, "unrealized": 0}})
        
        total_cost = 0
        current_value = 0
        
        try:
            rows = ctx.db._c().execute(
                "SELECT total_cost, current_value FROM portfolio_watchlist"
            ).fetchall()
            for r in rows:
                d = dict(r)
                total_cost += d.get("total_cost", 0)
                current_value += d.get("current_value", 0)
        except Exception:
            pass
        
        pnl = current_value - total_cost
        pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0
        
        return jsonify({
            "pnl": {
                "total": round(pnl, 2),
                "realized": 0,
                "unrealized": round(pnl, 2),
                "daily": 0,
                "weekly": 0,
                "monthly": 0,
                "pct": round(pnl_pct, 2),
                "total_cost": round(total_cost, 2),
                "current_value": round(current_value, 2)
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@portfolio_bp.route("/add", methods=["POST"])
def add_transaction():
    """Add a portfolio transaction."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        symbol = str(data.get("symbol", "")).strip().upper()
        action = str(data.get("action", "BUY")).upper()
        quantity = int(data.get("quantity", 0))
        price = float(data.get("price", 0))
        
        if not symbol or quantity <= 0:
            return jsonify({"success": False, "error": "Invalid data"}), 400
        
        total = quantity * price
        
        ctx.db._c().execute(
            """INSERT INTO portfolio_transactions (symbol, action, quantity, price, total, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (symbol, action, quantity, price, total, "completed")
        )
        ctx.db._conn.commit()
        
        return jsonify({
            "success": True,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "total": round(total, 2)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
