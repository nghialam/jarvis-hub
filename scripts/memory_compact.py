#!/usr/bin/env python3
"""
memory_compact.py -- Weekly Memory Compaction Script

Distills daily memory files into a lean MEMORY.md.
Archives old daily files. Detects recurring error/fix patterns.

Schedule: Sunday 9:30 AM (cron), or --auto flag at session end.
"""

import os
import sys
import glob
from datetime import datetime, timedelta
from collections import Counter


HERMES_HOME = os.path.expanduser("~/.hermes/memory/")
MEMORY_MD_PATH = os.path.expanduser("~/.hermes/MEMORY.md")
BACKUP_DIR = os.path.expanduser("~/.hermes/memory/backups/")
ARCHIVE_DIR = os.path.expanduser("~/.hermes/memory/archived/")

MAX_MEMORY_MD_LINES = 50
MIN_DAILY_FILE_AGE_DAYS = 14
KEEP_RECENT_DAYS = 7


def ensure_dirs():
    os.makedirs(HERMES_HOME, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)


def read_memory_md():
    if os.path.exists(MEMORY_MD_PATH):
        with open(MEMORY_MD_PATH, "r") as f:
            return f.read()
    return None


def daily_files():
    pattern = os.path.join(HERMES_HOME, "*.md")
    files = glob.glob(pattern)
    active = []
    for f in files:
        name = os.path.basename(f)
        if "backup" not in name and "archive" not in name and "TEMPLATE" not in name:
            active.append(f)
    return sorted(active)


def parse_daily_file(filepath):
    with open(filepath, "r") as f:
        content = f.read()

    result = {
        "filename": os.path.basename(filepath),
        "date": filepath.split("/")[-1].replace(".md", ""),
        "content": content,
        "tasks_completed": [],
        "key_decisions": [],
        "lessons_learned": [],
        "pending_items": [],
        "errors": [],
    }

    current_section = None
    for line in content.split("\n"):
        stripped = line.strip()

        if stripped.startswith("## Tasks Completed") or stripped.startswith("### Tasks Completed"):
            current_section = "tasks_completed"
            continue
        elif stripped.startswith("## Key Decisions") or stripped.startswith("### Key Decisions"):
            current_section = "key_decisions"
            continue
        elif stripped.startswith("## Lessons Learned") or stripped.startswith("### Lessons Learned"):
            current_section = "lessons_learned"
            continue
        elif stripped.startswith("## Pending ") or stripped.startswith("### Pending "):
            current_section = "pending_items"
            continue
        elif stripped.startswith("## Errors") or stripped.startswith("### Errors"):
            current_section = "errors"
            continue

        if any(stripped.startswith(c) for c in ["-", "*", "\u2022"]):
            item = stripped.lstrip("-* \u2022").strip()
            if current_section:
                result[current_section].append(item)

    try:
        date_obj = datetime.strptime(result["date"], "%Y-%m-%d")
        result["date_parsed"] = date_obj.strftime("%A, %B %d, %Y")
    except (ValueError, KeyError):
        result["date_parsed"] = result["date"]

    return result


def detect_recurring_patterns(daily_contents):
    all_items = []
    for d in daily_contents:
        all_items.extend(d["tasks_completed"])
        all_items.extend(d["errors"])

    pattern_counts = Counter()
    keywords = [
        "fix", "bug", "error", "import", "add", "update", "config",
        "cron", "schedule", "memory", "backup", "test", "deploy"
    ]

    for item in all_items:
        lower_item = item.lower()
        for kw in keywords:
            if kw in lower_item:
                pattern_counts[kw] += 1

    recurring = [(kw, count) for kw, count in pattern_counts.most_common(10)]
    return [(kw, c) for kw, c in recurring if c >= 2]


