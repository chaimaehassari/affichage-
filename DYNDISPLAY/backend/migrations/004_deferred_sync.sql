-- Migration 004: Deferred sync scheduling
-- Adds scheduled_at to sync_jobs for deferred sync.

ALTER TABLE sync_jobs ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN sync_jobs.scheduled_at IS 'Scheduled execution time for deferred sync, NULL for immediate';
