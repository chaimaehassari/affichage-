-- Migration 007: Screen groups as config targets
-- Guarantees DB-level uniqueness so a group membership can never contain
-- duplicate posts, and a post can never hold two configurations.

CREATE UNIQUE INDEX IF NOT EXISTS uq_group_post
    ON screen_group_posts (group_id, post_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_post_configuration
    ON post_configurations (post_id);

-- Accelerate group composition lookups (sites -> posts in a group).
CREATE INDEX IF NOT EXISTS idx_group_posts_post
    ON screen_group_posts (post_id);
CREATE INDEX IF NOT EXISTS idx_group_posts_group
    ON screen_group_posts (group_id);