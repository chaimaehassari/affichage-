import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Plus, Pencil, Trash2, LayoutGrid } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getLayouts, deleteLayout } from '../services/layouts';
import { extractDetailMessage } from '../services/api';

export default function LayoutList() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [layouts, setLayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const fetchLayouts = useCallback(async () => {
    setLoading(true);
    const result = await getLayouts();
    if (result.ok && result.data) setLayouts(result.data);
    setLoading(false);
  }, []);

  useEffect(() => { fetchLayouts(); }, [fetchLayouts]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  }

  async function handleDelete() {
    if (!deleteConfirm) return;
    const result = await deleteLayout(deleteConfirm);
    if (result.ok) {
      showNotif('success', 'Modèle supprimé.');
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.'));
    }
    setDeleteConfirm(null);
    await fetchLayouts();
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0" style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent 0px, transparent 60px, rgba(255,255,255,0.01) 60px, rgba(255,255,255,0.01) 61px, transparent 61px, transparent 120px), repeating-linear-gradient(-45deg, transparent 0px, transparent 60px, rgba(246,194,0,0.02) 60px, rgba(246,194,0,0.02) 61px, transparent 61px, transparent 120px)' }} />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-2">Confirmation de suppression</h3>
            <p className="text-[#a0a7b3] text-sm mb-6">Êtes-vous sûr de vouloir supprimer ce modèle ?</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
              <button onClick={handleDelete} className="px-4 py-2 bg-red-700 text-white text-sm rounded-lg hover:bg-red-600">Supprimer</button>
            </div>
          </div>
        </div>
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">DynDisplay</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {user && <span className="text-[#a0a7b3] text-xs">{user.login} \u2014 {user.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        <NavBar />

        <main className="flex-1 px-8 py-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                <ArrowLeft className="w-4 h-4" /> Retour
              </button>
              <h2 className="text-white text-lg font-semibold">Modèles de découpage</h2>
            </div>
            <button onClick={() => navigate('/layouts/new')}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
              <Plus className="w-4 h-4 text-[#111418]" /> <span className="text-[#111418]">Nouveau modèle</span>
            </button>
          </div>

          {loading ? (
            <span className="text-[#a0a7b3] text-sm">Chargement...</span>
          ) : layouts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <LayoutGrid className="w-12 h-12 text-[#2a2f36] mb-3" />
              <p className="text-[#a0a7b3] text-sm">Aucun modèle de découpage.</p>
              <button onClick={() => navigate('/layouts/new')} className="mt-3 text-xs text-[#f6c200] hover:underline">Créer un modèle</button>
            </div>
          ) : (
            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Nom</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Zones actives</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Statut</th>
                    <th className="text-right px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {layouts.map(l => (
                    <tr key={l.layout_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3 text-sm text-white font-medium">{l.name}</td>
                      <td className="px-4 py-3 text-sm text-center text-[#a0a7b3]">{l.active_zone_count} / 8</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full border ${l.is_active ? 'bg-emerald-500/15 border-emerald-500/20 text-emerald-300' : 'bg-zinc-500/15 border-zinc-500/20 text-zinc-400'}`}>
                          {l.is_active ? 'Actif' : 'Inactif'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button onClick={() => navigate(`/layouts/edit/${l.layout_id}`)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Modifier">
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button onClick={() => setDeleteConfirm(l.layout_id)} className="p-1.5 text-[#a0a7b3] hover:text-red-400 transition-colors rounded hover:bg-white/5" title="Supprimer">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
