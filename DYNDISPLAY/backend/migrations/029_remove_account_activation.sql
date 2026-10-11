-- Migration 029 : retrait du mécanisme d'activation des comptes / appareils.
--
-- Supprime l'ensemble des colonnes ajoutées par les migrations 011
-- (sérialisation des comptes clients) et 016 (activation par code + liaison
-- appareil). Le mécanisme d'activation par code HMAC/base32 (ACTV) est
-- retiré du backend ; les quotas de licences restent portés par
-- `clients.license_sites` / `clients.license_posts` (migration 018 / 025).
--
-- Idempotent : chaque colonne / index n'est supprimé que s'il existe encore,
-- de sorte que cette migration est applicable une seule fois sans erreur.

ALTER TABLE users DROP COLUMN IF EXISTS sites_limit;
ALTER TABLE users DROP COLUMN IF EXISTS posts_limit;
ALTER TABLE users DROP COLUMN IF EXISTS is_activated;
ALTER TABLE users DROP COLUMN IF EXISTS activation_code;
ALTER TABLE users DROP COLUMN IF EXISTS activated_at;
ALTER TABLE users DROP COLUMN IF EXISTS account_code;
ALTER TABLE users DROP COLUMN IF EXISTS requires_activation;
ALTER TABLE users DROP COLUMN IF EXISTS authorized_device_id;

DROP INDEX IF EXISTS idx_users_requires_activation;
DROP INDEX IF EXISTS idx_users_account_code;