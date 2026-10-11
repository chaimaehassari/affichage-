import apiService from './api';

const PREFIX = '/api/v1';

export async function getLayouts() {
  return apiService.get(`${PREFIX}/layouts`);
}

// Cache module du lot « modèles + zones ». La requête étant unique et
// volumineuse (700+ modèles), on évite de la relancer à chaque focus.
let withZonesCache = null;
let withZonesCachedAt = 0;
let withZonesPromise = null;

// Fenêtre de fraîcheur : le cache évite la rafale, mais un modèle créé depuis
// un autre écran doit tout de même apparaître au prochain retour sur la page.
// Sans expiration, la liste resterait figée jusqu'au rechargement de l'onglet.
const CACHE_TTL_MS = 2 * 60 * 1000;

export function invalidateLayoutsCache() {
  withZonesCache = null;
  withZonesCachedAt = 0;
  withZonesPromise = null;
}

// Tous les modèles AVEC leurs zones, en une seule requête, servies depuis le
// cache. Remplace un GET /layouts puis un GET /layouts/{id} par modèle.
export async function getLayoutsWithZones() {
  const fresh = withZonesCache && Date.now() - withZonesCachedAt < CACHE_TTL_MS;
  if (fresh) return withZonesCache;
  // Requête déjà en vol : on la partage au lieu d'en lancer une seconde.
  if (withZonesPromise) return withZonesPromise;

  withZonesPromise = apiService
    .get(`${PREFIX}/layouts?include_zones=true`)
    .then(res => {
      // Un échec réseau ou un 401 ne doit PAS être mis en cache : sinon la
      // page resterait vide jusqu'à la prochaine modification, au lieu de
      // retenter au prochain focus.
      if (res.ok && Array.isArray(res.data)) {
        withZonesCache = res.data;
        withZonesCachedAt = Date.now();
        return withZonesCache;
      }
      return [];
    })
    .catch(() => [])
    .finally(() => {
      withZonesPromise = null;
    });

  return withZonesPromise;
}

export async function getLayout(id) {
  return apiService.get(`${PREFIX}/layouts/${id}`);
}

export async function createLayout(data) {
  const res = await apiService.post(`${PREFIX}/layouts`, data);
  if (res.ok) invalidateLayoutsCache();
  return res;
}

export async function updateLayout(id, data) {
  const res = await apiService.put(`${PREFIX}/layouts/${id}`, data);
  // Les zones du modèle viennent d'être modifiées : le cache du lot est périmé.
  if (res.ok) invalidateLayoutsCache();
  return res;
}

export async function deleteLayout(id) {
  const res = await apiService.delete(`${PREFIX}/layouts/${id}`);
  if (res.ok) invalidateLayoutsCache();
  return res;
}
