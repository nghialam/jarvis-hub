"""
api/intelligence.py - Intelligence API blueprints (Phase 3.9)

JH3.0: Market intelligence, AI intelligence, and pipeline endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

intelligence_bp = Blueprint("intelligence", __name__, url_prefix="/api/v1/intelligence")


@intelligence_bp.route("/market/latest", methods=["GET"])
def get_latest_market_intel():
    """Get latest market intelligence run."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"intelligence": None, "count": 0})
        
        try:
            row = ctx.db._c().execute(
                """SELECT * FROM market_intelligence 
                   ORDER BY created_at DESC LIMIT 1"""
            ).fetchone()
            if row:
                return jsonify({
                    "intelligence": dict(row),
                    "count": 1
                })
            return jsonify({"intelligence": None, "count": 0})
        except Exception:
            return jsonify({"intelligence": None, "count": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@intelligence_bp.route("/market/history", methods=["GET"])
def get_market_intel_history():
    """Get market intelligence history."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"runs": [], "count": 0})
        
        try:
            rows = ctx.db._c().execute(
                """SELECT id, run_date, run_period, status, created_at 
                   FROM market_intelligence 
                   ORDER BY created_at DESC LIMIT 20"""
            ).fetchall()
            runs = [dict(r) for r in rows]
            return jsonify({"runs": runs, "count": len(runs)})
        except Exception:
            return jsonify({"runs": [], "count": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@intelligence_bp.route("/market/run", methods=["POST"])
def run_market_intelligence():
    """Trigger market intelligence pipeline immediately."""
    try:
        from core.async_queue import get_async_queue
        
        queue = get_async_queue()
        task_id = queue.submit("market_intelligence", {})
        
        return jsonify({
            "status": "accepted",
            "task_id": task_id,
            "message": "Market intelligence pipeline queued"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@intelligence_bp.route("/market/<run_id>", methods=["GET"])
def get_market_intel_run(run_id: str):
    """Get specific market intelligence run."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"run": None}), 404
        
        try:
            row = ctx.db._c().execute(
                "SELECT * FROM market_intelligence WHERE id = ?", (run_id,)
            ).fetchone()
            if row:
                return jsonify({"run": dict(row)})
            return jsonify({"run": None, "error": "Not found"}), 404
        except Exception as e:
            return jsonify({"run": None, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"run": None, "error": str(e)}), 500


@intelligence_bp.route("/market/<run_id>/sentiment", methods=["GET"])
def get_market_intel_sentiment(run_id: str):
    """Get sentiment distribution for a market intelligence run."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"sentiment": {}})
        
        try:
            # Parse articles_json to extract sentiment
            row = ctx.db._c().execute(
                "SELECT articles_json FROM market_intelligence WHERE id = ?", (run_id,)
            ).fetchone()
            if row and row[0]:
                import json
                articles = json.loads(row[0])
                sentiment = {"Bullish": 0, "Bearish": 0, "Neutral": 0}
                for article in articles:
                    s = article.get("sentiment", "Neutral")
                    if s in sentiment:
                        sentiment[s] += 1
                return jsonify({"sentiment": sentiment})
            return jsonify({"sentiment": {}})
        except Exception:
            return jsonify({"sentiment": {}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@intelligence_bp.route("/market/<run_id>", methods=["DELETE"])
def delete_market_intel_run(run_id: str):
    """Delete a market intelligence run."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        try:
            ctx.db._c().execute("DELETE FROM market_intelligence WHERE id = ?", (run_id,))
            ctx.db._conn.commit()
            return jsonify({"success": True, "id": run_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@intelligence_bp.route("/ai/daily-list", methods=["GET"])
def get_ai_intelligence_daily():
    """Get AI intelligence daily list from AI-finance runs."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        if not ctx.db:
            return jsonify({"intelligence": [], "count": 0})
        
        # Query from pipeline runs stored in db
        runs = []
        try:
            rows = ctx.db._c().execute(
                """SELECT run_id, pipeline_date, total_articles, total_sources, status
                   FROM gotham_runs 
                   ORDER BY pipeline_date DESC LIMIT 30"""
            ).fetchall()
            for row in rows:
                r = dict(row)
                # Get article count from articles table if possible
                try:
                    count = ctx.db._c().execute(
                        "SELECT COUNT(*) FROM articles WHERE run_id = ?", (r["run_id"],)
                    ).fetchone()[0]
                    r["article_count"] = count
                except Exception:
                    r["article_count"] = r.get("total_articles", 0)
                runs.append(r)
        except Exception:
            runs = []
        
        return jsonify({"intelligence": runs, "count": len(runs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@intelligence_bp.route("/pipeline/status", methods=["GET"])
def get_pipeline_status():
    """Get pipeline status."""
    try:
        from core.async_queue import get_async_queue
        
        queue = get_async_queue()
        tasks = queue.list_tasks(task_type="market_intelligence", limit=5)
        
        return jsonify({
            "status": "ok",
            "pending_tasks": len([t for t in tasks if t["status"] == "pending"]),
            "recent_tasks": tasks
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
