/*
 * Client SFTP du player — accès au serveur DynDisplay.
 *
 * Rappel Étape 0 (STEP0_ANALYSE.md) : le serveur écrit
 *   players/<code_poste>/config.json
 *   players/<code_poste>/media/<sftp_path>
 * via son propre job de synchronisation. Le player se connecte avec les
 * mêmes identifiants SFTP que le backend et lit uniquement ce qu'il doit.
 *
 * Chaque opération ouvre/ferme sa propre connexion SFTP (robuste, idempotente,
 * tolérante aux coupures du serveur). Le delta (nouveaux / modifiés
 * uniquement) est comparé dans mediaCache.js (taille + mtime).
 */
// Accès au pont ftp, avec repli si l'app tourne hors Electron (ex. navigateur).
function bridge() {
  const b = window.dyndisplay;
  if (!b || !b.ftp) {
    return {
      test: async () => ({ ok: false, message: "Pont Electron non disponible. Lancez l'application via Electron (npm run dev ou l'exe), pas dans un navigateur." }),
      stat: async () => ({ ok: false }),
      fetchConfig: async () => ({ ok: false, error: 'Pont Electron non disponible.', code: 'NO_BRIDGE' }),
      downloadMedia: async () => ({ ok: false, error: 'Pont Electron non disponible.', code: 'NO_BRIDGE' }),
    };
  }
  return b.ftp;
}

export function buildConn(cfg) {
  return {
    host: (cfg?.serverHost || '').trim(),
    port: parseInt(cfg?.ftpPort, 10) || 22,
    username: (cfg?.username || '').trim(),
    password: cfg?.password || '',
    rootPath: (cfg?.sftpRoot || '').trim().replace(/\/+$/, ''),
    timeoutSec: 20,
  };
}

/** Chemin distant complet = racine SFTP (si fournie) + chemin relatif. */
export function remotePath(conn, relative) {
  const root = conn?.rootPath || '';
  return root ? `${root}/${relative}` : relative;
}

export async function testConnection(cfg) {
  return bridge().test(buildConn(cfg));
}

/**
 * Récupère et enregistre config.json en cache.
 * @returns {Promise<{ok:boolean, config?:object, changed?:boolean,
 *                    remote?:object, error?:string}>}
 */
export async function fetchConfig(cfg, previousFingerprint) {
  const result = await bridge().fetchConfig(buildConn(cfg), cfg.postCode.trim());
  if (!result.ok || !result.config) {
    return { ok: false, error: result.error, code: result.code };
  }
  const fp = fingerprint(result.config);
  return {
    ok: true,
    config: result.config,
    remote: result.remote,
    changed: fp !== previousFingerprint,
    fingerprint: fp,
  };
}

/**
 * Empreinte stable des parties qui influent sur l'affichage/sync.
 * Le heartbeat a besoin de post_id ; la sync a besoin du contenu des
 * playlists. Une modification d'un seul média change l'empreinte → sync delta.
 */
export function fingerprint(config) {
  try {
    const zones = (config?.zones || []).map((z) => ({
      zone_number: z?.zone_number,
      playlist: (z?.media_playlist || []).map((m) => ({
        media_id: m?.media_id,
        media_type: m?.media_type,
        filename: m?.filename,
        duration_seconds: m?.duration_seconds,
        display_order: m?.display_order,
      })),
    }));
    return JSON.stringify({
      post_id: config?.post_id,
      code: config?.code,
      layout: config?.layout,
      zones,
      loop_enabled: config?.loop_enabled,
      display_enabled: config?.display_enabled,
    });
  } catch (err) {
    return '';
  }
}

export function playlistOf(config, zoneNumber) {
  const zone = (config?.zones || []).find((z) => z?.zone_number === zoneNumber);
  return zone?.media_playlist || (zone?.media ? [zone.media] : []);
}

export function activeZones(config) {
  return (config?.zones || []).filter((z) => {
    const layoutZone = (config?.layout?.zones || []).find((lz) => lz.zone_number === z.zone_number);
    return layoutZone !== undefined ? layoutZone.is_active : z.is_active;
  });
}