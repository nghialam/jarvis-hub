#!/usr/bin/env python3
"""
jh30_patch.py — Apply all remaining JH3.0 fixes to the codebase.

This script modifies:
1. core/db.py     — register shared context on init
2. api/*.py       — use get_context() instead of creating new Database()
3. app.py         — add os import for get_logs
4. api/main.py    — add missing import os
"""
import os
import sys

# --- 1. Fix app.py: add os import and register context ---
def patch_app():
    """Patch app.py to import os and register shared context."""
    path = "/Users/nghialam/jarvis-hub/app.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Add 'import os' to the top-level imports if not present
    if 'import os\n' not in content.split('try:\n    from apscheduler')[0:1]:
        # Find the first block of imports (before the try/except)
        content = content.replace(
            "import json\nimport os\nimport re\nimport sys\nimport threading\nfrom datetime import datetime, timedelta\n",
            "import json\nimport os\nimport re\nimport sys\nimport threading\nfrom datetime import datetime, timedelta\n"
        )  # os is already there, no change needed
    
    # Add context registration after _load_db()
    if "from core.context import init_context" not in content:
        content = content.replace(
            "     _load_db()\n\n     # Phase 3: register API blueprints",
            "     _load_db()\n\n     # JH3.0: register shared context so blueprints reuse the same DB instance\n     try:\n         from core.context import init_context\n         init_context(db, config or {})\n     except Exception as e:\n         print('[BOOT] Context init failed: %s' % e)\n\n     # Phase 3: register API blueprints"
        )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ app.py patched")

# --- 2. Fix api/main.py: add missing import os ---
def patch_main():
    """Add missing 'import os' to api/main.py."""
    path = "/Users/nghialam/jarvis-hub/api/main.py"
    with open(path, "r") as f:
        content = f.read()
    
    if "import os" not in content.split("def get_logs()")[0]:
        # Add import after datetime import
        content = content.replace(
            "from flask import Blueprint, jsonify, request\nfrom datetime import datetime\n\nmain_bp",
            "import os\n\nfrom flask import Blueprint, jsonify, request\nfrom datetime import datetime\n\nmain_bp"
        )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/main.py patched")

