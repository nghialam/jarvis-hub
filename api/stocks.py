"""
api/stocks.py - Stock API blueprints (Phase 3.4, 3.5)

JH3.0: Stock analysis, quotes, and watchlist endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import time

stocks_bp = Blueprint("stocks", __name__, url_prefix="/api/v1/stocks")

# Common VN stock tickers (top VN-Index constituents)
COMMON_VN_TICKERS = [
    "ACB", "AGG", "BAC", "BBA", "BCG", "BID", "BIN", "BKM", "BKE", "BKR",
    "BSR", "BVH", "C12", "C21", "CAP", "CCL", "CFM", "CGV", "CHP", "CIX",
    "CII", "CLC", "CLG", "CMG", "CMP", "CMS", "CNA", "CNS", "CTP", "CTR",
    "CTW", "D11", "DAG", "DBC", "DCF", "DGC", "DIG", "DIP", "DJK", "DNC",
    "DNN", "DNA", "DRC", "DST", "DTH", "DTS", "EIB", "EPC", "ERC", "FPT",
    "G32", "GAS", "GCM", "GDI", "GIL", "GVR", "HAG", "HAR", "HBC", "HCC",
    "HCP", "HDB", "HEJ", "HMC", "HNM", "HPF", "HPG", "HPT", "HSG", "HVA",
    "HVN", "IAM", "ICG", "ICN", "IDA", "IHK", "IMP", "JVC", "KDC", "KDH",
    "KHA", "KOS", "L14", "L39", "LDG", "MHB", "MIC", "MSN", "NAB", "NAM",
    "NAR", "NAC", "NCF", "NGC", "NKG", "NVL", "PAC", "PDR", "PEG", "PLX",
    "PNA", "PSP", "PVT", "QNC", "QRN", "REE", "S79", "SAM", "SBA", "SBV",
    "SCR", "SDU", "SEA", "SHS", "ST8", "STB", "STF", "STK", "STP", "TDG",
    "TDP", "THE", "TIG", "TKC", "TKG", "TL4", "TMT", "TNI", "TTP", "TV2",
    "TV4", "TWM", "VAT", "VC1", "VCI", "VCF", "VIC", "VIG", "VJC", "VNM",
    "VPF", "VRE", "VRT", "VSC", "VTP", "VNX", "VCG"
]


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
            return jsonify({"matches": [], "count": 0})
        
        results = []
        seen = set()
        
        # 1. Search in common VN tickers (prefix matching + partial matching)
        for ticker in COMMON_VN_TICKERS:
            if query in ticker:
                results.append({
                    "symbol": ticker,
                    "type": "stock",
                    "exchange": "HOSE",
                    "confidence": "prefix" if ticker.startswith(query) else "partial"
                })
                seen.add(ticker)
        
        # 2. Add watchlist items (even if not in COMMON_TICKERS)
        try:
            from core.context import get_context
            ctx = get_context()
            if ctx.db:
                watchlist = ctx.db.get_watchlist()
                for item in watchlist:
                    symbol = item.get("symbol", "") if isinstance(item, dict) else str(item)
                    if symbol and symbol not in seen and query in symbol:
                        results.append({
                            "symbol": symbol,
                            "type": "watchlist",
                            "exchange": "HOSE",
                            "confidence": "exact"
                        })
                        seen.add(symbol)
        except Exception:
            pass  # Ignore watchlist errors
        
        return jsonify({"matches": results, "count": len(results)})
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
