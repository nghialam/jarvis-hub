"""
market_intelligence/__init__.py — Market Intelligence Agent Pipeline Orchestrator

Orchestrates the 5-stage pipeline:
    Stage 1: Ingestion   → RSS/web scrapers fetch last 6h of articles
    Stage 2: Parsing     → HTML stripping, boilerplate removal, text cleaning
    Stage 3: Analysis    → LLM generates summary + sentiment per article (Analyst Agent)
    Stage 4: Synthesis   → LLM creates Market Brief from all summaries (Strategist Agent)
    Stage 5: Delivery    → Persist to DB, trigger notifications (Telegram/dashboard)

Usage:
    from core.market_intelligence import run_pipeline
    result = run_pipeline()
"""

import json
import logging
from datetime import datetime

log = logging.getLogger(__name__)


def determine_period():
    """Determine the 6-hour period based on current hour."""
    hour = datetime.utcnow().hour
    if 5 <= hour < 11:
        return "morning"
    elif 11 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 23:
        return "evening"
    else:
        return "night"


def run_pipeline():
    """Execute the complete Market Intelligence pipeline.

    Returns:
        dict with status, run_id, article_count, period, elapsed_seconds
    """
    from core.market_intelligence import ingestion, parsing, analyst, synthesizer, delivery

    start_time = datetime.utcnow()
    period = determine_period()

    try:
        # Stage 1: Ingestion
        log.info("[MI] Stage 1: Ingesting articles...")
        raw_articles = ingestion.fetch_articles(hours_back=6)
        log.info(f"[MI] Ingested {len(raw_articles)} articles")

        if not raw_articles:
            log.warning("[MI] No articles found in last 6 hours")
            return {"status": "no_articles", "article_count": 0}

        # Stage 2: Parsing
        log.info("[MI] Stage 2: Parsing and cleaning articles...")
        cleaned_articles = [parsing.clean_article(a) for a in raw_articles]

        # Stage 3: Analysis
        log.info(f"[MI] Stage 3: Analyzing {len(cleaned_articles)} articles with LLM...")
        analyzed_articles = analyst.analyze_articles(cleaned_articles)

        # Stage 4: Synthesis
        log.info("[MI] Stage 4: Synthesizing Market Brief...")
        market_brief = synthesizer.synthesize_market_brief(analyzed_articles)

        # Stage 5: Delivery
        log.info("[MI] Stage 5: Delivering to DB and notifications...")
        articles_json = json.dumps(analyzed_articles, ensure_ascii=False)
        run_id = delivery.save_to_db(
            run_date=datetime.utcnow().strftime("%Y-%m-%d"),
            run_period=period,
            articles_json=articles_json,
            market_brief=market_brief,
        )

        # Trigger notifications
        sentiment_dist = delivery.get_sentiment_distribution()
        delivery.trigger_notifications(run_id, market_brief, analyzed_articles)

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        log.info(f"[MI] Pipeline complete in {elapsed:.1f}s — Run ID: {run_id}")

        return {
            "status": "complete",
            "run_id": run_id,
            "article_count": len(analyzed_articles),
            "period": period,
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        log.error(f"[MI] Pipeline failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
