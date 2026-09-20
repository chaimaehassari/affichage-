import psycopg

conn = psycopg.connect("postgresql://postgres:chaimae@127.0.0.1:5433/DYNDISPLAY")

cur = conn.execute(
    "SELECT column_name FROM information_schema.columns WHERE table_name='general_settings' ORDER BY ordinal_position"
)
print("general_settings cols:", [r[0] for r in cur.fetchall()])

cur = conn.execute(
    "SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position"
)
print("users cols:", [r[0] for r in cur.fetchall()])

cur = conn.execute("SELECT login, is_superadmin, requires_activation, is_activated FROM users WHERE login IN ('admin','chaimae')")
for r in cur.fetchall():
    print("user row:", r)

cur = conn.execute("SELECT setting_key, setting_value FROM general_settings")
for r in cur.fetchall():
    print("gs:", r)