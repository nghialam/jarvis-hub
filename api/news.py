"""
api/news.py - News API blueprints (Phase 2.7)

JH3.0: Async news scoring with heuristic fallback.
"""

from flask import Blueprint, jsonify, request

news_bp = Blueprint("news", __name__, url_prefix="/api/v1/news")


@news_bp.route("/score", methods=["POST"])
def score_articles():
    """Score news articles asynchronously.
    
    Phase 2.7: Returns immediately with task_id, articles scored in background.
    """
    try:
        from core.async_queue import get_async_queue, TaskPriority
        
        data = request.get_json() or {}
        articles = data.get("articles", [])
        
        if not articles:
            # Phase 2.7: No articles to score, return empty
            return jsonify({
                "status": "ok",
                "scored": 0,
                "articles": []
            })
        
        # Phase 2.7: Submit batch scoring task
        queue = get_async_queue()
        task_id = queue.submit("news_score_batch", {"articles": articles}, priority=TaskPriority.HIGH)
        
        return jsonify({
            "status": "accepted",
            "task_id": task_id,
            "message": f"Scoring {len(articles)} articles asynchronously"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@news_bp.route("/trending", methods=["GET"])
def get_trending():
    """Get trending news articles."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        limit = int(request.args.get("limit", "10"))
        
        # Get articles with highest importance (handle missing table gracefully)
        trending_articles = []
        try:
            rows = ctx.db._c().execute(
                """SELECT a.*, e.importance 
                   FROM articles a 
                   LEFT JOIN news_enhanced e ON a.id = e.article_id
                   ORDER BY COALESCE(e.importance, 5) DESC
                   LIMIT ?""",
                (limit,)
            ).fetchall()
            trending_articles = [dict(r) for r in rows]
        except Exception:
            # Table doesn't exist yet, return empty
            trending_articles = []
        
        return jsonify({
            "status": "ok",
            "count": len(trending_articles),
            "articles": trending_articles
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@news_bp.route("/categories", methods=["GET"])
def get_categories():
    """Get news categories with counts."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        categories = []
        try:
            rows = ctx.db._c().execute(
                "SELECT category, COUNT(*) as count FROM articles GROUP BY category ORDER BY count DESC"
            ).fetchall()
            categories = [dict(r) for r in rows]
        except Exception:
            categories = []
        
        return jsonify({
            "status": "ok",
            "categories": categories
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@news_bp.route("/search", methods=["GET"])
def search_news():
    """Search news articles."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        query = request.args.get("q", "").strip()
        limit = int(request.args.get("limit", "20"))
        
        if not query:
            return jsonify({"articles": [], "total": 0})
        
        articles = []
        try:
            rows = ctx.db._c().execute(
                """SELECT * FROM articles 
                   WHERE title LIKE ? OR content LIKE ?
                   ORDER BY publication_date DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
            articles = [dict(r) for r in rows]
        except Exception:
            articles = []
        
        return jsonify({
            "status": "ok",
            "count": len(articles),
            "total": len(articles),
            "articles": articles
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
