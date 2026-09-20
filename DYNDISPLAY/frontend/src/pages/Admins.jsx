import { useState, useEffect } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Plus, Pencil, Trash2, ShieldCheck, Building2, X } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import AdminFormModal from '../components/AdminFormModal';
import { extractDetailMessage } from '../services/api';
import { getAdmins, getClients, createAdmin, updateAdmin, deleteAdmin, assignAdminClient, removeAdminClient } from '../services/admins';

export default function Admins() {
  const { logout, user, isSuperAdmin } = useAuth();
  const navigate = useNavigate();
  const [admins, setAdmins] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingAdmin, setEditingAdmin] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [addClientAdmin, setAddClientAdmin] = useState(null);

  function notify(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 3000);
  }

  async function refreshAdmins() {
    const adminsRes = await getAdmins();
    if (adminsRes.ok) setAdmins(adminsRes.data?.admins || []);
  }

  async function loadData() {
    setLoading(true);
    try {
      const [adminsRes, clientsRes] = await Promise.all([getAdmins(), getClients()]);
      if (adminsRes.ok) setAdmins(adminsRes.data?.admins || []);
      if (clientsRes.ok) setClients(clientsRes.data?.clients || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadData(); }, []);

  async function handleAdminSave(payload, adminId) {
    const result = adminId ? await updateAdmin(adminId, payload) : await createAdmin(payload);
    if (result.ok) {
      notify('success', adminId ? 'Admin mis à jour.' : 'Admin créé.');
      setShowForm(false);
      setEditingAdmin(null);
      await refreshAdmins();
      return { ok: true };
    }
    return { ok: false, error: extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.') };
  }

  async function handleDelete() {
    if (!deleteConfirm) return;
    const result = await deleteAdmin(deleteConfirm.user_id);
    if (result.ok) {
      notify('success', 'Admin supprimé.');
      setDeleteConfirm(null);
      await refreshAdmins();
    } else {
      notify('error', extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.'));
    }
  }

  async function handleAddClient(admin, code) {
    setAddClientAdmin(null);
    const result = await assignAdminClient(admin.user_id, code);
    if (result.ok) {
      notify('success', `Client ${code} affecté.`);
    } else {
      notify('error', extractDetailMessage(result.data?.detail, 'Impossible d\'affecter ce client.'));
    }
    await refreshAdmins();
  }

  async function handleRemoveClient(admin, code) {
    const result = await removeAdminClient(admin.user_id, code);
    if (result.ok) {
      notify('success', `Client ${code} retiré.`);
    } else {
      notify('error', extractDetailMessage(result.data?.detail, 'Impossible de retirer ce client.'));
    }
    await refreshAdmins();
  }

  if (!isSuperAdmin) {
    return <Navigate to="/" replace />;
  }

  const clientNameMap = {};
  clients.forEach(c => { clientNameMap[c.client_code] = c.client_name; });

  const sortedAdmins = [...admins].sort((a, b) => {
    if (a.is_superadmin !== b.is_superadmin) return a.is_superadmin ? -1 : 1;
    return (a.login || '').localeCompare(b.login || '');
  });

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

      {showForm && (
        <AdminFormModal
          admin={editingAdmin}
          clients={clients}
          onSave={handleAdminSave}
          onCancel={() => { setShowForm(false); setEditingAdmin(null); }}
        />
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-2">Confirmation de suppression</h3>
            <p className="text-[#a0a7b3] text-sm mb-6">Voulez-vous vraiment supprimer l'admin « {deleteConfirm.login} » ?</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
                Annuler
              </button>
              <button onClick={handleDelete} className="px-4 py-2 bg-red-700 text-white text-sm rounded-lg hover:bg-red-600">
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}

      {addClientAdmin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setAddClientAdmin(null)}>
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl" onClick={e => e.stopPropagation()}>
            <h3 className="text-white font-semibold text-sm mb-1">Affecter un client — {addClientAdmin.login}</h3>
            <p className="text-[#a0a7b3] text-xs mb-4">
              Sélectionnez le client à affecter à cet admin.
            </p>
            {(() => {
              const available = clients.filter(c => !(addClientAdmin.client_codes || []).includes(c.client_code));
              if (available.length === 0) {
                return <p className="text-sm text-[#a0a7b3] py-4 text-center">Tous les clients sont déjà affectés.</p>;
              }
              return (
                <div className="max-h-[50vh] overflow-y-auto pr-1 space-y-1">
                  {available.map(c => (
                    <button
                      key={c.client_code}
                      onClick={() => handleAddClient(addClientAdmin, c.client_code)}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left rounded-lg text-[#a0a7b3] hover:text-white hover:bg-white/5 transition-colors border border-transparent hover:border-white/10"
                    >
                      <Building2 className="w-4 h-4 shrink-0 opacity-70" />
                      <span className="font-mono text-xs">{c.client_code}</span>
                      {c.client_name && <span className="truncate">— {c.client_name}</span>}
                    </button>
                  ))}
                </div>
              );
            })()}
            <div className="flex gap-3 justify-end mt-6">
              <button onClick={() => setAddClientAdmin(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
                Fermer
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
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

        <NavBar />

        <main className="flex-1 px-8 py-6">
          <div className="max-w-6xl mx-auto">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                  <ArrowLeft className="w-4 h-4" />
                  Retour
                </button>
                <ShieldCheck className="w-5 h-5 text-[#f6c200]" />
                <h2 className="text-white text-lg font-semibold">Gestion des admins</h2>
              </div>
              <button onClick={() => { setEditingAdmin(null); setShowForm(true); }} className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-colors" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                <Plus className="w-4 h-4 text-[#111418]" />
                <span className="text-[#111418]">Nouvel Admin</span>
              </button>
            </div>

            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Login</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Code</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Email</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Statut</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Clients</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Créé le</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Chargement...</td></tr>
                  ) : sortedAdmins.length === 0 ? (
                    <tr><td colSpan={7} className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Aucun admin trouvé.</td></tr>
                  ) : (
                    sortedAdmins.map(a => {
                      const codes = a.client_codes || [];
                      return (
                        <tr key={a.user_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                          <td className="px-4 py-3">
                            <span className="flex items-center gap-2">
                              <span className="text-sm text-white">{a.login}</span>
                              {a.is_superadmin && (
                                <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#f6c200]/15 text-[#f6c200] border border-[#f6c200]/30">
                                  <ShieldCheck className="w-3 h-3" /> Super Admin
                                </span>
                              )}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm text-[#a0a7b3] font-mono text-xs">{a.user_code || '—'}</td>
                          <td className="px-4 py-3 text-sm text-[#a0a7b3]">{a.email || '—'}</td>
                          <td className="px-4 py-3">
                            {a.is_active ? (
                              <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/15 text-white border border-emerald-500/20">
                                Actif
                              </span>
                            ) : (
                              <span className="inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full bg-zinc-500/15 text-white border border-zinc-500/20">
                                Inactif
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {a.is_superadmin ? (
                              <span className="text-xs text-[#a0a7b3]">Tous les clients</span>
                            ) : (
                              <div className="flex flex-wrap gap-1.5 items-center">
                                {codes.map(c => (
                                  <span key={c} title={clientNameMap[c] || ''} className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded bg-white/5 border border-white/10 text-white">
                                    {c}
                                    <button onClick={() => handleRemoveClient(a, c)} className="text-[#a0a7b3] hover:text-red-400 transition-colors" title="Retirer">
                                      <X className="w-3 h-3" />
                                    </button>
                                  </span>
                                ))}
                                <button onClick={() => setAddClientAdmin(a)} className="inline-flex items-center justify-center w-5 h-5 text-[#f6c200] hover:text-[#ffdb4d] border border-[#f6c200]/30 rounded hover:bg-[#f6c200]/10 transition-colors" title="Affecter un client">
                                  <Plus className="w-3 h-3" />
                                </button>
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-[#a0a7b3] text-xs">{a.created_at ? a.created_at.slice(0, 10) : '—'}</td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              {!a.is_superadmin && (
                                <>
                                  <button onClick={() => { setEditingAdmin(a); setShowForm(true); }} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Modifier">
                                    <Pencil className="w-4 h-4" />
                                  </button>
                                  <button onClick={() => setDeleteConfirm(a)} className="p-1.5 text-[#a0a7b3] hover:text-red-400 transition-colors rounded hover:bg-white/5" title="Supprimer">
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                </>
                              )}
                              {a.is_superadmin && <span className="text-xs text-[#a0a7b3] pr-2">—</span>}
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