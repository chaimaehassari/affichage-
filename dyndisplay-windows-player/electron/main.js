/*
 * DynDisplay Player — processus principal (Electron)
 *
 * ─── RAPPEL ÉTAPE 0 (cf. STEP0_ANALYSE.md pour le détail) ────────────────────
 * 1. Heartbeat  : POST {serveur}:8000/api/v1/posts/heartbeat, corps {"post_id": int},
 *                 NON authentifié. post_id = identifiant DB contenu dans config.json.
 * 2. Ping       : POST /posts/{id}/ping est un ping ICMP serveur → ip_address du poste
 *                 (commande système). Aucun endpoint local à exposer par la box, aucune
 *                 commande en attente à poller. Le player n'a aucune action réseau pour
 *                 le ping (juste autoriser ICMP dans le pare-feu Windows).
 * 3. config.json: fichiers lus sur SFTP sous players/<code_poste>/config.json et
 *                 players/<code_poste>/media/<sftp_path>. Champs : post_id, layout.zones
 *                 (coordonnées en %), zones[].media_playlist[] {media_id, name, media_type,
 *                 filename, duration_seconds, display_order}, loop_enabled, display_enabled.
 *                 PAS de url/pdf_pages/sync_auto_time dans le fichier FTP (voir §3c/§ouverts).
 *
 * Ce processus gère : fenêtre kiosque verrouillée, cycle de vie, watchdog, auto-start,
 * cache local, protocole dyndisplay-media:// (cache media), SFTP (ssh2-sftp-client),
 * heartbeat HTTP, raccourcis cachés.
 */

const { app, BrowserWindow, ipcMain, protocol, globalShortcut, net } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const { Readable } = require('stream');

let Client = null;
try {
  // ssh2-sftp-client est chargé uniquement au besoin (import tardif sympa pour le CI).
  Client = require('ssh2-sftp-client');
} catch (e) {
  // Les opérations FTP échoueront proprement si la dépendance manque.
  Client = null;
}

// ────────────────────────────────────────────────────────────────────────────
// Chemins de stockage local (%APPDATA%/dyndisplay-player)
// ────────────────────────────────────────────────────────────────────────────
function appRootDir() {
  return path.join(app.getPath('appData'), 'dyndisplay-player');
}
function localConfigPath() {
  return path.join(appRootDir(), 'config.json');
}
function cacheDir() {
  return path.join(appRootDir(), 'cache');
}
function mediaCacheDir() {
  return path.join(cacheDir(), 'media');
}
function syncedConfigPath() {
  return path.join(cacheDir(), 'last-config.json');
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function safeReadJson(file) {
  try {
    if (!fs.existsSync(file)) return null;
    const raw = fs.readFileSync(file, 'utf8');
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (err) {
    return null;
  }
}

function safeWriteJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
}

const isDev = () => process.env.NODE_ENV === 'development'
  || (process.env.VITE_DEV_SERVER_URL && !app.isPackaged);

// Protocole custom pour servir les médias du cache comme des URLs classiques.
// (évite les restrictions file:// et le nodeIntegration dans le renderer)
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'dyndisplay-media',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, bypassCSP: true },
  },
]);

