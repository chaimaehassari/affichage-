import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, RefreshCw, CheckCircle, XCircle, Loader, Clock, ChevronRight, MonitorPlay, Image as ImageIcon, Film, LayoutGrid } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getGroups, getGroupPosts } from '../services/sites';
import { startSync, getPostSyncStatus, syncGroup, getGroupMediaHierarchy, syncGroupMedia } from '../services/sync';
import SyncProgressModal from '../components/SyncProgressModal';
import { extractDetailMessage } from '../services/api';

function MediaSyncBadge({ status }) {
  if (!status || status === 'NOT_SYNCED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-zinc-500/15 border-zinc-500/20 text-zinc-400">
        <Clock className="w-2.5 h-2.5" /> Non synchronisé
      </span>
    );
  }
  if (status === 'SYNCED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-emerald-500/15 border-emerald-500/20 text-emerald-300">
        <CheckCircle className="w-2.5 h-2.5" /> À jour
      </span>
    );
  }
  if (status === 'SYNCING' || status === 'PARTIAL') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-yellow-500/15 border-yellow-500/20 text-yellow-300">
        <Loader className="w-2.5 h-2.5 animate-spin" /> {status === 'SYNCING' ? 'En cours' : 'Partiel'}
      </span>
    );
  }
  if (status === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-red-500/15 border-red-500/20 text-red-300">
        <XCircle className="w-2.5 h-2.5" /> Erreur
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-zinc-500/15 border-zinc-500/20 text-zinc-400">
      <Clock className="w-2.5 h-2.5" /> Inconnu
    </span>
  );
}

function PostSyncBadge({ status }) {
  if (!status) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-zinc-500/15 border-zinc-500/20 text-zinc-400">
        <Clock className="w-2.5 h-2.5" /> Jamais synchronisé
      </span>
    );
  }
  const s = status.status;
  if (s === 'COMPLETED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-emerald-500/15 border-emerald-500/20 text-emerald-300">
        <CheckCircle className="w-2.5 h-2.5" /> À jour
      </span>
    );
  }
  if (s === 'RUNNING') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-yellow-500/15 border-yellow-500/20 text-yellow-300">
        <Loader className="w-2.5 h-2.5 animate-spin" /> En cours
      </span>
    );
  }
  if (s === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-red-500/15 border-red-500/20 text-red-300">
        <XCircle className="w-2.5 h-2.5" /> Échoué
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full border bg-zinc-500/15 border-zinc-500/20 text-zinc-400">
      <Clock className="w-2.5 h-2.5" /> En attente
    </span>
  );
}

