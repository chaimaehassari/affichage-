-- Migration 016 : activation par compte et liaison à un appareil.
--
-- account_code            : code d'activation du compte (généré à la création).
-- requires_activation     : le compte doit être activé par un code d'activation
--                           (HMAC/base32) avant sa première connexion.
-- authorized_device_id    : identifiant de l'appareil auquel le compte est lié.
--                           NULL = non lié ; un compte lié à un autre appareil
--                           est bloqué à la connexion (sauf admin suprême).
--
-- Rétrocompatibilité : tous les comptes existants sont laissés actifs
-- (requires_activation = FALSE) pour ne pas bloquer les comptes en production.
-- Seuls les comptes créés après cette migration (POST /users) demanderont
-- une activation avant la première connexion.

ALTER TABLE users ADD COLUMN IF NOT EXISTS account_code VARCHAR(16) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS requires_activation BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS authorized_device_id VARCHAR(64);

-- Les comptes déjà présents restent utilisables sans activation.
UPDATE users SET requires_activation = FALSE, activated_at = COALESCE(activated_at, NOW())
WHERE requires_activation IS TRUE;

CREATE INDEX IF NOT EXISTS idx_users_requires_activation ON users (requires_activation);
CREATE INDEX IF NOT EXISTS idx_users_account_code ON users (account_code);

COMMENT ON COLUMN users.account_code IS 'Code d''activation du compte (pour la première connexion / changement d''appareil)';
COMMENT ON COLUMN users.requires_activation IS 'Le compte doit activer un appareil avant sa première connexion';
COMMENT ON COLUMN users.activated_at IS 'Date de la première activation du compte (nullable, NULL = jamais activé)';
COMMENT ON COLUMN users.authorized_device_id IS 'Appareil lié au compte (un compte = un appareil actif)';