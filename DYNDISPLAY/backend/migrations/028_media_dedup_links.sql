-- Migration 028 : stockage média adressé par contenu (Phase 2, Partie 3, Option B)
--
-- POURQUOI
--   Le stockage média historisait un FICHIER PHYSIQUE PAR UPLOAD : deux imports
--   du même contenu créaient deux fichiers distincts (deux `media.sftp_path`).
--   L'Option B retenue rend le stockage adressé par contenu DANS UN MÊME CLIENT :
--   un seul fichier physique par `(client_code, checksum)`, plusieurs lignes
--   `media` (liens portant un nom/dossier distinct) pouvant le référencer.
--   Plusieurs lignes partageant le même `sftp_path` exigent la levée de la
--   contrainte UNIQUE(sftp_path) : sans cela, la création d'un second lien est
--   rejetée par la base.
--
-- EFFETS
--   1. Supprime la contrainte UNIQUE `media_sftp_path_key` (idempotent).
--      La correspondance chemin -> client reste 1:1 (la dédup est intra-client),
--      donc `MediaService.media_id_for_path` (LIMIT 1) reste correct.
--   2. Recrée un index NON unique sur `sftp_path` : la contrainte UNIQUE servait
--      aussi d'index pour `media_id_for_path` et le comptage des références.
--   3. Ajoute un index `(client_code, checksum)` pour la recherche de
--      réutilisation à l'upload.
--
-- ROLLBACK : voir migrations/rollback/028_media_dedup_links_rollback.sql.
-- ATTENTION : rétablir UNIQUE(sftp_path) échoue s'il existe des doublons.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public'
          AND rel.relname = 'media'
          AND con.conname = 'media_sftp_path_key'
    ) THEN
        ALTER TABLE ONLY public.media DROP CONSTRAINT media_sftp_path_key;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_media_sftp_path
    ON public.media (sftp_path);

CREATE INDEX IF NOT EXISTS idx_media_client_checksum
    ON public.media (client_code, checksum)
    WHERE is_active;
