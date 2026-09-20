/*
 * Réponse au ping serveur.
 *
 * ─── CONSTAT ÉTAPE 0 (STEP0_ANALYSE.md, §2) ─────────────────────────────────
 * POST /posts/{id}/ping (supervision.py:35, supervision_service.py:140)
 * est un **ping ICMP réel** exécuté par le serveur vers `posts.ip_address`
 * (commande système `ping`), avec mesure du RTT. Il est de plus protégé
 * (require_permission + scope).
 *
 * Conséquences :
 *  - La box NE doit PAS exposer d'endpoint HTTP local.
 *  - La box NE doit PAS interroger de « commande en attente » au heartbeat.
 *  - Le player n'a donc AUCUNE action réseau à effectuer pour répondre au
 *    ping : ce module est volontairement un no-op documenté.
 *
 * Seule contrainte technique : le poste Windows doit répondre aux requêtes
 * ICMP echo entrantes (autoriser ICMPv4 dans le Pare-feu Windows). C'est une
 * configuration du système, pas de l'application.
 */
export function handlePing() {
  // No-op intentionnel. Voir le commentaire ci-dessus.
  return { handled: false, reason: 'icmp-server-side' };
}

/**
 * Si un « ping applicatif » (commande serveur → box) était souhaité à terme,
 * il faudra le construire côté backend (nouveau canal pollé au heartbeat),
 * aucun mécanisme n'existe aujourd'hui — cf. STEP0_ANALYSE.md « points ouverts ».
 */
export function isAppPingSupported() {
  return false;
}