// ────────────────────────────────────────────────────────────────────────────
// Helpers réseau / SFTP
// ────────────────────────────────────────────────────────────────────────────
function httpRequestJson(url, body, timeoutMs) {
  return new Promise((resolve) => {
    const mod = url.startsWith('https://') ? https : http;
    const reqOpts = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeout: timeoutMs || 8000,
    };
    const req = mod.request(url, reqOpts, (res) => {
      let raw = '';
      res.on('data', (c) => (raw += c));
      res.on('end', () => {
        let data = null;
        try { data = raw ? JSON.parse(raw) : null; } catch (e) { data = raw; }
        resolve({ ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data });
      });
    });
    req.on('error', (err) => resolve({ ok: false, status: 0, data: null, error: err.message }));
    req.on('timeout', () => { req.destroy(new Error('Timeout')); });
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

function buildSftp(conn, timeoutMs) {
  if (!Client) {
    throw new Error('ssh2-sftp-client indisponible (dépendance manquante).');
  }
  const sftp = new Client();
  const t = (conn && conn.timeoutSec) || 20;
  return sftp.connect({
    host: conn.host,
    port: conn.port || 22,
    username: conn.username || '',
    password: conn.password || '',
    readyTimeout: t * 1000,
  }).then(() => ({ sftpInstance: sftp, t }));
}

// Fermeture de connexion "best effort" : une erreur ici (ex. ECONNRESET levé par
// le serveur pendant le teardown) ne doit JAMAIS invalider le résultat obtenu.
async function closeSftp(sftpInstance) {
  if (!sftpInstance) return;
  try {
    await sftpInstance.end();
  } catch (err) {
    // nettoyage uniquement — on ignore.
  }
}

// Exécute fn(sftp) sur une connexion dédiée, avec un retry en cas d'erreur
// réseau transitoire (ECONNRESET / END_OF_FILE / ETIMEDOUT).
async function withSftp(conn, fn) {
  let attempt = 0;
  while (true) {
    attempt += 1;
    let sftpInstance = null;
    try {
      const s = await buildSftp(conn, conn.timeoutSec);
      sftpInstance = s.sftpInstance;
      const result = await fn(sftpInstance);
      await closeSftp(sftpInstance);
      return result;
    } catch (err) {
      await closeSftp(sftpInstance);
      if (attempt >= 2) throw err;
      const transient =
        err && (err.code === 'ECONNRESET' || err.code === 'END_OF_FILE' ||
          err.code === 'ETIMEDOUT' || err.code === 'ECONNREFUSED' ||
          ((err.message || '').indexOf('ECONNRESET') !== -1));
      if (!transient) throw err;
      await new Promise((r) => setTimeout(r, 500));
    }
  }
}

function getContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const map = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.bmp': 'image/bmp', '.webp': 'image/webp',
    '.svg': 'image/svg+xml', '.pdf': 'application/pdf',
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo',
  };
  return map[ext] || 'application/octet-stream';
}

function sanitizeRemote(remotePath) {
  return String(remotePath || '').replace(/^\/+/, '');
}

// Racine SFTP optionnelle (ex. "/C:/DYNDISPLAY-SFTP") préfixant le chemin distant.
function qualifyRemote(rootPath, relative) {
  const root = String(rootPath || '').trim().replace(/\/+$/, '');
  return root ? `${root}/${relative}` : relative;
}

