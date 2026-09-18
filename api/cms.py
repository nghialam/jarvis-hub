"""
api/cms.py - CMS API blueprints (Phase 3.8)

JH3.0: CMS articles CRUD endpoints.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

cms_bp = Blueprint("cms", __name__, url_prefix="/api/v1/cms")


@cms_bp.route("/articles", methods=["GET"])
def get_articles():
    """Get CMS articles."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"articles": [], "count": 0})
        
        try:
            rows = ctx.db._c().execute(
                "SELECT * FROM cms_articles ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            articles = [dict(r) for r in rows]
            return jsonify({"articles": articles, "count": len(articles)})
        except Exception:
            return jsonify({"articles": [], "count": 0})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cms_bp.route("/articles/<article_id>", methods=["GET"])
def get_article(article_id: str):
    """Get single CMS article."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"article": None}), 404
        
        try:
            row = ctx.db._c().execute(
                "SELECT * FROM cms_articles WHERE id = ?", (article_id,)
            ).fetchone()
            if row:
                return jsonify({"article": dict(row)})
            return jsonify({"article": None, "error": "Not found"}), 404
        except Exception as e:
            return jsonify({"article": None, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"article": None, "error": str(e)}), 404


@cms_bp.route("/articles", methods=["POST"])
def create_article():
    """Create CMS article."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()
        slug = str(data.get("slug", "")).strip()
        
        if not title or not content:
            return jsonify({"success": False, "error": "Title and content required"}), 400
        
        try:
            if not slug:
                slug = title.lower().replace(" ", "-")[:100]
            
            slug_auto = slug or title.lower().replace(" ", "-")[:100]
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            cursor = ctx.db._c().execute(
                """INSERT INTO cms_articles (slug, title, content, category, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (slug_auto, title, content, "general", "published", now, now)
            )
            ctx.db._conn.commit()
            return jsonify({
                "success": True,
                "id": cursor.lastrowid,
                "title": title,
                "slug": slug
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@cms_bp.route("/articles/<article_id>", methods=["PUT"])
def update_article(article_id: str):
    """Update CMS article."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        data = request.get_json() or {}
        title = str(data.get("title", "")).strip()
        content = str(data.get("content", "")).strip()
        slug = str(data.get("slug", "")).strip()
        
        if not title or not content:
            return jsonify({"success": False, "error": "Title and content required"}), 400
        
        try:
            if not slug:
                slug = title.lower().replace(" ", "-")[:100]
            
            ctx.db._c().execute(
                """UPDATE cms_articles SET title=?, content=?, slug=?, updated_at=? WHERE id=?""",
                (title, content, slug, datetime.now().isoformat(), article_id)
            )
            ctx.db._conn.commit()
            return jsonify({"success": True, "id": article_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@cms_bp.route("/articles/<article_id>", methods=["DELETE"])
def delete_article(article_id: str):
    """Delete CMS article."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"success": False, "error": "DB not available"}), 503
        
        try:
            ctx.db._c().execute("DELETE FROM cms_articles WHERE id = ?", (article_id,))
            ctx.db._conn.commit()
            return jsonify({"success": True, "id": article_id})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@cms_bp.route("/articles/<slug>", methods=["GET"])
def get_article_by_slug(slug: str):
    """Get CMS article by slug."""
    try:
        from core.context import get_context
        
        ctx = get_context()
        
        if not ctx.db:
            return jsonify({"article": None}), 404
        
        try:
            row = ctx.db._c().execute(
                "SELECT * FROM cms_articles WHERE slug = ?", (slug,)
            ).fetchone()
            if row:
                return jsonify({"article": dict(row)})
            return jsonify({"article": None, "error": "Not found"}), 404
        except Exception as e:
            return jsonify({"article": None, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"article": None, "error": str(e)}), 404
