/**
 * Harnais de test pour le vrai `services/api.js` du frontend.
 *
 * On recharge le module à chaque test avec un localStorage en mémoire (donc
 * sans état résiduel), et on remplace le `fetch` global : c'est le seul point
 * d'entrée réseau du service, aussi bien pour les requêtes métier que pour
 * l'appel à /auth/refresh.
 */
import { installDomStubs } from './domStub.mjs';

const BASE = 'http://test.local';

export async function loadApiService(initialStore = {}) {
  installDomStubs();

  const store = { ...initialStore };
  globalThis.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
    clear: () => { for (const k of Object.keys(store)) delete store[k]; },
  };
  globalThis.window = {
    ...(globalThis.window || {}),
    localStorage: globalThis.localStorage,
    crypto: { randomUUID: () => 'test-device-id' },
  };

  // Import dynamique avec cache-busting : chaque test repart d'un module
  // neuf, donc d'un singleton `apiService` neuf ET d'un jeu d'abonnés
  // `subscribeUnauthorized` vide.
  const url = new URL('../../src/services/api.js', import.meta.url);
  const mod = await import(`${url.href}?t=${Date.now()}${Math.random()}`);
  const service = mod.default;
  service.baseUrl = BASE;
  return { service, mod, store };
}

export class FakeBackend {
  constructor() {
    this.refreshCalls = 0;
    this.layoutsListCalls = 0;
    this.layoutDetailCalls = 0;
    this.updateCalls = 0;
    this.createCalls = 0;
    this.deleteCalls = 0;
    // Nombre de réponses 401 réellement émises (cf. makeResponse).
    this.unauthorizedCount = 0;
    this.refreshStatus = 200;
    this.updateStatus = 200;
    // Charge utile renvoyée par GET /layouts?include_zones=true.
    this.layoutPayload = [];
    // Chaque refresh émet un jeton NEUVEAU et distinct : le client doit donc
    // le réécrire en session.
    this.issued = 0;
    this.currentAccessToken = 'NEW';
    this.validAccessTokens = new Set();
    // Si vrai, /layouts répond 401 même avec un jeton « valide » : sert à
    // vérifier que le client ne boucle pas sur son rejeu.
    this.alwaysRejectLayouts = false;
  }

  /** Simule l'expiration du jeton d'accès en cours de session. */
  expireCurrentAccessToken() {
    if (this.currentAccessToken) {
      this.validAccessTokens.delete(this.currentAccessToken);
    }
  }

  makeResponse(status, payload) {
    // Compteur global des 401 RÉELLEMENT émis par le serveur : permet de
    // distinguer « la requête est partie avec un jeton frais » (0) de
    // « le 401 a été subi puis réparé par un refresh » (>= 1).
    if (status === 401) this.unauthorizedCount += 1;
    // `clone()` doit renvoyer une réponse INDEPENDANTE : api.js fait
    // `response.clone().json()` pour lire le corps d'un 401 avant de
    // décider quoi en faire.
    const build = () => ({
      status,
      ok: status >= 200 && status < 300,
      clone: build,
      async json() { return payload; },
    });
    return build();
  }

  /** Remplace globalThis.fetch et retourne une fonction de restauration. */
  install() {
    const previous = globalThis.fetch;
    globalThis.fetch = (url, config = {}) => this.handle(String(url), config);
    return () => { globalThis.fetch = previous; };
  }

  handle(url, config = {}) {
    const endpoint = url.startsWith(BASE) ? url.slice(BASE.length) : url;
    const method = (config.method || 'GET').toUpperCase();
    const auth = (config.headers || {})['Authorization'] || '';
    const bearer = auth.startsWith('Bearer ') ? auth.slice(7) : null;
    const authorized = () => bearer && this.validAccessTokens.has(bearer);

    if (endpoint === '/api/v1/auth/refresh') {
      this.refreshCalls += 1;
      if (this.refreshStatus !== 200) {
        return Promise.resolve(
          this.makeResponse(this.refreshStatus, { detail: 'Refresh refusé.' }),
        );
      }
      this.issued += 1;
      const token = `NEW${this.issued}`;
      this.validAccessTokens.add(token);
      this.currentAccessToken = token;
      return Promise.resolve(this.makeResponse(200, {
        access_token: token,
        refresh_token: `REFRESH${this.issued + 1}`,
      }));
    }

    // Liste groupée des modèles avec leurs zones.
    if (endpoint.startsWith('/api/v1/layouts?include_zones')) {
      this.layoutsListCalls += 1;
      if (this.alwaysRejectLayouts || !authorized()) {
        return Promise.resolve(
          this.makeResponse(401, { detail: 'Token invalide ou expiré.' }),
        );
      }
      return Promise.resolve(this.makeResponse(200, this.layoutPayload));
    }

    const isLayoutCollection = endpoint === '/api/v1/layouts';
    const layoutDetail = endpoint.match(/^\/api\/v1\/layouts\/(\d+)$/);

    // Écritures : create / update / delete d'un modèle.
    if (isLayoutCollection && method === 'POST') {
      this.createCalls += 1;
      return Promise.resolve(
        this.makeResponse(this.updateStatus, { layout_id: 9999, zones: [] }),
      );
    }
    if (layoutDetail && method === 'PUT') {
      this.updateCalls += 1;
      if (this.updateStatus !== 200) {
        return Promise.resolve(
          this.makeResponse(this.updateStatus, { detail: 'Refusé.' }),
        );
      }
      return Promise.resolve(
        this.makeResponse(200, { layout_id: Number(layoutDetail[1]), zones: [] }),
      );
    }
    if (layoutDetail && method === 'DELETE') {
      this.deleteCalls += 1;
      return Promise.resolve(this.makeResponse(200, { message: 'Supprimé.' }));
    }

    // Liste simple (sans zones).
    if (isLayoutCollection) {
      this.layoutsListCalls += 1;
      if (!authorized()) {
        return Promise.resolve(
          this.makeResponse(401, { detail: 'Token invalide ou expiré.' }),
        );
      }
      return Promise.resolve(this.makeResponse(200, []));
    }

    // Détail unitaire, utilisé par LayoutEditor. Un id absent de
    // `layoutPayload` renvoie tout de même un modèle : le but de ces tests
    // est le comportement d'authentification, pas le 404 métier.
    if (layoutDetail) {
      this.layoutDetailCalls += 1;
      if (this.alwaysRejectLayouts || !authorized()) {
        return Promise.resolve(
          this.makeResponse(401, { detail: 'Token invalide ou expiré.' }),
        );
      }
      const id = Number(layoutDetail[1]);
      const found = this.layoutPayload.find((l) => l.layout_id === id);
      return Promise.resolve(this.makeResponse(200, found ?? {
        layout_id: id, name: `Modele ${id}`, is_active: true,
        active_zone_count: 0, zones: [],
      }));
    }

    if (endpoint.includes('verify-access')) {
      return Promise.resolve(
        this.makeResponse(401, { detail: "Mot de passe d'accès incorrect." }),
      );
    }

    return Promise.resolve(this.makeResponse(404, {}));
  }
}
