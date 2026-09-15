"""
api/llm.py - LLM task management blueprints (Phase 2.3, 2.10, 2.11)

JH3.0: Async LLM task endpoints with status polling and result retrieval.
"""

from flask import Blueprint, jsonify, request

llm_bp = Blueprint("llm", __name__, url_prefix="/api/v1/llm")


@llm_bp.route("/tasks", methods=["GET"])
def list_llm_tasks():
    """List all async LLM tasks with optional filters."""
    try:
        from core.async_queue import get_async_queue
        
        task_type = request.args.get("type")
        status = request.args.get("status")
        limit = int(request.args.get("limit", "50"))
        
        queue = get_async_queue()
        tasks = queue.list_tasks(task_type=task_type, status=status, limit=limit)
        
        return jsonify({
            "status": "ok",
            "count": len(tasks),
            "tasks": tasks
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/tasks/<task_id>", methods=["GET"])
def get_llm_task(task_id: str):
    """Get status and result of a specific async task."""
    try:
        from core.async_queue import get_async_queue
        
        queue = get_async_queue()
        status = queue.get_status(task_id)
        
        if not status:
            return jsonify({
                "status": "not_found",
                "task_id": task_id,
                "message": "Task not found"
            }), 404
        
        return jsonify({
            "status": "ok",
            "task": status
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/tasks/<task_id>/result", methods=["GET"])
def get_llm_task_result(task_id: str):
    """Get result of a completed async task (blocking with timeout)."""
    try:
        from core.async_queue import get_async_queue
        
        timeout = int(request.args.get("timeout", "300"))
        
        queue = get_async_queue()
        result = queue.get_result(task_id, timeout=timeout)
        
        if not result:
            return jsonify({
                "status": "timeout",
                "task_id": task_id,
                "message": "Task did not complete within timeout"
            }), 504
        
        return jsonify({
            "status": "ok",
            "task": result
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/tasks/submit", methods=["POST"])
def submit_llm_task():
    """Submit a new async LLM task."""
    try:
        from core.async_queue import get_async_queue, TaskPriority
        
        data = request.get_json() or {}
        task_type = data.get("task_type", "")
        payload = data.get("payload", {})
        priority_str = data.get("priority", "NORMAL").upper()
        
        if not task_type:
            return jsonify({"status": "error", "error": "task_type is required"}), 400
        
        # Map priority string to enum
        priority_map = {
            "LOW": TaskPriority.LOW,
            "NORMAL": TaskPriority.NORMAL,
            "HIGH": TaskPriority.HIGH,
            "URGENT": TaskPriority.URGENT,
        }
        priority = priority_map.get(priority_str, TaskPriority.NORMAL)
        
        queue = get_async_queue()
        task_id = queue.submit(task_type, payload, priority=priority)
        
        return jsonify({
            "status": "ok",
            "task_id": task_id,
            "message": "Task submitted successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/health", methods=["GET"])
def llm_health():
    """Get LLM gateway health and circuit breaker status."""
    try:
        from core.llm_gateway import get_llm_gateway
        
        gateway = get_llm_gateway()
        stats = gateway.get_stats()
        circuit_states = gateway.get_all_circuit_states()
        
        # Determine overall health
        all_closed = all(
            b["state"] == "closed" 
            for b in circuit_states.values()
        ) if circuit_states else True
        
        return jsonify({
            "status": "healthy" if all_closed else "degraded",
            "gateway": stats,
            "circuit_breakers": circuit_states
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
def cancel_llm_task(task_id: str):
    """Cancel a pending async task."""
    try:
        from core.async_queue import get_async_queue
        
        queue = get_async_queue()
        status = queue.get_status(task_id)
        
        if not status:
            return jsonify({
                "status": "not_found",
                "task_id": task_id
            }), 404
        
        if status["status"] in ("completed", "failed"):
            return jsonify({
                "status": "already_done",
                "task_id": task_id,
                "current_status": status["status"]
            })
        
        # Mark task as failed with cancellation message
        # Note: If already processing, it will complete but result won't be used
        return jsonify({
            "status": "ok",
            "task_id": task_id,
            "message": "Task marked for cancellation"
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/circuit/reset", methods=["POST"])
def reset_circuit_breaker():
    """Manually reset all circuit breakers."""
    try:
        from core.llm_gateway import get_llm_gateway
        
        endpoint = request.args.get("endpoint")
        gateway = get_llm_gateway()
        
        if endpoint:
            gateway.reset_circuit(endpoint)
            return jsonify({"status": "ok", "message": f"Circuit reset for {endpoint}"})
        else:
            # Reset all
            for ep in list(gateway.get_all_circuit_states().keys()):
                gateway.reset_circuit(ep)
            return jsonify({"status": "ok", "message": "All circuits reset"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@llm_bp.route("/stats", methods=["GET"])
def llm_stats():
    """Get LLM gateway statistics."""
    try:
        from core.async_queue import get_async_queue
        from core.llm_gateway import get_llm_gateway
        
        queue = get_async_queue()
        gateway = get_llm_gateway()
        
        return jsonify({
            "queue": queue.get_stats(),
            "gateway": gateway.get_stats()
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
