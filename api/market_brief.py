"""
api/market_brief.py - Market briefs API endpoints

JH3.0: CRUD for market_briefs table (cron output persistence).
"""
import os
import json
from datetime import datetime

from flask import Blueprint, jsonify, request, g, abort
import sqlite3

market_brief_bp = Blueprint("market_brief", __name__, url_prefix="/api/v1")


def get_db():
    """Get database connection (per-request)."""
    if "db" not in g:
        db_path = "data/jarvis.db"
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"Database not found: {db_path}")
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@market_brief_bp.teardown_app_request
def close_db(exception):
    """Close database connection at end of request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


@market_brief_bp.route("/market-briefs", methods=["GET"])
def list_market_briefs():
    """List market briefs with pagination and filtering.
    
    Query params:
        page (int): Page number, default 1
        per_page (int): Items per page, default 20, max 100
        source (str): Filter by source (cron, manual, etc.)
        date_from (str): Filter date >= this (YYYY-MM-DD)
        date_to (str): Filter date <= this (YYYY-MM-DD)
        search (str): Search in formatted_output
    """
    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
        source = request.args.get("source")
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        search = request.args.get("search")
        
        query = "SELECT id, date, source, created_at, formatted_output FROM market_briefs"
        count_query = "SELECT COUNT(*) FROM market_briefs"
        conditions = []
        params = []
        where_clause = ""
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        if date_from:
            conditions.append("date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("date <= ?")
            params.append(date_to)
        if search:
            conditions.append("formatted_output LIKE ?")
            params.append(f"%{search}%")
        
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)
            count_query += where_clause
        
        db = get_db()
        total = db.execute(count_query, params).fetchone()[0]
        
        query += where_clause
        query += " ORDER BY date DESC LIMIT ? OFFSET ?"
        params.extend([per_page, (page - 1) * per_page])
        
        rows = db.execute(query, params).fetchall()
        briefs = []
        for row in rows:
            briefs.append({
                "id": row["id"],
                "date": row["date"],
                "source": row["source"],
                "created_at": row["created_at"],
                "formatted_output": row["formatted_output"],
                "has_raw": True if row["formatted_output"] else False
            })
        
        return jsonify({
            "success": True,
            "data": briefs,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@market_brief_bp.route("/market-briefs/<int:b_id>", methods=["GET"])
def get_market_brief(b_id):
    """Get a single market brief by ID with full data."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, date, raw_json, formatted_output, source, created_at FROM market_briefs WHERE id = ?",
            (b_id,)
        ).fetchone()
        
        if row is None:
            return jsonify({"success": False, "error": "Brief not found"}), 404
        
        return jsonify({
            "success": True,
            "data": {
                "id": row["id"],
                "date": row["date"],
                "raw_json": row["raw_json"],
                "formatted_output": row["formatted_output"],
                "source": row["source"],
                "created_at": row["created_at"]
            }
        })
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Database not available"}), 503
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market_brief_bp.route("/market-briefs/latest", methods=["GET"])
def latest_market_brief():
    """Get the most recent market brief."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT id, date, raw_json, formatted_output, source, created_at FROM market_briefs ORDER BY date DESC LIMIT 1"
        ).fetchone()
        
        if row is None:
            return jsonify({"success": False, "error": "No briefs found"}), 404
        
        return jsonify({
            "success": True,
            "data": {
                "id": row["id"],
                "date": row["date"],
                "raw_json": row["raw_json"],
                "formatted_output": row["formatted_output"],
                "source": row["source"],
                "created_at": row["created_at"]
            }
        })
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Database not available"}), 503
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@market_brief_bp.route("/market-briefs/count", methods=["GET"])
def brief_count():
    """Get total count of stored briefs."""
    try:
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM market_briefs").fetchone()[0]
        by_source = db.execute(
            "SELECT source, COUNT(*) as cnt FROM market_briefs GROUP BY source"
        ).fetchall()
        
        return jsonify({
            "success": True,
            "total": total,
            "by_source": {row["source"]: row["cnt"] for row in by_source}
        })
    except FileNotFoundError:
        return jsonify({"success": False, "error": "Database not available"}), 503
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
