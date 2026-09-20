import psycopg

conn = psycopg.connect("postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY")
cur = conn.cursor()
cur.execute("SELECT setting_value FROM general_settings WHERE setting_key='license_posts'")
print("license_posts=", cur.fetchone())
cur.execute("SELECT COUNT(*) FROM users WHERE requires_activation=FALSE AND COALESCE(is_superadmin,FALSE)=FALSE")
print("activated=", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM users WHERE requires_activation=TRUE")
print("pending=", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM users")
print("total=", cur.fetchone()[0])
cur.execute(
    "SELECT login, is_superadmin, is_activated, requires_activation, authorized_device_id FROM users ORDER BY user_id LIMIT 25"
)
for r in cur.fetchall():
    print(r)
conn.close()