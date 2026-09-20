import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Plus, Pencil, Trash2, Search, ToggleLeft, ToggleRight, ShieldCheck, Building2 } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import apiService, { extractDetailMessage } from '../services/api';

export default function UserList() {
  const { logout, user, hasPermission, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [adminClients, setAdminClients] = useState({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [clientsModal, setClientsModal] = useState(null);
  const [clients, setClients] = useState([]);
  const [selectedClientCodes, setSelectedClientCodes] = useState([]);
  const [savingClients, setSavingClients] = useState(false);
  const [notification, setNotification] = useState(null);

  async function fetchUsers() {
    setLoading(true);
    try {
      const params = search ? `?search=${encodeURIComponent(search)}` : '';
      const result = await apiService.get(`/api/v1/users${params}`);
      if (result.ok && result.data) {
        setUsers(result.data.users || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      const profilesRes = await apiService.get('/api/v1/users/profiles');
      if (profilesRes.ok) setProfiles(profilesRes.data || []);
      if (isSuperAdmin) {
        const adminsRes = await apiService.get('/api/v1/admins');
        if (adminsRes.ok && adminsRes.data) {
          const map = {};
          (adminsRes.data.admins || []).forEach(a => {
            map[a.user_id] = a.client_codes || [];
          });
          setAdminClients(map);
        }
      }
    })();
  }, [isSuperAdmin]);

  useEffect(() => { fetchUsers(); }, [search]);

  async function handleDelete(userId) {
    try {
      const result = await apiService.delete(`/api/v1/users/${userId}`);
      if (result.ok) {
        setNotification({ type: 'success', text: 'Utilisateur supprimé.' });
        setDeleteConfirm(null);
        fetchUsers();
      } else {
        setNotification({ type: 'error', text: extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.') });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    }
    setTimeout(() => setNotification(null), 3000);
  }

  async function handleToggleActive(u) {
    try {
      const detail = await apiService.get(`/api/v1/users/${u.user_id}`);
      if (!detail.ok) {
        setNotification({ type: 'error', text: 'Erreur lors du chargement.' });
        setTimeout(() => setNotification(null), 3000);
        return;
      }
      const ud = detail.data;
      const result = await apiService.put(`/api/v1/users/${u.user_id}`, {
        user_code: ud.user_code || '',
        login: ud.login,
        email: ud.email || '',
        profile_id: ud.profile_id,
        admin_id: ud.admin_id || null,
        is_active: !u.is_active,
        requires_activation: ud.is_activated === false,
        zones: (ud.zones || []).filter(z => z.is_allowed).map(z => z.zone_number),
        groups: (ud.groups || []).map(g => g),
        permissions: (ud.permissions || []).map(p => ({
          permission_id: p.permission_id,
          can_view: p.can_view,
          can_create: p.can_create,
          can_update: p.can_update,
          can_delete: p.can_delete,
        })),
      });
      if (result.ok) {
        setNotification({ type: 'success', text: u.is_active ? `${u.login} désactivé.` : `${u.login} activé.` });
        fetchUsers();
      } else {
        setNotification({ type: 'error', text: extractDetailMessage(result.data?.detail, 'Erreur.') });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    }
    setTimeout(() => setNotification(null), 3000);
  }

  async function openClientsModal(u) {
    setNotification(null);
    setClientsModal(u);
    setSavingClients(false);
    try {
      const [clientsRes, adminRes] = await Promise.all([
        apiService.get('/api/v1/clients'),
        apiService.get(`/api/v1/admins/${u.user_id}`),
      ]);
      if (clientsRes.ok) setClients(clientsRes.data?.clients || []);
      if (adminRes.ok) setSelectedClientCodes(adminRes.data?.client_codes || []);
    } catch (e) {
      console.error(e);
      setNotification({ type: 'error', text: 'Erreur lors du chargement des clients.' });
    }
  }

  function toggleClientCode(code) {
    setSelectedClientCodes(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    );
  }

  async function saveClients() {
    if (!clientsModal) return;
    setSavingClients(true);
    try {
      const adminRes = await apiService.get(`/api/v1/admins/${clientsModal.user_id}`);
      if (!adminRes.ok) throw new Error('load');
      const a = adminRes.data;
      const result = await apiService.put(`/api/v1/admins/${clientsModal.user_id}`, {
        user_code: a.user_code || null,
        login: a.login,
        email: a.email || null,
        is_active: a.is_active,
        client_codes: selectedClientCodes,
      });
      if (result.ok) {
        setNotification({ type: 'success', text: 'Clients affectés mis à jour.' });
        setClientsModal(null);
        const adminsRes = await apiService.get('/api/v1/admins');
        if (adminsRes.ok && adminsRes.data) {
          const map = {};
          (adminsRes.data.admins || []).forEach(x => { map[x.user_id] = x.client_codes || []; });
          setAdminClients(map);
        }
      } else {
        setNotification({ type: 'error', text: extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.') });
      }
    } catch {
      setNotification({ type: 'error', text: 'Erreur de connexion.' });
    }
    setSavingClients(false);
    setTimeout(() => setNotification(null), 3000);
  }

  const filteredUsers = roleFilter
    ? users.filter(u => u.profile_name === roleFilter)
    : users;

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0" style={{ backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 60px, rgba(255,255,255,0.01) 60px, rgba(255,255,255,0.01) 61px, transparent 61px, transparent 120px), repeating-linear-gradient(-45deg, transparent 0px, transparent 60px, rgba(246,194,0,0.02) 60px, rgba(246,194,0,0.02) 61px, transparent 61px, transparent 120px)` }} />
        <div className="absolute inset-0" style={{ backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 200px, rgba(246,194,0,0.04) 200px, rgba(246,194,0,0.04) 201px, transparent 201px, transparent 400px)` }} />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {/* Notification */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {/* Delete confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-2">Confirmation de suppression</h3>
            <p className="text-[#a0a7b3] text-sm mb-6">Voulez-vous vraiment supprimer cet utilisateur ?</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
                Annuler
              </button>
              <button onClick={() => handleDelete(deleteConfirm)} className="px-4 py-2 bg-red-700 text-white text-sm rounded-lg hover:bg-red-600">
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clients assignment modal */}
      {clientsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-2xl max-w-2xl shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-1">Clients affectés</h3>
            <p className="text-[#a0a7b3] text-xs mb-4">
              {clientsModal.login} n'aura accès qu'aux clients sélectionnés (leurs sites, postes, médias et utilisateurs).
            </p>
            <div className="grid grid-cols-2 gap-3 max-h-[50vh] overflow-y-auto pr-2">
              {clients.length === 0 ? (
                <p className="text-sm text-[#a0a7b3] col-span-2">Aucun client disponible. Créez d'abord des utilisateurs avec un code client.</p>
              ) : (
                clients.map(c => (
                  <label key={c.client_code} className="flex items-center gap-2 cursor-pointer group">
                    <input type="checkbox" checked={selectedClientCodes.includes(c.client_code)} onChange={() => toggleClientCode(c.client_code)}
                      className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                    <span className="text-sm text-[#a0a7b3] group-hover:text-white transition-colors">
                      {c.client_code}{c.client_name ? ` — ${c.client_name}` : ''}
                    </span>
                  </label>
                ))
              )}
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button onClick={() => setClientsModal(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
                Annuler
              </button>
              <button onClick={saveClients} disabled={savingClients} className="px-4 py-2 text-sm font-semibold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                <span className="text-[#111418]">{savingClients ? 'Enregistrement...' : 'Enregistrer'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Header */}
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">
            DynDisplay
          </h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {user && <span className="text-[#a0a7b3] text-xs">{user.login} — {user.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" />
              Déconnexion
            </button>
          </div>
        </header>

        {/* Menu bar */}
        <NavBar />

        {/* Content */}
        <main className="flex-1 px-8 py-6">
          <div className="max-w-6xl mx-auto">
            {/* Toolbar */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                  <ArrowLeft className="w-4 h-4" />
                  Retour
                </button>
                <h2 className="text-white text-lg font-semibold">Liste des utilisateurs</h2>
              </div>
              {hasPermission('user_create') && (
                <button onClick={() => navigate('/users/new')} className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-colors" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <Plus className="w-4 h-4 text-[#111418]" />
                  <span className="text-[#111418]">Nouveau</span>
                </button>
              )}
            </div>

            {/* Search + Role filter */}
            <div className="flex items-center gap-4 mb-4">
              <div className="relative max-w-sm flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
                <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Rechercher..."
                  className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div className="relative">
                <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}
                  className="appearance-none bg-[#1a1f24] text-white px-4 py-2.5 pr-10 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50">
                  <option value="">Tous les rôles</option>
                  {profiles.map(p => (
                    <option key={p.profile_id} value={p.name}>{p.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Table */}
            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Code</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Rôle</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Login</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Email</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">{isSuperAdmin ? 'Admin responsable / Clients' : 'Admin responsable'}</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Statut</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Chargement...</td></tr>
                  ) : filteredUsers.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Aucun utilisateur trouvé.</td></tr>
                  ) : (
                    filteredUsers.map((u) => {
                      const codes = adminClients[u.user_id] || [];
                      return (
                        <tr key={u.user_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                          <td className="px-4 py-3 text-sm text-[#a0a7b3] overflow-visible">
                            <span className="flex items-center gap-2">
                              {u.user_code || '—'}
                              {u.is_superadmin && (
                                <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#f6c200]/15 text-[#f6c200] border border-[#f6c200]/30">
                                  <ShieldCheck className="w-3 h-3" /> Super Admin
                                </span>
                              )}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-white">{u.profile_name || '—'}</td>
                          <td className="px-4 py-3 text-sm text-white">{u.login}</td>
                          <td className="px-4 py-3 text-sm text-[#a0a7b3]">{u.email || '—'}</td>
                          <td className="px-4 py-3 text-sm text-[#a0a7b3]">
                            {u.is_superadmin ? (
                              <span className="text-xs text-[#a0a7b3]">Tous les clients</span>
                            ) : u.profile_name === 'Administrateur' ? (
                              codes.length > 0 ? (
                                <div className="flex flex-wrap gap-1.5">
                                  {codes.map((c) => (
                                    <span key={c} className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white">
                                      {c}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <span className="text-xs text-[#a0a7b3]">Aucun client</span>
                              )
                            ) : (u.admin_login && u.admin_code) ? (
                              `${u.admin_login} (${u.admin_code})`
                            ) : u.admin_login ? (
                              u.admin_login
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {u.is_active ? (
                              <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/15 text-white border border-emerald-500/20">
                                Actif
                              </span>
                            ) : (
                              <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-zinc-500/15 text-white border border-zinc-500/20">
                                Inactif
                              </span>
                            )}
                            {u.is_activated === false && (
                              <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/25">
                                À activer
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {isSuperAdmin && u.profile_name === 'Administrateur' && !u.is_superadmin && (
                                <button onClick={() => openClientsModal(u)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Affecter des clients">
                                  <Building2 className="w-4 h-4" />
                                </button>
                              )}
                              {hasPermission('user_update') && !u.is_superadmin && (
                                <button onClick={() => navigate(`/users/${u.user_id}/edit`)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Modifier">
                                  <Pencil className="w-4 h-4" />
                                </button>
                              )}
                              {hasPermission('user_update') && !u.is_superadmin && (
                                <button onClick={() => handleToggleActive(u)} className={`p-1.5 transition-colors rounded hover:bg-white/5 ${u.is_active ? 'text-emerald-400 hover:text-emerald-300' : 'text-[#a0a7b3] hover:text-emerald-400'}`} title={u.is_active ? 'Désactiver' : 'Activer'}>
                                  {u.is_active ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                                </button>
                              )}
                              {hasPermission('user_delete') && !u.is_superadmin && (
                                <button onClick={() => setDeleteConfirm(u.user_id)} className="p-1.5 text-[#a0a7b3] hover:text-red-400 transition-colors rounded hover:bg-white/5" title="Supprimer">
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
                              {u.is_superadmin && <span className="text-xs text-[#a0a7b3] pr-2">—</span>}
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}