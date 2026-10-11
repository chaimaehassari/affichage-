import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, RefreshCw, Search, Eye } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getDiffusionReport } from '../services/supervision';

const REFRESH_MS = 30000;

/* Libellés du verdict serveur (`diffusion_state`, voir DIFFUSION_STATES côté
   backend). Le backend compare les IDENTIFIANTS de média : la console ne fait
   que traduire le verdict, elle ne recalcule rien. */
const STATE_META = {
  up_to_date: {
    label: 'À jour',
    badge: 'bg-green-500/15 border-green-500/30 text-green-300',
  },
  changed: {
    label: 'Pas encore changé',
    badge: 'bg-amber-500/15 border-amber-500/30 text-amber-300',
  },
  no_media: {
    label: 'Aucun média programmé',
    badge: 'bg-zinc-500/15 border-zinc-500/30 text-zinc-400',
  },
  unknown: {
    label: 'Diffusion inconnue',
    badge: 'bg-zinc-500/15 border-zinc-500/30 text-zinc-400',
  },
  offline: {
    label: 'Hors ligne',
    badge: 'bg-red-500/15 border-red-500/30 text-red-300',
  },
};

function formatDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function DiffusionReport() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [search, setSearch] = useState('');

  const fetchReport = useCallback(async () => {
    try {
      const result = await getDiffusionReport();
      if (result.ok && result.data) {
        setPosts(result.data.posts || []);
        setError(null);
        setLastRefresh(new Date());
      } else {
        setError('Rapport indisponible.');
      }
    } catch {
      setError('Erreur de connexion.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReport();
    const interval = setInterval(fetchReport, REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchReport]);

  const filtered = useMemo(() => {
    const t = search.trim().toLowerCase();
    if (!t) return posts;
    return posts.filter((p) =>
      `${p.client_name || ''} ${p.client_code || ''} ${p.site_name || ''} ${p.post_code || ''} ${p.post_name || ''} ${p.current_media_name || ''}`
        .toLowerCase()
        .includes(t),
    );
  }, [posts, search]);

  const totals = useMemo(() => {
    const online = posts.filter((p) => p.is_online).length;
    const upToDate = posts.filter((p) => p.diffusion_state === 'up_to_date').length;
    const changed = posts.filter((p) => p.diffusion_state === 'changed').length;
    return { total: posts.length, online, upToDate, changed };
  }, [posts]);

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

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

        <main className="flex-1 px-8 py-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Eye className="w-5 h-5 text-[#f6c200]" />
              <h2 className="text-white text-lg font-semibold">Rapport de diffusion</h2>
              {lastRefresh && (
                <span className="text-[#a0a7b3] text-xs ml-2">Dernière MAJ : {lastRefresh.toLocaleTimeString('fr-FR')}</span>
              )}
            </div>
            <button onClick={fetchReport} className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg hover:bg-white/5 transition-colors">
              <RefreshCw className="w-4 h-4" /> Rafraîchir
            </button>
          </div>

          <p className="text-xs text-[#a0a7b3] mb-4">
            Un poste = une ligne. « À jour » signifie que le média réellement affiché
            fait partie de ceux programmés sur ce poste ; « pas encore changé » que la
            box diffuse encore l'ancien contenu.
          </p>

          <div className="grid grid-cols-4 gap-3 mb-4">
            {[
              { label: 'Postes', value: totals.total, tone: 'text-white' },
              { label: 'En ligne', value: totals.online, tone: 'text-green-300' },
              { label: 'À jour', value: totals.upToDate, tone: 'text-green-300' },
              { label: 'Pas encore changé', value: totals.changed, tone: 'text-amber-300' },
            ].map((card) => (
              <div key={card.label} className="bg-[#111418]/80 border border-white/10 rounded-lg px-4 py-3">
                <p className="text-xs uppercase text-[#a0a7b3]">{card.label}</p>
                <p className={`text-xl font-semibold ${card.tone}`}>{card.value}</p>
              </div>
            ))}
          </div>

          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher un client, un site, un poste, un média..."
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-2 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
          </div>

          {error && (
            <div className="mb-3 px-4 py-2.5 rounded-lg text-sm border bg-red-950/80 border-red-700/50 text-red-300">
              {error}
            </div>
          )}

          <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
            {loading ? (
              <div className="flex items-center justify-center h-48">
                <div className="w-8 h-8 border-2 border-[#f6c200] border-t-transparent rounded-full animate-spin" />
              </div>
            ) : filtered.length === 0 ? (
              <p className="px-4 py-10 text-center text-[#a0a7b3] text-sm">
                {search ? 'Aucun poste ne correspond à la recherche.' : 'Aucun poste dans votre périmètre.'}
              </p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#a0a7b3] text-xs uppercase">
                    <th className="text-left px-4 py-2">Client</th>
                    <th className="text-left px-4 py-2">Box</th>
                    <th className="text-left px-4 py-2">Média affiché</th>
                    <th className="text-left px-4 py-2">Depuis</th>
                    <th className="text-left px-4 py-2">Programmé</th>
                    <th className="text-left px-4 py-2">État</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => {
                    const meta = STATE_META[p.diffusion_state] || STATE_META.unknown;
                    return (
                      <tr key={p.post_id} className="border-t border-white/5 hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-2.5">
                          <p className="text-white text-xs">{p.client_name || '—'}</p>
                          <p className="text-[#a0a7b3] font-mono text-[10px]">{p.client_code || '—'}</p>
                        </td>
                        <td className="px-4 py-2.5">
                          <p className="text-white text-xs">{p.post_name}</p>
                          <p className="text-[#a0a7b3] font-mono text-[10px]">
                            {p.post_code} — {p.site_name}
                          </p>
                        </td>
                        <td className="px-4 py-2.5 text-white text-xs">
                          {p.current_media_name || '—'}
                          {p.current_media_type && (
                            <span className="ml-1 text-[10px] text-[#a0a7b3] uppercase">{p.current_media_type}</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-[#a0a7b3] text-xs whitespace-nowrap">
                          {formatDateTime(p.current_media_started_at)}
                        </td>
                        <td className="px-4 py-2.5 text-[#a0a7b3] text-xs">
                          {p.assigned_media_names && p.assigned_media_names.length
                            ? p.assigned_media_names.join(', ')
                            : '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <div className="flex flex-col items-start gap-1">
                            <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${meta.badge}`}>
                              <span className={`w-2 h-2 rounded-full ${p.is_online ? 'bg-current' : 'bg-red-500'}`} />
                              {meta.label}
                            </span>
                            <span className="text-[10px] text-[#a0a7b3]">
                              {p.is_online ? 'En ligne' : 'Hors ligne'}
                            </span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