export default function SyncPage() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [groups, setGroups] = useState([]);
  const [groupPosts, setGroupPosts] = useState({});
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);
  const [expandedGroups, setExpandedGroups] = useState({});
  const [expandedZones, setExpandedZones] = useState({});
  const [groupMediaHierarchy, setGroupMediaHierarchy] = useState({});
  const [postStatuses, setPostStatuses] = useState({});
  const [showSyncModal, setShowSyncModal] = useState(false);
  const [syncJobId, setSyncJobId] = useState(null);
  const [syncingGroups, setSyncingGroups] = useState({});
  const [syncingMedia, setSyncingMedia] = useState({});
  const [syncingPosts, setSyncingPosts] = useState({});
  const [postSyncMode, setPostSyncMode] = useState({});
  const [postSyncTime, setPostSyncTime] = useState({});

  const init = useCallback(async () => {
    setLoading(true);
    const groupsRes = await getGroups();
    if (groupsRes.ok && groupsRes.data) {
      setGroups(groupsRes.data);
      const postsMap = {};
      const allPosts = [];
      const hierarchyMap = {};
      await Promise.all(
        groupsRes.data.map(async (g) => {
          const [postsRes, hierRes] = await Promise.all([
            getGroupPosts(g.group_id),
            getGroupMediaHierarchy(g.group_id),
          ]);
          if (postsRes.ok && postsRes.data) {
            postsMap[g.group_id] = postsRes.data;
            allPosts.push(...postsRes.data);
          } else {
            postsMap[g.group_id] = [];
          }
          if (hierRes.ok && hierRes.data) {
            hierarchyMap[g.group_id] = hierRes.data.zones || [];
          } else {
            hierarchyMap[g.group_id] = [];
          }
        })
      );
      setGroupPosts(postsMap);
      setGroupMediaHierarchy(hierarchyMap);
      const statuses = {};
      await Promise.all(
        allPosts.map(async (p) => {
          const r = await getPostSyncStatus(p.post_id);
          if (r.ok && r.data) statuses[p.post_id] = r.data;
        })
      );
      setPostStatuses(statuses);
    }
    setLoading(false);
  }, []);

  useEffect(() => { init(); }, [init]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 3000);
  }

  function toggleGroup(groupId) {
    setExpandedGroups(prev => ({ ...prev, [groupId]: !prev[groupId] }));
  }

  function toggleZone(key) {
    setExpandedZones(prev => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleSyncGroup(groupId) {
    if (syncingGroups[groupId]) return;
    setSyncingGroups(prev => ({ ...prev, [groupId]: true }));
    try {
      const result = await syncGroup(groupId);
      if (result.ok && result.data) {
        const started = (result.data.results || []).filter(r => r.status === 'STARTED');
        const skipped = (result.data.results || []).filter(r => r.status === 'SKIPPED');
        if (started.length > 0) {
          setSyncJobId(started[0].sync_job_id);
          setShowSyncModal(true);
          showNotif('success', `${started.length} poste(s) synchronisé(s).` + (skipped.length ? ` ${skipped.length} ignoré(s).` : ''));
        } else {
          showNotif('error', skipped.length ? 'Tous les postes sont déjà en cours.' : 'Aucun poste à synchroniser.');
        }
        await refreshGroup(groupId);
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur de synchronisation.'));
      }
    } finally {
      setSyncingGroups(prev => ({ ...prev, [groupId]: false }));
    }
  }

  async function handleSyncMedia(groupId, mediaId) {
    const key = `${groupId}-${mediaId}`;
    if (syncingMedia[key]) return;
    setSyncingMedia(prev => ({ ...prev, [key]: true }));
    try {
      const result = await syncGroupMedia(groupId, mediaId);
      if (result.ok && result.data) {
        const started = (result.data.results || []).filter(r => r.status === 'STARTED');
        const skipped = (result.data.results || []).filter(r => r.status === 'SKIPPED');
        if (started.length > 0) {
          setSyncJobId(started[0].sync_job_id);
          setShowSyncModal(true);
          showNotif('success', `Synchronisation du média lancée sur ${started.length} poste(s).` + (skipped.length ? ` ${skipped.length} ignoré(s).` : ''));
        } else {
          showNotif('error', skipped.length ? 'Poste déjà en cours de synchronisation.' : 'Aucun poste à synchroniser.');
        }
        await refreshGroup(groupId);
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur de synchronisation du média.'));
      }
    } finally {
      setSyncingMedia(prev => ({ ...prev, [key]: false }));
    }
  }

  async function handleSyncPost(postId, groupId) {
    if (syncingPosts[postId]) return;
    const mode = postSyncMode[postId] || 'now';
    if (mode === 'schedule' && !postSyncTime[postId]) {
      showNotif('error', 'Choisissez une date et une heure pour la programmation.');
      return;
    }
    const scheduledAt = mode === 'schedule' ? postSyncTime[postId] : null;
    setSyncingPosts(prev => ({ ...prev, [postId]: true }));
    try {
      const result = await startSync(postId, scheduledAt);
      if (result.ok && result.data) {
        setSyncJobId(result.data.sync_job_id);
        setShowSyncModal(true);
        if (result.data.status === 'SCHEDULED') {
          showNotif('success', 'Synchronisation programmée.');
        } else {
          showNotif('success', 'Synchronisation lancée.');
        }
        await refreshGroup(groupId);
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur de synchronisation.'));
      }
    } finally {
      setSyncingPosts(prev => ({ ...prev, [postId]: false }));
    }
  }

  async function refreshGroup(groupId) {
    const [postsRes, hierRes] = await Promise.all([
      getGroupPosts(groupId),
      getGroupMediaHierarchy(groupId),
    ]);
    if (postsRes.ok && postsRes.data) {
      setGroupPosts(prev => ({ ...prev, [groupId]: postsRes.data }));
      const statuses = {};
      await Promise.all(
        postsRes.data.map(async (p) => {
          const r = await getPostSyncStatus(p.post_id);
          if (r.ok && r.data) statuses[p.post_id] = r.data;
        })
      );
      setPostStatuses(prev => ({ ...prev, ...statuses }));
    }
    if (hierRes.ok && hierRes.data) {
      setGroupMediaHierarchy(prev => ({ ...prev, [groupId]: hierRes.data.zones || [] }));
    }
  }

  function getMediaIcon(type) {
    if (type === 'VIDEO') return <Film className="w-3.5 h-3.5" />;
    return <ImageIcon className="w-3.5 h-3.5" />;
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0" style={{ backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 60px, rgba(255,255,255,0.01) 60px, rgba(255,255,255,0.01) 61px, transparent 61px, transparent 120px), repeating-linear-gradient(-45deg, transparent 0px, transparent 60px, rgba(246,194,0,0.02) 60px, rgba(246,194,0,0.02) 61px, transparent 61px, transparent 120px)` }} />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {showSyncModal && syncJobId && (
        <SyncProgressModal jobId={syncJobId} onClose={() => setShowSyncModal(false)} />
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

        <main className="flex-1 px-8 py-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <RefreshCw className="w-5 h-5 text-[#f6c200]" />
              <h2 className="text-white text-lg font-semibold">Synchronisation</h2>
            </div>
            <button onClick={init} className="flex items-center gap-2 px-3 py-1.5 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg hover:bg-white/5 transition-colors">
              <RefreshCw className="w-4 h-4" /> Rafraîchir
            </button>
          </div>

          {loading ? (
            <div className="flex items-center gap-3 text-[#a0a7b3] text-sm py-12 justify-center">
              <Loader className="w-5 h-5 animate-spin" /> Chargement...
            </div>
          ) : groups.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-[#a0a7b3] text-sm">Aucun groupe configuré.</p>
            </div>
          ) : (
            <div className="space-y-3 max-w-5xl">
              {groups.map(group => {
                const posts = groupPosts[group.group_id] || [];
                const zones = groupMediaHierarchy[group.group_id] || [];
                const isExpanded = expandedGroups[group.group_id];
                const allMediaCount = zones.reduce((sum, z) => sum + (z.media?.length || 0), 0);
                const syncedCount = zones.reduce((sum, z) => sum + (z.media?.filter(m => m.sync_status === 'SYNCED').length || 0), 0);
                const groupSyncPercent = allMediaCount > 0 ? Math.round((syncedCount / allMediaCount) * 100) : 0;

                return (
                  <div key={group.group_id} className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                    <div
                      role="button"
                      tabIndex={0}
                      aria-expanded={isExpanded}
                      onClick={() => toggleGroup(group.group_id)}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          toggleGroup(group.group_id);
                        }
                      }}
                      className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <ChevronRight className={`w-4 h-4 text-[#a0a7b3] transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                        <MonitorPlay className="w-4 h-4 text-[#f6c200] opacity-70" />
                        <div className="text-left">
                          <p className="text-sm font-semibold text-white">{group.name}</p>
                          <p className="text-xs text-[#a0a7b3] mt-0.5">
                            {posts.length} {posts.length > 1 ? 'postes' : 'poste'} · {allMediaCount} média{allMediaCount !== 1 ? 'x' : ''} · {groupSyncPercent}% synchronisé
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleSyncGroup(group.group_id); }}
                        disabled={syncingGroups[group.group_id]}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors hover:opacity-90 disabled:opacity-50"
                        style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
                      >
                        {syncingGroups[group.group_id]
                          ? <Loader className="w-3 h-3 text-[#111418] animate-spin" />
                          : <RefreshCw className="w-3 h-3 text-[#111418]" />}
                        <span className="text-[#111418]">Tout synchroniser</span>
                      </button>
                    </div>

                    {isExpanded && (
                      <div className="border-t border-white/5">
                        {zones.length === 0 ? (
                          <p className="px-5 py-4 text-sm text-[#a0a7b3]">Aucune zone configurée dans ce groupe.</p>
                        ) : (
                          zones.map(zone => {
                            const zoneKey = `${group.group_id}-${zone.zone_number}`;
                            const isZoneExpanded = expandedZones[zoneKey];
                            const zoneMedia = zone.media || [];
                            const zoneSynced = zoneMedia.filter(m => m.sync_status === 'SYNCED').length;
                            return (
                              <div key={zoneKey} className="border-b border-white/5 last:border-b-0">
                                <button
                                  onClick={() => toggleZone(zoneKey)}
                                  className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/[0.01] transition-colors"
                                >
                                  <div className="flex items-center gap-3">
                                    <ChevronRight className={`w-3.5 h-3.5 text-[#a0a7b3] transition-transform ${isZoneExpanded ? 'rotate-90' : ''}`} />
                                    <LayoutGrid className="w-3.5 h-3.5 text-[#f6c200] opacity-50" />
                                    <div className="text-left">
                                      <p className="text-xs font-medium text-white">Zone {zone.zone_number}</p>
                                      <p className="text-[10px] text-[#a0a7b3]">
                                        {zoneMedia.length} média{zoneMedia.length !== 1 ? 'x' : ''} · {zoneSynced}/{zoneMedia.length} synchronisé{zoneSynced !== 1 ? 's' : ''}
                                      </p>
                                    </div>
                                  </div>
                                </button>

                                {isZoneExpanded && (
                                  <div className="pl-12 pr-5 pb-3 space-y-1">
                                    {zoneMedia.length === 0 ? (
                                      <p className="text-xs text-[#a0a7b3] py-2">Aucun média dans cette zone.</p>
                                    ) : (
                                      zoneMedia.map(media => {
                                        const mediaKey = `${group.group_id}-${media.media_id}`;
                                        const isSyncing = syncingMedia[mediaKey];
                                        return (
                                          <div key={media.media_id} className="flex items-center justify-between py-2 px-3 rounded-md bg-white/[0.02] hover:bg-white/[0.04] transition-colors">
                                            <div className="flex items-center gap-3">
                                              <span className="text-[#a0a7b3]">{getMediaIcon(media.media_type)}</span>
                                              <div>
                                                <p className="text-xs text-white font-medium">{media.name}</p>
                                                <p className="text-[10px] text-[#a0a7b3]">
                                                  {media.media_type === 'VIDEO' ? 'Vidéo' : 'Image'}
                                                  {media.duration_seconds ? ` · ${media.duration_seconds}s` : ''}
                                                  {media.display_order != null ? ` · #${media.display_order}` : ''}
                                                </p>
                                              </div>
                                              <MediaSyncBadge status={media.sync_status} />
                                            </div>
                                            <button
                                              onClick={() => handleSyncMedia(group.group_id, media.media_id)}
                                              disabled={isSyncing}
                                              className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold rounded transition-colors hover:opacity-90 disabled:opacity-50"
                                              style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
                                            >
                                              {isSyncing
                                                ? <Loader className="w-2.5 h-2.5 text-[#111418] animate-spin" />
                                                : <RefreshCw className="w-2.5 h-2.5 text-[#111418]" />}
                                              <span className="text-[#111418]">Synchroniser</span>
                                            </button>
                                          </div>
                                        );
                                      })
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })
                        )}

                        <div className="border-t border-white/5">
                          <p className="px-5 py-2 text-[10px] text-[#a0a7b3] uppercase tracking-wider font-medium">Postes</p>
                          {posts.length === 0 ? (
                            <p className="px-5 py-3 text-xs text-[#a0a7b3]">Aucun poste.</p>
                          ) : (
                            posts.map(post => {
                              const status = postStatuses[post.post_id];
                              const lastSync = status?.completed_at;
                              return (
                                <div key={post.post_id} className="flex items-center justify-between px-5 py-2.5 hover:bg-white/[0.01] transition-colors border-t border-white/[0.03]">
                                  <div className="flex items-center gap-4">
                                    <div>
                                      <p className="text-xs text-white font-medium">{post.code}</p>
                                      <p className="text-[10px] text-[#a0a7b3]">{post.name}</p>
                                    </div>
                                    <PostSyncBadge status={status} />
                                    {lastSync && (
                                      <span className="text-[10px] text-[#a0a7b3]">
                                        {new Date(lastSync).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                      </span>
                                    )}
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                    <select
                                      value={postSyncMode[post.post_id] || 'now'}
                                      onChange={(e) => setPostSyncMode(prev => ({ ...prev, [post.post_id]: e.target.value }))}
                                      className="px-2 py-1 bg-[#0f1217] border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[#f6c200]/50"
                                    >
                                      <option value="now">Maintenant</option>
                                      <option value="schedule">Programmer</option>
                                    </select>
                                    {postSyncMode[post.post_id] === 'schedule' && (
                                      <input
                                        type="datetime-local"
                                        value={postSyncTime[post.post_id] || ''}
                                        onChange={(e) => setPostSyncTime(prev => ({ ...prev, [post.post_id]: e.target.value }))}
                                        className="px-2 py-1 bg-[#0f1217] border border-white/10 rounded-lg text-xs text-white focus:outline-none focus:border-[#f6c200]/50"
                                      />
                                    )}
                                    <button
                                      onClick={() => handleSyncPost(post.post_id, group.group_id)}
                                      disabled={syncingPosts[post.post_id]}
                                      className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold rounded transition-colors hover:opacity-90 disabled:opacity-50"
                                      style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
                                    >
                                      {syncingPosts[post.post_id]
                                        ? <Loader className="w-2.5 h-2.5 text-[#111418] animate-spin" />
                                        : <RefreshCw className="w-2.5 h-2.5 text-[#111418]" />}
                                      <span className="text-[#111418]">Synchroniser</span>
                                    </button>
                                  </div>
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
