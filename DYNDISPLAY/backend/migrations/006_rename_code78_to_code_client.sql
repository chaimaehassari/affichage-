-- Migration 006 : renommer code78 -> code_client
-- code78 étant stocké dans la table de configuration clé/valeur general_settings,
-- le "rename column" correspond à la mise à jour des clés de configuration.
-- (Il n'existe pas de vraie colonne nommée code78; voir la note ci-dessous.)

-- Clé de code client
UPDATE general_settings
SET setting_key = 'code_client',
    description  = 'Code d''accès client'
WHERE setting_key = 'code78';

-- Clé métadonnée "code78 a été modifié"
UPDATE general_settings
SET setting_key = 'code_client_changed'
WHERE setting_key = 'code78_changed';