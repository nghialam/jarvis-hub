"""
api/market.py - Market Overview API blueprint (JH3.0 restoration + perf fix)

The v3.0 blueprint refactor deleted the v2.0 market-overview / companies /
heatmap routes (they lived inline in app.py) and never re-implemented them,
leaving the primary landing tab dead (all /api/v1/overview* 404'd).

This blueprint restores those routes and adds two usability fixes:
  1. A 15-minute in-memory TTL cache on /overview — the full external fetch
     (VN/global indices, crypto, gold, oil, DXY) is expensive; caching makes
     repeat loads instant.
  2. Top-movers served from the aggregated_data table (latest trading day)
     instead of re-fetching ~14 tickers live with 1.5s stagger sleeps — the
     landing call drops from ~47s to sub-second on warm, and motions/heatmap
     are fast on every call. Live vnstock fetch remains the fallback when the
     DB has no data.

Registered under url_prefix="/api/v1".
"""

import time

from flask import Blueprint, jsonify, request

market_bp = Blueprint("market", __name__, url_prefix="/api/v1")

# --- Overview TTL cache ------------------------------------------------------
_OV_CACHE = {"data": None, "ts": 0.0}
_OV_TTL = 900  # 15 minutes


def _db():
    """Return the shared Database instance (or None)."""
    try:
        from core.context import get_context
        return get_context().db
    except Exception:
        return None


def _mo():
    """Lazy-import core.market_overview."""
    import core.market_overview as mo
    return mo


