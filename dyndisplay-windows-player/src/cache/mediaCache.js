/*
 * Cache local des médias.
 *
 * - Répertoire : %APPDATA%/dyndisplay-player/cache/media/<sftp_path>
 *   (p.ex. cache/media/images/1690000000_logo.png).
 * - URLs d'affichage : protocole custom `dyndisplay-media://local/<sftp_path>`
 *   servi par electron/main.js, clé = le `sftp_path` (field `filename`) de
 *   config.json — même convention que l'API web `/media/<sftp_path>`.
 * - Synchronisation delta : on ne télécharge que les fichiers absents ou
 *   modifiés (comparaison taille + mtime avec le fichier distant).
 */
import { remotePath } from '../sync/ftpClient.js';

const api = () => window.dyndisplay;

export function mediaCacheUrl(filename) {
  return `dyndisplay-media://local/${String(filename || '').replace(/\\/g, '/')}`;
}

export async function loadSyncedConfig() {
  try {
    return await api().cache.readConfig();
  } catch (err) {
    return null;
  }
}

export async function storeSyncedConfig(config) {
  try {
    await api().cache.writeConfig(config || {});
    return true;
  } catch (err) {
    return false;
  }
}

/**
 * Nombre de médias référencés par config.json absents du cache local.
 * Permet de relancer un téléchargement même si l'empreinte de config
 * n'a pas changé (cas : un premier sync a échoué, fichiers jamais obtenus).
 */
export async function missingMediaCount(config) {
  let missing = 0;
  const seen = new Set();
  for (const zone of (config?.zones || [])) {
    for (const m of (zone?.media_playlist || [])) {
      if (!m || !m.filename || !m.media_id || seen.has(m.filename)) continue;
      seen.add(m.filename);
      try {
        const exists = await api().cache.mediaExists(m.filename);
        if (!exists) missing += 1;
      } catch (err) {
        missing += 1;
      }
    }
  }
  return missing;
}

/**
 * S'assure qu'un média est présent en cache (delta). Conserve silencieusement
 * les médias qui existent déjà : la box continue d'afficher le dernier
 * contenu connu si le serveur/réseau tombe.
 */
export async function ensureMedia(conn, postCode, filename, onProgress) {
  if (!filename) return { ok: false, skipped: true };
  const normalized = String(filename).replace(/\\/g, '/');
  const sftpPath = remotePath(conn, `players/${postCode}/media/${normalized}`);

  const local = await api().cache.mediaLocalInfo(normalized);

  // Pas de fichier distant consultable → on garde l'existant (offline tolerant).
  const remote = await api().ftp.stat(conn, sftpPath);
  if (!remote.ok && local.exists) return { ok: true, cached: true };

  if (remote.ok) {
    const sameSize = local.exists && local.size === remote.size;
    const sameMtime = local.exists && Math.abs(local.mtimeMs - remote.mtimeMs) < 1500;
    if (sameSize && sameMtime) {
      if (onProgress) onProgress({ filename: normalized, status: 'uptodate' });
      return { ok: true, cached: true };
    }
  }

  const result = await api().ftp.downloadMedia(conn, postCode, normalized);
  if (result.ok) {
    if (onProgress) onProgress({ filename: normalized, status: 'downloaded' });
    return { ok: true, cached: result.downloaded === false };
  }
  // Échec réseau mais une copie locale existe → on continue avec la copie.
  if (local.exists) {
    if (onProgress) onProgress({ filename: normalized, status: 'offline-fallback' });
    return { ok: true, cached: true };
  }
  return { ok: false, filename, error: result.error };
}

/**
 * Télécharge (ou vérifie) tous les médias référencés dans config.json.
 * Retourne { downloaded, uptodate, failed } — les erreurs ne bloquent pas
 * l'affichage du dernier contenu connu.
 */
export async function syncMediaForConfig(conn, postCode, config, onProgress) {
  const files = [];
  for (const zone of (config?.zones || [])) {
    const playlist = zone?.media_playlist || [];
    for (const m of playlist) {
      if (m && m.filename && m.media_id) files.push(m);
    }
  }
  // Dédoublonnage par filename.
  const seen = new Set();
  const unique = files.filter((m) => {
    if (seen.has(m.filename)) return false;
    seen.add(m.filename);
    return true;
  });

  const stats = { downloaded: 0, uptodate: 0, failed: 0, files: unique.length };
  for (const m of unique) {
    const res = await ensureMedia(conn, postCode, m.filename, onProgress);
    if (res.ok) {
      if (res.cached) stats.uptodate += 1; else stats.downloaded += 1;
    } else {
      stats.failed += 1;
    }
  }
  return stats;
}