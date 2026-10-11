-- Rollback de la migration 028 : stockage média adressé par contenu.
--
-- Restaure la contrainte UNIQUE(sftp_path) et retire les index ajoutés.
--
-- ATTENTION : la contrainte UNIQUE ne peut être rétablie QUE s'il n'existe pas
-- deux lignes `media` partageant le même `sftp_path`. Comme l'Option B crée
-- précisément de tels liens, un rollback complet suppose :
--   1. avoir consolidé les doublons (script scripts/migrate_media_dedup.py --apply),
--      ou
--   2. restaurer le dump DB + la copie du dossier médias pris AVANT l'option B
--      (voir rapport Phase 2).
-- Le bloc ci-dessous n'ajoute la contrainte que si aucun doublon ne subsiste ;
-- sinon il ne fait rien (l'opérateur doit d'abord consolider/restaurer).

DROP INDEX IF EXISTS public.idx_media_client_checksum;
DROP INDEX IF EXISTS public.idx_media_sftp_path;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.media
        GROUP BY sftp_path
        HAVING count(*) > 1
    ) AND NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public'
          AND rel.relname = 'media'
          AND con.conname = 'media_sftp_path_key'
    ) THEN
        ALTER TABLE ONLY public.media ADD CONSTRAINT media_sftp_path_key UNIQUE (sftp_path);
    END IF;
END $$;
