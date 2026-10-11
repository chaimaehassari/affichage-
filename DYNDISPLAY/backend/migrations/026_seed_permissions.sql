-- Migration 026 : le catalogue des permissions EXISTS enfin.
--
-- Problème constaté :
--   `000_baseline.sql` crée la TABLE `permissions`, mais AUCUN script du dépôt
--   n'inscrit ses lignes. Les codes étaient seulement *référencés* :
--     * backend  : `require_permission("<code>")` sur ~58 routes
--     * frontend : `p.code === 'user_list'`… dans le formulaire de compte
--   Sur une base neuve (donc sur TOUTE installation issue de install.bat),
--   `SELECT count(*) FROM permissions` renvoyait 0.
--
--   Conséquences, toutes silencieuses :
--     * GET /api/v1/users/permissions renvoyait `[]` (HTTP 200), donc
--       `UserForm` calculait `userPerms`, `sitePerms` et `menuPerms` vides :
--       les sections « Gestion utilisateurs » et « Gestion sites / postes »
--       s'affichaient avec leur titre mais AUCUNE case à cocher. Impossible
--       de donner la moindre permission à un compte — sans le moindre
--       message d'erreur, puisque la requête avait réussi ;
--     * tout compte NON Administrateur (`is_admin_user` court-circuite les
--       `require_permission`, un Administrateur n'en a pas besoin) se
--       retrouvait sans aucune permission : menus vides et 403 sur
--       l'ensemble des routes.
--
-- Correctif :
--   on inscrit le catalogue des 15 permissions réellement utilisées par le
--   code. `ON CONFLICT (code) DO NOTHING` : la migration est idempotente et
--   respecte un catalogue déjà personnalisé (désactivé ou renommé par
--   l'exploitant), elle ne l'écrase pas.
--
-- Choix de périmètre :
--   AUCUNE permission n'est accordée ici. `user_permissions` reste vide : ce
--   sont les cases du formulaire — désormais alimentées — qui l'alimentent.
--   Inscrire le catalogue ne donne aucun accès ; seul un Administrateur peut
--   ensuite Distribuer des droits, explicitement, comme il le doit.

INSERT INTO permissions (code, name, description) VALUES
    -- Menus (visibility de la navigation + acces aux ecrans associes)
    ('menu_conception', 'Conception',
        'Acces aux modeles et a la conception des zones'),
    ('menu_sync', 'Synchronisation',
        'Acces a la synchronisation des players'),
    ('menu_media', 'Medias',
        'Acces a la mediatheque et a l import des fichiers'),
    ('menu_config', 'Configuration',
        'Acces a la supervision et a la configuration des postes'),

    -- Gestion des utilisateurs
    ('user_list', 'Liste des utilisateurs',
        'Consulter la liste des comptes'),
    ('user_create', 'Creation d''utilisateur',
        'Creer un compte'),
    ('user_update', 'Modification d''utilisateur',
        'Modifier un compte existant'),
    ('user_delete', 'Suppression d''utilisateur',
        'Supprimer un compte'),

    -- Gestion des sites
    ('list_sites_posts', 'Liste des sites / postes',
        'Consulter les sites et les postes'),
    ('create_site', 'Creation site',
        'Creer un site'),
    ('update_site', 'Modification site',
        'Modifier un site'),
    ('delete_site', 'Suppression site',
        'Supprimer un site'),

    -- Gestion des postes
    ('create_post', 'Creation poste',
        'Creer un poste dans un site'),
    ('update_post', 'Modification poste',
        'Modifier un poste'),
    ('delete_post', 'Suppression poste',
        'Supprimer un poste')
ON CONFLICT (code) DO NOTHING;
