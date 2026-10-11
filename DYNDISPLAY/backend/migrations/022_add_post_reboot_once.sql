-- Migration 022 : redémarrage ponctuel (one-shot) par poste.
--
-- Champ porté par la table `posts` (un par poste) :
--   * reboot_once_at : instant unique de redémarrage (TIMESTAMPTZ, UTC),
--                      NULL = aucun redémarrage ponctuel programmé.
--
-- À ne PAS confondre avec le redémarrage récurrent de la migration 021 :
--   * reboot_time     : heure quotidienne ( colonne TIME, récurrence ) ;
--   * next_reboot_at  : prochaine échéance calculée du récurrent ;
--   * reboot_once_at  : UN instant, consommé puis purgé (voir
--                       app/services/reboot_schedule_service.py).
-- Les deux mécanismes sont indépendants et cohabitent sur un même poste.
--
-- Règles :
--   * Une valeur dans le passé est REJETÉE à l'écriture (422) : pas de
--     rattrapage. Si la box est éteinte à l'instant programmé, la demande est
--     perdue — c'est le comportement voulu pour un one-shot.
--   * Purge par déduction serveur, jamais par confirmation du player :
--     à chaque lecture de la configuration, si now() >= reboot_once_at +
--     marge de grâce, le champ repasse à NULL (même modèle que
--     refresh_next_reboot_at pour le récurrent).
--   * Désactivation du récurrent (reboot_enabled = FALSE) NE touche pas
--     reboot_once_at, et l'inverse.

ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS reboot_once_at TIMESTAMPTZ;

-- Index partiel : seuls les postes réellement armés sont indexés, la purge
-- balaie ce sous-ensemble.
CREATE INDEX IF NOT EXISTS idx_posts_reboot_once_at
    ON posts (reboot_once_at)
    WHERE reboot_once_at IS NOT NULL;
