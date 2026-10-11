function detectBaseUrl() {
  // `?.` : import.meta.env n'existe pas hors Vite (tests Node), on reste
  // alors sur la même origine au lieu de lever une TypeError au chargement.
  const envBase = import.meta.env?.VITE_API_BASE_URL;
  if (envBase) return envBase.replace(/\/+$/, '');

  // Vide = même origine : le backend FastAPI sert l'API (et le frontend compilé en production).
  return '';
}

const API_BASE_URL = detectBaseUrl();

let unauthorizedListeners = new Set();
function emitUnauthorized() {
  unauthorizedListeners.forEach((l) => l());
}
export function subscribeUnauthorized(fn) {
  unauthorizedListeners.add(fn);
  return () => unauthorizedListeners.delete(fn);
}

const ACCESS_TOKEN_KEY = 'dyndisplay_token';
const REFRESH_TOKEN_KEY = 'dyndisplay_refresh_token';

class ApiService {
  constructor() {
    this.baseUrl = API_BASE_URL;
    // Promesse de renouvellement partagée : le verrou du refresh.
    // `null` = aucun renouvellement en cours. Toutes les requêtes qui
    // recoivent un 401 attendent LA MÊME promesse au lieu d'en déclencher
    // une chacune.
    this.refreshPromise = null;
    // Passe à true quand la session est close (échec définitif du refresh).
    // Évite que N requêtes en échec n'émettent N déconnexions.
    this.sessionClosed = false;
  }

  getToken() {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  }

  setToken(token) {
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
    this.sessionClosed = false;
  }

