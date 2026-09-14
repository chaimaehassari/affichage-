-- Migration 008: Per-media sync state tracking
-- Tracks sync status of each media file per post, enabling media-level sync control.

CREATE TABLE IF NOT EXISTS media_sync_state (
    media_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    synced_at TIMESTAMPTZ DEFAULT NULL,
    status TEXT DEFAULT 'NOT_SYNCED' CHECK (status IN ('SYNCED', 'NOT_SYNCED', 'SYNCING', 'FAILED')),
    PRIMARY KEY (media_id, post_id),
    FOREIGN KEY (media_id) REFERENCES media(media_id) ON DELETE CASCADE,
    FOREIGN KEY (post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mss_post ON media_sync_state (post_id);
CREATE INDEX IF NOT EXISTS idx_mss_media ON media_sync_state (media_id);
