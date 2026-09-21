import { getDeviceId } from '../utils/deviceId';

function detectBaseUrl() {
  const envBase = import.meta.env.VITE_API_BASE_URL;
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

class ApiService {
  constructor() {
    this.baseUrl = API_BASE_URL;
  }

  getToken() {
    return localStorage.getItem('dyndisplay_token');
  }

  setToken(token) {
    localStorage.setItem('dyndisplay_token', token);
  }

  clearToken() {
    localStorage.removeItem('dyndisplay_token');
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

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const token = this.getToken();

    const headers = {
      'Content-Type': 'application/json',
      'X-Device-Id': getDeviceId(),
      ...options.headers,
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const config = {
      ...options,
      headers,
    };

    try {
      const response = await fetch(url, config);

      if (response.status === 401) {
        this.clearToken();
        emitUnauthorized();
        return { data: null, status: 401, ok: false, error: 'Unauthorized' };
      }

      const data = await response.json();
      return { data, status: response.status, ok: response.ok };
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