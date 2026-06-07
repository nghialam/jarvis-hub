#!/usr/bin/env python3
"""
session_init.py -- Session Auto-Initialization

On session start, creates today's daily memory file if it doesn't exist.
Loads recent context and prepares the session for memory operations.

This script is called at the beginning of each Hermes agent session.
"""

import os
import sys
import json
from datetime import datetime, timedelta

HERMES_HOME = os.path.expanduser("~/.hermes/memory/")
MEMORY_MD_PATH = os.path.expanduser("~/.hermes/MEMORY.md")


def ensure_dirs():
    os.makedirs(HERMES_HOME, exist_ok=True)


def get_today_file():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(HERMES_HOME, today + ".md")


def load_recent_context(days=3):
    """Load recent daily memory files for session context."""
    now = datetime.now()
    files = []

    for i in range(days):
        date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        filepath = os.path.join(HERMES_HOME, date + ".md")

        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                content = f.read()

            lines = content.split("\n")
            summary = {
                 "date": date,
                 "tasks_completed": [],
                 "key_decisions": [],
                 "pending_items": []
             }

            current_section = None
            for line in lines:
                stripped = line.strip()

                if stripped.startswith("## Tasks Completed") or stripped.startswith("### Tasks Completed"):
                    current_section = "tasks_completed"
                    continue
                elif stripped.startswith("## Key Decisions") or stripped.startswith("### Key Decisions"):
                    current_section = "key_decisions"
                    continue
                elif stripped.startswith("## Pending ") or stripped.startswith("### Pending "):
                    current_section = "pending_items"
                    continue

                if any(stripped.startswith(c) for c in ["-", "*", "\u2022"]):
                    item = stripped.lstrip("-* \u2022").strip()
                    if current_section:
                        summary[current_section].append(item)

            files.append(summary)

    return files


def load_active_tasks():
    """Load active tasks from MEMORY.md."""
    if not os.path.exists(MEMORY_MD_PATH):
        return []

    with open(MEMORY_MD_PATH, "r") as f:
        content = f.read()

    lines = content.split("\n")
    active_section = False
    tasks = []

    for line in lines:
        if line.startswith("## Active Tasks"):
            active_section = True
            continue
        elif active_section and line.startswith("## "):
            break

        if active_section and line.strip().startswith("- "):
            task = line.strip()[2:].strip()
            if task:
                tasks.append(task)

    return tasks


def create_todays_file():
    """Create today's daily memory file if it doesn't exist."""
    today = datetime.now().strftime("%Y-%m-%d")
    filepath = get_today_file()

    if os.path.exists(filepath):
        return "existed"

    now = datetime.now()
    day_name = now.strftime("%A")

    content = "# Day Log -- " + today + " (" + day_name + ")\n"
    content += "\n## Tasks Completed\n- None yet\n\n"
    content += "## Key Decisions\n- \n\n"
    content += "## Pending / Open Questions\n- \n\n"
    content += "## Lessons Learned\n- \n"

    with open(filepath, "w") as f:
        f.write(content)

    return "created"


def init_session():
    """Main initialization routine."""
    ensure_dirs()

    status = create_todays_file()
    print("[Session Init] Today's daily file: " + status)

    recent = load_recent_context(days=3)
    active = load_active_tasks()

    if recent:
        print("[Session Init] Loaded context from " + str(len(recent)) + " recent days")
        for ctx in recent:
            tasks = len(ctx.get("tasks_completed", []))
            pending = len(ctx.get("pending_items", []))
            print("    - " + ctx["date"] + ": " + str(tasks) + " tasks, " + str(pending) + " pending")

    if active:
        print("[Session Init] Active MEMORY.md tasks: " + str(len(active)))
        for task in active[-5:]:
            print("    - " + task)

    return {
         "daily_file_status": status,
         "recent_days_loaded": len(recent),
         "active_tasks_count": len(active)
     }


if __name__ == "__main__":
    try:
        result = init_session()
        print("[Session Init] Complete:", json.dumps(result))
    except Exception as e:
        error_msg = "[Session Init] Error during initialization: " + str(e)
        print(error_msg)
        sys.exit(0)
