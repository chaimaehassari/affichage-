"""Portée (scope) des données selon l'utilisateur connecté.

Isolation par client dans la base unique :
- Super Admin → vue globale (scope None = aucun filtre).
- Admin classique → uniquement les Clients qui lui sont affectés (liste de codes).
- Compte client → uniquement les sites/postes rattachés à son n° client.
"""

ADMIN_PROFILE = "Administrateur"

# Niveaux des profils CLIENT, du plus élevé (1) au plus faible (3). Un créateur
# ne peut attribuer qu'un profil de niveau SUPÉRIEUR OU ÉGAL au sien, c'est-à-
# dire un profil « égal ou inférieur » en autorité (règle 2.4). Un profil absent
# de cette table n'est pas un profil client : il ne peut être attribué que par
# un Super Admin (jamais par un admin client).
PROFILE_LEVELS = {
    "Administrateur": 1,
    "Superviseur": 2,
    "Utilisateur": 3,
}


def profile_level(name: str | None) -> int | None:
    return PROFILE_LEVELS.get(name or "")


def is_admin(user) -> bool:
    return bool(user and user.profile_name == ADMIN_PROFILE)


def is_superadmin(user) -> bool:
    return bool(user and user.profile_name == ADMIN_PROFILE
                and getattr(user, "is_superadmin", False))


def is_regular_admin(user) -> bool:
    return bool(user and user.profile_name == ADMIN_PROFILE
                and not getattr(user, "is_superadmin", False))


def admin_client_codes(conn, user) -> list[str]:
    """Codes clients affectés à un Admin classique."""
    rows = conn.execute(
        "SELECT client_code FROM admin_clients WHERE admin_id = %s ORDER BY client_code",
        (user.user_id,),
    ).fetchall()
    return [r["client_code"] for r in rows]


def user_owner_user_id(user) -> int | None:
    """Admin propriétaire pour le filtrage de la liste des utilisateurs.

    - Super Admin → None (vue globale)
    - Admin classique → son user_id (il ne voit que les utilisateurs dont
      `users.admin_id` pointe vers lui)
    - Compte client → None (filtré par son code client, géré ailleurs)
    """
    if is_regular_admin(user):
        return user.user_id
    return None


# Périmètre renvoyé à un compte qui n'est rattaché à AUCUN client. Cette
# sentinelle ne correspond à aucun `clients.code_client` : le périmètre est
# donc vide. Ne jamais renvoyer None dans ce cas, `None` signifie « pas de
# filtre » et ouvrirait la vue globale à un compte client.
NO_CLIENT_SCOPE = "__no_client__"


def client_scope(conn, user) -> str | list[str] | None:
    """Portée client utilisée pour filtrer les données.

    - Super Admin → None (aucun filtre → vue globale)
    - Admin classique → liste des codes clients affectés
    - Compte client → le `clients.code_client` de SON client (via `client_id`)

    Le code du périmètre est toujours un **code client** (`clients.code_client`),
    jamais le `users.user_code` du compte. Les deux coexistent en base et se
    ressemblent (`SCO8B02F5` contre `3C48DBF1`), mais n'appartiennent pas au
    même espace :

    - le contenu est stocké et filtré sous le code client ;
    - un Admin filtre sur `admin_clients.client_code`, qui contient des
      `clients.code_client` ;
    - `users.user_code` est le code de CONNEXION du compte (c'est lui que
      l'utilisateur saisit à la place du mot de passe).

    Un périmètre exprimé en `user_code` ne trouvait donc plus aucune ligne, et
    un Admin ne voyait ni les sites ni les médias créés par ses propres comptes.
    """
    if is_superadmin(user):
        return None
    if is_regular_admin(user):
        return admin_client_codes(conn, user)
    return user_client_code(conn, user.user_id) or NO_CLIENT_SCOPE


