#!/usr/bin/env python3
"""
session_self_audit.py - Session Self-Audit System

Runs at session end to validate:
1. Hindsight plugin status (primary memory store)
2. Backlog consistency
3. Cron job health
4. Recurring pattern alerts
"""

import os
import sys
import glob
import re
from datetime import datetime, timedelta

HERMES_HOME = os.path.expanduser("~/.hermes/memory/")
MEMORY_MD_PATH = os.path.expanduser("~/.hermes/MEMORY.md")
MAX_MEMORY_AGE_HOURS = 24


def get_today_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(HERMES_HOME, today + ".md")


def audit_hindsight_status():
    """Check Hindsight plugin is active and responsive."""
    import subprocess

    try:
        result = subprocess.run(
            ["hermes", "memory", "status"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            content = result.stdout
            has_provider = "Provider:" in content and "hindsight" in content.lower()
            is_available = "available" in content.lower()

            if has_provider and is_available:
                return {
                    "status": "OK",
                    "messages": ["Hindsight plugin active, provider confirmed"],
                    "recommendation": None,
                    "plugin": "hindsight",
                    "provider_available": True
                }
            else:
                return {
                    "status": "WARN",
                    "messages": ["Hindsight installed but provider not confirmed or unavailable"],
                    "recommendation": "Check Hermes memory configuration and restart",
                    "plugin": "hindsight",
                    "provider_available": False
                }
        else:
            return {
                "status": "WARN",
                "messages": ["Hindsight status command returned non-zero output"],
                "recommendation": "Verify Hermes memory plugin is properly installed and configured"
            }
    except Exception as e:
        return {
            "status": "WARN",
            "messages": ["Hindsight check failed: " + str(e)],
            "recommendation": "Ensure Hermes agent is running with memory plugin enabled"
        }


def audit_daily_files():
    """Check that daily files (if kept) are being created and maintained."""
    today = get_today_file()
    status = "OK"
    messages = []

    if os.path.exists(today):
        size = os.path.getsize(today)
        if size < 50:
            status = "WARN"
            messages.append("Today's daily file is small (" + str(size) + "B) - likely empty")

        for i in range(1, 4):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            filepath = os.path.join(HERMES_HOME, date + ".md")
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                if size < 50:
                    if status != "WARN":
                        status = "INFO"
                    messages.append(date + ": Small file (" + str(size) + "B), likely empty")

    return {"status": status, "messages": messages}


def audit_backlog_consistency():
    """Check backlog for consistency issues."""
    backlog_path = os.path.join(os.path.dirname(HERMES_HOME), "backlog.md")

    if not os.path.exists(backlog_path):
        return {
            "status": "INFO",
            "messages": ["No backlog.md found. Ensure it exists if feature is active."],
            "recommendation": None
        }

    with open(backlog_path, "r") as f:
        content = f.read()

    pending_count = content.count("- [ ]") + content.count("- ")
    active_status = content.lower().count("pending") + content.lower().count("in progress")

    if pending_count < 1 and any(x in content for x in ["TODO", "backlog"]):
        status = "WARN"
        messages = ["Backlog has items but no active tasks - may be empty"]
        recommendation = None
    else:
        status = "OK" if pending_count > 0 else "INFO"
        messages = ["Backlog has ~" + str(pending_count) + " items, " + str(active_status) + " active"]
        recommendation = None

    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    matches = date_pattern.findall(content)
    if len(matches) > 30:
        status = "WARN"
        messages.append("Backlog accumulated (" + str(len(matches)) + " dates)")
        recommendation = "Review backlog for completion/archive."

    return {
        "status": status,
        "messages": messages,
        "recommendation": recommendation,
        "item_count": pending_count
    }


def audit_cron_health():
    """Check that related scripts exist and are non-trivial."""
    cron_scripts = {
        "session_init.py": "/Users/nghialam/jarvis-hub/scripts/session_init.py",
        "auto_improvement_engine.py": "/Users/nghialam/jarvis-hub/scripts/auto_improvement_engine.py",
        "backlog_digest.py": "/Users/nghialam/jarvis-hub/scripts/backlog_digest.py"
    }

    status = "INFO"
    messages = []

    for name, path in cron_scripts.items():
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > 100:
                messages.append(name + ": ready (" + str(size) + "B)")
            else:
                status = "WARN"
                messages.append(name + ": too small (" + str(size) + "B)")
        else:
            status = "WARN"
            messages.append(name + ": NOT FOUND (cron will fail)")

    recommendation = None if all(os.path.exists(p) for p in cron_scripts.values()) else "Missing scripts - add to cron jobs."

    return {
        "status": status,
        "messages": messages,
        "recommendation": recommendation,
        "scripts_checked": len(cron_scripts)
    }


def detect_context_drift():
    """Detect if context has drifted from recent actions."""
    now = datetime.now()
    daily_files = glob.glob(os.path.join(HERMES_HOME, "*.md"))

    if not daily_files:
        return {
            "status": "INFO",
            "messages": ["No daily files found (memory backed by Hindsight) - this is normal"],
            "recommendation": None
        }

    most_recent = max(daily_files, key=os.path.getmtime)
    age_hours = (now.timestamp() - os.path.getmtime(most_recent)) / 3600

    if age_hours > MAX_MEMORY_AGE_HOURS:
        status = "WARN"
        messages = ["Most recent daily file is " + str(int(age_hours)) + "h old"]
        recommendation = "Consider archiving old daily files"
    else:
        status = "OK"
        messages = ["Daily files current (" + str(int(age_hours)) + "h old)"]
        recommendation = None

    return {
        "status": status,
        "messages": messages,
        "recommendation": recommendation
    }


def audit_error_patterns():
    """Check for recurring error patterns in memory files."""
    daily_files = glob.glob(os.path.join(HERMES_HOME, "*.md"))
    errors = []
    error_keywords = ["error", "fail", "exception", "crash", "bug", "fix"]

    for filepath in daily_files[-5:]:
        try:
            with open(filepath, "r") as f:
                content = f.read().lower()
            for kw in error_keywords:
                if kw in content:
                    count = content.count(kw)
                    errors.append({"file": filepath.split("/")[-1], "keyword": kw, "count": count})
        except Exception:
            continue

    pattern_counts = {}
    for err in errors:
        kw = err["keyword"]
        pattern_counts[kw] = pattern_counts.get(kw, 0) + err["count"]

    recurring = [(kw, c) for kw, c in pattern_counts.items() if c >= 2]

    status = "INFO"
    messages = ["Checked last 5 daily files for error patterns (optional, memory is Hindsight-backed)"]
    recommendation = None

    if recurring:
        status = "WARN"
        messages.append("Recurring error patterns found:")
        for kw, c in recurring:
            messages.append("- `" + kw + "` appears " + str(c) + "x - consider AGENTS.md")
        recommendation = "Investigate recurring errors and document fix in AGENTS.md"

    return {
        "status": status,
        "messages": messages,
        "recommendation": recommendation,
        "pattern_count": len(recurring)
    }


def run_audit():
    """Run all audit checks and produce consolidated report."""
    results = {}
    warnings = []

    results["hindsight_status"] = audit_hindsight_status()
    results["daily_files"] = audit_daily_files()
    results["backlog"] = audit_backlog_consistency()
    results["cron_health"] = audit_cron_health()
    results["context_drift"] = detect_context_drift()
    results["error_patterns"] = audit_error_patterns()

    statuses = [v["status"] for v in results.values()]

    if "ERROR" in statuses:
        overall = "ERROR"
    elif "WARN" in statuses:
        overall = "WARN"
    else:
        overall = "OK"

    if overall == "WARN":
        warnings = []
        for name, data in results.items():
            if data["status"] == "WARN":
                for m in data["messages"]:
                    warnings.append(m)

    report_lines = [
        "### Session Self-Audit Report",
        "Date: " + datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Memory Store: Hindsight (primary, replaced MEMORY.md)",
        "Overall Status: " + overall,
        ""
    ]

    for key, data in results.items():
        icon_map = {"OK": "\u2705", "WARN": "\u26a0\ufe0f", "ERROR": "\u274c", "INFO": "\u2139\ufe0f"}
        icon = icon_map.get(data["status"], "?")
        report_lines.append(icon + " " + key + ": " + data["status"])
        for msg in data["messages"]:
            report_lines.append("    - " + msg)

    if overall == "WARN" and warnings:
        report_lines.append("")
        report_lines.append("**Recommendations:**")
        recs = [v.get("recommendation") for v in results.values() if v.get("recommendation")]
        for rec in recs:
            report_lines.append("- " + rec)

    report_text = "\n".join(report_lines)

    return {
        "overall_status": overall,
        "details": results,
        "report_text": report_text,
        "warnings": warnings
    }


def main():
    """Main entry point for session self-audit."""
    try:
        result = run_audit()
        print("[Self-Audit] Status: " + result["overall_status"])
        print(result["report_text"])

        if result["overall_status"] in ["WARN", "ERROR"]:
            filepath = get_today_file()
            warnings_str = "\n".join(
                ["- AUTO-AUDIT: " + w for w in result.get("warnings", [])]
            )
            with open(filepath, "a") as f:
                f.write("\n\n## Session Auto-Audit\n" + warnings_str)

    except Exception as e:
        print("[Self-Audit] Error during audit: " + str(e))


if __name__ == "__main__":
    main()
