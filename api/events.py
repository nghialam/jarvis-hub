"""
api/events.py — Event viewer API routes (JH3.0 audit trail)

Endpoints:
    GET /api/v1/events           — Query events with filters
    GET /api/v1/events/stats     — Event statistics (last N hours)
    GET /api/v1/events/errors    — Failed events
    GET /api/v1/events/trace/<id> — Full event trace
    POST /api/v1/events/archive  — Archive old events
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify

bp = Blueprint("events", __name__, url_prefix="/api/v1/events")


@bp.route("/", methods=["GET"])
def list_events():
    """Query events with filters."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        event_type = request.args.get("type")
        status = request.args.get("status")
        source = request.args.get("source")
        trace_id = request.args.get("trace_id")
        start_time = request.args.get("start")
        end_time = request.args.get("end")
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))

        from core.events import EventType, EventStatus

        et = EventType(event_type) if event_type else None
        st = EventStatus(status) if status else None

        events = event_store.query(
            event_type=et,
            status=st,
            source=source,
            trace_id=trace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset,
        )

        return jsonify({
            "events": [e.to_dict() for e in events],
            "count": len(events),
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/stats", methods=["GET"])
def event_stats():
    """Get event statistics for the last N hours."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        hours = int(request.args.get("hours", 24))
        stats = event_store.get_stats(hours=hours)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/errors", methods=["GET"])
def get_errors():
    """Get failed events."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        limit = int(request.args.get("limit", 50))
        source = request.args.get("source")
        errors = event_store.get_errors(limit=limit, source=source)

        return jsonify({
            "errors": [e.to_dict() for e in errors],
            "count": len(errors),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/trace/<trace_id>", methods=["GET"])
def get_trace(trace_id):
    """Get all events in a trace (ordered by timestamp)."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        events = event_store.get_trace(trace_id)

        return jsonify({
            "trace_id": trace_id,
            "events": [e.to_dict() for e in events],
            "count": len(events),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/archive", methods=["POST"])
def archive_events():
    """Archive events older than N days."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        days = int(request.args.get("days", 30))
        count = event_store.archive_old(days=days)

        return jsonify({
            "status": "completed",
            "archived": count,
            "days": days,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/archive/<event_id>", methods=["POST"])
def archive_single(event_id):
    """Archive a single event."""
    try:
        from app import event_store
        if event_store is None:
            return jsonify({"error": "EventStore not initialized"}), 503

        success = event_store.archive(event_id)
        if not success:
            return jsonify({"error": "Event not found"}), 404

        return jsonify({"status": "archived", "event_id": event_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