# --- Top movers from the DB (fast, no network) --------------------------------
def _top_motions_from_db(limit=10):
    """Top gainers/losers from aggregated_data (latest trading day).

    Returns {"gainers": [...], "losers": [...], "as_of": date, "source": "db"}
    or None if the DB has no usable data.
    """
    db = _db()
    if not db:
        return None
    try:
        cur = db._c()
        as_of = cur.execute("SELECT MAX(date) FROM aggregated_data").fetchone()[0]
        if not as_of:
            return None
        rows = cur.execute(
            """SELECT ticker, close, price_change_pct, volume_ratio, ma5, ma20, rsi14
               FROM aggregated_data
               WHERE date = ? AND price_change_pct IS NOT NULL
               ORDER BY price_change_pct DESC""",
            (as_of,),
        ).fetchall()
        if not rows:
            return None
        half = max(1, limit // 2)

        def _shape(r):
            d = dict(r)
            d["symbol"] = str(d.get("ticker", "")).replace(".VN", "")
            d["price"] = d.get("close")
            d["change_pct"] = d.get("price_change_pct")
            return d

        gainers = [_shape(r) for r in rows[:half]]
        losers = [_shape(r) for r in rows[-half:]]
        losers.sort(key=lambda x: (x.get("change_pct") or 0))
        return {"gainers": gainers, "losers": losers, "as_of": as_of, "source": "db"}
    except Exception:
        return None


def _top_motions(limit=10):
    """Top movers: DB-first (fast), live vnstock fallback."""
    dbm = _top_motions_from_db(limit)
    if dbm and (dbm["gainers"] or dbm["losers"]):
        return dbm
    try:
        mo = _mo()
        lm = mo.get_top_motions(limit=limit)
        if lm:
            lm = dict(lm)
            lm.setdefault("source", "live")
            return lm
    except Exception:
        pass
    return {"gainers": [], "losers": [], "source": "none"}


def _overview_fresh():
    """Return cached overview if younger than _OV_TTL, else None."""
    if _OV_CACHE["data"] is not None and (time.time() - _OV_CACHE["ts"]) < _OV_TTL:
        return _OV_CACHE["data"]
    return None


def _refresh_overview():
    """Fetch the full overview (slow on cold) and top movers, then cache."""
    mo = _mo()
    data = mo.fetch_all_overview() or {}
    # Top movers from the DB (fast); fall back to live inside _top_motions.
    data["top_motions"] = _top_motions(limit=10)
    _OV_CACHE["data"] = data
    _OV_CACHE["ts"] = time.time()
    return data


# --- Routes -------------------------------------------------------------------
@market_bp.route("/overview", methods=["GET"])
def overview():
    """Get full market overview (indices, crypto, gold, oil, dxy) + top motions."""
    try:
        fresh = _overview_fresh()
        if fresh is not None:
            return jsonify({"status": "ok", "data": fresh, "cached": True})
        data = _refresh_overview()
        return jsonify({"status": "ok", "data": data, "cached": False})
    except Exception as e:
        # Serve a possibly-stale cache if a live refresh fails.
        if _OV_CACHE["data"] is not None:
            return jsonify({"status": "ok", "data": _OV_CACHE["data"], "cached": True, "stale": True})
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/refresh", methods=["POST"])
def overview_refresh():
    """Force a cache refresh (used by the frontend refresh button)."""
    try:
        data = _refresh_overview()
        return jsonify({"status": "ok", "data": data, "cached": False})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/indices", methods=["GET"])
def overview_indices():
    """Get market indices (VN + global)."""
    try:
        mo = _mo()
        vn = mo.fetch_vn_indices()
        global_idx = mo.fetch_global_indices()
        vn_list = [{**d, "name": name, "symbol": d.get("symbol", name)} for name, d in (vn or {}).items()]
        global_list = [{**d, "name": name, "symbol": d.get("symbol", name)} for name, d in (global_idx or {}).items()]
        return jsonify({"status": "ok", "vn": vn_list, "global": global_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/crypto", methods=["GET"])
def overview_crypto():
    """Get crypto prices."""
    try:
        mo = _mo()
        data = mo.fetch_crypto()
        crypto_list = [{**d, "name": name, "symbol": d.get("symbol", name)} for name, d in (data or {}).items()]
        return jsonify({"status": "ok", "data": crypto_list})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/gold", methods=["GET"])
def overview_gold():
    """Get gold price."""
    try:
        mo = _mo()
        data = mo.fetch_gold()
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/motions", methods=["GET"])
def overview_motions():
    """Get top gainers/losers (DB-first, live fallback)."""
    try:
        limit = int(request.args.get("limit", 10))
        data = _top_motions(limit=limit)
        flat = []
        if isinstance(data, dict):
            flat.extend(data.get("gainers", []) or [])
            flat.extend(data.get("losers", []) or [])
        return jsonify({"status": "ok", "data": flat, "source": data.get("source"), "as_of": data.get("as_of")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/overview/chart", methods=["GET"])
def overview_chart():
    """Get chart (price history) data for a symbol."""
    symbol = request.args.get("symbol", "")
    if not symbol:
        return jsonify({"status": "error", "error": "Missing symbol"}), 400
    try:
        mo = _mo()
        data = mo._fetch_yahoo_price(symbol)
        return jsonify({"status": "ok", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@market_bp.route("/companies", methods=["GET"])
def companies():
    """Search companies by symbol or name (from the shared watchlist)."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"status": "ok", "count": 0, "companies": []})
    db = _db()
    if not db:
        return jsonify({"status": "ok", "count": 0, "companies": []})
    try:
        q = "%" + query.upper() + "%"
        rows = db._c().execute(
            """SELECT DISTINCT symbol, name FROM watchlist
               WHERE UPPER(symbol) LIKE ? OR UPPER(COALESCE(name,'')) LIKE ?
               LIMIT 50""",
            (q, q),
        ).fetchall()
        companies_list = [dict(r) for r in rows]
        return jsonify({"status": "ok", "count": len(companies_list), "companies": companies_list})
    except Exception:
        return jsonify({"status": "ok", "count": 0, "companies": []})


@market_bp.route("/companies/<symbol>/news", methods=["GET"])
def company_news(symbol):
    """Get recent news mentioning a company symbol (graceful empty if no store)."""
    db = _db()
    articles = []
    if db:
        for table, symcol, titlecol in (
            ("news_enhanced", "affected_symbols", "title"),
            ("articles", "affected_symbols", "title"),
        ):
            try:
                rows = db._c().execute(
                    f"""SELECT * FROM {table}
                        WHERE {symcol} LIKE ? OR {titlecol} LIKE ?
                        ORDER BY rowid DESC LIMIT 20""",
                    ("%" + symbol.upper() + "%", "%" + symbol.upper() + "%"),
                ).fetchall()
                articles = [dict(r) for r in rows]
                if articles:
                    break
            except Exception:
                continue
    return jsonify({"status": "ok", "count": len(articles), "articles": articles})


@market_bp.route("/market/heatmap", methods=["GET"])
def sector_heatmap():
    """Sector/performance heatmap from top movers (DB-first, fast).

    Groups by sector when the source provides it, otherwise by performance
    bucket (top gainers / flat / top losers) so the tile is always meaningful.
    """
    try:
        data = _top_motions(limit=30)
        gainers = data.get("gainers", []) or []
        losers = data.get("losers", []) or []
        all_stocks = gainers + losers
        if not all_stocks:
            return jsonify({"status": "ok", "sectors": []})

        sectors = {}
        for stock in all_stocks:
            pct = stock.get("change_pct", 0) or 0
            sector = stock.get("sector")
            if not sector:
                if pct > 1:
                    sector = "Top Gainers"
                elif pct < -1:
                    sector = "Top Losers"
                else:
                    sector = "Flat"
            if sector not in sectors:
                sectors[sector] = {"gainers": 0, "losers": 0, "total": 0, "stocks": []}
            if pct >= 0:
                sectors[sector]["gainers"] += 1
            else:
                sectors[sector]["losers"] += 1
            sectors[sector]["total"] += 1
            sectors[sector]["stocks"].append({
                "symbol": stock.get("symbol", ""),
                "change_pct": pct,
                "price": stock.get("price", ""),
            })

        for d in sectors.values():
            if d["stocks"]:
                d["avg_change"] = round(sum(s["change_pct"] for s in d["stocks"]) / len(d["stocks"]), 2)
            else:
                d["avg_change"] = 0

        sector_list = [
            {"name": name, "avg_change": d["avg_change"], "gainers": d["gainers"],
             "losers": d["losers"], "total": d["total"], "stocks": d["stocks"][:5]}
            for name, d in sectors.items()
        ]
        sector_list.sort(key=lambda x: x["avg_change"], reverse=True)
        return jsonify({"status": "ok", "sectors": sector_list, "as_of": data.get("as_of")})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
