-- Migration 024 : plus aucun Admin classique sans périmètre.
--
-- Problème constaté :
--   depuis la migration 019, `admin_clients` est l'UNIQUE source de vérité du
--   périmètre d'un Admin classique (`scope.admin_client_codes`). Or la
--   création d'un admin ne renseignait `admin_clients` que si l'appelant
--   cochait explicitement des clients dans le formulaire.
--
--   Résultat : un Admin créé sans cocher de client se retrouvait avec
--   `users.client_id` renseigné (repli sur le client par défaut) mais AUCUNE
--   ligne dans `admin_clients`. Cet admin :
--     * ne voyait aucun client (GET /clients vide) ;
--     * ne pouvait créer aucun utilisateur, `POST /users` renvoyant 400
--       « Aucun client ne vous est affecté : impossible de rattacher un
--       utilisateur. » ;
--     * ne pouvait rien piloter du tout : un compte mort.
--
-- Correctif :
--   1) `UserService._resolve_admin_client_codes()` applique désormais ce
--      repli à la création ET à la modification d'un admin (cf.
--      user_service.py) : à défaut de sélection, l'admin est rattaché au
--      client déjà résolu pour lui.
--   2) Cette migration rattrape les comptes déjà concernés.
--
-- Choix de périmètre : on rattache l'admin à SON propre client
-- (`users.client_id`, toujours renseigné et NOT NULL depuis 019), jamais à
-- l'ensemble des clients. Un admin sans périmètre ne peut RIEN voir ; lui
-- donner exactement UN client ne peut qu'élargir ce qu'il voyait déjà de
-- lui-même, et reste très loin du périmètre global du Super Admin
-- (`is_superadmin = TRUE`, exclu ci-dessous). L'isolation est préservée.

INSERT INTO admin_clients (admin_id, client_code)
SELECT u.user_id, c.code_client
FROM users u
JOIN profiles p ON p.profile_id = u.profile_id
JOIN clients c ON c.id = u.client_id
WHERE p.name = 'Administrateur'
  AND u.is_superadmin = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM admin_clients ac WHERE ac.admin_id = u.user_id
  )
ON CONFLICT (admin_id, client_code) DO NOTHING;
