from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import Connection

from app.db.database import get_db
from app.dependencies.auth import get_current_user_dependency
from app.schemas.auth import UserInfo
from app.services.scope import audit_scope_sql

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


def _get_admin_user(current_user: UserInfo = Depends(get_current_user_dependency)):
    if current_user.profile_name != "Administrateur":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'avez pas les droits nécessaires.",
        )
    return current_user


@router.get("")
def list_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    entity_type: str | None = Query(None),
    current_user=Depends(_get_admin_user),
    db: Connection = Depends(get_db),
):
    """Journaux d'audit DU PÉRIMÈTRE de l'utilisateur connecté.

    Le filtre vient de `audit_scope_sql()` (source de vérité unique, dans
    scope.py). Avant, la requête ne portait AUCUN filtre : n'importe quel
    Administrateur recevait la table entière — 33 631 journaux, y compris les
    licences de clients qui ne lui sont pas affectés.
    """
    conditions: list[str] = []
    params: list = []

    if entity_type:
        conditions.append("al.entity_type = %s")
        params.append(entity_type)

    join_sql, frag, frag_params = audit_scope_sql(db, current_user, "al")
    if frag:
        conditions.append(frag)
    params.extend(frag_params)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = db.execute(
        f"SELECT COUNT(*) AS c FROM audit_logs al {join_sql} {where}", params
    ).fetchone()
    rows = db.execute(
        f"""
        SELECT al.audit_id, al.user_id, u.login AS user_login, al.action,
               al.entity_type, al.entity_id, al.description, al.ip_address, al.created_at
        FROM audit_logs al
        LEFT JOIN users u ON u.user_id = al.user_id
        {join_sql}
        {where}
        ORDER BY al.created_at DESC, al.audit_id DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    ).fetchall()

    return {
        "total": total["c"] if total else 0,
        "items": [
            {
                "audit_id": r["audit_id"],
                "user_id": r["user_id"],
                "user_login": r["user_login"],
                "action": r["action"],
                "entity_type": r["entity_type"],
                "entity_id": r["entity_id"],
                "description": r["description"],
                "ip_address": r["ip_address"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }
