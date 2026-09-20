/*
 * Heartbeat de supervision.
 *
 * Rappel Étape 0 (STEP0_ANALYSE.md) :
 *   POST http://<serveur>:8000/api/v1/posts/heartbeat
 *   body : {"post_id": <int>}   (aucune auth)
 *   réponse : 200 {"message": "Heartbeat reçu."} | 404 si poste inconnu.
 *
 * Le seuil offline serveur = HEARTBEAT_OFFLINE_THRESHOLD_SECONDS = 90 s
 * (supervision_service.py:10). On garde une marge de sécurité : 60 s.
 * L'intervalle est rendu configurable mais ne doit jamais dépasser ~85 s.
 */
import { apiPortDefault } from '../config/localConfig.js';

const HEARTBEAT_INTERVAL_SECONDS = 60;
const MAX_SAFE_INTERVAL_SECONDS = 80;

let timer = null;
let stopped = false;

export function startHeartbeat({ getLocalConfig, getPostId, onStatus }) {
  stopHeartbeat();
  stopped = false;

  const run = async () => {
    if (stopped) return;
    const cfg = getLocalConfig();
    const postId = getPostId();
    if (!cfg || !cfg.serverHost || !postId) {
      if (onStatus) onStatus({ ok: false, reason: 'unauthorized', detail: 'post_id inconnu (sync en attente).' });
      return; // on retentera au prochain tick
    }
    const result = await window.dyndisplay.heartbeat.send({
      host: cfg.serverHost,
      apiPort: parseInt(cfg.apiPort, 10) || apiPortDefault,
      postId,
      timeoutMs: 8000,
    });
    if (onStatus) {
      onStatus({
        ok: result.ok,
        status: result.status,
        detail: result.ok ? 'Heartbeat reçu.' : (result.error || `HTTP ${result.status}`),
      });
    }
  };

  run();
  timer = setInterval(run, Math.min(HEARTBEAT_INTERVAL_SECONDS, MAX_SAFE_INTERVAL_SECONDS) * 1000);
}

export function stopHeartbeat() {
  stopped = true;
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

export function sendHeartbeatNow(opts) {
  return window.dyndisplay.heartbeat.send(opts);
}