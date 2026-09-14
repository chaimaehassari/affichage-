-- Migration 003: Add PDF support
-- Adds page_count column to media table for PDF page tracking.

ALTER TABLE media ADD COLUMN IF NOT EXISTS page_count INTEGER DEFAULT NULL;

COMMENT ON COLUMN media.page_count IS 'Number of pages for PDF media, NULL for images/videos';

-- Extend the media_type check constraint to allow PDF
ALTER TABLE media DROP CONSTRAINT IF EXISTS chk_media_type;
ALTER TABLE media ADD CONSTRAINT chk_media_type CHECK ((media_type)::text = ANY (ARRAY['IMAGE','VIDEO','DOCUMENT','OTHER','PDF']::text[]));
