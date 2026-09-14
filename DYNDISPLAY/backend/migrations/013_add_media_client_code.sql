-- Migration 013 : rattachement des médias à un compte client (isolation des données).
-- Comme pour les sites, NULL = média global (déposé par l'administrateur).

ALTER TABLE media ADD COLUMN IF NOT EXISTS client_code VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_media_client_code ON media (client_code);

COMMENT ON COLUMN media.client_code IS 'N° client propriétaire du média (NULL = média global/admin)';