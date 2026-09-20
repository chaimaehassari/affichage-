/*
 * Config locale du player — stockée dans %APPDATA%/dyndisplay-player/config.json
 * (lecture/écriture via IPC, jamais de filesystem direct côté renderer).
 *
 * Champs métier (cf. STEP0_ANALYSE.md) :
 *  - siteCode      : référence libre (INUTILISÉ pour l'arborescence SFTP)
 *  - postCode      : code libre → construit players/<postCode>/config.json et .../media/*
 *  - serverHost    : IP du serveur (SFTP + heartbeat HTTP)
 *  - ftpPort       : port SFTP (backend = 22)
 *  - username / password : comptes SFTP
 *  - sftpRoot      : dossier racine SFTP (ex. "/C:/DYNDISPLAY-SFTP") ;
 *                    vide = relatif au dossier du compte SFTP
 *  - clientCode    : code client (tenant serveur, information uniquement ici)
 *  - apiPort       : port HTTP de l'API FastAPI (défaut 8000) pour le heartbeat
 *  - pollIntervalSec : intervalle de détection de changement de config.json (défaut 60 s)
 *  - syncTime      : heure quotidienne de synchro ("HH:MM", défaut 02:00)
 *  - showOverlays  : badges/couleurs fidèles à la prévisualisation web
 */
export const apiPortDefault = 8000;

const DEFAULT_CONFIG = {
  siteCode: '',
  postCode: '',
  serverHost: '',
  ftpPort: 22,
  username: '',
  password: '',
  sftpRoot: '',
  clientCode: '',
  apiPort: 8000,
  pollIntervalSec: 60,
  syncTime: '02:00',
  showOverlays: true,
};

const api = () => window.dyndisplay;

export async function loadLocalConfig() {
  try {
    const stored = await api().config.get();
    if (!stored || !stored.postCode || !stored.serverHost) return { ...DEFAULT_CONFIG };
    return { ...DEFAULT_CONFIG, ...stored };
  } catch (err) {
    return { ...DEFAULT_CONFIG };
  }
}

export async function saveLocalConfig(cfg) {
  const sanitized = { ...DEFAULT_CONFIG, ...(cfg || {}) };
  const saved = await api().config.set(sanitized);
  return { ...DEFAULT_CONFIG, ...saved };
}

export function isConfigured(cfg) {
  return !!(cfg && cfg.postCode && cfg.serverHost && cfg.username);
}