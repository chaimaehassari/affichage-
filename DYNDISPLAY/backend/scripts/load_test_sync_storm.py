"""Test de charge reproduisant la tempête d'auto-sync.

Scénario : N postes actifs avec un job SCHEDULED échu chacun, laissés au
scheduler (15 s) pour promotion + exécution. Mesure pendant la vague :
  - nombre total de connexions PostgreSQL (pg_stat_activity),
  - connexions taggées gesto-sync / gesto-api,
  - latence de requêtes API normales durant la vague,
  - état de la file via GET /sync/load,
  - achèvement de tous les jobs (aucun perdu).

Usage : python scripts/load_test_sync_storm.py [N] [--keep]
N défaut = 60. Sans --keep, suppression des postes/jobs créés à la fin.
"""
import sys
import os
import time
import uuid
import threading

import psycopg
import requests

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)
for line in open(".env", encoding="utf-8"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

from tests._test_config import get_test_db_url

BASE_URL = "http://localhost:8000"
DB_URL = get_test_db_url()
KEEP = "--keep" in sys.argv
CSV_PATH = os.environ.get("STORM_CSV") or ""
N = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60
STORM_PREFIX = "LOADFTSTORM"

import secrets as _secrets
ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get("TEST_ADMIN_PASSWORD") or "admin123"


def _db():
    conn = psycopg.connect(DB_URL)
    conn.row_factory = psycopg.rows.dict_row
    return conn


def login():
    r = requests.post(f"{BASE_URL}/api/v1/auth/login",
                      json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD},
                      headers={"X-Device-Id": f"loadtest-{uuid.uuid4().hex[:8]}"}, timeout=10)
    if r.status_code != 200:
        raise SystemExit(f"login failed: {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def setup_post(job_conn, tag):
    code = f"{STORM_PREFIX}{tag}"
    site = job_conn.execute(
        "INSERT INTO sites (code, name, is_active, client_id) VALUES (%s, %s, TRUE, "
        "(SELECT id FROM clients ORDER BY id LIMIT 1)) RETURNING site_id",
        (code + "SITE", "Storm Site"),).fetchone()
    post = job_conn.execute(
        "INSERT INTO posts (site_id, code, name, is_active) VALUES (%s, %s, %s, TRUE) "
        "RETURNING post_id",
        (site["site_id"], code, "Storm Post")).fetchone()
    job = job_conn.execute(
        "INSERT INTO sync_jobs (post_id, status, scheduled_at) VALUES (%s, 'SCHEDULED', now() - interval '5 minutes') "
        "RETURNING sync_job_id",
        (post["post_id"],)).fetchone()
    return site["site_id"], post["post_id"], job["sync_job_id"]


def main():
    conn = _db()
    token = login()
    headers = {"Authorization": f"Bearer {token}", "X-Device-Id": f"loadtest-{uuid.uuid4().hex[:8]}"}
    monitor = _db()

    created = [setup_post(conn, f"{n:04d}") for n in range(N)]
    conn.commit()
    site_ids = [s for s, _, _ in created]
    post_ids = [p for _, p, _ in created]
    job_ids = [j for _, _, j in created]
    print(f"[storm] {N} postes actifs + {N} jobs SCHEDULED échus injectés (sites={site_ids[0]}..{site_ids[-1]})")

    baseline = monitor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()").fetchone()["count"]

    peak = {"total": 0, "sync": 0, "api": 0}
    samples = []
    api_latencies = []
    load_points = []
    stop = threading.Event()

    csv_f = open(CSV_PATH, "w", encoding="utf-8") if CSV_PATH else None
    if csv_f:
        csv_f.write("t,total,sync,api\n")

    def sampler():
        while not stop.is_set():
            try:
                rows = monitor.execute(
                    "SELECT application_name, count(*) c FROM pg_stat_activity "
                    "WHERE datname = current_database() GROUP BY application_name").fetchall()
                total = sum(r["c"] for r in rows)
                sync = next((r["c"] for r in rows if r["application_name"] == "gesto-sync"), 0)
                api = next((r["c"] for r in rows if r["application_name"] == "gesto-api"), 0)
                peak["total"] = max(peak["total"], total)
                peak["sync"] = max(peak["sync"], sync)
                peak["api"] = max(peak["api"], api)
                samples.append((time.monotonic(), total, sync, api))
                if csv_f:
                    csv_f.write(f"{time.monotonic():.3f},{total},{sync},{api}\n")
            except Exception as e:
                try:
                    monitor.rollback()
                except Exception:
                    pass
            # Échantillonnage très fin pour capturer les bursts brefs.
            time.sleep(0.002)
        if csv_f:
            csv_f.flush()
            csv_f.close()

    def api_latency():
        t0 = time.monotonic()
        try:
            r = requests.get(f"{BASE_URL}/api/v1/sync-jobs/{job_ids[0]}", headers=headers, timeout=10)
            api_latencies.append((time.monotonic() - t0, r.status_code))
            try:
                load_points.append(requests.get(f"{BASE_URL}/api/v1/sync/load", headers=headers, timeout=5).json())
            except Exception:
                pass
        except Exception as e:
            api_latencies.append((time.monotonic() - t0, 0))

    api_latency()

    th = threading.Thread(target=sampler, daemon=True)
    th.start()

    deadline = time.monotonic() + 240
    terminal = 0
    while time.monotonic() < deadline:
        statuses = monitor.execute(
            "SELECT status, count(*) c FROM sync_jobs WHERE sync_job_id = ANY(%s) GROUP BY status",
            (job_ids,)).fetchall()
        terminal = sum(r["c"] for r in statuses if r["status"] in ("COMPLETED", "FAILED"))
        api_latency()
        if terminal >= N:
            break
        time.sleep(0.2)

    stop.set()
    th.join(timeout=5)
    for row in statuses:
        print(f"[storm] status final : {row['status']}={row['c']}")

    first = samples[0][0] if samples else time.monotonic()
    duration = time.monotonic() - first if samples else 0
    ok_lat = [l for l in api_latencies if l[1] == 200]
    lat_vals = sorted(l for l, _ in ok_lat)
    p50 = lat_vals[len(lat_vals)//2] if lat_vals else 0.0
    p99 = lat_vals[int(len(lat_vals)*0.99)-1] if len(lat_vals) >= 20 else None
    print(f"[blitz] baseline_conns={baseline} peak_total={peak['total']} peak_sync={peak['sync']} peak_api={peak['api']}")
    print(f"[blitz] duree_vague~={duration:.1f}s jobs_terminal={terminal}/{N}")
    print(
        f"[blitz] API ok={len(ok_lat)}/{len(api_latencies)} p50={p50*1000:.0f}ms"
        + (f" p99={p99*1000:.0f}ms" if p99 is not None else " p99=n/a(<20 mesures)")
        if lat_vals else "[blitz] API: aucune reponse 200 pendant la vague!"
    )
    if load_points:
        last = load_points[-1]
        print(f"[blitz] /sync/load (fin) : running={last.get('running')} queued={last.get('queued')} "
              f"max_workers={last.get('max_workers')} active={last.get('active')} "
              f"submitted={last.get('submitted_total')} completed={last.get('completed')} failed={last.get('failed')}")

    if not KEEP:
        c = _db()
        c.execute("DELETE FROM sync_items WHERE sync_job_id = ANY(%s)", (job_ids,))
        c.execute("DELETE FROM sync_jobs WHERE sync_job_id = ANY(%s)", (job_ids,))
        c.execute("DELETE FROM posts WHERE post_id = ANY(%s)", (post_ids,))
        c.execute("DELETE FROM sites WHERE site_id = ANY(%s)", (site_ids,))
        c.commit()
        print(f"[storm] nettoyage : {N} postes/sites/jobs supprimés")
    else:
        print(f"[storm] {KEEP=} : les postes/jobs créés sont conservés (codes {STORM_PREFIX}*)")


if __name__ == "__main__":
    main()