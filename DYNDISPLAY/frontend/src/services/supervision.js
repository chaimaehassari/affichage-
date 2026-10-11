import apiService from './api';

const PREFIX = '/api/v1';

export async function getSupervision() {
  return apiService.get(`${PREFIX}/supervision`);
}

export async function sendHeartbeat(postId) {
  return apiService.post(`${PREFIX}/posts/heartbeat`, { post_id: postId });
}

export async function pingPost(postId) {
  return apiService.post(`${PREFIX}/posts/${postId}/ping`);
}

// Ping automatique : un seul appel qui ping TOUS les postes du périmètre en
// parallèle côté backend. Volontairement pas une boucle de `pingPost` : chaque
// ping bloque le serveur jusqu'à 5 s, donc N appels simultanés satureraient le
// pool de connexions et le rechargement de page semblerait figé.
export async function pingAllPosts() {
  return apiService.post(`${PREFIX}/supervision/ping`);
}

// Rapport de diffusion : une ligne par box, sur TOUS les clients du périmètre
// de l'utilisateur (un admin de groupe voit ainsi tous ses clients). Le
// périmètre est imposé par le backend, jamais par un paramètre d'appel.
export async function getDiffusionReport(postId) {
  const params = postId ? `?post_id=${encodeURIComponent(postId)}` : '';
  return apiService.get(`${PREFIX}/supervision/diffusion-report${params}`);
}
