-- Migration 005: Multi-media zone playlists
-- Adds duration_seconds to zone_media for per-media display duration.

ALTER TABLE zone_media ADD COLUMN IF NOT EXISTS duration_seconds INTEGER DEFAULT NULL;

COMMENT ON COLUMN zone_media.duration_seconds IS 'Display duration in seconds (NULL = default 10s for images, native for videos)';
