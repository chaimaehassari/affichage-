import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Monitor, RefreshCw, Activity } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSupervision, pingPost, pingAllPosts } from '../services/supervision';
import { batchRebootSchedule } from '../services/sites';
import { extractDetailMessage } from '../services/api';

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

const PING_BATCH_TIMEOUT_MS = 15000;

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
  const [pingSkipped, setPingSkipped] = useState(0);
  const [pinging, setPinging] = useState({});
  const [pingingAll, setPingingAll] = useState(false);
  // Un rechargement de page (ou deux clics « Rafraîchir » rapprochés) ne doit
  // pas empiler deux lots de ping côté serveur.
  const pingBatchRunning = useRef(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [rebootModalOpen, setRebootModalOpen] = useState(false);
  const [rebootEnabled, setRebootEnabled] = useState(true);
  const [rebootTime, setRebootTime] = useState('');
  const [rebootSaving, setRebootSaving] = useState(false);
  const [rebootNotif, setRebootNotif] = useState(null);

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


  // Ping automatique de tous les postes du périmètre. Le backend ping en
  // parallèle et renvoie la map {post_id: {reachable, rtt_ms, message}} :
  // un seul aller-retour, au lieu d'un appel par poste.
  const runPingAll = useCallback(async () => {
    if (pingBatchRunning.current) return;
    pingBatchRunning.current = true;
    setPingingAll(true);
    try {
      // Garde-fou : le lot est borné côté serveur (~PING_TIMEOUT_SECONDS),
      // mais on ne veut surtout pas un indicateur « Ping... » bloqué si la
      // requête HTTP se perd. Au-delà du garde-fou, on abandonne l'affichage
      // du résultat ; les résultats déjà affichés restent les derniers connus.
      const result = await Promise.race([
        pingAllPosts(),
        new Promise(resolve => setTimeout(
          () => resolve({ ok: false, data: null, error: 'timeout' }),
          PING_BATCH_TIMEOUT_MS,
        )),
      ]);
      if (result.error === 'timeout') {
        console.warn('Ping automatique : aucune réponse au bout de', PING_BATCH_TIMEOUT_MS, 'ms.');
      } else if (result.ok && result.data && result.data.results) {
        // Les clés d'un objet JSON sont des chaînes : l'accès par
        // `pingResults[post.post_id]` (nombre) coerce et retrouve l'entrée.
        setPingResults(result.data.results);
        // Le backend plafonne les pings réels : un poste sans résultat est
        // alors « non mesuré », pas « injoignable ». On le dit, sinon la
        // colonne Ping affiche un vide silencieux trompeur.
        setPingSkipped(result.data.skipped || 0);
      }
    } catch (e) {
      console.error(e);
    } finally {
      pingBatchRunning.current = false;
      setPingingAll(false);
    }
  }, []);

  // Rafraîchissement manuel : données + ping, pour que le bouton donne
  // l'état joignabilité à jour en un clic.
  const refreshAll = useCallback(async () => {
    await fetchData();
    await runPingAll();
  }, [fetchData, runPingAll]);

  useEffect(() => {
    // Au chargement de la page : le ping part tout seul, l'utilisateur n'a
    // rien à cliquer. Le fond (30 s) ne se re-ping PAS : c'est un simple
    // sondage d'état, et un ICMP toutes les 30 s sur tout le parc serait
    // inutile. Seul un rechargement de page ou « Rafraîchir » re-pinge.
    fetchData();
    runPingAll();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData, runPingAll]);

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

  function toggleSelect(postId) {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(postId)) {
        next.delete(postId);
      } else {
        next.add(postId);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    const all = rows.map(r => r.post_id);
    const allSelected = all.every(id => selectedIds.has(id));
    setSelectedIds(new Set(allSelected ? [] : all));
  }

  async function handleApplyReboot() {
    const postIds = [...selectedIds];
    if (postIds.length === 0) return;
    if (rebootEnabled && !rebootTime) {
      setRebootNotif({ type: 'error', text: 'Indiquez une heure pour le redémarrage automatique.' });
      setTimeout(() => setRebootNotif(null), 5000);
      return;
    }
    setRebootSaving(true);
    const result = await batchRebootSchedule({
      post_ids: postIds,
      reboot_enabled: rebootEnabled,
      reboot_time: rebootTime || null,
      sync: true,
    });
    setRebootSaving(false);
    if (result.ok && result.data) {
      const { success_count, failed_ids: failed, synced_post_ids, failed_posts = [] } = result.data;
      const codeFor = new Map(rows.map(r => [String(r.post_id), r.code]));
      const failedDetail = failed_posts.length
        ? failed_posts.map(f => `${codeFor.get(String(f.post_id)) || f.post_id} (${f.reason})`).join(', ')
        : (failed.length ? failed.map(id => codeFor.get(String(id)) || id).join(', ') : '');
      setRebootNotif({
        type: failed.length ? 'error' : 'success',
        text: `Redémarrage ${rebootEnabled ? 'programmé' : 'désactivé'} sur ${success_count} poste(s), ` +
          `${synced_post_ids.length} synchronisé(s).` +
          (failedDetail ? ` Échecs : ${failedDetail}` : ''),
      });
      setRebootModalOpen(false);
      setSelectedIds(new Set());
      fetchData();
    } else {
      setRebootNotif({
        type: 'error',
        text: extractDetailMessage(result.data?.detail, 'Erreur lors de l\'application du redémarrage.'),
      });
    }
    setTimeout(() => setRebootNotif(null), 6000);
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      <div className="relative z-10 flex flex-col min-h-screen">
        {rebootNotif && (
          <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${rebootNotif.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
            {rebootNotif.text}
          </div>
        )}

        {rebootModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={() => setRebootModalOpen(false)}>
            <div className="bg-[#111418] border border-white/10 rounded-xl p-6 w-[380px]" onClick={e => e.stopPropagation()}>
              <h3 className="text-white font-semibold text-sm mb-1">Programmer le redémarrage automatique</h3>
              <p className="text-xs text-[#a0a7b3] mb-4">{selectedIds.size} poste(s) concerné(s)</p>
              <label className="flex items-center gap-3 cursor-pointer mb-3">
                <input type="checkbox" checked={rebootEnabled} onChange={e => setRebootEnabled(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#f6c200] cursor-pointer" style={{ accentColor: '#f6c200' }} />
                <span className="text-sm text-white">Redémarrage quotidien</span>
              </label>
              {rebootEnabled && (
                <div className="flex items-center gap-3 mb-4">
                  <label htmlFor="bulk-reboot-time" className="text-xs text-[#a0a7b3]">Heure</label>
                  <input id="bulk-reboot-time" type="time" value={rebootTime} onChange={e => setRebootTime(e.target.value)}
                    className="bg-[#1a1f24] border border-white/10 rounded px-2 py-1.5 text-xs text-white focus:border-[#f6c200] focus:outline-none" />
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button onClick={() => setRebootModalOpen(false)}
                  className="px-3 py-1.5 text-xs text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg transition-colors">
                  Annuler
                </button>
                <button onClick={handleApplyReboot} disabled={rebootSaving}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg disabled:opacity-50"
                  style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <span className="text-[#111418]">{rebootSaving ? 'Application...' : (rebootEnabled ? 'Programmer' : 'Désactiver')}</span>
                </button>
              </div>
            </div>
          </div>
        )}

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
          {pingSkipped > 0 && (
            <div className="mb-4 px-4 py-2.5 rounded-lg text-sm border bg-yellow-950/60 border-yellow-700/40 text-yellow-200">
              {pingSkipped} poste(s) non testés : le ping automatique est plafonné
              par lot. Utilisez le bouton « Ping » d'un poste pour le mesurer individuellement.
            </div>
          )}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <Monitor className="w-5 h-5 text-[#f6c200]" />
              <h2 className="text-white text-lg font-semibold">Supervision</h2>
              {lastRefresh && (
                <span className="text-[#a0a7b3] text-xs ml-2">Dernière MAJ : {lastRefresh.toLocaleTimeString('fr-FR')}</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {pingingAll && (
                <span className="flex items-center gap-1.5 text-xs text-[#a0a7b3]">
                  <Activity className="w-3.5 h-3.5 animate-pulse text-[#f6c200]" />
                  Ping automatique…
                </span>
              )}
              <button onClick={refreshAll} disabled={pingingAll}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg hover:bg-white/5 transition-colors disabled:opacity-50 disabled:cursor-wait">
                <RefreshCw className={`w-4 h-4 ${pingingAll ? 'animate-spin' : ''}`} /> Rafraîchir
              </button>
            </div>
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
            <>
            {selectedIds.size > 0 && (
            <div className="mb-4 flex items-center justify-between gap-3 bg-[#111418]/80 border border-[#f6c200]/30 rounded-lg px-4 py-2.5">
              <span className="text-sm text-white">{selectedIds.size} poste(s) sélectionné(s)</span>
              <button onClick={() => setRebootModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg hover:opacity-90 transition-opacity"
                style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                <RefreshCw className="w-3.5 h-3.5 text-[#111418]" />
                <span className="text-[#111418]">Programmer le redémarrage</span>
              </button>
            </div>
          )}

            <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[#a0a7b3] text-xs uppercase">
                    <th className="px-4 py-2 w-8">
                      <input type="checkbox" checked={rows.length > 0 && rows.every(r => selectedIds.has(r.post_id))}
                        onChange={toggleSelectAll}
                        className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200] cursor-pointer" />
                    </th>
                    <th className="text-left px-4 py-2">Site</th>
                    <th className="text-left px-4 py-2">Code</th>
                    <th className="text-left px-4 py-2">Nom</th>
                    <th className="text-left px-4 py-2">Statut</th>
                    <th className="text-left px-4 py-2">Dernière sync</th>
                    <th className="text-left px-4 py-2">Dernier heartbeat</th>
                    <th className="text-left px-4 py-2">Ping</th>
                    <th className="text-right px-4 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(post => (
                    <tr key={post.post_id} className={`border-t border-white/5 hover:bg-white/[0.02] ${selectedIds.has(post.post_id) ? 'bg-[#f6c200]/5' : ''}`}>
                      <td className="px-4 py-2.5">
                        <input type="checkbox" checked={selectedIds.has(post.post_id)}
                          onChange={() => toggleSelect(post.post_id)}
                          className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200] cursor-pointer" />
                      </td>
                      <td className="px-4 py-2.5 text-white text-xs">
                        <span className="text-white">{post.site_name}</span>
                        <span className="text-[#a0a7b3] font-mono ml-1">({post.site_code})</span>
                      </td>
                      <td className="px-4 py-2.5 text-white font-mono text-xs">{post.code}</td>
                      <td className="px-4 py-2.5 text-white">{post.name}</td>
                      <td className="px-4 py-2.5">
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
                      <td className="px-4 py-2.5 text-[#a0a7b3] text-xs">{formatDate(post.last_sync_at)}</td>
                      <td className="px-4 py-2.5 text-[#a0a7b3] text-xs">{formatDate(post.last_heartbeat_at)}</td>
                      <td className="px-4 py-2.5">
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
                            <span
                              className={`text-xs font-medium ${
                                pingResults[post.post_id].reachable ? 'text-green-300' : 'text-red-300'
                              }`}
                              title={pingResults[post.post_id].message || ''}
                            >
                              {pingResults[post.post_id].reachable
                                ? `${Math.round(pingResults[post.post_id].rtt_ms)} ms`
                                : 'Injoignable'}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right">
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
            </>
          )}
        </main>
      </div>
    </div>
  );
}