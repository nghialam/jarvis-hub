#!/usr/bin/env python3
"""
migrate_memory.py — Consolidate all existing memory sources into the new SQLite store.

Runs once to populate jarvis.db from:
1. ~/.hermes/MEMORY.md (original structured memory)
2. System prompt compacted sections (recovered facts, learnings, user profile)
3. Any existing daily log files with useful info
"""

import sys
import os
sys.path.insert(0, "/Users/nghialam/jarvis-hub/scripts")

from memory_db import MemoryDB


def migrate():
    db = MemoryDB("/Users/nghialam/jarvis-hub/knowledge/jarvis.db")

    # ─── 1. Existing MEMORY.md entries (structured) ──────────────────
    
    facts = [
        ("macos", "Agent runs on Mac Mini M4 Pro with Tail-scale LAN, Hermes + qwen3.6 via Ollama MLX"),
        ("architecture", "Gateway architecture: local Ollama gateway at port 8000, no cloud dependencies for core capabilities"),
        ("models", "Main agent uses qwen3.6:35b-a3b-mxfp8 (~37GB), reserved for main agent + coding subagent"),
        ("models", "gemma4:e4b reserved ONLY for lightweight fast tasks where speed > depth"),
        ("models", "vision subagent (REMOVED, ~7.8GB) handles image/chart analysis only"),
        ("memory", "MEMORY.md compacted 2026-05-27 to 16 lines, max 2200 char system prompt limit active"),
        ("rss", "14 RSS sources → 35 unique articles per session (6:1 dedup ratio on most feeds)")
    ]

    lessons = [
        ("ollama", "CRITICAL: NEVER use ThreadPoolExecutor(max_workers>1) for /v1/chat/completions calls — causes timeouts with qwen3.6 (~37GB model runs sequentially). Retry up to 3x with 10s delay."),
        ("html", "CRITICAL: NEVER use .lstrip('<tag>') for HTML tags — strips characters recursively. Use .find()+slicing or .removeprefix()"),
        ("prompting", "Multiple patches corrupt HTML/JS bracket balance. Strategy: backup and rewrite entire script block; binary search+eval() locates exact parse failure point in O(log n) steps"),
        ("prompting", "Qwen3.6 returns EMPTY responses on pure Vietnamese prompts — must use English instructions with 'VIETNAMESE OUTPUT ONLY' directive"),
        ("memory", "Memory compacted 2026-05-27 resulted in MEMORY.md becoming 0 bytes — all knowledge lost except what's in system prompt compaction"),
    ]

    decisions = [
        ("architecture", "Skip Open WebUI, use qwen3.6 local only for Jarvis Hub deployment"),
        ("rss", "Global news fetched separately at 21:30, not inline with VN news (avoids timeout/bottleneck)"),
        ("rss", "Limit to 3 items per section max, 18 total across all sections for manageability"),
        ("rss", "Sources listed by name only in Telegram output — inline links don't render well"),
        ("memory", "Weekly memory compact runs Sunday 9:30 AM, archives daily files older than 14 days"),
    ]

    errors = [
        ("rss", "bedtime_mode prompt corrupted during patching — Vietnamese diacritics mangled (dòng→dong, không→khong), causing empty LLM responses"),
        ("rss", "URL query params not stripped from RSS → truncated/incomplete links in LLM output — fixed by splitting at '?'"),
    ]

    pending = [
        ("architecture", "Unified morning brief refactoring (merge VN + INTL into single 35-article dedupe pipeline)"),
        ("rss", "Investigate expanding international news sources beyond current 7"),
        ("memory", "Build automated memory compact that runs nightly on jarvis.db with proper archiving"),
    ]

    for entry_type, items in [("fact", facts), ("lesson", lessons), ("decision", decisions), ("error", errors), ("pending", pending)]:
        for item in items:
            db.add_memory(entry_type, item[0], item[1])

    # ─── 2. Additional knowledge from current system prompt context ──
    
    extra = [
        ("fact", "ollama", "qwen3.6:35b-a3b-mxfp8 requires ~37GB RAM — parallel calls timeout"),
        ("fact", "trading", "VN stock watchlist covers 16 symbols: VCB VIC VPB HPG VNM FPT TCB SSI HDB STB ACB VIB MSN POW GVR VHM"),
        ("fact", "trading", "vn_stock_realtime.py monitors TradingView HOSE for real-time price data on watchlist"),
        ("fact", "learning", "60-lesson trading syllabus across 5 phases (foundation, technical, fundamental, strategy, global markets)"),
        ("decision", "cron", "Cron jobs run bare script filenames (no python3 prefix) to ensure auto-detection works"),
        ("pending", "memory", "Implement SQLite-based memory with FTS5 search replacing flat-file MEMORY.md"),
    ]

    for entry_type, category, content in extra:
        db.add_memory(entry_type, category, content)

    # ─── 3. Verify migration ─────────────────────────────────────────
    
    summary = db.get_summary()
    print(f"✅ Migration complete!\n")
    print(f"Total active memories: {summary['total_active']}")
    for mem_type, stats in summary["by_type"].items():
        emoji = {"fact":"📦","lesson":"💡","decision":"🔀","error":"🚨","pending":"⏳"}[mem_type]
        print(f"   {emoji} {mem_type}: {stats['count']} entries")

    db.close()


if __name__ == "__main__":
    migrate()
