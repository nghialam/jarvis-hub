# Jarvis Hub 3.0 — AGENTS.md

## Project Structure
- `app.py` — Flask entry point, registers blueprints
- `api/` — Flask Blueprints (market, news, stocks, screener, research, portfolio, cms, intelligence, llm, auth, main, events)
- `core/` — Business logic (db.py, events.py, semantic.py, precompute_scheduler.py, market_service.py, etc.)
- `dashboard/` — Flask templates and static assets
- `data/jarvis.db` — SQLite database
- `config.yaml` — Application configuration

## Key Modules
- `core/events.py` — EventStore: event sourcing + audit trail for data pipeline
- `core/semantic.py` — MarketView + AggregateCache: precomputed technical indicators (MA/RSI/volume ratio)
- `core/precompute_scheduler.py` — PrecomputeScheduler: APScheduler-based daily precompute jobs
- `api/events.py` — Events API: query/filter/archive events via REST endpoints

## Code Conventions
- Flask Blueprint pattern for routes
- SQLite with sqlite3.Row factory (index access)
- EventStore stores raw sqlite3.Row, not dict (Event.from_row uses index access)
- APScheduler CronTrigger uses string format for hour: `hour="0,6,12,18"`
- Config loaded from config.yaml

## Running
```bash
cd /Users/nghialam/jarvis-hub
source venv/bin/activate
python app.py
```

## Deployment
- Local: Python virtualenv on Mac Mini
- Vercel: Flask app split into frontend static + serverless proxies → local tunnel
- Cron: Hermes Agent cron jobs for data collection + LLM briefing delivery