  getRefreshToken() {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  setRefreshToken(token) {
    if (token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  }

  clearToken() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  // Émet un token MÉDIA court vécu et scopé au fichier demandé (typ=media).
  // Ce token est inutilisable comme session : le token de session ne circule
  // jamais dans une URL (il n'est envoyé que dans l'en-tête Authorization).
  async getMediaToken(path) {
    const res = await this.post('/api/v1/media-token', { path });
    if (!res.ok || !res.data || !res.data.token) return null;
    return res.data.token;
  }

  // Construit l'URL signée d'un média (aperçus <img>/<video>/<a>).
  // Accepte un chemin nu (`sftp_path`) ou une URL complète `/media/<path>`.
  // Async : le jeton est minté à la demande, puis mis en cache côté rendu.
  async mediaUrl(pathLike) {
    if (!pathLike) return null;
    const p = String(pathLike).replace(/^\/media\//, '').replace(/^\/+/, '');
    if (!p) return null;
    const token = await this.getMediaToken(p);
    if (!token) return null;
    return `${this.baseUrl}/media/${p}?token=${encodeURIComponent(token)}`;
  }

  // Un 401 NE signifie pas forcément « session expirée » : deux endpoints le
  // renvoient pour un refus métier (mot de passe d'accès faux sur
  // /settings/verify-access). Dans ces cas le token est valide et l'effacer
  // déconnecterait l'utilisateur alors qu'il vient de taper un mauvais mot
  // de passe. On ne peut pas tester « detail est une chaîne » : /auth/login
  // et la dépendance d'authentification renvoient aussi `detail` en texte
  // pour une vraie erreur de session. D'où la liste explicite.
  static BUSINESS_401_PATHS = [
    '/api/v1/auth/login',
    '/api/v1/auth/refresh',
    '/api/v1/settings/verify-access',
  ];

  isBusinessRefusal(endpoint) {
    return ApiService.BUSINESS_401_PATHS.some(
      (e) => endpoint === e || endpoint.startsWith(`${e}?`)
    );
  }

  // Lecture UNIQUE du `exp` du jeton d'accès, sans vérification de signature :
  // le serveur reste seul juge de la validité, on sert seulement à décider
  // d'un renouvellement AVANT d'envoyer. Retourne false pour un jeton qui n'est
  // pas un JWT (opaque, hors tests) : on garde alors le comportement réactif.
  isAccessTokenExpired(token) {
    if (!token) return false;
    try {
      const segment = String(token).split('.')[1];
      if (!segment) return false;
      const b64 = segment.replace(/-/g, '+').replace(/_/g, '/');
      const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
      const { exp } = JSON.parse(atob(padded));
      if (typeof exp !== 'number') return false;
      // 5 s d'avance : une requête partie juste à la limite de validité
      // serait refusée au niveau réseau alors qu'on pouvait la prévenir.
      return exp * 1000 <= Date.now() + 5000;
    } catch {
      return false;
    }
  }

  // Renouvellement PROACTIF : un access token expiré est renouvelé avant
  // l'envoi, au lieu d'attendre un 401. Sans cela, chaque ouverture d'onglet
  // avec un jeton de plus de 30 min produisait un 401 visible dans la console
  // (et dans les journaux serveur) même si la session se rétablissait ensuite.
  // Renvoie false si le renouvellement a échoué : l'appelant sait alors qu'un
  // second essai réactif est inutile.
  async refreshIfExpired() {
    const token = this.getToken();
    if (!token || !this.isAccessTokenExpired(token)) return true;
    if (!this.getRefreshToken()) return false;
    return this.refreshSession();
  }

  // Renouvellement UNIQUE et verrouillé. Si N requêtes reçoivent un 401 en
  // même temps, elles attendent toutes cette promesse : un seul appel à
  // /auth/refresh, pas N.
  async refreshSession() {
    if (this.refreshPromise) return this.refreshPromise;

    const refreshToken = this.getRefreshToken();
    if (!refreshToken) return false;

    this.refreshPromise = (async () => {
      try {
        const res = await fetch(`${this.baseUrl}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        if (!data?.access_token) return false;
        this.setToken(data.access_token);
        this.setRefreshToken(data.refresh_token || refreshToken);
        return true;
      } catch {
        return false;
      } finally {
        // On libère le verrou seulement à la fin, pour que tous les appels en
        // attente observent le même résultat (succès ou échec).
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  buildConfig(options, token) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return { ...options, headers };
  }

  async send(endpoint, options, token) {
    const response = await fetch(`${this.baseUrl}${endpoint}`, this.buildConfig(options, token));
    let payload = null;
    try {
      payload = await response.clone().json();
    } catch {
      payload = null;
    }
    return { response, payload };
  }

  // Clôture de session : un seul clearToken/emitUnauthorized pour toute la
  // rafale, les requêtes suivantes reutilisant le même verdict.
  closeSession() {
    if (this.sessionClosed) return;
    this.sessionClosed = true;
    this.clearToken();
    emitUnauthorized();
  }

  async request(endpoint, options = {}) {
    // `isRetry` interdit toute boucle : une requête rejouée après un refresh
    // qui échoue ne repart pas une troisième fois.
    const isRetry = options.__isRetry === true;
    const sendOptions = { ...options };
    delete sendOptions.__isRetry;

    // Jeton déjà expiré AVANT l'envoi : on renouvelle d'abord, la requête
    // part alors directement avec un jeton frais — aucun 401 sur le chemin.
    //   null    : jeton encore valide (ou jeton opaque), rien fait ;
    //   true    : renouvellement proactive réussi ;
    //   false   : renouvellement impossible (échec ou pas de refresh token).
    let proactivelyRenewed = null;
    if (!isRetry && !this.isBusinessRefusal(endpoint)) {
      const token = this.getToken();
      if (token && this.isAccessTokenExpired(token)) {
        proactivelyRenewed = await this.refreshIfExpired();
      }
    }

    try {
      const { response, payload } = await this.send(endpoint, sendOptions, this.getToken());

      if (response.status === 401 && !this.isBusinessRefusal(endpoint)) {
        // `proactivelyRenewed !== null` = on a déjà tenté le renouvellement
        // pour CETTE requête : on ne le retente pas. Un jeton frais refusé est
        // un refus définitif, tout comme un renouvellement qui a échoué.
        if (!isRetry && proactivelyRenewed === null) {
          // Le token est peut-être simplement expiré (30 min). On tente UN
          // renouvellement, verrouillé, puis on rejoue CETTE requête avec le
          // nouveau token. Le token n'est effacé qu'en cas d'échec définitif :
          // l'effacer au premier 401 transformait une seule erreur en dizaines,
          // car toutes les requêtes déjà en vol partaient ensuite sans header.
          const refreshed = await this.refreshSession();
          if (refreshed) {
            return this.request(endpoint, { ...sendOptions, __isRetry: true });
          }
        }
        // Échec définitif : plus de refresh possible (échec du renouvellement),
        // ou le tokenFRAIS vient d'être refusé. Dans les deux cas la session
        // est terminée. Si une autre requête a déjà déclenché la déconnexion,
        // on n'émet pas un second événement (une rafale de N requêtes échouées
        // ne doit produire qu'un seul logout).
        this.closeSession();
      }

      return {
        data: payload,
        status: response.status,
        ok: response.ok,
        error: response.status === 401 ? 'Unauthorized' : undefined,
      };
    } catch (error) {
      return { data: null, status: 0, ok: false, error: error.message };
    }
  }

  async get(endpoint) {
    return this.request(endpoint);
  }

  async post(endpoint, body) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async put(endpoint, body) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async delete(endpoint) {
    return this.request(endpoint, {
      method: 'DELETE',
    });
  }

  async healthCheck() {
    return this.get('/api/health');
  }
}

export function extractDetailMessage(detail, fallback = 'Une erreur est survenue.') {
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg || JSON.stringify(d)).filter(Boolean).join('; ');
  }
  if (typeof detail === 'object' && detail.msg) return detail.msg;
  return fallback;
}

export const apiService = new ApiService();
export default apiService;