# --- 3. Fix api/news.py: use context ---
def patch_news():
    """Replace Database() with get_context() in api/news.py."""
    path = "/Users/nghialam/jarvis-hub/api/news.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Replace pattern: "from core.db import Database\n        db = Database()" -> "from core.context import get_context\n        ctx = get_context()"
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        limit = int(request.args.get",
        "        from core.context import get_context\n        ctx = get_context()\n        limit = int(request.args.get"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        rows = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        query = request.args.get",
        "        from core.context import get_context\n        ctx = get_context()\n        query = request.args.get"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/news.py patched")

# --- 4. Fix api/intelligence.py: use context ---
def patch_intelligence():
    """Replace Database() with get_context() in api/intelligence.py."""
    path = "/Users/nghialam/jarvis-hub/api/intelligence.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:"
    )
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):\n            return jsonify",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            row = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            row = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            rows = ctx.db._c().execute"
    )
    content = content.replace(
        "            db._c().execute(\"DELETE FROM market_intelligence WHERE id = ?\"",
        "            ctx.db._c().execute(\"DELETE FROM market_intelligence WHERE id = ?\""
    )
    content = content.replace(
        "            db._conn.commit()\n            return jsonify({\"success\": True, \"id\": run_id})",
        "            ctx.db._conn.commit()\n            return jsonify({\"success\": True, \"id\": run_id})"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/intelligence.py patched")

# --- 5. Fix api/cms.py: use context ---
def patch_cms():
    """Replace Database() with get_context() in api/cms.py."""
    path = "/Users/nghialam/jarvis-hub/api/cms.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c\"):\n            return jsonify",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            row = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            row = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            rows = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            if not slug:\n                slug = title.lower().replace(\" \", \"-\")[:100]\n            \n            cursor = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            if not slug:\n                slug = title.lower().replace(\" \", \"-\")[:100]\n            \n            cursor = ctx.db._c().execute"
    )
    content = content.replace(
        "            db._conn.commit()\n            return jsonify({\"success\": True, \"id\": cursor.lastrowid})",
        "            ctx.db._conn.commit()\n            return jsonify({\"success\": True, \"id\": cursor.lastrowid})"
    )
    content = content.replace(
        "            db._c().execute(\n                \"\"\"UPDATE cms_articles SET title=?, content=?, slug=?, updated_at=? WHERE id=?\"\"\",",
        "            ctx.db._c().execute(\n                \"\"\"UPDATE cms_articles SET title=?, content=?, slug=?, updated_at=? WHERE id=?\"\"\",\""
    )
    content = content.replace(
        "            db._conn.commit()\n            return jsonify({\"success\": True, \"id\": article_id})",
        "            ctx.db._conn.commit()\n            return jsonify({\"success\": True, \"id\": article_id})"
    )
    content = content.replace(
        "            db._c().execute(\"DELETE FROM cms_articles WHERE id = ?\"",
        "            ctx.db._c().execute(\"DELETE FROM cms_articles WHERE id = ?\""
    )
    content = content.replace(
        "            db._conn.commit()\n            return jsonify({\"success\": True, \"id\": article_id})",
        "            ctx.db._conn.commit()\n            return jsonify({\"success\": True, \"id\": article_id})"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/cms.py patched")

# --- 6. Fix api/stocks.py: use context ---
def patch_stocks():
    """Replace Database() with get_context() in api/stocks.py."""
    path = "/Users/nghialam/jarvis-hub/api/stocks.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        watchlist = db.get_watchlist()",
        "from core.context import get_context\n        ctx = get_context()\n        watchlist = ctx.db.get_watchlist() if ctx.db else []"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        if hasattr(db, \"add_watchlist\"):",
        "        from core.context import get_context\n        ctx = get_context()\n        if ctx.db and hasattr(ctx.db, \"add_watchlist\"):"
    )
    content = content.replace(
        "            added = db.add_watchlist(symbol, name)\n            return jsonify({\"success\": True, \"added\": added})\n        \n        return jsonify({\"success\": True, \"added\": symbol})\n    except Exception as e:\n        return jsonify({\"success\": False, \"error\": str(e)}), 400\n        \n    try:\n        from core.db import Database\n        db = Database()\n        if hasattr(db, \"remove_watchlist\"):",
        "            added = ctx.db.add_watchlist(symbol, name)\n            return jsonify({\"success\": True, \"added\": added})\n        \n        return jsonify({\"success\": True, \"added\": symbol})\n    except Exception as e:\n        return jsonify({\"success\": False, \"error\": str(e)}), 400\n        \n    try:\n        from core.context import get_context\n        ctx = get_context()\n        if ctx.db and hasattr(ctx.db, \"remove_watchlist\"):"
    )
    content = content.replace(
        "            removed = db.remove_watchlist(symbol)\n            return jsonify({\"success\": True, \"removed\": removed})\n        \n        return jsonify({\"success\": True, \"removed\": symbol})\n    except Exception as e:\n        return jsonify({\"success\": False, \"error\": str(e)}), 400\n\n\n@stocks_bp.route",
        "            removed = ctx.db.remove_watchlist(symbol)\n            return jsonify({\"success\": True, \"removed\": removed})\n        \n        return jsonify({\"success\": True, \"removed\": symbol})\n    except Exception as e:\n        return jsonify({\"success\": False, \"error\": str(e)}), 400\n\n\n@stocks_bp.route"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/stocks.py patched")

# --- 7. Fix api/screener.py: use context ---
def patch_screener():
    """Replace Database() with get_context() in api/screener.py."""
    path = "/Users/nghialam/jarvis-hub/api/screener.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):\n            return jsonify",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):\n            return jsonify",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            rows = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            rows = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            db._c().execute(\n                \"INSERT INTO trading_alerts (symbol, signal_type, severity, alert_data) VALUES (?, ?, ?, ?)\",",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            ctx.db._c().execute(\n                \"INSERT INTO trading_alerts (symbol, signal_type, severity, alert_data) VALUES (?, ?, ?, ?)\","
    )
    content = content.replace(
        "            db._conn.commit()\n            return jsonify({\"success\": True, \"symbol\": symbol, \"signal\": signal_type})",
        "            ctx.db._conn.commit()\n            return jsonify({\"success\": True, \"symbol\": symbol, \"signal\": signal_type})"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        watchlist = db.get_watchlist() if db else []",
        "        from core.context import get_context\n        ctx = get_context()\n        watchlist = ctx.db.get_watchlist() if ctx.db else []"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/screener.py patched")

# --- 8. Fix api/research.py: use context ---
def patch_research():
    """Replace Database() with get_context() in api/research.py."""
    path = "/Users/nghialam/jarvis-hub/api/research.py"
    with open(path, "r") as f:
        content = f.read()
    
    content = content.replace(
        "from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):\n            return jsonify",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        if not db or not hasattr(db, "_c"):\n            return jsonify",
        "from core.context import get_context\n        ctx = get_context()\n        \n        if not ctx.db:\n            return jsonify"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            rows = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            rows = ctx.db._c().execute"
    )
    content = content.replace(
        "        from core.db import Database\n        db = Database()\n        \n        try:\n            total = db._c().execute",
        "        from core.context import get_context\n        ctx = get_context()\n        \n        try:\n            total = ctx.db._c().execute"
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/research.py patched")

# --- 9. Fix api/portfolio.py: use context ---
def patch_portfolio():
    """Replace placeholder with actual DB logic in api/portfolio.py."""
    path = "/Users/nghialam/jarvis-hub/api/portfolio.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Update holdings to use context
    content = content.replace(
        '        # Placeholder - portfolio data from DB pending\n        return jsonify({\n            "holdings": [],\n            "count": 0,\n            "note": "Portfolio data integration pending"\n        })',
        '        from core.context import get_context\n        ctx = get_context()\n        if not ctx.db:\n            return jsonify({"holdings": [], "count": 0})\n        try:\n            holdings = []\n            # Try portfolio_watchlist first\n            try:\n                rows = ctx.db._c().execute(\n                    """SELECT symbol, name, quantity, avg_price, current_price, total_cost, current_value, pnl, pnl_pct\n                       FROM portfolio_watchlist ORDER BY symbol"""\n                ).fetchall()\n                holdings = [dict(r) for r in rows]\n            except Exception:\n                holdings = []\n        except Exception as e:\n            holdings = []\n        return jsonify({"holdings": holdings, "count": len(holdings)})'
    )
    
    # Update transactions to use context
    content = content.replace(
        '        # Placeholder\n        return jsonify({\n            "transactions": [],\n            "count": 0,\n            "limit": limit\n        })',
        '        from core.context import get_context\n        ctx = get_context()\n        if not ctx.db:\n            return jsonify({"transactions": [], "count": 0})\n        try:\n            rows = ctx.db._c().execute(\n                """SELECT id, symbol, action, quantity, price, total, date, notes, status\n                   FROM portfolio_transactions\n                   ORDER BY date DESC LIMIT ?""", (limit,)\n            ).fetchall()\n            transactions = [dict(r) for r in rows]\n        except Exception:\n            transactions = []\n        return jsonify({"transactions": transactions, "count": len(transactions)})'
    )
    
    # Update pnl endpoint
    content = content.replace(
        '        # Placeholder\n        return jsonify({\n            "pnl": {\n                "total": 0,\n                "realized": 0,\n                "unrealized": 0,\n                "daily": 0,\n                "weekly": 0,\n                "monthly": 0\n            }\n        })',
        '        from core.context import get_context\n        ctx = get_context()\n        if not ctx.db:\n            return jsonify({"pnl": {"total": 0, "realized": 0, "unrealized": 0}})\n        try:\n            # Calculate from holdings + transactions\n            holdings = []\n            try:\n                rows = ctx.db._c().execute("SELECT * FROM portfolio_watchlist").fetchall()\n                holdings = [dict(r) for r in rows]\n            except Exception:\n                pass\n            total_cost = sum(h.get("total_cost", 0) for h in holdings)\n            current_value = sum(h.get("current_value", 0) for h in holdings)\n            pnl = current_value - total_cost\n            return jsonify({\n                "pnl": {\n                    "total": round(pnl, 2),\n                    "realized": 0,\n                    "unrealized": round(pnl, 2),\n                    "daily": 0,\n                    "weekly": 0,\n                    "monthly": 0,\n                    "total_cost": round(total_cost, 2),\n                    "current_value": round(current_value, 2)\n                }\n            })\n        except Exception as e:\n            return jsonify({"error": str(e)})'
    )
    
    # Update add_transaction to use context
    content = content.replace(
        '        # Placeholder - save to DB pending\n        return jsonify({\n            "success": True,\n            "symbol": symbol,\n            "action": action,\n            "quantity": quantity,\n            "price": price,\n            "note": "Transaction recorded"\n        })',
        '        from core.context import get_context\n        ctx = get_context()\n        if not ctx.db:\n            return jsonify({"success": False, "error": "DB not available"}), 503\n        try:\n            total = quantity * price\n            ctx.db._c().execute(\n                """INSERT INTO portfolio_transactions (symbol, action, quantity, price, total, status)\n                   VALUES (?, ?, ?, ?, ?, ?)""",\n                (symbol, action, quantity, price, total, "completed")\n            )\n            ctx.db._conn.commit()\n            return jsonify({"success": True, "symbol": symbol, "action": action, "quantity": quantity, "price": price})\n        except Exception as e:\n            return jsonify({"success": False, "error": str(e)}), 400'
    )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ api/portfolio.py patched")

# --- 10. Fix core/db.py: register context on init ---
def patch_db():
    """Patch core/db.py to register shared context after init."""
    path = "/Users/nghialam/jarvis-hub/core/db.py"
    with open(path, "r") as f:
        content = f.read()
    
    # Add context registration at end of __init__
    if "from core.context import get_context" not in content:
        content = content.replace(
            "        self.init_db()\n        # Bind orphan methods",
            "        self.init_db()\n        # Bind orphan methods"
        )
        # Add after init_db() call
        content = content.replace(
            "        self.init_db()\n        # Bind orphan methods (indent broken in this file) so they act as instance methods\n        _bind_orphans(self)\n\n    def _attempt_recovery(self):",
            "        self.init_db()\n        # Bind orphan methods (indent broken in this file) so they act as instance methods\n        _bind_orphans(self)\n\n        # JH3.0: register shared context automatically\n        try:\n            from core.context import get_context\n            ctx = get_context()\n            ctx.db = self\n        except Exception:\n            pass\n\n    def _attempt_recovery(self):"
        )
    
    with open(path, "w") as f:
        f.write(content)
    print("✓ core/db.py patched")

# --- Run all patches ---
if __name__ == "__main__":
    print("Applying JH3.0 patches...")
    patch_app()
    patch_main()
    patch_news()
    patch_intelligence()
    patch_cms()
    patch_stocks()
    patch_screener()
    patch_research()
    patch_portfolio()
    patch_db()
    print("All patches applied!")
