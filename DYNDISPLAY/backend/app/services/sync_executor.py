"""Exécution bornée des jobs de synchronisation SFTP.

Remplace les ``threading.Thread(...).start()`` bruts qui existaient partout
(scheduler 15 s, POST /posts/{id}/sync, sync de groupe, sync média de groupe,
apply-configuration de groupe) : un job échu ne spawn plus son propre thread
ni sa propre connexion DB sans limite.

- Le nombre de threads d'exécution est borné par ``SYNC_MAX_WORKERS``,
  configurable par variable d'environnement (défaut 8) — voir Settings.
- Chaque worker prend sa connexion dans le pool dédié ``gesto-sync``
  (app.db.database.sync_pool), dimensionné à la même valeur : la limite est
  donc respectée de bout en bout (threads ET connexions simultanées).
- Les jobs au-delà de la limite attendent dans la file interne du
  ThreadPoolExecutor. Tant qu'ils sont « en file ou en cours » ils sont :
    * laissés PENDING/SCHEDULED (aucun nouveau statut inventé),
    * EXCLUS de la reprise des orphelins (recover_orphan_jobs) pour ne pas
      être faussement marqués FAILED avant d'avoir eu leur chance — le
      scheduler passe ``active_job_ids()`` en paramètre d'exclusion.
- ``snapshot()`` rend l'état de la file observable (endpoint /sync/load et
  log périodique du scheduler).
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.db.database import get_sync_connection
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_WORKERS = max(int(settings.SYNC_MAX_WORKERS or 8), 1)

# Fenêtre pendant laquelle un worker attend de voir le job committé avant de
# démarrer. L'appelant (route HTTP, apply_configuration_to_group applique la
# config de groupe dans UNE transaction commitée à la fin) peut soumettre le
# job AVANT que l'INSERT de sync_jobs ne soit committé : sans attente, un
# worker réveillé trop tôt lirait get_job() = None et sortirait sans rien
# faire = succès fantôme (compteur {completed} incrémenté, job PENDING figé).
JOB_COMMIT_WAIT_SECONDS = 5.0
JOB_COMMIT_POLL_SECONDS = 0.05


def run_sync_task(post_id: int, job_id: int, media_ids: list[int] | None = None) -> bool:
    """Runner commun à tous les chemins de sync.

    Ouvre la connexion via le pool dédié gesto-sync (jamais une connexion
    brute hors pool) : le nombre de connexions sync simultanées reste borné
    quelle que soit la famille d'appel.

    Garde anti-course : on attend que la ligne sync_jobs soit visible avant de
    lancer run_sync (voir JOB_COMMIT_WAIT_SECONDS). Si elle n'apparaît jamais,
    on rend False : le job est compté en échec par l'appelant (et sera repris
    par recover_orphan_jobs s'il existe réellement).
    """
    deadline = time.monotonic() + JOB_COMMIT_WAIT_SECONDS
    while True:
        try:
            with get_sync_connection() as conn:
                job = SyncService(conn).get_job(job_id)
        except Exception:
            job = None
        if job is not None:
            break
        if time.monotonic() >= deadline:
            logger.error(
                "Job %s (post %s) jamais visible après %ss — soumission fantôme, abandon",
                job_id, post_id, JOB_COMMIT_WAIT_SECONDS,
            )
            return False
        time.sleep(JOB_COMMIT_POLL_SECONDS)

    try:
        with get_sync_connection() as conn:
            SyncService(conn).run_sync(post_id, job_id, media_ids=media_ids)
        return True
    except Exception as e:
        logger.error("Sync task failed for job %s (post %s): %s", job_id, post_id, e, exc_info=True)
        return False


class BoundedSyncExecutor:
    """Borne la concurrence des syncs et observe la file d'attente."""

    def __init__(self, max_workers: int):
        self.max_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="sync-worker"
        )
        self._lock = threading.Lock()
        self._in_flight: dict[int, int] = {}
        self._running: set[int] = set()
        self._submitted = 0
        self._completed = 0
        self._failed = 0
        self._queue_peak = 0

    def submit(self, post_id: int, job_id: int, media_ids: list[int] | None = None) -> None:
        with self._lock:
            self._in_flight[job_id] = post_id
            self._submitted += 1
            self._queue_peak = max(self._queue_peak, len(self._in_flight) - len(self._running))
        self._executor.submit(self._execute, post_id, job_id, media_ids)

    def _execute(self, post_id: int, job_id: int, media_ids: list[int] | None) -> None:
        with self._lock:
            self._running.add(job_id)
        ok = False
        try:
            ok = run_sync_task(post_id, job_id, media_ids)
        except Exception:
            logger.exception("run_sync_task raised for job %s (post %s)", job_id, post_id)
        finally:
            with self._lock:
                self._running.discard(job_id)
                self._in_flight.pop(job_id, None)
                if ok:
                    self._completed += 1
                else:
                    self._failed += 1

    def active_job_ids(self) -> set[int]:
        """Jobs soumis mais pas encore terminés (en cours ou en file).

        Utilisé pour exclure ces jobs de la détection d'orphelins : un job
        légitimement en attente de sa place dans la file ne doit pas être
        marqué FAILED.
        """
        with self._lock:
            return set(self._in_flight)

    def snapshot(self) -> dict:
        with self._lock:
            running = len(self._running)
            queued = max(len(self._in_flight) - running, 0)
            return {
                "max_workers": self.max_workers,
                "running": running,
                "queued": queued,
                "active": len(self._in_flight),
                "submitted_total": self._submitted,
                "completed": self._completed,
                "failed": self._failed,
                "queue_peak": self._queue_peak,
                "in_flight_job_ids": sorted(self._in_flight),
            }

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


sync_executor = BoundedSyncExecutor(MAX_WORKERS)