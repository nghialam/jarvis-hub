"""
api/research.py - Research API blueprints (Phase 3.6)

JH3.0: Research reports, stats, and crawling endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

research_bp = Blueprint("research", __name__, url_prefix="/api/v1/research")


@research_bp.route("/reports", methods=["GET"])
def get_reports():
    """Get research reports."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"reports": [], "count": 0})
        
        try:
            rows = ctx.db._c().execute(
                "SELECT * FROM report_summaries ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            reports = [dict(r) for r in rows]
            return jsonify({"reports": reports, "count": len(reports)})
        except Exception:
            return jsonify({"reports": [], "count": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@research_bp.route("/stats", methods=["GET"])
def get_stats():
    """Get research statistics."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"stats": {}})
        
        try:
            total = ctx.db._c().execute("SELECT COUNT(*) FROM report_summaries").fetchone()[0]
            by_type = ctx.db._c().execute(
                "SELECT report_type, COUNT(*) FROM report_summaries GROUP BY report_type"
            ).fetchall()
            return jsonify({
                "total_reports": total,
                "by_type": {r[0]: r[1] for r in by_type}
            })
        except Exception:
            return jsonify({"stats": {}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@research_bp.route("/crawl", methods=["POST"])
def crawl():
    """Crawl research reports from sources."""
    try:
        data = request.get_json() or {}
        source = data.get("source", "all")
        
        # Return placeholder for now
        return jsonify({
            "status": "ok",
            "message": f"Crawling {source} reports...",
            "note": "Crawling implementation pending"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@research_bp.route("/pdf/<report_id>", methods=["GET"])
def download_pdf(report_id: str):
    """Download research report PDF."""
    try:
        # Placeholder - PDF download implementation pending
        return jsonify({
            "status": "ok",
            "message": "PDF download endpoint ready",
            "report_id": report_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
