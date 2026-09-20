import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Save, Plus, Pencil, Trash2, Wifi, Folder, Key, Shield, Settings as SettingsIcon } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSettings, updateSettings, getFtpProfiles, createFtpProfile, updateFtpProfile, deleteFtpProfile, changePassword, updateLicenses, getAccountDevices, revokeDeviceAccount } from '../services/settings';
import { getClients, updateClientLicense } from '../services/admins';
import { extractDetailMessage } from '../services/api';
import SettingsAccessModal from '../components/SettingsAccessModal';
import FtpProfileModal from '../components/FtpProfileModal';
import TestFtpModal from '../components/TestFtpModal';
import LicenseModal from '../components/LicenseModal';
import ClientLicenseModal from '../components/ClientLicenseModal';
import ClientSettings from './ClientSettings';

export default function Settings() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const [authenticated, setAuthenticated] = useState(false);
  const [showAccessModal, setShowAccessModal] = useState(true);
  const [lastActivity, setLastActivity] = useState(Date.now());
  const [accessExpired, setAccessExpired] = useState(false);
  const SETTINGS_IDLE_TIMEOUT_MS = 15 * 60 * 1000;

  const [settings, setSettings] = useState(null);
  const [ftpProfiles, setFtpProfiles] = useState([]);
  const [devices, setDevices] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState(null);

  const [showFtpModal, setShowFtpModal] = useState(false);
  const [editingFtp, setEditingFtp] = useState(null);
  const [testingFtp, setTestingFtp] = useState(null);
  const [showLicenseModal, setShowLicenseModal] = useState(false);
  const [clients, setClients] = useState([]);
  const [licenseClient, setLicenseClient] = useState(null);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [smtpPassword, setSmtpPassword] = useState('');

  async function loadData() {
    setLoading(true);
    try {
      const [settingsRes, profilesRes, clientsRes] = await Promise.all([getSettings(), getFtpProfiles(), getClients()]);
      if (settingsRes.ok) setSettings(settingsRes.data);
      if (profilesRes.ok) setFtpProfiles(profilesRes.data);
      if (clientsRes.ok) setClients(clientsRes.data?.clients || []);
      if (user?.is_superadmin) {
        const devicesRes = await getAccountDevices();
        if (devicesRes.ok) setDevices(devicesRes.data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (authenticated) {
      loadData();
    }
  }, [authenticated]);

  useEffect(() => {
    if (!authenticated) return;
    const timer = setInterval(() => {
      if (Date.now() - lastActivity > SETTINGS_IDLE_TIMEOUT_MS) {
        setAuthenticated(false);
        setAccessExpired(true);
        setShowAccessModal(true);
      }
    }, 10000);
    return () => clearInterval(timer);
  }, [authenticated, lastActivity]);

  useEffect(() => {
    if (!authenticated) return;
    const reset = () => setLastActivity(Date.now());
    window.addEventListener('mousemove', reset);
    window.addEventListener('keydown', reset);
    window.addEventListener('click', reset);
    return () => {
      window.removeEventListener('mousemove', reset);
      window.removeEventListener('keydown', reset);
      window.removeEventListener('click', reset);
    };
  }, [authenticated]);

  async function handleSave() {
    setSaving(true);
    try {
      const payload = { ...settings };
      if (smtpPassword.trim()) {
        payload.smtp_password = smtpPassword;
      }
      const result = await updateSettings(payload);
      if (result.ok) {
        setSettings(result.data);
        setSmtpPassword('');
        setNotification({ type: 'success', text: 'Paramètres enregistrés.' });
      } else {
        setNotification({ type: 'error', text: 'Erreur lors de la sauvegarde.' });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    }
    setTimeout(() => setNotification(null), 3000);
    setSaving(false);
  }

  async function handleFtpSave(data) {
    if (editingFtp) {
      const result = await updateFtpProfile(editingFtp.profile_id, data);
      if (result.ok) {
        setFtpProfiles(prev => prev.map(p => p.profile_id === editingFtp.profile_id ? result.data : p));
      }
    } else {
      const result = await createFtpProfile(data);
      if (result.ok) {
        setFtpProfiles(prev => [...prev, result.data]);
      }
    }
    setShowFtpModal(false);
    setEditingFtp(null);
  }

  async function handleFtpDelete(id) {
    const result = await deleteFtpProfile(id);
    if (result.ok) {
      setFtpProfiles(prev => prev.filter(p => p.profile_id !== id));
    }
  }

  async function handleRevokeDevice(userId) {
    const result = await revokeDeviceAccount(userId);
    if (result.ok) {
      setNotification({ type: 'success', text: 'Appareil libéré. Le prochain appareil sera autorisé automatiquement.' });
      const devicesRes = await getAccountDevices();
      if (devicesRes.ok) setDevices(devicesRes.data);
    } else {
      const detail = result.data?.detail;
      setNotification({ type: 'error', text: typeof detail === 'string' && detail ? detail : 'Impossible de libérer cet appareil.' });
    }
    setTimeout(() => setNotification(null), 4000);
  }

  async function handleClientLicenseSave(client, sites, posts) {
    const res = await updateClientLicense(client.client_code, sites, posts);
    if (!res.ok) {
      const detail = res.data?.detail;
      throw new Error(typeof detail === 'string' && detail ? detail : 'Impossible de mettre à jour la licence.');
    }
    setClients(prev => prev.map(c => c.client_code === client.client_code ? { ...c, license_sites: sites, license_posts: posts } : c));
    setLicenseClient(null);
    setNotification({ type: 'success', text: 'Licences mises à jour.' });
    setTimeout(() => setNotification(null), 3000);
  }

  function updateField(field, value) {
    setSettings(prev => ({ ...prev, [field]: value }));
  }

  async function handleChangePassword() {
    if (!currentPassword || !newPassword) {
      setNotification({ type: 'error', text: 'Veuillez remplir tous les champs.' });
      setTimeout(() => setNotification(null), 3000);
      return;
    }
    if (newPassword !== confirmPassword) {
      setNotification({ type: 'error', text: 'Les mots de passe ne correspondent pas.' });
      setTimeout(() => setNotification(null), 3000);
      return;
    }
    setChangingPassword(true);
    try {
      const result = await changePassword(currentPassword, newPassword);
      if (result.ok) {
        setNotification({ type: 'success', text: 'Mot de passe modifié avec succès.' });
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        setNotification({ type: 'error', text: extractDetailMessage(result.data?.detail, 'Erreur lors du changement de mot de passe.') });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    }
    setTimeout(() => setNotification(null), 3000);
    setChangingPassword(false);
  }

  if (user?.profile_name !== 'Administrateur') {
    return <ClientSettings />;
  }

  if (showAccessModal) {
    return <SettingsAccessModal expired={accessExpired} onSuccess={() => { setAuthenticated(true); setLastActivity(Date.now()); setAccessExpired(false); setShowAccessModal(false); }} onCancel={() => navigate('/')} />;
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {showFtpModal && (
        <FtpProfileModal profile={editingFtp} onSave={handleFtpSave} onCancel={() => { setShowFtpModal(false); setEditingFtp(null); }} />
      )}
      {testingFtp && (
        <TestFtpModal profileId={testingFtp.profile_id} profileName={testingFtp.name} onClose={() => setTestingFtp(null)} />
      )}
      {showLicenseModal && (
        <LicenseModal
          currentSites={settings?.license_sites || 0}
          currentPosts={settings?.license_posts || 0}
          onUpdate={async (code, sites, posts) => {
            const res = await updateLicenses(code, sites, posts);
            if (!res.ok) {
              const detail = res.data?.detail;
              throw new Error(typeof detail === 'string' && detail ? detail : 'Code de licence invalide.');
            }
            setSettings(prev => ({
              ...prev,
              license_sites: sites,
              license_posts: posts,
              used_sites: res.data.used_sites ?? prev?.used_sites,
              used_posts: res.data.used_posts ?? prev?.used_posts,
            }));
            setShowLicenseModal(false);
            setNotification({ type: 'success', text: 'Licences mises à jour.' });
            setTimeout(() => setNotification(null), 3000);
          }}
          onCancel={() => setShowLicenseModal(false)}
        />
      )}
      {licenseClient && (
        <ClientLicenseModal
          client={licenseClient}
          onSave={(sites, posts) => handleClientLicenseSave(licenseClient, sites, posts)}
          onClose={() => setLicenseClient(null)}
        />
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">DynDisplay</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {user && <span className="text-[#a0a7b3] text-xs">{user.login} — {user.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        <NavBar />

        <main className="flex-1 px-8 py-6 overflow-y-auto">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <SettingsIcon className="w-5 h-5 text-[#f6c200]" />
                <h2 className="text-white text-lg font-semibold">Paramètres généraux</h2>
              </div>
              <div className="flex gap-3">
                <button onClick={() => navigate(-1)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
                <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <Save className="w-4 h-4 text-[#111418]" />
                  <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
                </button>
              </div>
            </div>

            {loading ? (
              <div className="flex items-center justify-center h-64">
                <div className="w-8 h-8 border-2 border-[#f6c200] border-t-transparent rounded-full animate-spin" />
              </div>
            ) : settings && (
              <div className="space-y-6">
                <Section title="Mot de passe">
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Mot de passe actuel</label>
                      <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Nouveau mot de passe</label>
                      <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Confirmer le mot de passe</label>
                      <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <button onClick={handleChangePassword} disabled={changingPassword}
                      className="flex items-center gap-2 px-4 py-2 text-sm text-[#f6c200] border border-[#f6c200]/30 rounded-lg hover:bg-[#f6c200]/10 transition-colors disabled:opacity-50">
                      <Key className="w-4 h-4" />
                      {changingPassword ? 'Modification...' : 'Changer le mot de passe'}
                    </button>
                  </div>
                </Section>

                <Section title="Licences">
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div className="bg-[#0f1217] border border-white/5 rounded-lg p-4">
                      <p className="text-xs text-[#a0a7b3] mb-1">Licences sites</p>
                      <p className="text-white text-2xl font-bold">
                        {settings.license_sites != null ? settings.license_sites : '—'}
                      </p>
                      <p className="text-xs text-[#a0a7b3] mt-1">
                        {settings.used_sites != null ? `${settings.used_sites} utilisés` : 'Utilisation inconnue'}
                      </p>
                    </div>
                    <div className="bg-[#0f1217] border border-white/5 rounded-lg p-4">
                      <p className="text-xs text-[#a0a7b3] mb-1">Licences postes</p>
                      <p className="text-white text-2xl font-bold">
                        {settings.license_posts != null ? settings.license_posts : '—'}
                      </p>
                      <p className="text-xs text-[#a0a7b3] mt-1">
                        {settings.used_posts != null ? `${settings.used_posts} utilisés` : 'Utilisation inconnue'}
                      </p>
                    </div>
                    <div className="bg-[#0f1217] border border-white/5 rounded-lg p-4">
                      <p className="text-xs text-[#a0a7b3] mb-1">Code client</p>
                      <p className="text-white font-mono text-lg truncate">{settings.code_client || '—'}</p>
                      <button
                        onClick={() => setShowLicenseModal(true)}
                        className="mt-1 text-xs text-[#f6c200] hover:text-[#ffdb4d] transition-colors flex items-center gap-1"
                      >
                        <Key className="w-3.5 h-3.5" /> Modifier les licences
                      </button>
                    </div>
                  </div>

                  {user?.is_superadmin && devices && (
                    <div className="mt-5">
                      <h4 className="text-xs text-[#a0a7b3] mb-3 uppercase tracking-wider">Comptes & appareils</h4>
                      <div className="overflow-x-auto rounded-lg border border-white/5">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="bg-[#0f1217] text-left text-xs text-[#a0a7b3]">
                              <th className="px-3 py-2.5 font-medium">Compte</th>
                              <th className="px-3 py-2.5 font-medium">Profil</th>
                              <th className="px-3 py-2.5 font-medium">Code client</th>
                              <th className="px-3 py-2.5 font-medium">Appareil</th>
                              <th className="px-3 py-2.5 font-medium">Activé le</th>
                              <th className="px-3 py-2.5 font-medium text-right">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-white/5">
                            {devices.accounts.length === 0 && (
                              <tr>
                                <td colSpan="6" className="px-3 py-4 text-center text-[#a0a7b3] text-xs">
                                  Aucun compte actif.
                                </td>
                              </tr>
                            )}
                            {devices.accounts.map(a => (
                              <tr key={a.user_id} className="hover:bg-white/[0.02]">
                                <td className="px-3 py-2.5 text-white">{a.login}</td>
                                <td className="px-3 py-2.5 text-[#a0a7b3]">{a.profile_name || '—'}</td>
                                <td className="px-3 py-2.5 text-[#a0a7b3] font-mono text-xs">{a.user_code || '—'}</td>
                                <td className="px-3 py-2.5 text-[#a0a7b3] font-mono text-xs">
                                  {a.requires_activation
                                    ? <span className="text-[#f6c200]">En attente d'activation</span>
                                    : a.authorized_device_id || '—'}
                                </td>
                                <td className="px-3 py-2.5 text-[#a0a7b3] text-xs">
                                  {a.activated_at ? a.activated_at.slice(0, 10) : '—'}
                                </td>
                                <td className="px-3 py-2.5 text-right">
                                  {a.authorized_device_id ? (
                                    <button
                                      onClick={() => handleRevokeDevice(a.user_id)}
                                      className="text-xs text-[#f6c200] hover:text-[#ffdb4d] border border-[#f6c200]/30 rounded px-2 py-1 transition-colors"
                                    >
                                      Libérer l'appareil
                                    </button>
                                  ) : (
                                    <span className="text-[#a0a7b3] text-xs">—</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </Section>

                <Section title="Clients (multi-tenant)">
                  <div className="overflow-x-auto rounded-lg border border-white/5">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-[#0f1217] text-left text-xs text-[#a0a7b3]">
                          <th className="px-3 py-2.5 font-medium">Code client</th>
                          <th className="px-3 py-2.5 font-medium">Nom</th>
                          <th className="px-3 py-2.5 font-medium">Admins</th>
                          <th className="px-3 py-2.5 font-medium">Sites</th>
                          <th className="px-3 py-2.5 font-medium">Postes/Comptes</th>
                          <th className="px-3 py-2.5 font-medium">Statut</th>
                          {user?.is_superadmin && <th className="px-3 py-2.5 font-medium text-right">Action</th>}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {clients.length === 0 ? (
                          <tr>
                            <td colSpan={user?.is_superadmin ? 7 : 6} className="px-3 py-4 text-center text-[#a0a7b3] text-xs">
                              Aucun client.
                            </td>
                          </tr>
                        ) : (
                          clients.map(c => {
                            const posts = c.license_posts;
                            const full = posts > 0 && c.user_count >= posts;
                            return (
                              <tr key={c.client_code} className="hover:bg-white/[0.02]">
                                <td className="px-3 py-2.5 text-white font-mono text-xs">{c.client_code}</td>
                                <td className="px-3 py-2.5 text-[#a0a7b3]">{c.client_name || '—'}</td>
                                <td className="px-3 py-2.5 text-[#a0a7b3] text-xs">
                                  {c.admin_login ? `${c.admin_login}${c.admin_code ? ` (${c.admin_code})` : ''}` : '—'}
                                </td>
                                <td className="px-3 py-2.5 text-white text-xs">{c.site_count}/{c.license_sites}</td>
                                <td className="px-3 py-2.5 text-white text-xs">{c.user_count}/{c.license_posts}</td>
                                <td className="px-3 py-2.5">
                                  {posts > 0 ? (
                                    full ? (
                                      <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-red-500/15 text-red-300 border border-red-500/30">
                                        Quota atteint
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/15 text-white border border-emerald-500/20">
                                        Disponible
                                      </span>
                                    )
                                  ) : (
                                    <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-zinc-500/15 text-white border border-zinc-500/20">
                                      Aucun poste
                                    </span>
                                  )}
                                </td>
                                {user?.is_superadmin && (
                                  <td className="px-3 py-2.5 text-right">
                                    <button
                                      onClick={() => setLicenseClient(c)}
                                      className="text-xs text-[#f6c200] hover:text-[#ffdb4d] border border-[#f6c200]/30 rounded px-2 py-1 transition-colors"
                                    >
                                      Appliquer licence
                                    </button>
                                  </td>
                                )}
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </Section>

                <Section title="Gestion des profils (FTP)">
                  <div className="space-y-3">
                    {ftpProfiles.map(p => (
                      <div key={p.profile_id} className="flex items-center justify-between p-3 bg-[#0f1217] border border-white/5 rounded-lg">
                        <div className="flex items-center gap-4">
                          <Wifi className="w-4 h-4 text-[#f6c200]" />
                          <div>
                            <p className="text-white text-sm font-medium">{p.name}</p>
                            <p className="text-[#a0a7b3] text-xs">{p.username}@{p.server_address}:{p.port} ({p.security_mode})</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => setTestingFtp(p)} className="text-xs text-[#a0a7b3] hover:text-green-400 transition-colors px-2 py-1">FTP TEST</button>
                          <button onClick={() => { setEditingFtp(p); setShowFtpModal(true); }} className="text-xs text-[#a0a7b3] hover:text-[#f6c200] transition-colors px-2 py-1">
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => handleFtpDelete(p.profile_id)} className="text-xs text-[#a0a7b3] hover:text-red-400 transition-colors px-2 py-1">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                    <button onClick={() => { setEditingFtp(null); setShowFtpModal(true); }}
                      className="flex items-center gap-2 px-3 py-2 text-sm text-[#a0a7b3] hover:text-[#f6c200] border border-dashed border-white/10 rounded-lg hover:border-[#f6c200]/30 transition-colors w-full justify-center">
                      <Plus className="w-4 h-4" /> Nouveau profil
                    </button>
                  </div>
                </Section>

                <Section title="Synchronisation automatique">
                  <div className="space-y-4">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input type="checkbox" checked={settings.sync_auto_enabled} onChange={e => updateField('sync_auto_enabled', e.target.checked)}
                        className="w-4 h-4 rounded border-white/20 bg-[#0f1217] text-[#f6c200] focus:ring-[#f6c200]/50" />
                      <span className="text-white text-sm">Activer la synchronisation automatique</span>
                    </label>
                    {settings.sync_auto_enabled && (
                      <div className="grid grid-cols-2 gap-4 pl-7">
                        <div>
                          <label className="block text-xs text-[#a0a7b3] mb-1">Mode</label>
                          <select value={settings.sync_auto_mode} onChange={e => updateField('sync_auto_mode', e.target.value)}
                            className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50">
                            <option value="txt">Partage TXT</option>
                            <option value="hfsql">HFSQL</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs text-[#a0a7b3] mb-1">Horaire</label>
                          <select value={settings.sync_auto_schedule} onChange={e => updateField('sync_auto_schedule', e.target.value)}
                            className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50">
                            <option value="realtime">Temps réel</option>
                            <option value="deferred">Différé</option>
                          </select>
                        </div>
                        {settings.sync_auto_schedule === 'deferred' && (
                          <div>
                            <label className="block text-xs text-[#a0a7b3] mb-1">Heure de déclenchement</label>
                            <input type="time" value={settings.sync_auto_time} onChange={e => updateField('sync_auto_time', e.target.value)}
                              className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                          </div>
                        )}
                        <div>
                          <label className="block text-xs text-[#a0a7b3] mb-1">Source des médias</label>
                          <select value={settings.media_source} onChange={e => updateField('media_source', e.target.value)}
                            className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50">
                            <option value="shared">Partagé (local)</option>
                            <option value="ftp">FTP (serveur distant)</option>
                          </select>
                        </div>
                      </div>
                    )}
                  </div>
                </Section>

                <Section title="Report des gros médias (affluence)">
                  <p className="text-[#a0a7b3] text-xs mb-4">
                    Pendant la plage d'affluence, les médias volumineux ne sont pas transférés lors d'une synchronisation.
                  </p>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Heure de début</label>
                      <input type="number" min="0" max="23" value={settings.affluence_start_hour}
                        onChange={e => updateField('affluence_start_hour', parseInt(e.target.value) || 0)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Heure de fin</label>
                      <input type="number" min="0" max="23" value={settings.affluence_end_hour}
                        onChange={e => updateField('affluence_end_hour', parseInt(e.target.value) || 0)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Seuil média volumineux (Mo)</label>
                      <input type="number" min="1" value={settings.affluence_media_threshold_mb}
                        onChange={e => updateField('affluence_media_threshold_mb', parseInt(e.target.value) || 1)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                  </div>
                </Section>

                <Section title="Verrouillage de session">
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1">
                      Verrouiller la session après X minutes d'inactivité (0 = désactivé)
                    </label>
                    <input type="number" min="0" value={settings.session_timeout_minutes}
                      onChange={e => updateField('session_timeout_minutes', parseInt(e.target.value) || 0)}
                      className="w-full max-w-xs px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                </Section>

                <Section title="E-mail (SMTP) — réinitialisation du mot de passe">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Serveur SMTP</label>
                      <input type="text" value={settings.smtp_host} onChange={e => updateField('smtp_host', e.target.value)}
                        placeholder="smtp.gmail.com" className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Port</label>
                      <input type="number" value={settings.smtp_port} onChange={e => updateField('smtp_port', parseInt(e.target.value) || 587)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Utilisateur</label>
                      <input type="text" value={settings.smtp_user} onChange={e => updateField('smtp_user', e.target.value)}
                        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Mot de passe SMTP</label>
                      <input type="password" value={smtpPassword} onChange={e => setSmtpPassword(e.target.value)}
                        placeholder="Laisser vide pour conserver" className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">Expéditeur</label>
                      <input type="text" value={settings.smtp_from} onChange={e => updateField('smtp_from', e.target.value)}
                        placeholder="noreply@exemple.com" className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                    <div>
                      <label className="block text-xs text-[#a0a7b3] mb-1">URL de base de l'application</label>
                      <input type="text" value={settings.app_base_url} onChange={e => updateField('app_base_url', e.target.value)}
                        placeholder="http://localhost:5173" className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                    </div>
                  </div>
                </Section>

                <Section title="Répertoire partagé des médias">
                  <div className="flex items-center gap-3">
                    <Folder className="w-4 h-4 text-[#a0a7b3]" />
                    <input type="text" value={settings.media_root_path} onChange={e => updateField('media_root_path', e.target.value)}
                      placeholder="C:\GestoDynDisplay\MEDIA"
                      className="flex-1 px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                </Section>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-5">
      <h3 className="text-[#f6c200] text-sm font-semibold uppercase tracking-wider mb-4 pb-2 border-b border-white/5">{title}</h3>
      {children}
    </div>
  );
}
