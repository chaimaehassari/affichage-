# Architecture — Accès base de données (backend)

## Décision d'architecture (à ne pas remettre en cause sans discussion)

**Ce projet utilise psycopg 3 directement pour l'accès PostgreSQL.**

- Aucun ORM (SQLAlchemy, Alembic, Tortoise ORM, Peewee, SQLModel…) n'est utilisé, ni ne doit
  être introduit.
- Toutes les requêtes sont écrites en **SQL explicite** (paramétré via `%s`) et exécutées via
  `psycopg_pool.ConnectionPool` dans `app/db/database.py`.

C'est un choix délibéré : la pile (schemas métier Pydantic, contrôle d'accès par zones/portées,
migrations en fichiers SQL bruts) n'a pas besoin d'un ORM, et le SQL brut garde la maîtrise totale
des requêtes et des pools.

## Comment accéder à la base

`app/db/database.py` expose :

| Fonction | Usage |
|---|---|
| `get_db()` | Dépendance FastAPI : connexion du pool « gesto-api », commit/rollback automatique. |
| `get_connection()` | Connexion du pool « gesto-api » (usage direct, scripts, seeds). |
| `get_sync_connection()` | Connexion du pool dédié « gesto-sync », borné aux workers de synchro. |
| `connect_new()` | Connexion dédiée hors pool, réservée aux cas documentés (threads en arrière-plan). |

Conventions du code existant :

- Les services reçoivent une `psycopg.Connection` et exécutent du SQL brut :
  `conn.execute(sql, params).fetchall()`, `conn.execute(...).fetchone()`, etc.
- Toutes les requêtes sont paramétrées (`%s` + liste de paramètres) — jamais de formatage SQL par
  f-strings.
- `row_factory = dict_row` : les résultats sont des `dict`.
- Les pools sont bornés (`min_size` / `max_size`) ; `sync_pool` est borné au nombre de workers de
  synchro (`SYNC_MAX_WORKERS`) pour ne jamais affamer l'API web.
- Les migrations sont de simples fichiers SQL (`backend/migrations/*.sql`), appliqués par
  `backend/scripts/migrate.py` — aucun outil type Alembic.

## Garde-fous

- `backend/requirements.txt` contient un commentaire visible : ne pas ajouter d'ORM (voir le
  fichier).
- Règle de revue : toute PR introduisant `sqlalchemy`, `flask-sqlalchemy`, `tortoise-orm`,
  `peewee`, `sqlmodel` ou équivalent (même comme dépendance transitive) doit être refusée, sauf
  décision explicite validée hors de cette règle.

## Vérification rapide

```bash
cd backend
grep -ri "sqlalchemy\|declarative_base\|sessionmaker\|Base.metadata" app/ tests/ migrations/ scripts/
# → ne doit renvoyer aucun résultat.
```