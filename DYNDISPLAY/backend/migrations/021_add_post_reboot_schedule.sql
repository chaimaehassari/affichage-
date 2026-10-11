-- Migration 021 : programmation du redémarrage automatique quotidien par poste.
--
-- Champs portés par la table `posts` (un par poste) :
--   * reboot_enabled  : active/désactive le redémarrage automatique (BOOLEAN).
--   * reboot_time     : heure locale du redémarrage, format TIME "HH:MM".
--   * next_reboot_at  : prochaine échéance calculée (TIMESTAMPTZ, UTC),
--                       recalculée à chaque écriture ET en lecture si périmée
--                       (échéance dépassée → jour suivant).
--
-- Règles :
--   * « Désactiver » (reboot_enabled = FALSE) n'efface pas reboot_time :
--     l'heure reste mémorisée pour une future réactivation.
--   * Désactivation → next_reboot_at remis à NULL.
--   * Le fuseau de référence est celui de l'application (APP_TIMEZONE) :
--     reboot_time est exprimé dans ce fuseau, next_reboot_at est stocké en UTC
--     via la conversion to_utc().

ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS reboot_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS reboot_time TIME,
    ADD COLUMN IF NOT EXISTS next_reboot_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_posts_next_reboot_at
    ON posts (next_reboot_at)
    WHERE reboot_enabled = TRUE;