-- Migration 012 : affiliation des sites à un compte client (isolation des données).
-- Chaque site est rattaché au n° client qui le gère (NULL = données globales/admin).
-- Les postes héritent du rattachement via leur site (posts.site_id -> sites.site_id).

ALTER TABLE sites ADD COLUMN IF NOT EXISTS client_code VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_sites_client_code ON sites (client_code);

COMMENT ON COLUMN sites.client_code IS 'N° client propriétaire du site (NULL = site global/admin)';