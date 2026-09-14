"""Portée (scope) des données selon l'utilisateur connecté.

Isolation par client dans la base unique : chaque compte client ne voit
et ne manipule que les sites/postes rattachés à son n° client.
L'administrateur voit tout (portée None = aucun filtre).
"""


def is_admin(user) -> bool:
    return bool(user and user.profile_name == "Administrateur")


def client_scope(user) -> str | None:
    """N° client utilisé pour filtrer les données.

    Retourne None pour l'administrateur (aucun filtre) ;
    retourne le user_code du compte connecté pour un client.
    """
    if is_admin(user):
        return None
    return (user.user_code or "").strip() or None


def site_in_scope(scope: str | None, site_client_code) -> bool:
    """Un site appartient au client si son client_code correspond au scope."""
    if scope is None:
        return True
    return (site_client_code or "").strip() == scope