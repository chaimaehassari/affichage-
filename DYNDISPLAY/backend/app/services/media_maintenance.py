"""Maintenance des médias : consolidation des doublons INTRA-client.

Phase 2, Partie 3, Option B
---------------------------
Le stockage média historisait un FICHIER PAR UPLOAD : deux imports du même
contenu créaient deux fichiers physiques distincts (deux `media.sftp_path`).
L'Option B retenue rend le stockage « adressé par contenu » DANS UN MÊME
CLIENT : un seul fichier physique par `(client_code, checksum)`, plusieurs
lignes `media` pouvant le référencer. Les nouveaux uploads le font déjà
(voir `app.api.routes.sites.upload_media`).

Ce module traite les DONNÉES EXISTANTES :

  - `find_duplicate_groups` : liste les `(client_code, checksum)` ayant
    plusieurs fichiers physiques distincts (lecture seule, dry-run) ;
  - `consolidate` : repointe toutes les lignes d'un groupe vers un fichier
    canonique et supprime les fichiers devenus orphelins.

Garanties
---------
  - Idempotent : après consolidation, un groupe n'a plus qu'un seul chemin,
    donc `find_duplicate_groups` ne le renvoie plus.
  - Aucun fichier encore référencé par une autre ligne `media` active n'est
    supprimé (`ref_count = 0` avant `store.remove`).
  - `sftp_path` reste un chemin RELATIF : la synchronisation et les players
    lisent toujours le même chemin (`filename = sftp_path`).
  - Choix du fichier canonique DÉTERMINISTE (plus petit chemin, tri SQL).

Rollback d'une exécution `--apply` : restaurer le dump DB + la copie du
dossier médias pris AVANT l'opération (voir rapport Phase 2, Section rollback).
"""
from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from app.services.media_storage import MediaStore


def find_duplicate_groups(conn: Connection, checksum: str | None = None) -> list[dict]:
    """Renvoie les `(client_code, checksum)` actifs à plusieurs fichiers.

    Un groupe n'est renvoyé que si au moins DEUX chemins physiques distincts
    partagent le même contenu chez le même client. Les `client_code` NULL
    (médias globaux/super-admin) forment leur propre groupe.

    `checksum` restreint la recherche à un contenu précis (utile aux tests et
    aux migrations ciblées) ; `None` scanne toute la table.
    """
    sql = """
        SELECT client_code,
               checksum,
               array_agg(DISTINCT sftp_path ORDER BY sftp_path) AS paths,
               count(*) AS row_count
        FROM media
        WHERE is_active = TRUE
          AND sftp_path IS NOT NULL
          AND checksum IS NOT NULL
    """
    params: tuple = ()
    if checksum is not None:
        sql += " AND checksum = %s"
        params = (checksum,)
    sql += """
        GROUP BY client_code, checksum
        HAVING count(DISTINCT sftp_path) > 1
        ORDER BY client_code NULLS FIRST, checksum
    """
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def consolidate(
    conn: Connection,
    store: MediaStore,
    apply: bool = False,
    checksum: str | None = None,
) -> dict:
    """Consolide les doublons intra-client.

    `apply=False` (défaut) : dry-run, ne modifie rien, renvoie le plan.
    `apply=True` : repointe les lignes et supprime les fichiers orphelins,
    puis commit.

    `checksum` restreint l'opération à un contenu précis (isolation des tests).

    Renvoie un dict de statistiques :
        groups, rows_repointed, files_removed, groups_detail
    """
    groups = find_duplicate_groups(conn, checksum=checksum)
    stats = {
        "groups": len(groups),
        "rows_repointed": 0,
        "files_removed": 0,
        "groups_detail": [],
    }

    for group in groups:
        paths = list(group["paths"])
        canonical = paths[0]
        redundant = paths[1:]
        stats["groups_detail"].append(
            {
                "client_code": group["client_code"],
                "checksum": group["checksum"],
                "row_count": group["row_count"],
                "canonical": canonical,
                "redundant": redundant,
            }
        )
        if not apply:
            continue

        with conn.cursor() as cur:
            result = cur.execute(
                """
                UPDATE media
                SET sftp_path = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE client_code IS NOT DISTINCT FROM %s
                  AND checksum = %s
                  AND is_active = TRUE
                  AND sftp_path = ANY(%s)
                """,
                (canonical, group["client_code"], group["checksum"], redundant),
            )
            stats["rows_repointed"] += result.rowcount

        for path in redundant:
            with conn.cursor(row_factory=dict_row) as cur:
                refs = cur.execute(
                    "SELECT count(*) AS n FROM media WHERE sftp_path = %s AND is_active = TRUE",
                    (path,),
                ).fetchone()["n"]
            if refs == 0 and store.exists(path):
                store.remove(path)
                stats["files_removed"] += 1

    if apply:
        conn.commit()

    return stats
