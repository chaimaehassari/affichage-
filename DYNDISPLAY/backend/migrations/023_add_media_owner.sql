-- Migration 023 : auteur d'un média (perte de visibilité à l'upload).
--
-- Problème constaté :
--   un Admin classique qui n'a pas exactement UN client ne peut pas attribuer
--   son upload à un code client. `client_scope_scalar()` renvoie alors NULL
--   (média global), et le listing d'un Admin classique filtre sur ses codes
--   clients : le média qu'il vient d'ajouter n'apparaît donc jamais dans son
--   interface ("j'ajoute un média, il ne s'affiche pas").
--
-- Correctif : on trace l'auteur de l'upload (`owner_user_id`) et le listing
-- d'un Admin classique inclut :
--     * les médias de ses clients (client_code dans son périmètre), et
--     * les médias qu'il a lui-même importés (owner_user_id = lui).
-- L'isolation reste intacte : les autres admins ne voient pas ses imports,
-- et le Super Admin (scope None) voit tout.
--
-- Le rattachement au client reste prioritaire quand il est connu : un média
-- ayant à la fois un client_code dans le périmètre ET owner_user_id = moi
-- n'est bien compté qu'une fois (le SQL filtre sur des lignes, pas sur des
-- colonnes).

ALTER TABLE media
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER;

-- Les médias globaux antérieurs (client_code IS NULL) sans auteur connu
-- restent orphelins : on ne les rattache à personne (inventer un auteur
-- serait faux). En revanche on rattache les uploads déjà scopés à un
-- client, dont l'auteur est déductible, pour que la colonne soit cohérente.
UPDATE media m
SET owner_user_id = sub.admin_id
FROM (
    SELECT ac.client_code, MIN(ac.admin_id) AS admin_id
    FROM admin_clients ac
    GROUP BY ac.client_code
) sub
WHERE m.owner_user_id IS NULL
  AND m.client_code IS NOT NULL
  AND m.client_code = sub.client_code;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_media_owner_user_id'
    ) THEN
        ALTER TABLE media
            ADD CONSTRAINT fk_media_owner_user_id
            FOREIGN KEY (owner_user_id) REFERENCES users (user_id)
            ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_media_owner_user_id
    ON media (owner_user_id);
