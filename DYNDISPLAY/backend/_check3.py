import psycopg

conn = psycopg.connect("postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY")
rows = conn.execute("SELECT profile_id, name, description FROM profiles ORDER BY profile_id").fetchall()
for r in rows:
    print(f"profile_id={r[0]}, name={r[1]}, desc={r[2]}")

# Check if admin_id already exists on users
try:
    conn.execute("SELECT admin_id FROM users LIMIT 1")
    print("admin_id column exists on users")
except Exception as e:
    print(f"admin_id NOT on users: {e}")

# Check existing test_v8 admin test for /admins routes
admins = conn.execute("SELECT user_id, login, is_superadmin FROM users WHERE profile_id = (SELECT profile_id FROM profiles WHERE name = 'Administrateur') ORDER BY user_id").fetchall()
for a in admins:
    print(f"admin: id={a[0]}, login={a[1]}, superadmin={a[2]}")
