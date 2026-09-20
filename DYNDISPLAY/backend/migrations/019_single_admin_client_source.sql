-- Migration 019: source unique Admin↔Client + users.client_id obligatoire
-- =
-- 1) admin_clients devient l'UNIQUE source de vérité du lien Admin↔Client
--    (la colonne clients.admin_id, 018, pouvait diverger de la jointure).
-- 2) users.client_id devient obligatoire : plus aucun compte "hors client"
--    (fermeture du repli « pas de client_id → quota global » à l'activation).

-- 1a. Repli du lien vers admin_clients AVANT suppression de la colonne :
--     garantit que les clients créés avec un admin_id (ex: le « Client par
--     défaut », admin_id = Super Admin) gardent une affectation explicite.
INSERT INTO admin_clients (admin_id, client_code)
SELECT admin_id, code_client
FROM clients
WHERE admin_id IS NOT NULL
ON CONFLICT (admin_id, client_code) DO NOTHING;

-- 1b. Suppression de la colonne dépréciée.
ALTER TABLE clients DROP COLUMN IF EXISTS admin_id;
DROP INDEX IF EXISTS idx_clients_admin;

-- 2a. Rattachement EXPLICITE des comptes existants sans client_id
--     (y compris Super Admin, Admins et comptes créés avant 019) au
--     client par défaut (premier client). Aucun compte ne reste « sans client ».
UPDATE users u
SET client_id = (SELECT id FROM clients ORDER BY id LIMIT 1)
WHERE u.client_id IS NULL;

-- 2b. FK renforcée + NOT NULL : la suppression de client impose de supprimer
--     d'abord ses comptes (RESTRICT), et tout nouvel utilisateur DOIT avoir
--     un client rattaché.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_client_id_fkey;
ALTER TABLE users
    ADD CONSTRAINT users_client_id_fkey
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT;
ALTER TABLE users ALTER COLUMN client_id SET NOT NULL;