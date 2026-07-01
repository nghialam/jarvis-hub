#!/usr/bin/env python3
"""Auto-improvement engine - scans learnings, detects patterns, promotes to AGENTS.md."""

import os
import sys
import re
from datetime import datetime
from collections import Counter

LEARNINGS_DIR = os.path.expanduser("~/.hermes/.learnings/")
AGENTS_MD_PATH = os.path.expanduser("~/.hermes/hermes-agent/AGENTS.md")


def read_learning_file(filename):
    filepath = os.path.join(LEARNINGS_DIR, filename)
    if not os.path.exists(filepath):
        return []
    
    result = []
    with open(filepath, "r") as f:
        content = f.read()
    
    current_entry = {"raw": "", "details": []}
    started = False
    
    for line in content.split("\n"):
        if re.match(r"^[A-Z]+-\d+", line.strip()):
            if started and current_entry["raw"]:
                result.append(current_entry)
            current_entry = {"raw": line, "details": []}
            started = True
        elif started:
            if line.strip():
                current_entry["details"].append(line.strip())
    
    if started and current_entry["raw"]:
        result.append(current_entry)
    
    return result


def scan_learning_entries():
    if not os.path.exists(LEARNINGS_DIR):
        return []
    
    patterns = ["LEARNINGS.md", "ERRORS.md", "FEATURE_REQUESTS.md"]
    entries = []
    for p in patterns:
        try:
            entries.extend(read_learning_file(p))
        except Exception as e:
            print("[AutoImprovement] Error reading {}: {}".format(p, str(e)))
    
    return entries


def detect_patterns(entries):
    categories = {
         "API_errors": ["api", "endpoint", "request", "response", "timeout"],
         "Indentation_corruption": ["indent", "bracket", "parse", "corrupt", "patch"],
         "Ollama_issues": ["omlx", "model", "chat", "api/chat"],
         "Flask_issues": ["flask", "server", "port", "debug", "reload"],
         "Cron_reliability": ["cron", "scheduled", "schedule", "timer"],
         "Telegram_delivery": ["telegram", "delivery", "channel", "message"],
    }
    
    pattern_counts = {}
    for entry in entries:
        text = (entry["raw"] + " " + " ".join(entry.get("details", []))).lower()
        for cat, keywords in categories.items():
            for kw in keywords:
                if kw in text:
                    if cat not in pattern_counts:
                        pattern_counts[cat] = {"count": 0, "examples": []}
                    pattern_counts[cat]["count"] += 1
                    if len(pattern_counts[cat]["examples"]) < 3:
                        raw_short = entry["raw"][:80] + ("..." if len(entry["raw"]) > 80 else "")
                        pattern_counts[cat]["examples"].append(raw_short)
                    break
    
    return {cat: data for cat, data in pattern_counts.items()}


def should_promote(category, count):
    if category.startswith("Indentation"):
        return count >= 2
    elif category.startswith("Ollama"):
        return count >= 2
    else:
        return count >= 3


def generate_agents_entry(category, data):
    title_map = {
         "API_errors": "# API Error Handling",
         "Indentation_corruption": "# File Corruption Prevention",
         "Ollama_issues": "# Ollama API Reliability",
         "Flask_issues": "# Flask Server Stability",
         "Cron_reliability": "# Cron Job Reliability",
         "Telegram_delivery": "# Telegram Delivery Resilience",
    }
    
    title = title_map.get(category, "# Auto-Discovered Pattern: " + category)
    now = datetime.now().strftime("%Y-%m-%d")
    
    entry = "\n## " + title + "\n"
    entry += "**Detected:** {} occurrences in .learnings/\n".format(data["count"])
    entry += "**Date:** {}\n\n".format(now)
    entry += "**Evidence (from .learnings/):**\n"
    for example in data["examples"]:
        entry += "- {}\n".format(example)
    
    entry += "\n**Recommended Action:** Review and add appropriate handling to relevant modules.\n"
    return entry


def write_to_agents_md(entries):
    if not os.path.exists(AGENTS_MD_PATH):
        print("[AutoImprovement] AGENTS.md missing at: " + AGENTS_MD_PATH)
        return False
    
     # Backup before writing
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = AGENTS_MD_PATH.replace(".md", "_" + ts + ".md")
    
    try:
        with open(AGENTS_MD_PATH, "r") as f:
            old_content = f.read()
        
        shutil_copy = __import__("shutil")
        shutil_copy.copy2(AGENTS_MD_PATH, backup_path)
        print("[AutoImprovement] Backed up AGENTS.md to: " + backup_path)
    except Exception as e:
        print("[AutoImprovement] Warning: backup failed - " + str(e))
    
     # Append entries
    with open(AGENTS_MD_PATH, "a") as f:
        for category, entry in entries:
            f.write("\n" + entry + "\n")
    
    print("[AutoImprovement] Appended {} pattern(s) to AGENTS.md".format(len(entries)))
    return True


def run_auto_improvement():
    print("[AutoImprovement] Scanning .learnings/ directory...")
    
    entries = scan_learning_entries()
    if not entries:
        print("[AutoImprovement] No entries in .learnings/. Done.")
        return {"status": "no_changes", "promoted_count": 0}
    
    print("[AutoImprovement] Processed {} learning entries".format(len(entries)))
    
    patterns = detect_patterns(entries)
    if not patterns:
        print("[AutoImprovement] No recurring patterns found.")
        return {"status": "no_changes", "promoted_count": 0}
    
    print("[AutoImprovement] Found {} pattern categories:".format(len(patterns)))
    promoted = []
    for category, data in patterns.items():
        met = should_promote(category, data["count"])
        mark = "PROMOTING" if met else "BELOW THRESHOLD"
        print("     {}: {}x [{}]".format(category, data["count"], mark))
        if met:
            entry = generate_agents_entry(category, data)
            promoted.append((category, entry))
    
    success = write_to_agents_md(promoted) if promoted else False
    
    result = {
         "status": "promoted" if (success and promoted) else ("no_promotion" if not promoted else "failed_write"),
         "promoted_count": len(promoted),
    }
    
    print("[AutoImprovement] Cycle complete: {}".format(result["status"]))
    return result


if __name__ == "__main__":
    run_auto_improvement()
