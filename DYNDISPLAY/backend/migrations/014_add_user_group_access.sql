-- 014: Table de liaison utilisateurs <-> groupes d'écrans
-- Suit le même pattern que user_zone_access (user_zone_access_id, user_id, zone, is_allowed)

CREATE TABLE IF NOT EXISTS user_group_access (
    user_group_access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    group_id     BIGINT NOT NULL REFERENCES screen_groups(group_id) ON DELETE CASCADE,
    is_allowed   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_group_access
    ON user_group_access (user_id, group_id);