def compact_content(daily_contents):
    now = datetime.now()
    recent_files = [
        d for d in daily_contents
        if (now - datetime.strptime(d["date"], "%Y-%m-%d")).days <= KEEP_RECENT_DAYS
    ]

    recurring_patterns = detect_recurring_patterns(daily_contents)

    tasks_by_category = Counter()
    errors_seen = []

    for d in reversed(daily_contents):
        for task in d["tasks_completed"]:
            tl = task.lower()
            if any(kw in tl for kw in ["fix", "bug", "error"]):
                tasks_by_category["Bug fixes & repairs"] += 1
            elif any(kw in tl for kw in ["add", "build", "implement"]):
                tasks_by_category["New features & implementations"] += 1
            elif any(kw in tl for kw in ["config", "schedule", "cron", "deploy"]):
                tasks_by_category["Infrastructure & config"] += 1
            elif any(kw in tl for kw in ["learn", "note", "pattern"]):
                tasks_by_category["Lessons learned"] += 1
            else:
                tasks_by_category["General tasks"] += 1

        errors_seen.extend(d["errors"])

    active_tasks = []
    recent_recent = [d for d in reversed(recent_files[-KEEP_RECENT_DAYS:])]
    for d in recent_recent:
        if d["pending_items"]:
            items_str = ", ".join(d["pending_items"][:3])
            entry = "**" + d["date"] + "**: " + items_str
            active_tasks.append(entry)

    lines = []
    lines.append("# Memory Compact -- " + now.strftime("%Y-%m-%d %H:%M"))
    lines.append("")
    lines.append("## Active Tasks (" + str(len(active_tasks)) + " items)")
    if active_tasks:
        for t in active_tasks[-5:]:
            lines.append("- " + t)
    else:
        lines.append("- No active pending tasks")

    lines.append("")
    lines.append("## Patterns This Week")
    significant = [(kw, c) for kw, c in recurring_patterns if c >= 2]
    if significant:
        for kw, count in significant:
            lines.append("- `" + kw + "`: " + str(count) + " occurrences (repeat >= 2)")
    else:
        lines.append("- No significant recurring patterns detected this week")

    all_lessons = []
    for d in daily_contents:
        all_lessons.extend(d["lessons_learned"])
    unique_lessons = list(dict.fromkeys(all_lessons[-10:]))

    if unique_lessons:
        lines.append("")
        lines.append("## Key Learning Points")
        for l in unique_lessons[-5:]:
            lines.append("- " + l)

    lines.append("")
    lines.append("## Active Errors to Watch")
    unique_errors = list(dict.fromkeys(errors_seen[-5:]))
    if unique_errors:
        for e in unique_errors:
            lines.append("- " + e)
    else:
        lines.append("- No active errors logged this week")

    if tasks_by_category:
        lines.append("")
        lines.append("## Task Summary This Week")
        for category, count in sorted(tasks_by_category.items(), key=lambda x: -x[1]):
            lines.append("- **" + category + "**: " + str(count))

    return "\n".join(lines)


def backup_old_memory(content):
    if content:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, "MEMORY_" + timestamp + ".md")
        with open(backup_path, "w") as f:
            f.write(content)
        return True
    return False


def archive_old_daily_files():
    now = datetime.now()
    archived_count = 0

    for filepath in daily_files():
        filename = os.path.basename(filepath)
        try:
            date_str = filename.replace(".md", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if (now - file_date).days > MIN_DAILY_FILE_AGE_DAYS:
                archive_month = file_date.strftime("%Y-%m")
                archive_subdir = os.path.join(ARCHIVE_DIR, archive_month)
                os.makedirs(archive_subdir, exist_ok=True)
                target = os.path.join(archive_subdir, filename)
                if not os.path.exists(target):
                    import shutil
                    shutil.copy2(filepath, target)
                    archived_count += 1
        except (ValueError, KeyError):
            continue

    return archived_count


def main(mode="weekly"):
    ensure_dirs()
    print("[Memory Compact] Starting memory compaction (" + mode + ")")

    daily_contents = [parse_daily_file(f) for f in daily_files()]
    old_memory = read_memory_md()

    if not daily_contents:
        print("[Memory Compact] No active daily files found. Nothing to compact.")
        return

    print("[Memory Compact] Processed " + str(len(daily_contents)) + " daily files")

    if old_memory and mode == "weekly":
        success = backup_old_memory(old_memory)
        print("[Memory Compact] Backup created: " + ("YES" if success else "NO"))

    compaction = compact_content(daily_contents)

    with open(MEMORY_MD_PATH, "w") as f:
        f.write(compaction + "\n")

    char_count = len(compaction)
    line_count = len(compaction.split("\n"))
    print("[Memory Compact] MEMORY.md updated: " + str(char_count) + " chars, " + str(line_count) + " lines")

    if mode == "weekly":
        archived = archive_old_daily_files()
        if archived > 0:
            print("[Memory Compact] Archived " + str(archived) + " old daily files")

        all_data = [parse_daily_file(f) for f in daily_files()]
        patterns = detect_recurring_patterns(all_data)
        flagged = [(kw, c) for kw, c in patterns if c >= 3]
        if flagged:
            print("[Memory Compact] Recurring patterns detected (copy to AGENTS.md?):")
            for kw, count in flagged[:5]:
                print("   WARNING: `" + kw + "` appeared " + str(count) + " times")


if __name__ == "__main__":
    mode = "weekly"
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        mode = "auto"
    main(mode=mode)
