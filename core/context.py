"""
core/context.py — Shared app context for API blueprints (JH3.0)

The Flask app (`app.py`) loads `db` and `config` at startup. This module
exposes them via a singleton so API blueprints can reuse the same DB
instance (same file, same WAL connection pool) instead of each creating
a divergent `Database()` with a different default path.

Usage in blueprints:
    from core.context import get_context
    ctx = get_context()
    if ctx.db is None:
        return jsonify({"error": "DB not initialized"}), 503
    rows = ctx.db._c().execute("SELECT ...").fetchall()
"""

import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()


class _AppContext:
    """Lightweight holder for app-level shared state."""
    db: Any = None          # core.db.Database instance (or None)
    config: Dict[str, Any] = {}


_ctx: Optional[_AppContext] = None


def init_context(db, config: Dict[str, Any]) -> None:
    """Called once from app.py::_init() after _load_db() succeeds."""
    global _ctx
    with _lock:
        _ctx = _AppContext()
        _ctx.db = db
        _ctx.config = config


def get_context() -> _AppContext:
    """Return the live app context. Always returns an object (never None)."""
    global _ctx
    if _ctx is None:
        with _lock:
            if _ctx is None:
                _ctx = _AppContext()  # fallback to empty
    return _ctx
