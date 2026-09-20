import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Save, RotateCcw, Eye, EyeOff } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import apiService from '../services/api';

const ZONES = [1, 2, 3, 4, 5, 6, 7, 8];

export default function UserForm() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const { logout, user: currentUser, canAccessZone, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState([]);
  const [admins, setAdmins] = useState([]);
  const [allPermissions, setAllPermissions] = useState([]);
  const [groupsList, setGroupsList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState(null);

  const [form, setForm] = useState({
    user_code: '',
    login: '',
    password: '',
    password_confirm: '',
    profile_id: '',
    admin_id: null,
    is_active: true,
    requires_activation: false,
    zones: [],
    groups: [],
    permissions: [],
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [resetForm, setResetForm] = useState({ new_password: '', password_confirm: '' });
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    async function init() {
      const [profilesRes, permsRes, groupsRes] = await Promise.all([
        apiService.get('/api/v1/users/profiles'),
        apiService.get('/api/v1/users/permissions'),
        apiService.get('/api/v1/groups'),
      ]);
      if (profilesRes.ok) setProfiles(profilesRes.data || []);
      if (permsRes.ok) setAllPermissions(permsRes.data || []);
      if (groupsRes.ok) setGroupsList(groupsRes.data || []);

      let adminList = [];
      if (isSuperAdmin) {
        const adminsRes = await apiService.get('/api/v1/admins');
        adminList = adminsRes.ok ? (adminsRes.data?.admins || []) : [];
        setAdmins(adminList);
      }

      if (isEdit) {
        const userRes = await apiService.get(`/api/v1/users/${id}`);
        if (userRes.ok && userRes.data) {
          const u = userRes.data;
          setForm({
            user_code: u.user_code || '',
            login: u.login,
            password: '',
            password_confirm: '',
            profile_id: u.profile_id,
            is_active: u.is_active,
            requires_activation: u.is_activated === false,
            admin_id: u.admin_id || '',
            admin_code: adminList.find(a => String(a.user_id) === String(u.admin_id))?.user_code || '',
            zones: (u.zones || []).filter(z => z.is_allowed).map(z => z.zone_number),
            permissions: (u.permissions || []).map(p => ({
              permission_id: p.permission_id,
              can_view: p.can_view,
              can_create: p.can_create,
              can_update: p.can_update,
              can_delete: p.can_delete,
            })),
          });
        }
      }
      setLoading(false);
    }
    init();
  }, [id, isEdit]);

  function updateField(key, value) {
    setForm(prev => {
      const next = { ...prev, [key]: value };
      if (key === 'profile_id') {
        const p = profiles.find(x => String(x.profile_id) === String(value));
        if (p && p.name === 'Administrateur') {
          next.admin_code = '';
          next.admin_id = '';
        }
      }
      return next;
    });
  }

  function resolveAdminCode(code) {
    const c = (code || '').trim().toUpperCase();
    if (!c) return null;
    return admins.find(a => String(a.user_code || '').toUpperCase() === c) || null;
  }

  function toggleZone(zone) {
    setForm(prev => {
      const zones = prev.zones.includes(zone) ? prev.zones.filter(z => z !== zone) : [...prev.zones, zone];
      return { ...prev, zones };
    });
  }

  function toggleAllZones(select) {
    const available = ZONES.filter(z => canAccessZone(z));
    setForm(prev => ({ ...prev, zones: select ? [...available] : [] }));
  }

  function updatePermission(permId, field, value) {
    setForm(prev => {
      const existing = prev.permissions.find(p => p.permission_id === permId);
      if (existing) {
        return { ...prev, permissions: prev.permissions.map(p => p.permission_id === permId ? { ...p, [field]: value } : p) };
      }
      return { ...prev, permissions: [...prev.permissions, { permission_id: permId, can_view: false, can_create: false, can_update: false, can_delete: false, [field]: value }] };
    });
  }

  function getPerm(permId) {
    return form.permissions.find(p => p.permission_id === permId) || { can_view: false, can_create: false, can_update: false, can_delete: false };
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setNotification(null);

    if (needsAdmin && form.admin_code.trim() && !resolvedAdmin) {
      setSaving(false);
      setNotification({ type: 'error', text: 'Code admin introuvable : saisissez un code admin existant.' });
      return;
    }

    const adminIdToSend = needsAdmin
      ? (resolvedAdmin ? resolvedAdmin.user_id : null)
      : (isSuperAdmin ? (form.admin_id || null) : (currentUser?.user_id || null));

    try {
      let result;
      if (isEdit) {
        const payload = {
          user_code: form.user_code,
          login: form.login,
          profile_id: parseInt(form.profile_id),
          is_active: form.is_active,
          requires_activation: form.requires_activation,
          admin_id: adminIdToSend,
          zones: form.zones,
          permissions: form.permissions,
        };
        result = await apiService.put(`/api/v1/users/${id}`, payload);
      } else {
        result = await apiService.post('/api/v1/users', {
          user_code: form.user_code,
          login: form.login,
          password: form.password,
          password_confirm: form.password_confirm,
          profile_id: parseInt(form.profile_id),
          is_active: form.is_active,
          requires_activation: form.requires_activation,
          admin_id: adminIdToSend,
          zones: form.zones,
          permissions: form.permissions,
        });
      }

      if (result.ok) {
        setNotification({ type: 'success', text: result.data?.message || 'Enregistré avec succès.' });
        setTimeout(() => navigate('/users'), 1500);
      } else {
        const msg = result.data?.detail || 'Erreur lors de l\'enregistrement.';
        setNotification({ type: 'error', text: Array.isArray(msg) ? msg.map(e => e.msg).join(', ') : msg });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    } finally {
      setSaving(false);
    }
  }

  async function handleResetPassword() {
    if (resetForm.new_password !== resetForm.password_confirm) {
      setNotification({ type: 'error', text: 'Les mots de passe ne correspondent pas.' });
      return;
    }
    setResetting(true);
    try {
      const result = await apiService.post(`/api/v1/users/${id}/reset-password`, {
        new_password: resetForm.new_password,
        password_confirm: resetForm.password_confirm,
      });
      if (result.ok) {
        setNotification({ type: 'success', text: 'Mot de passe réinitialisé.' });
        setShowResetModal(false);
        setResetForm({ new_password: '', password_confirm: '' });
      } else {
        const msg = result.data?.detail || 'Erreur.';
        setNotification({ type: 'error', text: Array.isArray(msg) ? msg.map(e => e.msg).join(', ') : msg });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    } finally {
      setResetting(false);
    }
  }

  const menuPerms = allPermissions.filter(p => ['menu_conception', 'menu_sync', 'menu_media', 'menu_config'].includes(p.code));
  const userPerms = allPermissions.filter(p => ['user_list', 'user_create', 'user_update', 'user_delete'].includes(p.code));
  const sitePerms = allPermissions.filter(p => ['list_sites_posts', 'create_site', 'update_site', 'delete_site', 'create_post', 'update_post', 'delete_post'].includes(p.code));
  const selectedProfile = profiles.find(p => String(p.profile_id) === String(form.profile_id))?.name || '';
  const needsAdmin = isSuperAdmin && selectedProfile && selectedProfile !== 'Administrateur';
  const resolvedAdmin = needsAdmin ? resolveAdminCode(form.admin_code) : null;

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0d10] flex items-center justify-center">
        <span className="text-[#a0a7b3] text-sm">Chargement...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0" style={{ backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 60px, rgba(255,255,255,0.01) 60px, rgba(255,255,255,0.01) 61px, transparent 61px, transparent 120px), repeating-linear-gradient(-45deg, transparent 0px, transparent 60px, rgba(246,194,0,0.02) 60px, rgba(246,194,0,0.02) 61px, transparent 61px, transparent 120px)` }} />
        <div className="absolute inset-0" style={{ backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 200px, rgba(246,194,0,0.04) 200px, rgba(246,194,0,0.04) 201px, transparent 201px, transparent 400px)` }} />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {showResetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-2">Réinitialiser le mot de passe</h3>
            <p className="text-[#a0a7b3] text-xs mb-4">
              Définissez un mot de passe temporaire pour cet utilisateur. Il ne vous sera pas
              possible de connaître l'ancien mot de passe, et l'utilisateur devra le modifier
              lors de sa prochaine connexion.
            </p>
            <div className="space-y-3">
              <input type="password" placeholder="Nouveau mot de passe" value={resetForm.new_password} onChange={(e) => setResetForm(p => ({ ...p, new_password: e.target.value }))}
                className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              <input type="password" placeholder="Confirmer le mot de passe" value={resetForm.password_confirm} onChange={(e) => setResetForm(p => ({ ...p, password_confirm: e.target.value }))}
                className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button onClick={() => setShowResetModal(false)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
              <button onClick={handleResetPassword} disabled={resetting} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                <span className="text-[#111418]">{resetting ? 'En cours...' : 'Réinitialiser'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Header */}
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">DynDisplay</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {currentUser && <span className="text-[#a0a7b3] text-xs">{currentUser.login} — {currentUser.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        {/* Menu bar */}
        <NavBar />

        {/* Content */}
        <main className="flex-1 px-8 py-6 overflow-y-auto">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <button onClick={() => navigate('/users')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                  <ArrowLeft className="w-4 h-4" /> Retour
                </button>
                <h2 className="text-white text-lg font-semibold">{isEdit ? 'Modifier l\'utilisateur' : 'Nouvel utilisateur'}</h2>
              </div>
              {isEdit && (
                <button onClick={() => setShowResetModal(true)} className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg hover:bg-white/5 transition-colors">
                  <RotateCcw className="w-3.5 h-3.5" /> Réinitialiser le mot de passe
                </button>
              )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Section 1: Authentification */}
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-6">
                <h3 className="text-[#f6c200] text-sm font-semibold uppercase tracking-wider mb-4 pb-2 border-b border-white/5">Authentification</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1.5">Code client</label>
                    <input type="text" value={form.user_code} onChange={(e) => updateField('user_code', e.target.value)}
                      placeholder="Code attribué au client"
                      className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1.5">Login <span className="text-red-400">*</span></label>
                    <input type="text" value={form.login} onChange={(e) => updateField('login', e.target.value)} required
                      className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
<div>
                        <label className="block text-xs text-[#a0a7b3] mb-1.5">Profil <span className="text-red-400">*</span></label>
                        <select value={form.profile_id} onChange={(e) => updateField('profile_id', e.target.value)} required
                          className="w-full bg-[#1a1f24] text-white px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50 appearance-none">
                          <option value="">-- Sélectionner --</option>
                          {profiles.map(p => <option key={p.profile_id} value={p.profile_id}>{p.name}</option>)}
                        </select>
                      </div>
                      {needsAdmin && (
                        <div>
                          <label className="block text-xs text-[#a0a7b3] mb-1.5">Code Admin</label>
                          <input type="text" value={form.admin_code}
                            onChange={(e) => {
                              const code = e.target.value;
                              const matched = resolveAdminCode(code);
                              setForm(prev => ({ ...prev, admin_code: code, admin_id: matched ? matched.user_id : '' }));
                            }}
                            placeholder="Code admin responsable"
                            className={`w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border text-sm focus:outline-none focus:border-[#f6c200]/50 ${form.admin_code.trim() && !resolvedAdmin ? 'border-red-500/60' : 'border-white/10'}`} />
                          {form.admin_code.trim() && !resolvedAdmin && (
                            <p className="text-[11px] text-red-400 mt-1">Code admin introuvable : saisissez un code admin existant.</p>
                          )}
                          {resolvedAdmin && (
                            <p className="text-[11px] text-green-400 mt-1">✓ Admin : {resolvedAdmin.user_code || ''}{resolvedAdmin.login ? ` — ${resolvedAdmin.login}` : ''}</p>
                          )}
                        </div>
                      )}
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1.5">Statut</label>
                    <div className="flex items-center gap-3 py-2.5">
                      <button type="button" onClick={() => updateField('is_active', !form.is_active)}
                        className={`w-10 h-5 rounded-full transition-colors relative ${form.is_active ? 'bg-[#f6c200]' : 'bg-[#2a2f36]'}`}>
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.is_active ? 'left-5.5 translate-x-0' : 'left-0.5'}`} />
                      </button>
                      <span className="text-sm text-white">{form.is_active ? 'Actif' : 'Inactif'}</span>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1.5">Compte à activer par un code de sérialisation</label>
                    <div className="flex items-center gap-3 py-2.5">
                      <button type="button" onClick={() => updateField('requires_activation', !form.requires_activation)}
                        className={`w-10 h-5 rounded-full transition-colors relative ${form.requires_activation ? 'bg-[#f6c200]' : 'bg-[#2a2f36]'}`}>
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.requires_activation ? 'left-5.5 translate-x-0' : 'left-0.5'}`} />
                      </button>
                      <span className="text-sm text-white">{form.requires_activation ? 'Oui' : 'Non'}</span>
                    </div>
                    {form.requires_activation && (
                      <p className="text-[11px] text-[#f6c200]">Le client devra saisir son code de sérialisation avant de pouvoir accéder à l'application.</p>
                    )}
                  </div>
                  {!isEdit && (
                    <>
                      <div className="relative">
                        <label className="block text-xs text-[#a0a7b3] mb-1.5">Mot de passe <span className="text-red-400">*</span></label>
                        <div className="relative">
                          <input type={showPassword ? 'text' : 'password'} value={form.password} onChange={(e) => updateField('password', e.target.value)} required
                            className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] px-3 py-2.5 pr-10 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                          <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a0a7b3] hover:text-white transition-colors">
                            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                      <div className="relative">
                        <label className="block text-xs text-[#a0a7b3] mb-1.5">Confirmation <span className="text-red-400">*</span></label>
                        <div className="relative">
                          <input type={showConfirm ? 'text' : 'password'} value={form.password_confirm} onChange={(e) => updateField('password_confirm', e.target.value)} required
                            className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] px-3 py-2.5 pr-10 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                          <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a0a7b3] hover:text-white transition-colors">
                            {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Section 2: Autorisations */}
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-6">
                <h3 className="text-[#f6c200] text-sm font-semibold uppercase tracking-wider mb-4 pb-2 border-b border-white/5">Autorisations</h3>

                {/* Zones */}
                <div className="mb-6">
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-xs text-[#a0a7b3] font-medium uppercase tracking-wider">Zones d'affichage</label>
                    <div className="flex gap-2">
                      <button type="button" onClick={() => toggleAllZones(true)} className="text-xs text-[#f6c200] hover:underline">Tout sélectionner</button>
                      <span className="text-[#a0a7b3] text-xs">|</span>
                      <button type="button" onClick={() => toggleAllZones(false)} className="text-xs text-[#a0a7b3] hover:text-white hover:underline">Tout désélectionner</button>
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-3">
                    {ZONES.filter(z => canAccessZone(z)).map(z => (
                      <label key={z} className="flex items-center gap-2 cursor-pointer group">
                        <input type="checkbox" checked={form.zones.includes(z)} onChange={() => toggleZone(z)}
                          className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                        <span className="text-sm text-[#a0a7b3] group-hover:text-white transition-colors">Zone {z}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Menus */}
                <div className="mb-6">
                  <label className="block text-xs text-[#a0a7b3] font-medium uppercase tracking-wider mb-3">Menus</label>
                  <div className="space-y-2">
                    {menuPerms.map(p => {
                      const perm = getPerm(p.permission_id);
                      return (
                        <div key={p.permission_id} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                          <span className="text-sm text-white">{p.name}</span>
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={perm.can_view} onChange={(e) => updatePermission(p.permission_id, 'can_view', e.target.checked)}
                              className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                            <span className="text-xs text-[#a0a7b3]">Accès</span>
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Gestion utilisateurs */}
                <div className="mb-6">
                  <label className="block text-xs text-[#a0a7b3] font-medium uppercase tracking-wider mb-3">Gestion utilisateurs</label>
                  <div className="bg-[#0f1217] border border-white/5 rounded-lg p-4">
                    <span className="text-xs text-white font-medium block mb-3">Liste des utilisateurs</span>
                    <div className="grid grid-cols-2 gap-2">
                      {userPerms.map(p => {
                        const perm = getPerm(p.permission_id);
                        return (
                          <label key={p.permission_id} className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={perm.can_view} onChange={(e) => updatePermission(p.permission_id, 'can_view', e.target.checked)}
                              className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                            <span className="text-sm text-[#a0a7b3]">
                              {p.code === 'user_list' ? 'Consultation' : p.code === 'user_create' ? 'Création' : p.code === 'user_update' ? 'Modification' : 'Suppression'}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Gestion sites / postes */}
                <div>
                  <label className="block text-xs text-[#a0a7b3] font-medium uppercase tracking-wider mb-3">Gestion sites / postes</label>
                  <div className="bg-[#0f1217] border border-white/5 rounded-lg p-4">
                    <span className="text-xs text-white font-medium block mb-3">Liste des sites / postes</span>
                    <div className="grid grid-cols-2 gap-2">
                      {sitePerms.map(p => {
                        const perm = getPerm(p.permission_id);
                        const labels = {
                          list_sites_posts: 'Consultation',
                          create_site: 'Création site',
                          update_site: 'Modification site',
                          delete_site: 'Suppression site',
                          create_post: 'Création poste',
                          update_post: 'Modification poste',
                          delete_post: 'Suppression poste',
                        };
                        return (
                          <label key={p.permission_id} className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={perm.can_view} onChange={(e) => updatePermission(p.permission_id, 'can_view', e.target.checked)}
                              className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                            <span className="text-sm text-[#a0a7b3]">{labels[p.code] || p.name}</span>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Buttons */}
              <div className="flex gap-3 justify-end">
                <button type="button" onClick={() => navigate('/users')} className="px-6 py-2.5 bg-[#2a2f36] text-white/80 text-sm font-semibold rounded-lg hover:bg-[#3a3646] border border-white/5 transition-colors">
                  Annuler
                </button>
                <button type="submit" disabled={saving} className="px-6 py-2.5 text-sm font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <Save className="w-4 h-4 text-[#111418]" />
                  <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
                </button>
              </div>
            </form>
          </div>
        </main>
      </div>
    </div>
  );
}