def canonical_client_code(conn, client_code: str | None) -> str | None:
    """Ramène un code à sa forme canonique `clients.code_client`.

    Appelé sur TOUTE écriture de la colonne texte `client_code` (sites, media)
    pour garantir que le contenu stocké est trouvable par le filtre client de
    l'admin. Un `user_code` est d'abord traduit en code client via
    `users.client_id` : c'est le cas legacy des sites et médias créés avant le
    correctif de `client_scope()`.

    Un code inconnu est renvoyé tel quel (on ne perd pas d'information) et un
    code vide devient None.
    """
    code = str(client_code or "").strip()
    if not code or code == NO_CLIENT_SCOPE:
        return None
    row = conn.execute(
        "SELECT code_client FROM clients WHERE code_client = %s", (code,)
    ).fetchone()
    if row:
        return row["code_client"]
    row = conn.execute(
        """
        SELECT c.code_client
        FROM users u
        JOIN clients c ON c.id = u.client_id
        WHERE u.user_code = %s
        LIMIT 1
        """,
        (code,),
    ).fetchone()
    return row["code_client"] if row else code


def client_scope_scalar(conn, user) -> str | None:
    """Code client **unique** à écrire dans une colonne texte (`client_code`).

    `client_scope()` renvoie une liste pour un Admin classique : l'utiliser
    tel quel dans un INSERT texte faisait écrire la représentation de la
    liste, donc les chaines littérales `'{}'` ou `'None'` en base. Ces
    médias devenaient invisibles (le listing filtre sur le vrai code) et
    le dédoublonnage par checksum les retrouvait comme « déjà présents ».

    - Super Admin → None (global, non attribuable)
    - Compte client → le `clients.code_client` de son client
    - Admin classique avec exactement 1 client → ce code
    - Admin classique avec 0 ou >1 clients → None (non attribuable)
    """
    scope = client_scope(conn, user)
    if scope is None:
        return None
    if isinstance(scope, (list, tuple, set)):
        codes = [str(c).strip() for c in scope if str(c).strip()]
        return codes[0] if len(codes) == 1 else None
    text = str(scope).strip()
    return text or None


def scope_as_list(scope) -> list[str] | None:
    """Normalise un scope (str ou liste) en liste de codes clients nettoyés."""
    if scope is None:
        return None
    if isinstance(scope, (list, tuple, set)):
        values = scope
    else:
        values = [scope]
    return [str(v).strip() for v in values if str(v).strip()]


def site_in_scope(scope, site_client_code) -> bool:
    """Un site appartient au périmètre si son client_code est dans le scope."""
    if scope is None:
        return True
    value = (site_client_code or "").strip()
    if isinstance(scope, (list, tuple, set)):
        return value in scope
    return value == scope


def media_in_scope(scope, media_client_code, owner_user_id=None,
                   viewer_user_id=None) -> bool:
    """Un média est-il visible par l'utilisateur connecté ?

    Même logique que `media_scope_sql` : périmètre client **ou** média
    importé par l'utilisateur connecté (cf. la doc de `media_scope_sql` pour
    pourquoi cette seconde branche est nécessaire).
    """
    if scope is None:
        return True
    if site_in_scope(scope, media_client_code):
        return True
    if isinstance(scope, (list, tuple, set)) and owner_user_id is not None \
            and viewer_user_id is not None:
        return int(owner_user_id) == int(viewer_user_id)
    return False


def scoped_post_ids(conn, post_ids, scope) -> list[int]:
    """Ne garde que les postes dont le SITE est dans le périmètre.

    Un groupe d'écrans est une entité GLOBALE : son accès se décide par
    `assert_group_access`, c'est-à-dire « j'ai accès à CE groupe ». Mais un
    groupe peut contenir les postes de plusieurs clients (rien ne l'interdit en
    base), et l'accès au groupe ne doit pas donner accès à son contenu. Les
    endpoints de synchronisation de groupe prenaient `post_ids` tel quel : un
    client pouvait donc déclencher une sync — donc une écriture SFTP — sur les
    postes d'un autre client.

    `scope is None` (Super Admin) ne filtre rien.
    """
    if not post_ids:
        return []
    if scope is None:
        return list(post_ids)
    frag, args = scope_sql(scope, "s.client_code")
    rows = conn.execute(
        "SELECT p.post_id FROM posts p"
        " LEFT JOIN sites s ON s.site_id = p.site_id"
        " WHERE p.post_id = ANY(%s)" + frag,
        [list(post_ids), *args],
    ).fetchall()
    return [r["post_id"] for r in rows]


