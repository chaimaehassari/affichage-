-- Migration 011 : sérialisation / activation des comptes clients.
-- Chaque compte client dispose de ses propres limites (sites / postes)
-- issues du code de sérialisation généré par l'app Android.
--
-- is_activated : TRUE par défaut pour ne rien casser pour les comptes
-- existants et les comptes internes. Seuls les comptes marqués
-- « client à activer » (requires_activation) seront créés non activés.

ALTER TABLE users ADD COLUMN IF NOT EXISTS sites_limit INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS posts_limit INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_activated BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS activation_code VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN users.sites_limit IS 'Nombre de sites autorisés (issu du code de sérialisation)';
COMMENT ON COLUMN users.posts_limit IS 'Nombre de postes autorisés (issu du code de sérialisation)';
COMMENT ON COLUMN users.is_activated IS 'Compte activé par code de sérialisation';
COMMENT ON COLUMN users.activation_code IS 'Dernier code de sérialisation utilisé';
COMMENT ON COLUMN users.activated_at IS 'Date d''activation du compte';