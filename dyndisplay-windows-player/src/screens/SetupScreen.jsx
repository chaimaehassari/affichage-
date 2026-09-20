/*
 * Écran de configuration du player (installation + paramètres cachés).
 *
 * Premier lancement : affiché une seule fois. Ensuite, accessible
 * uniquement par le raccourci caché Ctrl+Alt+Shift+P (géré dans
 * electron/main.js) — jamais par un clic normal en mode kiosque.
 *
 * Les valeurs collectées correspondent au contrat réel du serveur
 * (STEP0_ANALYSE.md) :
 *   - le « code poste » construit l'arborescence SFTP players/<code>/...
 *   - le heartbeat HTTP utilise serverHost + apiPort (défaut 8000).
 *   - le port SFTP par défaut est 22 (le backend utilise SFTP/paramiko,
 *     pas du FTP classique en 21).
 */
import { useState } from 'react';
import { apiPortDefault } from '../config/localConfig.js';
import { testConnection } from '../sync/ftpClient.js';

export default function SetupScreen({
  initial = null,
  onSaved,
  onCancel = null,
  standalone = false,
  overlays = true,
  onToggleOverlays = null,
  onSyncNow = null,
  syncing = false,
  syncStatus = null,
}) {
  const [form, setForm] = useState(() => ({
    siteCode: initial?.siteCode || '',
    postCode: initial?.postCode || '',
    serverHost: initial?.serverHost || '',
    ftpPort: initial?.ftpPort || 22,
    username: initial?.username || '',
    password: initial?.password || '',
    sftpRoot: initial?.sftpRoot || '',
    clientCode: initial?.clientCode || '',
    apiPort: initial?.apiPort || apiPortDefault,
    pollIntervalSec: initial?.pollIntervalSec || 60,
    syncTime: initial?.syncTime || '02:00',
    showOverlays: overlays,
  }));

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saving, setSaving] = useState(false);
  const [autostart, setAutostart] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const fieldsFilled =
    form.postCode.trim() && form.serverHost.trim() && form.username.trim();

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    const res = await testConnection(form);
    setTesting(false);
    setTestResult({ ok: res.ok, message: res.message });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSaved({ ...form });
    } finally {
      setSaving(false);
    }
  };

  const handleAutostartToggle = async () => {
    const next = !autostart;
    setAutostart(next);
    try {
      await window.dyndisplay.app.setAutostart(next);
    } catch (err) {
      setTestResult({ ok: false, message: `Auto-start non disponible : ${err.message}` });
    }
  };

  const field = (label, value, onChange, opts = {}) => (
    <label className="field">
      <span className="field-label">{label}</span>
      <input
        className="field-input"
        value={value}
        onChange={onChange}
        type={opts.type || 'text'}
        placeholder={opts.placeholder || ''}
        autoComplete="off"
      />
      {opts.hint && <span className="field-hint">{opts.hint}</span>}
    </label>
  );

  return (
    <div className="setup">
      <div className="setup-card">
        <h1 className="setup-title">DynDisplay Player</h1>
        <h2 className="setup-subtitle">
          {standalone && !initial?.postCode
            ? 'Configuration initiale du poste'
            : 'Paramètres du poste'}
        </h2>

        <div className="setup-grid">
          {field('Code site', form.siteCode, set('siteCode'), {
            hint: 'Libre (référence)',
          })}
          {field('Code poste', form.postCode, set('postCode'), {
            hint: 'Libre — dossier players/<code>/ sur le SFTP',
          })}
          {field('Adresse IP du serveur', form.serverHost, set('serverHost'), {
            hint: 'SFTP + heartbeat HTTP',
          })}
          {field('Port FTP/SFTP', form.ftpPort, set('ftpPort'), {
            hint: 'Défaut 22 (SFTP)',
          })}
          {field('Utilisateur FTP', form.username, set('username'))}
          {field('Mot de passe FTP', form.password, set('password'), {
            type: 'password',
          })}
          {field('Dossier racine SFTP', form.sftpRoot, set('sftpRoot'), {
            hint: 'ex. /C:/DYNDISPLAY-SFTP (vide = dossier du compte)',
          })}
          {field('Code client', form.clientCode, set('clientCode'), {
            hint: 'Tenant serveur (info)',
          })}
          {field('Port API HTTP', form.apiPort, set('apiPort'), {
            hint: 'Défaut 8000 (heartbeat)',
          })}
          {field('Poll (s)', form.pollIntervalSec, set('pollIntervalSec'), {
            hint: 'Intervalle de détection des changements',
          })}
          {field('Synchro quotidienne', form.syncTime, set('syncTime'), {
            hint: 'HH:MM',
          })}
        </div>

        <div className="setup-row">
          {!standalone && (
            <button className="btn" onClick={handleSave} disabled={saving || syncing}>
              {saving ? 'Enregistrement…' : 'Enregistrer'}
            </button>
          )}
          {!standalone && (
            <button className="btn btn-ghost" onClick={onCancel}>Fermer</button>
          )}
          <button className="btn" onClick={handleTest} disabled={testing || !fieldsFilled}>
            {testing ? 'Test en cours…' : 'Tester la connexion'}
          </button>
          {standalone && (
            <button
              className={`btn ${fieldsFilled ? 'btn-primary' : ''}`}
              onClick={handleSave}
              disabled={saving || !fieldsFilled || !!testResult === false}
            >
              {saving ? 'Enregistrement…' : 'Démarrer le player'}
            </button>
          )}
        </div>

        {testResult && (
          <p className={`setup-result ${testResult.ok ? 'ok' : 'ko'}`}>
            {testResult.ok ? '✓ ' : '✗ '}
            {testResult.message}
          </p>
        )}

        {!standalone && (
          <div className="setup-extra">
            <button className="btn btn-ghost" onClick={onSyncNow} disabled={syncing}>
              {syncing ? 'Synchronisation…' : 'Synchroniser maintenant'}
            </button>
            {syncStatus && (
              <span className="setup-result ok">
                {syncStatus.ok ? `✓ ${syncStatus.detail || 'OK'}` : `✗ ${syncStatus.error || 'échec'}`}
              </span>
            )}
          </div>
        )}

        {!standalone && (
          <div className="setup-extra">
            <label className="check">
              <input
                type="checkbox"
                checked={form.showOverlays}
                onChange={(e) => {
                  setForm((f) => ({ ...f, showOverlays: e.target.checked }));
                  if (onToggleOverlays) onToggleOverlays(e.target.checked);
                }}
              />
              Afficher les badges/couleurs comme la prévisualisation web
            </label>
            <button className="btn btn-ghost" onClick={handleAutostartToggle}>
              {autostart ? 'Auto-start : activé' : 'Activer l\'auto-start Windows'}
            </button>
            <button className="btn btn-danger" onClick={() => window.dyndisplay.app.quit()}>
              Quitter
            </button>
          </div>
        )}

        {standalone && (
          <p className="setup-foot">
            Après validation, le player synchronise <b>players/{form.postCode.trim() || '<poste>'}/config.json</b>
            {' '}et ses médias, puis démarre l'affichage kiosque en plein écran.
          </p>
        )}
      </div>
    </div>
  );
}