def assert_media_in_scope(conn, scope, viewer_user_id, media_id) -> None:
    """Vérifie qu'un média peut être UTILISÉ par l'utilisateur (pas seulement vu).

    `media_in_scope()` ne fait que tester l'appartenance au périmètre ;
    l'affectation d'un média à une zone, ou sa synchronisation, ne vérifiait pas
    cette appartenance : on contrôlait que le POST était dans le périmètre, et
    que le média EXISTAIT, jamais que le média était accessible. Un client
    pouvait donc servir sur ses propres postes un média d'un autre client —
    l'information croisée suffisait à le deviner (le `sftp_path` du média est
    renvoyé par le listing, et un nom de fichier est souvent devinable).

    Un média absent lève `ValueError` (404/400 : le client n'a pas à savoir
    si l'id existe), un média hors périmètre lève `PermissionError` (403).

    La branche « importé par l'utilisateur connecté » de `media_in_scope` est
    conservée : sans elle, un Admin à 0 ou >1 clients (dont les uploads sont
    stockés en global, `client_code` NULL) ne pourrait plus utiliser ses propres
    médias alors qu'il les voit dans sa bibliothèque. Même règle que
    `PostService.batch_assign_media`.
    """
    row = conn.execute(
        "SELECT client_code, owner_user_id FROM media WHERE media_id = %s",
        (media_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Média introuvable : {media_id}")
    if not media_in_scope(scope, row["client_code"], row["owner_user_id"], viewer_user_id):
        raise PermissionError(
            "Vous n'êtes pas autorisé à utiliser ce média : il n'appartient pas "
            "à votre périmètre."
        )


def assert_media_ids_in_scope(conn, scope, viewer_user_id, media_ids) -> None:
    """Variante de `assert_media_in_scope` pour une liste d'identifiants.

    À appeler AVANT toute écriture : `ConfigurationService._rebuild_zones_playlists`
    supprime les zones existantes avant de les recréer, donc une validation
    faite pendant l'insertion effacerait la configuration d'un poste alors que
    la requête est rejetée.
    """
    for media_id in media_ids:
        if media_id is None:
            continue
        assert_media_in_scope(conn, scope, viewer_user_id, media_id)


# ---------------------------------------------------------------------------
# Journal d'audit : filtrage par entité OU par auteur
# ---------------------------------------------------------------------------

# Entités dont on sait résoudre le client (cf. le CASE plus bas) : site, post,
# client, media, zone_media, user, screen_group. Le filtrage se fait par
# LISTE BLANCHE et non par exclusion : un type d'entité INCONNU ne doit pas
# pouvoir se glisser dans la branche « auteur » via un `client_code` résolu à
# NULL, sinon un journal portant un type qu'on ne sait pas interpréter
# deviendrait visible par son seul auteur. Fail-closed : ce qu'on ne sait pas
# classer est réservé au Super Admin.
#
# `settings` et `general_settings` sont des ressources GLOBALES, hors
# périmètre d'un client : ils sont simplement absents de cette liste.
_AUDIT_RESOLVABLE_TYPES = (
    "('site', 'post', 'client', 'media', 'zone_media', 'user', 'screen_group')"
)


def audit_scope_sql(conn, user, alias: str = "al") -> tuple[str, str, list]:
    """Restreint une requête sur `audit_logs` au périmètre de l'utilisateur.

    Retourne `(join_sql, condition, params)`, à poser ainsi dans la requête :

        FROM audit_logs al
        LEFT JOIN users u ON u.user_id = al.user_id
        {join_sql}
        WHERE {condition}

    `condition` est une expression **sans préfixe `AND`** et vide si aucun
    filtre n'est nécessaire (Super Admin). `join_sql` est vide ou une
    `LEFT JOIN LATERAL` qui résout le client de l'entité une seule fois.

    Règle de visibilité, par ordre de PRÉCÉDENCE :

    1. l'entité se résout à un client → elle n'est visible que si ce client est
       dans mon périmètre, même si c'est MOI qui ai écrit le journal. Sans
       cette précédence, la branche « auteur » réintroduisait la fuite : un
       admin voit alors « Licences du client C26M427EEF : 4 sites / 9 postes »
       ou « site_create (client 3C48DBF1) » pour des clients qui ne sont pas
       les siens, parce que le compte auteur lui est rattaché.
    2. l'entité est SUPPRIMÉE (non résoluble) → le journal n'est visible que si
       l'action est l'œuvre d'un compte que je gère. C'est indispensable :
       `audit_logs` ne stocke pas le client, et la quasi-totalité des lignes
       vise une entité déjà supprimée (4 964 journaux de site et 5 446 de poste
       pointent sur un id introuvable, conséquence de la purge des données de
       test). Un filtre par entité seul rendrait le journal du client quasi
       vide.
    3. `settings` / `general_settings` sont des ressources GLOBALES : hors
       périmètre d'un client, donc réservées au Super Admin. Tout type
       d'entité qui n'est pas dans `_AUDIT_RESOLVABLE_TYPES` — y compris
       inconnu — est traité de même (fail-closed : on ne devine pas
       l'appartenance d'une entité dont on ne connaît pas la nature). Le
       filtrage est donc une liste blanche, et non une liste noire.

    Un `screen_group` n'appartient à aucun client en propre : il est visible si
    au moins un de ses postes est dans le périmètre, et sinon uniquement via
    son auteur.

    Limite connue, signalée et non contournée : `audit_logs` n'a pas de colonne
    `client_code`. Une action du Super Admin sur une entité DÉJÀ supprimée d'un
    client n'est donc pas restaurable pour l'admin de ce client. Le correctif
    durable est une colonne `client_code` renseignée à l'écriture par
    `log_action` ; elle n'est pas ajoutée ici pour ne pas modifier le schéma.
    """
    if is_superadmin(user):
        return "", "", []

    a = f"{alias}."
    codes = scope_as_list(client_scope(conn, user))

    # Branche AUTEUR : les actions des comptes que je gère (cf. règle 2).
    if is_regular_admin(user):
        # L'alias doit correspondre à celui utilisé dans la EXISTS ci-dessous :
        # `admin_owned_users_sql` préfixe chaque colonne par l'alias fourni.
        owner_frag, owner_params = admin_owned_users_sql(user.user_id, "au")
        author_clause = (f"EXISTS (SELECT 1 FROM users au WHERE au.user_id = {a}user_id"
                         f" AND {owner_frag})")
        author_params = list(owner_params)
    elif codes:
        author_clause = (f"EXISTS (SELECT 1 FROM users au"
                         f" JOIN clients ac ON ac.id = au.client_id"
                         f" WHERE au.user_id = {a}user_id AND ac.code_client = ANY(%s))")
        author_params = [codes]
    else:
        # Aucun client affecté, pas d'admin : rien ne lui est attribuable.
        return "", "1 = 0", []

    if not codes:
        # Aucun client affecté : la branche « client de l'entité » ne peut rien
        # remonter, mais la branche auteur doit TOUJOURS exiger une entité non
        # résoluble. On ne court-circuite donc pas ici : sans le `LEFT JOIN
        # LATERAL` et son `ec.client_code IS NULL`, un admin sans client verrait
        # les journaux d'entités VIVANTES d'un autre client, dès lors que
        # l'auteur est un compte qu'il gère. Le cas est traité par le chemin
        # commun ci-dessous, où `ec.client_code = ANY('{}')` est simplement
        # toujours faux.
        pass

    # Client de l'entité, calculé une fois (NULL = supprimée ou inconnue).
    join_sql = f"""LEFT JOIN LATERAL (
        SELECT CASE {a}entity_type
            WHEN 'site'       THEN (SELECT s.client_code FROM sites s
                                     WHERE s.site_id = {a}entity_id)
            WHEN 'post'       THEN (SELECT s.client_code FROM posts p
                                     JOIN sites s ON s.site_id = p.site_id
                                     WHERE p.post_id = {a}entity_id)
            WHEN 'client'     THEN (SELECT c.code_client FROM clients c
                                     WHERE c.id = {a}entity_id)
            WHEN 'media'      THEN (SELECT m.client_code FROM media m
                                     WHERE m.media_id = {a}entity_id)
            WHEN 'zone_media' THEN (SELECT s.client_code FROM zone_media zm
                                     JOIN posts p ON p.post_id = zm.post_id
                                     JOIN sites s ON s.site_id = p.site_id
                                     WHERE zm.zone_media_id = {a}entity_id)
            WHEN 'user'       THEN (SELECT c.code_client FROM users u
                                     JOIN clients c ON c.id = u.client_id
                                     WHERE u.user_id = {a}entity_id)
            ELSE NULL
        END AS client_code
    ) ec ON TRUE"""

    conditions = [f"ec.client_code = ANY(%s)"]
    params: list = [codes]

    # Un média importé par l'utilisateur connecté reste visible même sans client
    # : même règle que `media_scope_sql` (uploads stockés en global pour un
    # Admin à 0 ou >1 clients).
    conditions.append(
        f"({a}entity_type = 'media' AND EXISTS (SELECT 1 FROM media m"
        f" WHERE m.media_id = {a}entity_id AND ec.client_code IS NULL"
        f" AND m.owner_user_id = %s))"
    )
    params.append(user.user_id)

    # Règle 2 : entité non résoluble + action d'un compte que je gère.
    conditions.append(f"(ec.client_code IS NULL AND {author_clause})")
    params.extend(author_params)

    # Un groupe d'écrans est visible par ses postes.
    conditions.append(
        f"({a}entity_type = 'screen_group' AND EXISTS ("
        f"  SELECT 1 FROM screen_group_posts gp"
        f"  JOIN posts p ON p.post_id = gp.post_id"
        f"  JOIN sites s ON s.site_id = p.site_id"
        f"  WHERE gp.group_id = {a}entity_id AND s.client_code = ANY(%s)))"
    )
    params.append(codes)

    return (join_sql,
            f"({a}entity_type IN {_AUDIT_RESOLVABLE_TYPES}"
            f" AND (" + " OR ".join(conditions) + "))",
            params)


def scope_sql(scope, column="client_code"):
    """Fragment SQL + arguments pour filtrer selon le scope.

    Retourne un tuple (sql_fragment, params). Le fragment est préfixé par AND.
    - scope None → aucun filtre
    - scope liste → ``AND column = ANY(%s)``
    - scope str → ``AND column = %s``
    """
    if scope is None:
        return "", []
    if isinstance(scope, (list, tuple, set)):
        codes = [str(c).strip() for c in scope if str(c).strip()]
        if not codes:
            return " AND 1 = 0", []
        return f" AND {column} = ANY(%s)", [codes]
    return f" AND {column} = %s", [scope]


def media_scope_sql(scope, viewer_user_id: int | None = None):
    """Filtre d'un média, en tenant compte de son auteur.

    Un Admin classique qui n'a pas exactement un client ne peut pas attribuer
    son upload à un code client (voir `client_scope_scalar`) : le média est
    alors stocké en global (`client_code` NULL) et sortait du listing, qui
    filtre sur les codes clients. Concrètement : l'admin ajoutait un média et
    ne le voyait jamais apparaître dans sa bibliothèque.

    On ajoute donc une seconde branche : le média reste visible s'il est
    dans le périmètre client **ou** s'il a été importé par l'utilisateur
    connecté. L'isolation est préservée : les autres administrateurs ne
    voient pas ces imports.

    - scope None (Super Admin) → aucun filtre
    - scope liste (Admin classique) → ``client_code = ANY(...) OR owner_user_id = <moi>``
    - scope str (compte client) → ``client_code = %s`` (un client ne voit pas
      les imports de l'admin, seulement ce qui lui est affecté)
    """
    if scope is None:
        return "", []
    if isinstance(scope, (list, tuple, set)):
        codes = [str(c).strip() for c in scope if str(c).strip()]
        if not codes:
            # Aucun client : l'admin ne voit que ses propres imports.
            if viewer_user_id is None:
                return " AND 1 = 0", []
            return " AND owner_user_id = %s", [viewer_user_id]
        if viewer_user_id is None:
            return " AND client_code = ANY(%s)", [codes]
        return (
            " AND (client_code = ANY(%s) OR owner_user_id = %s)",
            [codes, viewer_user_id],
        )
    return " AND client_code = %s", [scope]


# ---------------------------------------------------------------------------
# Groupes d'écrans : filtrage par accès utilisateur
# ---------------------------------------------------------------------------

def group_scope(conn, user) -> set[int] | None:
    """Identifiants des groupes d'écrans accessibles pour l'utilisateur.

    Retourne None pour le Super Admin (tous les groupes) ;
    retourne un set d'id pour un admin classique ou un compte client
    (vide si aucun groupe accessible).
    """
    if is_superadmin(user):
        return None

    group_ids: set[int] = {
        r["group_id"]
        for r in conn.execute(
            "SELECT group_id FROM user_group_access WHERE user_id = %s AND is_allowed = TRUE",
            (user.user_id,),
        ).fetchall()
    }

    if is_regular_admin(user):
        codes = admin_client_codes(conn, user)
        if codes:
            rows = conn.execute(
                """
                SELECT DISTINCT gp.group_id
                FROM screen_group_posts gp
                JOIN posts p ON p.post_id = gp.post_id
                JOIN sites s ON s.site_id = p.site_id
                WHERE s.client_code = ANY(%s)
                """,
                (codes,),
            ).fetchall()
            group_ids.update(r["group_id"] for r in rows)

    return group_ids


def assert_group_access(conn, user, group_id) -> None:
    """Lève PermissionError si l'utilisateur n'a pas accès au groupe donné."""
    allowed = group_scope(conn, user)
    if allowed is None:
        return
    if group_id not in allowed:
        raise PermissionError("Vous n'avez pas accès à ce groupe d'écrans.")


# ---------------------------------------------------------------------------
# Postes : périmètre de supervision (client OU groupes assignés)
# ---------------------------------------------------------------------------

def post_in_perimeter(conn, user, post_id) -> bool:
    """Un poste appartient-il au périmètre de l'utilisateur connecté ?

    Trois cas :

    - Super Admin → tout ;
    - Admin classique → les postes des sites de SES clients (`admin_clients`) ;
    - compte client (profils 2/3) → les postes des sites de SON client.

    Le rattachement d'un compte client se résout par `users.client_id` et NON
    par `users.user_code` : `sites.client_code` contient un `clients.code_client`
    (code du client), alors que `user_code` est le code de connexion du compte.
    Comparer les deux ne trouvait plus aucune ligne depuis le passage des sites
    au vrai code client : un profil 2/3 était privé de la configuration de ses
    propres postes alors que le rapport de diffusion, lui, les voyait bien
    (celui-ci passe par `client_scope()`, qui résout déjà `client_id`).

    Dans tous les cas, un poste reste accessible si le compte a le groupe
    d'écrans correspondant explicitement autorisé (`user_group_access`).
    """
    if is_admin(user):
        if is_superadmin(user):
            return True
        scope_list = admin_client_codes(conn, user)
        if not scope_list:
            return False
    else:
        code = user_client_code(conn, user.user_id)
        if not code:
            return False
        scope_list = [code]

    row = conn.execute(
        """
        SELECT 1
        FROM posts p
        JOIN sites s ON p.site_id = s.site_id
        LEFT JOIN screen_group_posts sgp ON sgp.post_id = p.post_id
        LEFT JOIN user_group_access uga
               ON uga.group_id = sgp.group_id AND uga.user_id = %s AND uga.is_allowed = TRUE
        WHERE p.post_id = %s
          AND (s.client_code = ANY(%s) OR uga.user_group_access_id IS NOT NULL)
        LIMIT 1
        """,
        (user.user_id, post_id, scope_list),
    ).fetchone()
    return row is not None


def user_client_code(conn, user_id) -> str | None:
    """Code client (`clients.code_client`) auquel un compte est rattaché.

    C'est le seul lien fiable entre un compte et son client : la colonne
    `users.user_code` est le code *du compte* (et vaut le plus souvent NULL),
    tandis que `users.client_id` pointe réellement sur la table `clients`.
    """
    row = conn.execute(
        """
        SELECT c.code_client
        FROM users u
        JOIN clients c ON c.id = u.client_id
        WHERE u.user_id = %s
        """,
        (user_id,),
    ).fetchone()
    return row["code_client"] if row else None


def admin_owned_users_sql(admin_id: int, alias: str = "u") -> tuple[str, list]:

    """Source de vérité unique : quels comptes un Admin classique possède.

    Retourne `(fragment_sql, params)`, le fragment étant à coller dans un
    `WHERE` (sans `AND` initial, sans `WHERE`).

    Trois cas, volontairement distincts :

    1. les comptes qu'il a lui-même créés (`users.admin_id` = lui) ;
    2. les comptes SANS propriétaire (`admin_id IS NULL`) d'un client qui lui
       est EXCLUSIVEMENT affecté. Un client partagé par plusieurs admins ne
       doit pas déverser tous ses comptes chez chacun d'eux ;
    3. les comptes d'un admin SUPPRIMÉ (`admin_id` pointant un `user_id`
       inexistant) rattachés à l'un de ses clients : sans ce cas ils
       deviendraient orphelins, donc ni listables ni gérables par personne.

    `users.admin_id` est NULL pour la quasi-totalité des comptes : sans le cas
    2 la liste serait VIDE pour tous les Admins. Le rattachement client passe
    par `client_id` (jamais par `users.user_code`, qui est le code du compte),
    d'où les jointures sur `clients` et `admin_clients`.

    Cette fonction est utilisée par `UserService.list_users()` ET par
    `target_user_in_scope()` : c'est ce qui garantit qu'un compte invisible
    dans la liste l'est aussi pour `GET/PUT/DELETE /users/{id}`. Deux règles
    différentes donnaient un contournement : le tableau cachait la ligne, mais
    l'API acceptait encore l'ID.
    """
    a = f"{alias}." if alias else ""
    frag = (
        f"({a}admin_id = %s"
        f" OR ({a}admin_id IS NULL AND {a}client_id IN ("
        f"      SELECT c.id FROM clients c"
        f"      JOIN admin_clients ac ON ac.client_code = c.code_client"
        f"      WHERE ac.admin_id = %s"
        f"        AND NOT EXISTS (SELECT 1 FROM admin_clients ac2"
        f"                        WHERE ac2.client_code = c.code_client"
        f"                          AND ac2.admin_id <> %s)))"
        f" OR ({a}admin_id IS NOT NULL"
        f"     AND NOT EXISTS (SELECT 1 FROM users o WHERE o.user_id = {a}admin_id)"
        f"     AND {a}client_id IN ("
        f"      SELECT c.id FROM clients c"
        f"      JOIN admin_clients ac ON ac.client_code = c.code_client"
        f"      WHERE ac.admin_id = %s)))"
    )
    return frag, [admin_id] * 4


def target_user_in_scope(conn, actor, target_user_id) -> bool:
    """Un compte cible est-il gérable par cet utilisateur ?

    Appelé par la liste, le détail, l'édition, la suppression, la réinitialisation
    de mot de passe et la page Appareils : une seule règle pour tous, sinon un
    compte invisible dans le tableau resterait manipulable via son ID.
    """
    if is_superadmin(actor):
        return True
    if target_user_id is None:
        return False
    if is_regular_admin(actor):
        if int(target_user_id) == int(actor.user_id):
            return True
        frag, params = admin_owned_users_sql(actor.user_id)
        row = conn.execute(
            f"SELECT 1 FROM users u WHERE u.user_id = %s AND {frag} LIMIT 1",
            [target_user_id, *params],
        ).fetchone()
        return row is not None
    scope = client_scope(conn, actor)
    if scope is None:
        return True
    code = user_client_code(conn, target_user_id)
    return bool(code) and site_in_scope(scope, code)


def user_in_scope(conn, user, *, user_code=None, admin_id=None) -> bool:
    """Un utilisateur cible est-il dans le périmètre de l'utilisateur connecté ?

    ⚠ NON UTILISÉE : le paramètre `user_code` est comparé au périmètre, qui
    est désormais exprimé en `clients.code_client` — la comparaison ne peut
    donc plus être correcte. Utiliser `target_user_in_scope(conn, actor,
    target_user_id)`, qui résout le client du compte visé via
    `users.client_id`. Conservée pour ne pas casser un appelant externe.

    - Super Admin -> toujours True.
    - Admin classique -> les comptes qu'il porte (``users.admin_id`` =
      son ``user_id``) ET les comptes dont le code client fait partie de
      ses clients affectés.
    - Compte client -> uniquement les comptes de son code client.
    """
    if is_superadmin(user):
        return True
    if is_regular_admin(user):
        if admin_id and int(admin_id) == user.user_id:
            return True
        if not user_code:
            return False
        return site_in_scope(admin_client_codes(conn, user), user_code)
    scope = client_scope(conn, user)
    if scope is None:
        return True
    return site_in_scope(scope, user_code)


def assert_user_scope(conn, user, *, user_code=None, admin_id=None) -> None:
    """Lève PermissionError si l'utilisateur cible est hors périmètre."""
    if not user_in_scope(conn, user, user_code=user_code, admin_id=admin_id):
        raise PermissionError(
            "Vous ne pouvez gérer que les utilisateurs de votre périmètre."
        )


def assert_post_scope(conn, user, post_id) -> None:
    """Lève PermissionError si le poste est hors du périmètre de l'utilisateur."""
    if not post_in_perimeter(conn, user, post_id):
        raise PermissionError("Vous n'êtes pas autorisé à accéder à ce poste.")