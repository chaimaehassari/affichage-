-- Migration 025: Licence logicielle Ed25519 (specification 6.1)
--
-- Une seule licence active à la fois, par client. Le code d'activation est
-- conserve tel quel (il est la preuve chiffree) et les quotas sont stockes
-- en clair pour etre lisibles par l'API et l'administration.
--
-- `activated_at` date l'activation sur CE poste ; `superseded_at` permet de
-- garder l'historique quand un revendeur rejoue un nouveau code (upgrade).

CREATE TABLE IF NOT EXISTS licenses (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Client concerné. La licence appartient au poste du client, pas au
    -- compte qui l'active : deux utilisateurs du même client partagent donc
    -- la même licence.
    client_id       BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Code d'activation complet, tel que saisi par le client. Sert à
    -- l'audit et à la revalidation ; jamais utilisé pour autoriser sans
    -- repasser par la verification de signature.
    activation_code VARCHAR(512) NOT NULL,

    -- Code machine lisible capture au moment de l'activation (XXXX-XXXX-XXXX).
    -- Compare au code machine courant pour detecter un changement de materiel.
    machine_code    VARCHAR(16)  NOT NULL,

    -- Les trois empreintes materielles completes : la tolerance "1 sur 3"
    -- n'est pas evaluable avec le seul code machine court. Voir
    -- app/core/machine_fingerprint.py pour la definition exacte de chaque
    -- composant et la raison de ce triplet-la.
    fp_host         BYTEA       NOT NULL,
    fp_disk         BYTEA       NOT NULL,
    fp_net          BYTEA       NOT NULL,

    -- Quotas accordes, extraits du payload signe.
    license_sites   INTEGER     NOT NULL DEFAULT 0,
    license_posts   INTEGER     NOT NULL DEFAULT 0,

    -- Date d'expiration, NULL = licence perenne.
    expires_at      TIMESTAMPTZ,

    activated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Renseigné quand un nouveau code remplace cette licence (upgrade).
    superseded_at   TIMESTAMPTZ,
    superseded_by   BIGINT REFERENCES licenses(id) ON DELETE SET NULL,

    -- Code client recopié dans la licence. Redondant avec le JOIN clients,
    -- mais utile à l'audit : on voit le client visé même après renommage.
    license_client_code VARCHAR(50) NOT NULL DEFAULT ''
);

-- Une seule licence active par client : le "upgrade" remplace l'ancienne.
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_client_actif
    ON licenses (client_id)
    WHERE superseded_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_licenses_client     ON licenses (client_id);
CREATE INDEX IF NOT EXISTS idx_licenses_expires    ON licenses (expires_at);
CREATE INDEX IF NOT EXISTS idx_licenses_activated  ON licenses (activated_at DESC);

-- La table doit survivre au remplacement des quotas historiques sur clients.
-- `clients.license_sites` / `license_posts` restent la source de vérité pour
-- l'affichage admin, alimentés par la licence active ; on les garde en
-- synchronisation dans le service, pas dans une colonne calculée, pour éviter
-- une dépendance entre deux tables mutuellement récursives.
