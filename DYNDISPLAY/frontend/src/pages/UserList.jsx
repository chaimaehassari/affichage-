import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Plus, Pencil, Trash2, Search, ToggleLeft, ToggleRight } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import apiService, { extractDetailMessage } from '../services/api';

export default function UserList() {
  const { logout, user, hasPermission } = useAuth();
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState(null);
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
        is_active: !u.is_active,
        requires_activation: ud.is_activated === false,
        zones: (ud.zones || []).filter(z => z.is_allowed).map(z => z.zone_number),
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

            {/* Search */}
            <div className="mb-4">
              <div className="relative max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
                <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Rechercher..."
                  className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
            </div>

            {/* Table */}
            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Code client</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Login</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Mot de passe</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Profil</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Statut</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Chargement...</td></tr>
                  ) : users.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Aucun utilisateur trouvé.</td></tr>
                  ) : (
                    users.map((u) => (
                      <tr key={u.user_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3 text-sm text-[#a0a7b3]">{u.user_code || '—'}</td>
                        <td className="px-4 py-3 text-sm text-white">{u.login}</td>
                        <td className="px-4 py-3 text-sm text-[#a0a7b3] font-mono">{u.password_masked || '••••••••'}</td>
                        <td className="px-4 py-3 text-sm text-[#a0a7b3]">{u.profile_name}</td>
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
                            {hasPermission('user_update') && (
                              <button onClick={() => navigate(`/users/${u.user_id}/edit`)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Modifier">
                                <Pencil className="w-4 h-4" />
                              </button>
                            )}
                            {hasPermission('user_update') && (
                              <button onClick={() => handleToggleActive(u)} className={`p-1.5 transition-colors rounded hover:bg-white/5 ${u.is_active ? 'text-emerald-400 hover:text-emerald-300' : 'text-[#a0a7b3] hover:text-emerald-400'}`} title={u.is_active ? 'Désactiver' : 'Activer'}>
                                {u.is_active ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                              </button>
                            )}
                            {hasPermission('user_delete') && (
                              <button onClick={() => setDeleteConfirm(u.user_id)} className="p-1.5 text-[#a0a7b3] hover:text-red-400 transition-colors rounded hover:bg-white/5" title="Supprimer">
                                <Trash2 className="w-4 h-4" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
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
