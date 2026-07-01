import sys
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent / "feed"))

from flask import Flask, render_template, jsonify, request
import data_fetcher
import feed_engine
import markdown

app = Flask(__name__)


# ============================================================
#  Jinja2 Helpers (filters + globals) — defined FIRST so they're available
# ============================================================

def format_timestamp(ts_ms):
    """Format timestamp to local string."""
    if not ts_ms:
        return "-"
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "-"


def markdownify(text):
    """Convert Markdown to HTML for web rendering."""
    extensions = ["tables", "fenced_code", "attr_list", "toc"]
    return markdown.markdown(str(text), extensions=extensions)


def get_git_version():
    """Get current git version/hash for the dashboard."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "HEAD"],
            cwd=str(Path(__file__).parent),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        # Fallback: short hash
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(Path(__file__).parent),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().split()[0] if result.stdout.strip() else "v1.0"
    except Exception:
        pass
    return "v1.0"


def clean_markdown_for_summary(text):
    """Strip markdown AND HTML formatting for clean summary display."""
    if not text:
        return ""
    # Strip HTML tags first (tables, headings, etc.)
    t = re.sub(r'<[^>]+>', '', text)
    # Strip bold/italic markers
    t = re.sub(r'\*\*|__', '', t)
    t = re.sub(r'[*_]', '', t)
    # Strip code block markers
    t = re.sub(r'```[\s\S]*?```', '', t)
    t = re.sub(r'`', '', t)
    # Strip link syntax, keep only text
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    # Strip image syntax
    t = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', t)
    # Strip header markers
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    # Normalize whitespace
    t = ' '.join(t.split())
    return t.strip()

# Register filters and globals
app.jinja_env.filters["timestamp_to_local"] = format_timestamp
app.jinja_env.filters["markdownify"] = markdownify
app.jinja_env.filters["clean_markdown"] = clean_markdown_for_summary
app.jinja_env.globals["get_git_version"] = get_git_version


# ============================================================
#  Constants
# ============================================================

CATEGORY_ICONS = {
    "news": "\U0001f4f0",
    "alert": "\U0001f6a8",
    "learning": "\U0001f4da",
    "update": "\U0001f4cb",
    "insight": "\U0001f4a1",
    "warning": "\u26a0\ufe0f",
    "error": "\u274c",
}


# ============================================================
#  Routes
# ============================================================

@app.route("/")
def root_redirect():
    """Root redirects to feed — the landing page."""
    from flask import redirect
    return redirect("/feed")


@app.route("/jobs")
def dashboard():
    """Cron jobs overview (moved from / to /jobs)"""
    data = data_fetcher.build_jobs_data()
    return render_template("index.html", data=data)


@app.route("/watchlist")
def watchlist_page():
    """Watchlist and portfolio display page"""
    memory_path = Path("/Users/nghialam/MEMORY.md")
    watchlist = []
    portfolio = []

    if memory_path.exists():
        content = memory_path.read_text()
        in_watchlist = False
        in_portfolio = False
        for line in content.split("\n"):
            if "### Watchlist" in line or "**Watchlist:**" in line:
                in_watchlist = True
                in_portfolio = False
                continue
            elif "### Portfolio" in line or "**Portfolio:**" in line:
                in_portfolio = True
                in_watchlist = False
                continue
            elif line.startswith("###") and not line.startswith("##"):
                in_watchlist = False
                in_portfolio = False

            if in_watchlist and line.strip():
                watchlist.append(line.strip().strip("-").strip())
            elif in_portfolio and line.strip():
                portfolio.append(line.strip().strip("-").strip())

    data = data_fetcher.build_jobs_data()
    return render_template(
        "watchlist.html",
        data=data,
        watchlist=watchlist,
        portfolio=portfolio,
    )


@app.route("/activity")
def activity_page():
    """Activity log page"""
    limit = int(request.args.get("limit", 50))
    activities = data_fetcher.build_activity_log(limit)
    data = data_fetcher.build_jobs_data()
    return render_template("activity.html", data=data, activities=activities)




# ============================================================
#  Learning Library Routes
# ============================================================

@app.route("/learning")
def learning_page():
    """Learning library - browse all lessons"""
    try:
        import lesson_data as ld
        lessons = ld.get_lessons()
        data = data_fetcher.build_jobs_data()
        return render_template(
            "learning.html",
            data=data,
            lessons=lessons,
        )
    except Exception as e:
        import traceback
        return f"Error: {e}\n{traceback.format_exc()}", 500


@app.route("/learning/<string:lesson_id>")
def learning_detail(lesson_id):
    """Single lesson detail view"""
    try:
        import lesson_data as ld
        all_lessons = ld.get_lessons()
        target = None
        idx = -1
        for i, l in enumerate(all_lessons):
            if l.get("id") == lesson_id:
                target = l
                idx = i
                break

        if not target:
            return "Lesson not found", 404

        prev_lesson = all_lessons[idx - 1] if idx > 0 else None
        next_lesson = all_lessons[idx + 1] if idx < len(all_lessons) - 1 else None

        data = data_fetcher.build_jobs_data()
        return render_template(
            "learning_detail.html",
            data=data,
            lesson=target,
            lesson_id=lesson_id,
            lesson_id_prev=prev_lesson["id"] if prev_lesson else None,
            lesson_id_next=next_lesson["id"] if next_lesson else None,
            prev_lesson=prev_lesson,
            next_lesson=next_lesson,
            all_lessons=all_lessons,
        )
    except Exception as e:
        import traceback
        return f"Error: {e}\n{traceback.format_exc()}", 500

@app.route("/feed")
def feed_page():
    """Feed page - timeline view of all cron job outputs"""
    limit = int(request.args.get("limit", 50))
    source = request.args.get("source", None)
    category = request.args.get("category", None)

    entries = feed_engine.read_entries(limit=limit, source=source, category=category)
    sources = feed_engine.get_sources()
    categories = feed_engine.get_categories()
    total_entries = feed_engine.read_entries(limit=200)

    data = data_fetcher.build_jobs_data()
    return render_template(
        "feed.html",
        data=data,
        entries=entries,
        sources=sources,
        categories=categories,
        limit=limit,
        source_filter=source,
        category_filter=category,
        category_icons=CATEGORY_ICONS,
        total_entries=total_entries,
    )


@app.route("/api/dashboard")
def api_dashboard():
    """REST API endpoint for dashboard data"""
    data = data_fetcher.build_jobs_data()
    return jsonify(data)


@app.route("/api/activity")
def api_activity():
    """REST API endpoint for activity log"""
    limit = int(request.args.get("limit", 50))
    activities = data_fetcher.build_activity_log(limit)
    return jsonify({"activities": activities})


@app.route("/feed/<string:feed_id>")
def feed_detail(feed_id):
    """Detail view for a single feed entry with markdown rendering."""
    try:
        all_entries = feed_engine.read_entries(limit=1000)
        target = None
        idx = -1
        for i, e in enumerate(all_entries):
            if e.get("id") == feed_id:
                target = e
                idx = i
                break

        if not target:
            return "Entry not found", 404

        prev_entry = all_entries[idx - 1] if idx > 0 else None
        next_entry = all_entries[idx + 1] if idx < len(all_entries) - 1 else None

        related = []
        for e in all_entries:
            if e["id"] == feed_id:
                continue
            score = 0
            if e.get("source") == target.get("source"):
                score += 2
            tags_a = set(target.get("tags", []))
            tags_b = set(e.get("tags", []))
            shared = tags_a & tags_b
            if shared:
                score += len(shared)
            if score > 0:
                related.append((score, e))

        related.sort(key=lambda x: x[0], reverse=True)
        related = [r[1] for r in related[:5]]

        data = data_fetcher.build_jobs_data()
        return render_template(
            "feed_detail.html",
            data=data,
            entry=target,
            prev_entry=prev_entry,
            next_entry=next_entry,
            related_entries=related,
            category_icons=CATEGORY_ICONS,
        )
    except Exception as e:
        import traceback
        return f"Error: {e}\n{traceback.format_exc()}", 500


@app.route("/api/feed")
def api_feed():
    """REST API for feed entries"""
    limit = int(request.args.get("limit", 50))
    source = request.args.get("source", None)
    category = request.args.get("category", None)
    tag = request.args.get("tag", None)

    entries = feed_engine.read_entries(
        limit=limit, source=source, category=category, tag=tag
    )
    return jsonify({"entries": entries, "total": len(entries)})


@app.route("/api/feed/write", methods=["POST"])
def api_feed_write():
    """Write a feed entry manually via API"""
    try:
        body = request.get_json()
        if not body or "source" not in body or "content" not in body:
            return jsonify({"error": "Missing source/content fields"}), 400

        entry = feed_engine.write_entry(
            source=body["source"],
            category=body.get("category", "update"),
            title=body.get("title", body["source"] + " - Update"),
            content=body["content"],
            tags=body.get("tags", []),
            source_file=body.get("source_file", ""),
            url=body.get("url", ""),
        )
        return jsonify({"status": "ok", "feed_id": entry["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/feed/stats")
def api_feed_stats():
    """Feed statistics - count by source/category"""
    all_entries = feed_engine.read_entries(limit=500)

    stats = {
        "total": len(all_entries),
        "by_source": {},
        "by_category": {},
        "recent_errors": [],
    }

    for e in all_entries:
        src = e.get("source", "unknown")
        cat = e.get("category", "unknown")
        stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
        if cat == "error":
            stats["recent_errors"].append(e)

    return jsonify(stats)


@app.route("/api/jobs/<job_id>/toggle")
def api_toggle_job(job_id):
    """Toggle a cron job on/off - disabled until needed"""
    return jsonify(
        {"status": "disabled", "message": "Use /api/feed/write to add entries instead"}
    ), 501


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9876
    print(f"Alfred Dashboard starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
