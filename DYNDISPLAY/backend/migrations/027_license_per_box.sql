-- Migration 027: licence par BOX (specification "serialisation des boxes")
--
-- Jusque-la migration 025, une licence etait un couple (client, quotas) : une
-- seule licence ACTIVE par client. C'est incompatible avec la serialisation des
-- boxes : deux boxes d'un meme client doivent pouvoir etre activees
-- independamment, chacune liee a SON materiel et a SON poste.
--
-- Cette migration ajoute l'affectation (site + poste) et le code machine
-- COMPLET, puis remplace l'unicite « une licence active par client » par
-- « une licence active par box ».
--
-- Le controle des quotas ne bouge pas : il reste porte par
-- `clients.license_sites` / `clients.license_posts`, alimentes par le service a
-- chaque activation. Les colonnes sont donc ajoutees sans toucher aux quotas.

-- --- Affectation de la licence a une box -------------------------------------

ALTER TABLE licenses
    ADD COLUMN IF NOT EXISTS site_code VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS post_code VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS license_version SMALLINT NOT NULL DEFAULT 2;

-- Code machine COMPLET (3 x 4 octets = 24 hex, en 3 blocs de 8).
-- `machine_code` (12 hex) reste : c'est la forme lisible, affichée dans
-- l'interface et lisible dans les logs. Le complet est ce que la box affiche
-- au revendeur et ce qui permet de rejouer une signature.
-- NULL = licence emise avant la v3, qui ne portait pas cette information.
ALTER TABLE licenses
    ADD COLUMN IF NOT EXISTS machine_code_full VARCHAR(32);

-- `license_version` enregistre la version de payload reellement signee, pour
-- qu'un audit ne confond pas une licence v2 (liee au serveur, sans site/post)
-- avec une licence v3 (liee a une box).

-- Backfill : les licences existantes sont, par construction, des licences de
-- SERVEUR au format v2. On le materialise plutot que de le laisser deviner.
UPDATE licenses
   SET license_version = 2
 WHERE license_version IS NULL OR license_version = 0;

-- --- Unicite : par box, plus par client --------------------------------------
--
-- L'ancien index interdisait deux licences actives pour un meme client. On le
-- retire : il est remplace par l'unicite sur (client_id, post_code).
--
-- `post_code` est non vide a partir de la v3. Les lignes v2 (post_code = '')
-- sont exclues de cet index pour ne pas se chevaucher entre elles : leur
-- unicite historique « une seule licence serveur active par client » est
-- conservee par un index partiel distinct, applique uniquement a ces lignes.

DROP INDEX IF EXISTS idx_licenses_client_actif;

-- Une seule licence ACTIVE par box, et par client.
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_box_actif
    ON licenses (client_id, post_code)
    WHERE superseded_at IS NULL AND post_code <> '';

-- Une seule licence ACTIVE de type "serveur" (v2, sans poste) par client.
CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_server_actif
    ON licenses (client_id)
    WHERE superseded_at IS NULL AND post_code = '';

-- Recherche de l'etat d'une box : (client, poste).
CREATE INDEX IF NOT EXISTS idx_licenses_post
    ON licenses (client_id, post_code);

-- --- Vue de lecture : etat par box ------------------------------------------
--
-- La console doit pouvoir repondre « cette box est-elle licenciee, pour quel
-- poste, sur quel site ? » sans connaitre le format du payload. Cette vue
-- expose les trois reponses normalisees, v2 comprise.

CREATE OR REPLACE VIEW v_box_licenses AS
SELECT
    l.id,
    l.client_id,
    c.code_client,
    NULLIF(l.post_code, '')      AS post_code,
    NULLIF(l.site_code, '')      AS site_code,
    l.machine_code,
    l.machine_code_full,
    l.license_version,
    (NULLIF(l.post_code, '') IS NOT NULL) AS is_box_license,
    l.license_sites,
    l.license_posts,
    l.expires_at,
    l.activated_at,
    (l.superseded_at IS NULL)   AS is_active
FROM licenses l
JOIN clients c ON c.id = l.client_id;