/*
 * Preload — pont sécurisé (contextBridge) entre le renderer React et le
 * processus principal. Aucune API destructive (exécution d'arbitraire) n'est
 * exposée : uniquement des opérations métier du player.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('dyndisplay', {
  config: {
    get: () => ipcRenderer.invoke('config:get'),
    set: (cfg) => ipcRenderer.invoke('config:set', cfg),
  },
  paths: () => ipcRenderer.invoke('paths:get'),
  cache: {
    writeConfig: (cfg) => ipcRenderer.invoke('cache:write-config', cfg),
    readConfig: () => ipcRenderer.invoke('cache:read-config'),
    mediaExists: (relative) => ipcRenderer.invoke('cache:media-exists', relative),
    mediaLocalInfo: (relative) => ipcRenderer.invoke('cache:media-local-info', relative),
  },
  ftp: {
    test: (conn) => ipcRenderer.invoke('ftp:test', conn),
    stat: (conn, remotePath) => ipcRenderer.invoke('ftp:stat', { conn, remotePath }),
    fetchConfig: (conn, postCode) => ipcRenderer.invoke('ftp:fetch-config', { conn, postCode }),
    downloadMedia: (conn, postCode, filename) =>
      ipcRenderer.invoke('ftp:download-media', { conn, postCode, filename }),
  },
  heartbeat: {
    send: (hb) => ipcRenderer.invoke('heartbeat:send', hb),
  },
  app: {
    isDev: () => ipcRenderer.invoke('app:is-dev'),
    getAutostart: () => ipcRenderer.invoke('app:get-autostart'),
    setAutostart: (enabled) => ipcRenderer.invoke('app:set-autostart', enabled),
    quit: () => ipcRenderer.invoke('app:quit'),
    // Raccourci caché (Ctrl+Alt+Shift+P) géré côté main.
    onOpenSettings: (cb) => ipcRenderer.on('open-settings', () => cb()),
  },
});