"""
api/main.py - Main API blueprints (health, overview, logs)

JH3.0: Centralized health check and system monitoring endpoints.
"""
import os

from flask import Blueprint, jsonify, request
from datetime import datetime

main_bp = Blueprint("main", __name__, url_prefix="/api/v1")


@main_bp.route("/health", methods=["GET"])
def health_check():
    """Comprehensive health check for all system components."""
    try:
        from core.logging_config import LOG
        import os
        import sqlite3
        
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # Check database
        try:
            db_path = "data/jarvis.db"
            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                tables = conn.execute(
                    'SELECT name FROM sqlite_master WHERE type="table"'
                ).fetchall()
                conn.close()
                health["components"]["database"] = {
                    "status": "ok",
                    "path": db_path,
                    "tables": len(tables)
                }
            else:
                health["components"]["database"] = {
                    "status": "missing",
                    "path": db_path
                }
                health["status"] = "degraded"
        except Exception as e:
            health["components"]["database"] = {
                "status": "error",
                "error": str(e)
            }
            health["status"] = "degraded"
        
        # Check LLM availability
        try:
            from core.fallback_engine import check_llm_availability
            llm_status = check_llm_availability()
            health["components"]["llm"] = llm_status
            if not llm_status.get("healthy"):
                health["components"]["llm"]["status"] = "offline"
        except Exception as e:
            health["components"]["llm"] = {
                "status": "unknown",
                "error": str(e)
            }
        
        # Check async queue
        try:
            from core.async_queue import get_async_queue
            queue = get_async_queue()
            queue_stats = queue.get_stats()
            health["components"]["async_queue"] = {
                "status": "ok",
                "stats": queue_stats
            }
        except Exception as e:
            health["components"]["async_queue"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Overall status
        if all(c.get("status") in ("ok", "offline") for c in health["components"].values()):
            health["status"] = "healthy"
        else:
            health["status"] = "degraded"
        
        return jsonify(health)
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@main_bp.route("/status", methods=["GET"])
def system_status():
    """Get overall system status and statistics."""
    try:
        from core.async_queue import get_async_queue
        from core.llm_gateway import get_llm_gateway
        
        queue = get_async_queue()
        gateway = get_llm_gateway()
        
        return jsonify({
            "status": "running",
            "version": "3.0.0",
            "timestamp": datetime.now().isoformat(),
            "async_queue": queue.get_stats(),
            "llm_gateway": gateway.get_stats()
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@main_bp.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries."""
    try:
        log_path = "logs/jarvis_hub.log"
        lines = int(request.args.get("lines", "50"))
        
        if not os.path.exists(log_path):
            return jsonify({"logs": [], "message": "Log file not found"})
        
        with open(log_path, "r") as f:
            all_lines = f.readlines()
        
        recent = all_lines[-lines:]
        
        return jsonify({
            "logs": recent,
            "total_lines": len(all_lines),
            "showing": len(recent)
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
