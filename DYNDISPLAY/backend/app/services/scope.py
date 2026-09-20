"""Portée (scope) des données selon l'utilisateur connecté.

Isolation par client dans la base unique :
- Super Admin → vue globale (scope None = aucun filtre).
- Admin classique → uniquement les Clients qui lui sont affectés (liste de codes).
- Compte client → uniquement les sites/postes rattachés à son n° client.
"""

ADMIN_PROFILE = "Administrateur"


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


def client_scope(conn, user) -> str | list[str] | None:
    """Portée client utilisée pour filtrer les données.

    - Super Admin → None (aucun filtre → vue globale)
    - Admin classique → liste des codes clients affectés
    - Compte client → son propre user_code
    """
    if is_superadmin(user):
        return None
    if is_regular_admin(user):
        return admin_client_codes(conn, user)
    return (user.user_code or "").strip() or None


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


# ---------------------------------------------------------------------------
# Groupes d'écrans : filtrage par accès utilisateur
# ---------------------------------------------------------------------------

def group_scope(conn, user) -> set[int] | None:
    """Identifiants des groupes d'écrans accessibles pour l'utilisateur.

    Retourne None pour l'administrateur (tous les groupes) ;
    retourne un set d'id pour un client (vide si aucun groupe assigné).
    """
    if is_admin(user):
        return None
    rows = conn.execute(
        "SELECT group_id FROM user_group_access WHERE user_id = %s AND is_allowed = TRUE",
        (user.user_id,),
    ).fetchall()
    return {r["group_id"] for r in rows}


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
    """Un poste appartient au périmètre d'un utilisateur non-admin s'il relève
    de son code client (sites.client_code = user_code) OU d'un de ses groupes
    d'écrans assignés. Le Super Admin a toujours accès à tout ; un Admin
    classique n'accède qu'aux postes des Clients affectés."""
    if is_admin(user):
        if is_superadmin(user):
            return True
        scope = admin_client_codes(conn, user)
        if not scope:
            return False
        scope_list = scope
    else:
        scope_list = [(user.user_code or "").strip()]
        if not scope_list or not scope_list[0]:
            return False

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


def assert_post_scope(conn, user, post_id) -> None:
    """Lève PermissionError si le poste est hors du périmètre de l'utilisateur."""
    if not post_in_perimeter(conn, user, post_id):
        raise PermissionError("Vous n'êtes pas autorisé à accéder à ce poste.")