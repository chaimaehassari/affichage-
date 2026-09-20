-- Migration 018: Table Clients (multi-tenant)
-- Hiérarchie : SUPER ADMIN → ADMIN → CLIENT → UTILISATEURS
-- Crée la table `clients`, le client par défaut issu de general_settings,
-- et rattache sites / users au client via client_id (FK).
--
-- ATTENTION : cette migration est IRRÉVERSIBLE sans backup. À appliquer
-- sur une base maîtrisée (comporter les valeurs de general_settings actuelles).

-- 1. Table clients
CREATE TABLE IF NOT EXISTS clients (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code_client     VARCHAR(50)  NOT NULL UNIQUE,
    nom_client      VARCHAR(255) NOT NULL DEFAULT '',
    admin_id        BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    license_sites   INTEGER      NOT NULL DEFAULT 0,
    license_posts   INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clients_admin ON clients (admin_id);
CREATE INDEX IF NOT EXISTS idx_clients_code  ON clients (code_client);

-- 2. Client par défaut : initialisé depuis general_settings (code + licences)
INSERT INTO clients (code_client, nom_client, admin_id, license_sites, license_posts)
SELECT
    gs_code.setting_value                                      AS code_client,
    'Client par défaut'                                        AS nom_client,
    (SELECT user_id FROM users WHERE is_superadmin = TRUE LIMIT 1) AS admin_id,
    COALESCE((SELECT NULLIF(setting_value, '')::INT FROM general_settings WHERE setting_key = 'license_sites'), 0) AS license_sites,
    COALESCE((SELECT NULLIF(setting_value, '')::INT FROM general_settings WHERE setting_key = 'license_posts'), 0) AS license_posts
FROM general_settings gs_code
WHERE gs_code.setting_key = 'code_client'
  AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.code_client = gs_code.setting_value)
ON CONFLICT (code_client) DO NOTHING;

-- Cas limite : general_settings vide → créer un client par défaut de code 'DEFAULT'
INSERT INTO clients (code_client, nom_client, admin_id, license_sites, license_posts)
SELECT
    'DEFAULT',
    'Client par défaut',
    (SELECT user_id FROM users WHERE is_superadmin = TRUE LIMIT 1),
    0, 0
WHERE NOT EXISTS (SELECT 1 FROM clients);

-- 3. sites.client_id → clients (opération de scoping, colonne client_code conservée)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS client_id BIGINT REFERENCES clients(id) ON DELETE RESTRICT;

UPDATE sites s
SET client_id = c.id
FROM clients c
WHERE s.client_code = c.code_client
  AND s.client_id IS NULL;

UPDATE sites s
SET client_id = (SELECT id FROM clients ORDER BY id LIMIT 1)
WHERE s.client_id IS NULL;

ALTER TABLE sites ALTER COLUMN client_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sites_client_id ON sites (client_id);

-- 4. users.client_id → clients (nullable : users hors client, ni Admins, ni SuperAdmin)
ALTER TABLE users ADD COLUMN IF NOT EXISTS client_id BIGINT REFERENCES clients(id) ON DELETE SET NULL;

UPDATE users u
SET client_id = c.id
FROM clients c
WHERE u.user_code = c.code_client
  AND u.client_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_client_id ON users (client_id);