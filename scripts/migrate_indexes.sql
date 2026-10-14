-- =============================================================================
-- Jarvis Hub Database Index Migration
-- Target: jarvis_hub_memory (PostgreSQL) + jarvis.db (SQLite)
-- Created: 2026-10-14
-- Purpose: Speed up common query patterns with targeted indexes
-- =============================================================================

-- ---------------------------------------------------------------------------
-- PostgreSQL: jarvis_hub_memory
-- Notes:
--   - idx_memdocs_collection already exists; we skip it in the executor.
--   - signals/articles tables may not exist yet — guarded by DO $$ blocks.
-- ---------------------------------------------------------------------------

-- memdocs: metadata JSONB key lookups (peer_id filtering)
CREATE INDEX IF NOT EXISTS idx_memdocs_peer
    ON public.memdocs ((metadata->>'peer_id'));

-- sessions: peer + time range queries (daily session overviews)
CREATE INDEX IF NOT EXISTS idx_sessions_peer_created
    ON public.sessions (peer_id, created_at DESC);

-- signals: timestamp-ordered retrieval (only if the table exists)
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'signals'
  ) THEN
    CREATE INDEX IF NOT EXISTS idx_signals_timestamp
      ON public.signals (created_at DESC);
  END IF;
END $$;

-- articles: category filtering (only if the table exists)
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'articles'
  ) THEN
    CREATE INDEX IF NOT EXISTS idx_articles_category
      ON public.articles (category);
  END IF;
END $$;


-- ---------------------------------------------------------------------------
-- SQLite: jarvis.db (data/jarvis.db)
-- SQLite supports "CREATE INDEX IF NOT EXISTS" natively.
-- ---------------------------------------------------------------------------

-- articles: category filtering (if table is added later)
CREATE INDEX IF NOT EXISTS idx_articles_category
    ON articles(category);

-- activity_log: timestamp-ordered query (replaces original "activities" reference)
-- The actual table is "activity_log" with a "timestamp" column
CREATE INDEX IF NOT EXISTS idx_activities_timestamp
    ON activity_log(timestamp DESC);

-- daily_snapshots: date-range queries for report generation
CREATE INDEX IF NOT EXISTS idx_daily_snapshot_date
    ON daily_snapshots(date);

-- knowledge: tags lookup (replaces original "category" — schema uses "tags")
CREATE INDEX IF NOT EXISTS idx_knowledge_category
    ON knowledge(tags);
