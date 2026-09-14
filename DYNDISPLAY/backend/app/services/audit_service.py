from psycopg import Connection


def log_action(
    conn: Connection,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    ip_address: str | None = None,
):
    conn.execute(
        """
        INSERT INTO audit_logs (user_id, action, entity_type, entity_id, description, ip_address)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user_id, action, entity_type, entity_id, description, ip_address),
    )