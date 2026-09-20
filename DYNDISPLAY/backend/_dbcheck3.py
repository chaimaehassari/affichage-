import psycopg

conn = psycopg.connect("postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY")

cur = conn.execute("SELECT profile_id, name, description, is_active FROM profiles ORDER BY profile_id")
for r in cur.fetchall():
    print("profile:", r)

cur = conn.execute("SELECT ac.admin_id, adm.login, adm.user_code, ac.client_code FROM admin_clients ac JOIN users adm ON adm.user_id = ac.admin_id ORDER BY ac.admin_id")
rows = cur.fetchall()
print("admin_clients rows:", len(rows))
for r in rows[:20]:
    print("ac:", r)