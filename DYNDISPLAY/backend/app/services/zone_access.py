from psycopg import Connection


def assert_zone_allowed(conn: Connection, user_id: int, zone_number: int) -> None:
    """Vérifie qu'un utilisateur non administrateur a le droit d'agir sur cette zone.

    Lève PermissionError si la zone n'est pas autorisée pour l'utilisateur.
    """
    profile = conn.execute(
        """
        SELECT p.name AS profile_name
        FROM users u
        JOIN profiles p ON p.profile_id = u.profile_id
        WHERE u.user_id = %s
        """,
        (user_id,),
    ).fetchone()
    if profile and profile["profile_name"] == "Administrateur":
        return

    allowed = conn.execute(
        """
        SELECT zone_number FROM user_zone_access
        WHERE user_id = %s AND is_allowed = TRUE
        """,
        (user_id,),
    ).fetchall()
    allowed_zones = {z["zone_number"] for z in allowed}
    if zone_number not in allowed_zones:
        raise PermissionError("Vous n'êtes pas autorisé à affecter un média sur cette zone.")
