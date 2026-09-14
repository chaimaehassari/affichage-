import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Monitor, RefreshCw, Activity } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSupervision, pingPost } from '../services/supervision';

const STATUS_COLORS = {
  online: 'bg-green-500',
  outdated: 'bg-yellow-500',
  offline: 'bg-red-500',
  never_synced: 'bg-gray-400',
};

const STATUS_LABELS = {
  online: 'En ligne',
  outdated: 'Périmé',
  offline: 'Hors ligne',
  never_synced: 'Jamais synchronisé',
};

const PING_RESULT_TTL_MS = 30000;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function Supervision() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [pingResults, setPingResults] = useState({});
  const [pinging, setPinging] = useState({});

  const fetchData = useCallback(async () => {
    try {
      const result = await getSupervision();
      if (result.ok && result.data) {
        setData(result.data);
        setLastRefresh(new Date());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const hasAutoPinged = useRef(false);

  const autoPingAll = useCallback(async () => {
    const allPosts = data.flatMap(site => site.posts.map(p => p.post_id));
    await Promise.all(allPosts.map(postId => handlePing(postId)));
  }, [data]);

  useEffect(() => {
    if (loading || data.length === 0) return;
    if (hasAutoPinged.current) return;
    hasAutoPinged.current = true;
    autoPingAll();
  }, [loading, data]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  async function handlePing(postId) {
    if (pinging[postId]) return;
    setPinging(prev => ({ ...prev, [postId]: true }));
    setPingResults(prev => {
      const next = { ...prev };
      delete next[postId];
      return next;
    });
    try {
      const result = await pingPost(postId);
      if (result.ok && result.data) {
        setPingResults(prev => ({ ...prev, [postId]: result.data }));
      } else {
        setPingResults(prev => ({ ...prev, [postId]: { reachable: false, rtt_ms: null, message: 'Erreur de ping.' } }));
      }
    } catch {
      setPingResults(prev => ({ ...prev, [postId]: { reachable: false, rtt_ms: null, message: 'Erreur de connexion.' } }));
    } finally {
      setPinging(prev => ({ ...prev, [postId]: false }));
      setTimeout(() => {
        setPingResults(prev => {
          const next = { ...prev };
          delete next[postId];
          return next;
        });
      }, PING_RESULT_TTL_MS);
    }
  }

  const rows = data.flatMap(site =>
    site.posts.map(post => ({
      site_id: site.site_id,
      site_name: site.name,
      site_code: site.code,
      ...post,
    }))
  );

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
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Monitor className="w-5 h-5 text-[#f6c200]" />
              <h2 className="text-white text-lg font-semibold">Supervision</h2>
              {lastRefresh && (
                <span className="text-[#a0a7b3] text-xs ml-2">Dernière MAJ : {lastRefresh.toLocaleTimeString('fr-FR')}</span>
              )}
            </div>
            <button onClick={fetchData} className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg hover:bg-white/5 transition-colors">
              <RefreshCw className="w-4 h-4" /> Rafraîchir
            </button>
          </div>

          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-8 h-8 border-2 border-[#f6c200] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : rows.length === 0 ? (
            <div className="text-center py-16">
              <Monitor className="w-16 h-16 text-[#a0a7b3]/30 mx-auto mb-4" />
              <p className="text-[#a0a7b3] text-sm">Aucun poste configuré.</p>
            </div>
          ) : (
            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#a0a7b3] text-xs uppercase">
                    <th className="text-left px-6 py-2">Site</th>
                    <th className="text-left px-6 py-2">Code</th>
                    <th className="text-left px-6 py-2">Nom</th>
                    <th className="text-left px-6 py-2">Statut</th>
                    <th className="text-left px-6 py-2">Dernière sync</th>
                    <th className="text-left px-6 py-2">Dernier heartbeat</th>
                    <th className="text-left px-6 py-2">Ping</th>
                    <th className="text-right px-6 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(post => (
                    <tr key={post.post_id} className="border-t border-white/5 hover:bg-white/[0.02]">
                      <td className="px-6 py-2.5 text-white text-xs">
                        <span className="text-white">{post.site_name}</span>
                        <span className="text-[#a0a7b3] font-mono ml-1">({post.site_code})</span>
                      </td>
                      <td className="px-6 py-2.5 text-white font-mono text-xs">{post.code}</td>
                      <td className="px-6 py-2.5 text-white">{post.name}</td>
                      <td className="px-6 py-2.5">
                        <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
                          post.status === 'online' ? 'bg-green-500/15 border-green-500/30 text-green-300' :
                          post.status === 'outdated' ? 'bg-yellow-500/15 border-yellow-500/30 text-yellow-300' :
                          post.status === 'offline' ? 'bg-red-500/15 border-red-500/30 text-red-300' :
                          'bg-gray-500/15 border-gray-500/30 text-gray-400'
                        }`}>
                          <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[post.status]}`} />
                          {STATUS_LABELS[post.status]}
                        </span>
                      </td>
                      <td className="px-6 py-2.5 text-[#a0a7b3] text-xs">{formatDate(post.last_sync_at)}</td>
                      <td className="px-6 py-2.5 text-[#a0a7b3] text-xs">{formatDate(post.last_heartbeat_at)}</td>
                      <td className="px-6 py-2.5">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => handlePing(post.post_id)}
                            disabled={pinging[post.post_id]}
                            className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded border transition-colors ${
                              pinging[post.post_id]
                                ? 'opacity-50 cursor-wait'
                                : 'hover:bg-white/5 border-white/10 text-[#a0a7b3] hover:text-white'
                            }`}
                            title="Ping vers le poste"
                          >
                            <Activity className={`w-3.5 h-3.5 ${pinging[post.post_id] ? 'animate-pulse text-[#f6c200]' : ''}`} />
                            {pinging[post.post_id] ? 'Ping...' : 'Ping'}
                          </button>
                          {pingResults[post.post_id] && (
                            <span className={`text-xs font-medium ${
                              pingResults[post.post_id].reachable ? 'text-green-300' : 'text-red-300'
                            }`}>
                              {pingResults[post.post_id].reachable
                                ? `${Math.round(pingResults[post.post_id].rtt_ms)} ms`
                                : 'Injoignable'}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-2.5 text-right">
                        <button onClick={() => navigate(`/display-config?post_id=${post.post_id}`)}
                          className="text-xs text-[#a0a7b3] hover:text-[#f6c200] transition-colors">
                          Configurer
                        </button>
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