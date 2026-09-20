import psycopg

DB_URL = "postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY"

with psycopg.connect(DB_URL) as conn:
    cur = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='admin_id'"
    )
    exists = cur.fetchone()
    if exists:
        print("admin_id already present")
    else:
        conn.execute(
            "ALTER TABLE users ADD COLUMN admin_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL"
        )
        conn.execute("CREATE INDEX idx_users_admin_id ON users(admin_id)")
        conn.commit()
        print("admin_id added")