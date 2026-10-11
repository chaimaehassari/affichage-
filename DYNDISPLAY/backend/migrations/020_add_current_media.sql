-- Migration 020 : suivi du média actuellement diffusé par chaque poste.
--
-- Informations remontées par les players (Windows / Android) au travers du
-- heartbeat POST /posts/heartbeat (champ optionnel `current_media`).
--
-- Règles documentées :
--   * current_media_id / current_media_name / current_media_type décrivent le
--     média en cours de diffusion sur l'écran du poste.
--   * Si plusieurs zones sont actives simultanément, le player envoie le média
--     de la zone active dont le `zone_number` est le plus bas (application côté
--     player ; le backend se contente de stocker).
--   * current_media_started_at est fourni par le player en UTC et est stocké en
--     TIMESTAMPTZ (colonne `with time zone`).
--   * Le champ `current_media` du heartbeat reste optionnel : un heartbeat sans
--     média = rien à afficher pour l'instant ; l'état précédent est écrasé à
--     chaque heartbeat reçu (absence → colonnes remises à NULL).

ALTER TABLE posts
    ADD COLUMN IF NOT EXISTS current_media_id BIGINT,
    ADD COLUMN IF NOT EXISTS current_media_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS current_media_type VARCHAR(8),
    ADD COLUMN IF NOT EXISTS current_media_started_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_posts_current_media_id
    ON posts (current_media_id);