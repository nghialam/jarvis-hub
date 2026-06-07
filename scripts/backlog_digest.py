#!/usr/bin/env python3
"""
backlog_digest.py - Backlog Management Script

Scans daily memory files and extracts pending/open items into a structured backlog.md.
Serves as the Phase 3 memory system component from AGENTS.md.

Schedule: Daily at 11 PM via cron job.
"""

import os
import sys
import shutil
from datetime import datetime, timedelta


HERMES_HOME = os.path.expanduser("~/.hermes/memory/")
BACKLOG_PATH = os.path.join(os.path.dirname(HERMES_HOME), "backlog.md")
ARCHIVE_DAYS = 30        # Archive items from daily files older than this


def load_pending_items():
    """Load pending/open items from recent daily memory files."""
    pending_items = []
    today = datetime.now()

    for i in range(min(ARCHIVE_DAYS, 14)):      # Last 2 weeks max
        date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        filepath = os.path.join(HERMES_HOME, date + ".md")

        if not os.path.exists(filepath):
            continue

        with open(filepath, "r") as f:
            content = f.read()

        in_pending_section = False

        for line in content.split("\n"):
            stripped = line.strip()

            # Section detection
            if any(stripped.startswith(s) for s in ["## Pending ", "### Pending "]):
                in_pending_section = True
                continue

            if in_pending_section and stripped.startswith("## "):
                break

            # Extract pending items
            if in_pending_section and (stripped.startswith("- ") or stripped.startswith("* ")):
                item_text = stripped[2:].strip()
                if item_text:                                    # Skip empty dashes/stars
                    entry = {
                        "date": date,
                        "text": item_text,
                        "done": False
                    }
                    pending_items.append(entry)

    return pending_items


def deduplicate_items(items):
    """Remove duplicate pending items by text."""
    seen = set()
    unique = []
    for item in items:
        key = item["text"].strip().lower()
        if key not in seen and key:
            seen.add(key)
            unique.append(item)

    return unique


def sort_by_priority(items):
    """Sort backlog by priority indicators."""
    high_keywords = ["urgent", "important", "critical", "blocker", "must"]
    medium_keywords = ["should", "need to", "todo", "plan"]

    def priority_score(item):
        text_lower = item["text"].lower()
        if any(kw in text_lower for kw in high_keywords):
            return 0       # Highest priority
        elif any(kw in text_lower for kw in medium_keywords):
            return 1
        else:
            return 2     # Default

    return sorted(items, key=priority_score)


def _get_priority(item):
    """Helper to get priority score."""
    text_lower = item.get("text", "").lower()
    high_keywords = ["urgent", "important", "critical", "blocker", "must", "high"]
    medium_keywords = ["should", "need", "todo", "plan", "later"]

    if any(kw in text_lower for kw in high_keywords):
        return 0
    elif any(kw in text_lower for kw in medium_keywords):
        return 1
    else:
        return 2


def load_existing_backlog():
    """Load existing backlog items if backlog.md exists."""
    if not os.path.exists(BACKLOG_PATH):
        return []

    items = []
    in_items_section = False

    with open(BACKLOG_PATH, "r") as f:
        for line in f:
            stripped = line.strip()

            # Find the items list section after headers
            if stripped.startswith("## Active"):
                in_items_section = True
                continue

            if in_items_section and stripped.startswith("## "):
                break

            if in_items_section and (stripped.startswith("- [ ]") or
                                     stripped.startswith("- ") or
                                     stripped.startswith("* ")):

                text = stripped
                if text.startswith("- [ ]"):
                    text = text[6:].strip()
                elif text.startswith("- "):
                    text = text[2:].strip()
                else:
                    text = text[1:].strip()

                item = {
                    "date": "pending",    # From backlog, not daily file
                    "text": text,
                    "done": False
                }
                items.append(item)

    return items


def merge_backlogs(daily_items, existing_items):
    """Merge daily items with existing backlog, removing duplicates."""
    merged = {}

    # Add existing backlog items first
    for item in existing_items:
        key = item["text"].strip().lower()
        merged[key] = item

    # Add new daily items (don't override existing)
    for item in daily_items:
        key = item["text"].strip().lower()
        if key not in merged:    # Only add if not already there
            merged[key] = item

    return list(merged.values())


def format_backlog(items):
    """Format backlog as markdown."""
    high_priority = [i for i in items if _get_priority(i) <= 1]
    normal_items = [i for i in items[5:] if _get_priority(i) > 1]

    lines = []
    lines.append("# Backlog\n")
    lines.append("**Last updated:** " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("**Total active:** " + str(len(items)))
    lines.append("")

    if high_priority:
        lines.append("## High Priority\n")
        for item in high_priority:
            date_tag = ""
            if item.get("date") and item["date"] != "pending":
                date_tag = " (" + item["date"] + ")"
            lines.append("- [ ] {}{}".format(item["text"], date_tag))
        lines.append("")

    if normal_items:
        lines.append("## Normal Priority\n")
        for item in normal_items[:20]:    # Limit to 20 items
            date_tag = ""
            if item.get("date") and item["date"] != "pending":
                date_tag = " (" + item["date"] + ")"
            lines.append("- [ ] {}{}".format(item["text"], date_tag))
        lines.append("")

    return "\n".join(lines)


def digest_backlog():
    """Run full backlog digestion cycle."""
    print("[Backlog Digest] Starting backlog synchronization...")

    # Load items from all sources
    daily_items = load_pending_items()
    existing = load_existing_backlog()

    if not daily_items and not existing:
        print("[Backlog Digest] No pending items found.")
        return {"status": "empty"}

    print("[Backlog Digest] Found {} from daily files, {} in existing backlog".format(
        len(daily_items), len(existing)))

    # Merge and deduplicate
    merged = merge_backlogs(daily_items, existing)
    merged = sort_by_priority(merged)

    # Format as markdown
    content = format_backlog(merged)

    # Write to backlog.md with backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKLOG_PATH.replace(".md", "_" + timestamp + ".md")

    if os.path.exists(BACKLOG_PATH):
        shutil.copy2(BACKLOG_PATH, backup_path)
        print("[Backlog Digest] Backed up to: " + backup_path)

    os.makedirs(os.path.dirname(BACKLOG_PATH), exist_ok=True)
    with open(BACKLOG_PATH, "w") as f:
        f.write(content)

    print("[Backlog Digest] Written {} items to backlog.md".format(len(merged)))

    return {
        "status": "completed",
        "total_items": len(merged),
        "high_priority": sum(1 for i in merged if _get_priority(i) == 0),
        "normal_priority": sum(1 for i in merged if _get_priority(i) > 0)
    }


if __name__ == "__main__":
    try:
        result = digest_backlog()
        print("[Backlog Digest] Complete:", result["status"])
    except Exception as e:
        print("[Backlog Digest] Error: " + str(e))
