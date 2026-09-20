-- Migration 015: Hiérarchie de gestion Super Admin / Admin / Clients
-- Ajoute un flag is_superadmin aux utilisateurs et une table admin_clients
-- pour lier chaque Admin classique aux Clients dont il est responsable.

-- 1. Ajouter le flag superadmin aux utilisateurs
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Table de liaison Admin ↔ Clients
CREATE TABLE IF NOT EXISTS admin_clients (
    admin_id      BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    client_code   VARCHAR(50) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (admin_id, client_code)
);

CREATE INDEX IF NOT EXISTS idx_admin_clients_admin ON admin_clients (admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_clients_client ON admin_clients (client_code);
