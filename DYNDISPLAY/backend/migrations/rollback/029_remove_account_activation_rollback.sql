-- Rollback de la migration 029 : ré-ajout du mécanisme d'activation des comptes.
--
-- ⚠️  STRUCTURE SEULE — LES DONNÉES NE SONT PAS RESTAURÉES.
--
-- Cette migration 029 est DESTRUCTIVE : elle supprime des colonnes entières
-- (`account_code`, `authorized_device_id`, `activated_at`, etc.). Rejouer ce
-- rollback recrée les colonnes VIDES ; il ne peut rendre ni les codes
-- d'activation, ni les appareils liés, ni les dates d'activation qui
-- existaient avant l'application de 029.
--
--   >>> La restauration des DONNÉES passe UNIQUEMENT par le dump PostgreSQL
--   >>> pris AVANT l'application de 029 (voir la procédure de déploiement) :
--   >>>   pg_restore -d <base> <dump_prit_avant_029>.dump
--   >>> (éventuellement avec --table=users ou --data-only selon le besoin).
--
-- Rollback complet = ce fichier (structure) PUIS restauration du dump (données).
--
-- Idempotent : chaque colonne / index / contrainte n'est recréé que s'il est
-- absent, de sorte que ce script peut être rejoué sans erreur.

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS sites_limit integer;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS posts_limit integer;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_activated boolean DEFAULT true NOT NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activation_code character varying(255);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS activated_at timestamp with time zone;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS account_code character varying(16);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS requires_activation boolean DEFAULT true NOT NULL;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS authorized_device_id character varying(64);

-- La contrainte d'unicité de account_code a disparu avec la colonne : on la
-- recrée seulement si elle est absente (les valeurs recréées sont NULL, que
-- UNIQUE autorise en multiple, donc aucune collision possible).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = rel.relnamespace
        WHERE n.nspname = 'public'
          AND rel.relname = 'users'
          AND con.conname = 'users_account_code_key'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_account_code_key UNIQUE (account_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_account_code ON public.users USING btree (account_code);
CREATE INDEX IF NOT EXISTS idx_users_requires_activation ON public.users USING btree (requires_activation);

COMMENT ON COLUMN public.users.sites_limit IS 'Nombre de sites autorisés (issu du code de sérialisation)';
COMMENT ON COLUMN public.users.posts_limit IS 'Nombre de postes autorisés (issu du code de sérialisation)';
COMMENT ON COLUMN public.users.is_activated IS 'Compte activé par code de sérialisation';
COMMENT ON COLUMN public.users.activation_code IS 'Dernier code de sérialisation utilisé';
COMMENT ON COLUMN public.users.activated_at IS 'Date d''activation du compte';
COMMENT ON COLUMN public.users.account_code IS 'Code d''activation du compte (pour la première connexion / changement d''appareil)';
COMMENT ON COLUMN public.users.requires_activation IS 'Le compte doit activer un appareil avant sa première connexion';
COMMENT ON COLUMN public.users.authorized_device_id IS 'Appareil lié au compte (un compte = un appareil actif)';
