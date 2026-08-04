#!/usr/bin/env python3
"""research_pipeline.py — Ingest a J-lens article, extract summary/ideas/backlog via Ollama.

Usage:
    # From URL (scrapes page if requests works)
    python research_pipeline.py --url https://example.com/article-slug

    # From raw text / file
    python research_pipeline.py --text "Long article text here..."
    python research_pipeline.py --file path/to/article.md

    # Dry run (prints extracted JSON without DB insert)
    python research_pipeline.py --url URL --dry-run

Output:
    Extracted summary, implementable ideas, and task backlog are stored in
    the `market_intelligence` table under a new row with status "Research Processed".
"""

import argparse
import json
import os
import sys
from datetime import datetime

# ── local deps ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from core.ollama_client import ollama_call, ollama_parse_json


# ── Prompt templates ─────────────────────────────────────────────────
SUMMARY_PROMPT = """You are a Vietnamese financial market analyst. Extract key insights from the following article.

Return strictly valid JSON — no markdown fences, no extra text.
{
  "summary": "<120-200 word summary in Vietnamese>",
  "key_points": ["point 1", "point 2", "..."],
  "sentiment": "bullish | bearish | neutral",
  "tickers_mentioned": ["VIC", "SSI", ...],
  "sector_focus": "<main sector discussed>"
}

Article:
{article}
"""

IDEAS_PROMPT = """You are a product/strategy assistant for a Vietnamese financial market intelligence platform. From the article below, generate actionable implementation ideas and a task backlog.

Return strictly valid JSON — no markdown fences, no extra text.
{
  "ideas": [
    {
      "title": "<Idea title>",
      "description": "<What to build or do>",
      "effort": "low | medium | high",
      "priority": "high | medium | low",
      "category": "data-source | dashboard | notification | analysis | automation"
    }
  ],
  "backlog": [
    {
      "title": "<Task title>",
      "description": "<Description>",
      "tags": ["tag1", "tag2"],
      "depends_on": "parent task title or null"
    }
  ]
}

Article:
{article}
"""


# ── Helpers ───────────────────────────────────────────────────────────
def fetch_article(url: str) -> str:
    """Fetch article content from URL via requests (simple text extraction)."""
    import requests

    resp = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 Jarvis-ResearchPipeline/1.0"
        },
        timeout=30,
    )
    resp.raise_for_status()

    # Strip HTML tags — try BeautifulSoup first, fall back to regex
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove script/style
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except ImportError:
        import re

        text = re.sub(r"<[^>]+>", "", resp.text)
        text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def truncate_for_llm(text: str, max_chars: int = 12000) -> str:
    """Truncate article to fit within LLM context limits."""
    if len(text) <= max_chars:
        return text
    # Keep header + first/last chunks for context
    half = max_chars // 2
    return text[:half] + "\n\n...[content truncated, {} chars omitted]...\n\n".format(len(text) - max_chars) + text[-half:]


def insert_to_db(summary: dict, ideas: dict, run_date: str = None):
    """Insert extracted data into the market_intelligence table."""
    import sqlite3
    from pathlib import Path

    db_path = Path(__file__).parent / "knowledge" / "jarvis.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    articles_json = json.dumps(
        {"summary": summary, "ideas": ideas},
        ensure_ascii=False,
        indent=2,
    )

    run_period = "research"  # one-off research item, not daily/weekly brief
    status = "Research Processed"

    cursor.execute(
        """INSERT INTO market_intelligence (run_date, run_period, articles_json, market_brief, status)
           VALUES (?, ?, ?, ?, ?)""",
        (run_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S"), run_period, articles_json, "", status),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


# ── Main pipeline ─────────────────────────────────────────────────────
def run_pipeline(article_text: str, dry_run: bool = False):
    """Run the full research analysis pipeline."""
    # Truncate for context limits
    text = truncate_for_llm(article_text)

    print("[pipeline] Phase 1/2: Extracting summary & insights...")
    summary_result = ollama_parse_json(SUMMARY_PROMPT.replace("{article}", text), timeout=180)

    if not summary_result:
        print("[pipeline] ERROR: Failed to get summary from LLM. Check Ollama status.")
        return None

    # Pretty-print for readability
    print(json.dumps(summary_result, ensure_ascii=False, indent=2))

    if dry_run:
        print("\n[pipeline] Dry run — skipping ideas extraction & DB insert.\n")
        return summary_result

    print("\n[pipeline] Phase 2/2: Generating ideas & backlog...")
    ideas_result = ollama_parse_json(IDEAS_PROMPT.replace("{article}", text), timeout=180)

    if not ideas_result:
        print("[pipeline] WARNING: Failed to get ideas/backlog from LLM (summary still saved).")
        ideas_result = {"ideas": [], "backlog": []}

    # Pretty-print ideas
    print(json.dumps(ideas_result, ensure_ascii=False, indent=2))

    if not dry_run:
        row_id = insert_to_db(summary_result, ideas_result)
        print(f"\n[pipeline] Done! Inserted into market_intelligence (id={row_id})")
    else:
        row_id = None

    return {"summary": summary_result, "ideas": ideas_result}


# ── CLI entrypoint ────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Research pipeline: extract summary/ideas/backlog from an article.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", type=str, help="URL of the article to process")
    group.add_argument("--text", type=str, help="Raw article text (paste directly)")
    group.add_argument("--file", type=str, help="Path to a local article file (.md/.txt)")
    parser.add_argument("--dry-run", action="store_true", help="Only extract, skip DB insert")

    args = parser.parse_args()

    # Get article text
    if args.url:
        print(f"[pipeline] Fetching article from URL: {args.url}")
        article_text = fetch_article(args.url)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            article_text = f.read()
    else:
        article_text = args.text

    if not article_text or len(article_text.strip()) < 50:
        print("[pipeline] ERROR: Article text is too short or empty. Ensure source provides substantial content.")
        sys.exit(1)

    print(f"[pipeline] Article loaded: {len(article_text)} chars\n")

    # Run pipeline
    result = run_pipeline(article_text, dry_run=args.dry_run)

    if not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