// ────────────────────────────────────────────────────────────────────────────
// Fenêtre kiosque
// ────────────────────────────────────────────────────────────────────────────
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1920,
    height: 1080,
    fullscreen: true,
    autoHideMenuBar: true,
    frame: false,
    menuBarVisible: false,
    kiosk: !isDev(),
    backgroundColor: '#0b0d10',
    title: 'DynDisplay Player',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webSecurity: true,
      autoplayPolicy: 'no-user-gesture-required',
    },
  });

  mainWindow.setMenuBarVisibility(false);
  if (isDev()) mainWindow.webContents.openDevTools({ mode: 'detach' });

  if (isDev() && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // Verrouillage kiosque : pas de navigation, pas de popups.
  mainWindow.webContents.on('will-navigate', (e) => e.preventDefault());
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

  // Bloque les raccourcis dangereux en mode exposition.
  mainWindow.webContents.on('before-input-event', (event, input) => {
    const k = input.key.toLowerCase();
    const blocked =
      input.type === 'keyDown' &&
      (k === 'f5' ||
        k === 'f11' ||
        (input.control && (k === 'r' || k === 'shift')) ||
        (input.control && input.shift && k === 'i'));
    if (blocked) event.preventDefault();
  });

  // Watchdog — relance automatique si le renderer crashe.
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    if (details.reason && details.reason !== 'clean-exit') {
      setTimeout(() => {
        app.relaunch();
        app.exit(0);
      }, 500);
    }
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ────────────────────────────────────────────────────────────────────────────
// IPC — config locale
// ────────────────────────────────────────────────────────────────────────────
function registerIpc() {
  ipcMain.handle('config:get', () => safeReadJson(localConfigPath()));
  ipcMain.handle('config:set', (_e, cfg) => {
    safeWriteJson(localConfigPath(), cfg || {});
    return safeReadJson(localConfigPath());
  });

  ipcMain.handle('paths:get', () => ({
    appRoot: appRootDir(),
    cache: cacheDir(),
    mediaCache: mediaCacheDir(),
    localConfig: localConfigPath(),
    syncedConfig: syncedConfigPath(),
  }));

  ipcMain.handle('cache:write-config', (_e, cfg) => {
    safeWriteJson(syncedConfigPath(), cfg || {});
    return true;
  });
  ipcMain.handle('cache:read-config', () => safeReadJson(syncedConfigPath()));
  ipcMain.handle('cache:media-exists', (_e, relative) => {
    const rel = sanitizeRemote(relative);
    return fs.existsSync(path.join(mediaCacheDir(), rel));
  });
  ipcMain.handle('cache:media-local-info', (_e, relative) => {
    const rel = sanitizeRemote(relative);
    const p = path.join(mediaCacheDir(), rel);
    try {
      const st = fs.statSync(p);
      return { exists: true, size: st.size, mtimeMs: st.mtimeMs };
    } catch (err) {
      return { exists: false };
    }
  });

  // ── SFTP ─────────────────────────────────────────────────────────────────
  ipcMain.handle('ftp:test', async (_e, conn) => {
    try {
      await withSftp(conn, async () => {});
      return { ok: true, message: 'Connexion SFTP réussie.' };
    } catch (err) {
      return { ok: false, message: `Échec : ${err.code || err.message || err}` };
    }
  });

  ipcMain.handle('ftp:stat', async (_e, payload) => {
    // payload : { conn, remotePath } → retourne stat à distance
    try {
      const st = await withSftp(payload.conn, (sftp) => sftp.stat(payload.remotePath));
      return { ok: true, size: st.size, mtimeMs: (st.mtime || 0) * 1000 };
    } catch (err) {
      return { ok: false, error: err.message || String(err) };
    }
  });

  ipcMain.handle('ftp:fetch-config', async (_e, payload) => {
    // payload : { conn, postCode } → lit players/<postCode>/config.json
    try {
      const postCode = String(payload.postCode || '').trim();
      if (!postCode) return { ok: false, error: 'Code poste manquant.' };
      const remotePath = qualifyRemote(payload.conn?.rootPath, `players/${postCode}/config.json`);
      const result = await withSftp(payload.conn, async (sftp) => {
        const st = await sftp.stat(remotePath);
        const buf = await sftp.get(remotePath);
        return { st, buf };
      });
      let config = null;
      try {
        config = JSON.parse(result.buf.toString('utf8'));
      } catch (e) {
        return { ok: false, error: 'config.json distant illisible (JSON invalide).', code: 'BAD_JSON' };
      }
      safeWriteJson(syncedConfigPath(), config);
      return {
        ok: true,
        config,
        remote: { size: result.st.size, mtimeMs: (result.st.mtime || 0) * 1000 },
      };
    } catch (err) {
      return { ok: false, error: err.message || String(err), code: err.code || null };
    }
  });

  ipcMain.handle('ftp:download-media', async (_e, payload) => {
    // payload : { conn, postCode, filename } → players/<code>/media/<filename>
    //           téléversé dans <cache>/media/<filename> (delta géré par le renderer).
    try {
      const postCode = String(payload.postCode || '').trim();
      const filename = sanitizeRemote(payload.filename);
      if (!postCode || !filename) return { ok: false, error: 'Code poste ou nom de fichier manquant.' };
      const remotePath = qualifyRemote(payload.conn?.rootPath, `players/${postCode}/media/${filename}`);
      const localPath = path.join(mediaCacheDir(), filename);
      ensureDir(path.dirname(localPath));

      const size = await withSftp(payload.conn, async (sftp) => {
        const st = await sftp.stat(remotePath);
        if (fs.existsSync(localPath)) {
          const ls = fs.statSync(localPath);
          const sameMtime = Math.abs(ls.mtimeMs - (st.mtime || 0) * 1000) < 1500;
          if (sameMtime && ls.size === st.size) {
            return { downloaded: false, existing: true, size: st.size };
          }
        }
        await sftp.get(remotePath, localPath);
        return { downloaded: true, existing: false, size: st.size };
      });
      return { ok: true, downloaded: !size.existing, size: size.size };
    } catch (err) {
      return { ok: false, error: err.message || String(err) };
    }
  });

  // ── Heartbeat (POST /api/v1/posts/heartbeat — non authentifié) ───────────
  ipcMain.handle('heartbeat:send', async (_e, hb) => {
    const host = String(hb.host || '').replace(/^https?:\/\//i, '').trim();
    const port = hb.apiPort || 8000;
    const postId = hb.postId;
    if (!host || !postId) return { ok: false, status: 0, error: 'Host ou post_id manquant.' };
    const url = `http://${host}:${port}/api/v1/posts/heartbeat`;
    return httpRequestJson(url, { post_id: postId }, hb.timeoutMs || 8000);
  });

  // ── Auto-start Windows ────────────────────────────────────────────────────
  ipcMain.handle('app:get-autostart', () => app.getLoginItemSettings && app.getLoginItemSettings().openAtLogin);
  ipcMain.handle('app:set-autostart', (_e, enabled) => {
    if (app.setLoginItemSettings) {
      const opts = { openAtLogin: !!enabled, openAsHidden: true };
      if (app.isPackaged) opts.path = process.execPath;
      app.setLoginItemSettings(opts);
      return true;
    }
    return false;
  });

  ipcMain.handle('app:quit', () => { app.quit(); return true; });
  ipcMain.handle('app:is-dev', () => isDev());
}

// ────────────────────────────────────────────────────────────────────────────
// Cycle de vie
// ────────────────────────────────────────────────────────────────────────────
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    // Protocole dyndisplay-media://local/<relatif> → <cache>/media/<relatif>
    protocol.handle('dyndisplay-media', async (request) => {
      try {
        const url = new URL(request.url);
        const host = url.host;
        let rel = decodeURIComponent(url.pathname).replace(/^\/+/, '');
        if (host && !['local', 'media', 'localhost'].includes(host)) {
          rel = `${host}/${rel}`;
        }
        const root = path.resolve(mediaCacheDir());
        const file = path.resolve(path.join(mediaCacheDir(), rel.split('/').join(path.sep)));
        if (file !== root && !file.startsWith(root + path.sep)) {
          return new Response('Nope', { status: 403 });
        }
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
          return new Response('Not found', { status: 404 });
        }
        try {
          return await net.fetch(require('url').pathToFileURL(file).toString(), {
            headers: request.headers,
          });
        } catch (err) {
          // Repli : pas de support Range, mais l'affichage (image/vidéo courte) marche.
          const stream = Readable.toWeb(fs.createReadStream(file));
          return new Response(stream, {
            headers: { 'Content-Type': getContentType(file) },
          });
        }
      } catch (err) {
        return new Response('Bad request', { status: 400 });
      }
    });

    registerIpc();
    createWindow();

    // Raccourci caché : Ctrl+Alt+Shift+P ouvre l'écran Paramètres (jamais par clic en kiosque).
    globalShortcut.register('Control+Alt+Shift+P', () => {
      if (mainWindow) mainWindow.webContents.send('open-settings');
    });

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('will-quit', () => {
    globalShortcut.unregisterAll();
  });
}