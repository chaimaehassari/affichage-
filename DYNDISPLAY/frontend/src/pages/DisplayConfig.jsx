import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ChevronRight, ChevronDown, Building2, Monitor, ArrowLeft, Save, Eye, Search, Plus, Pencil, Trash2, RefreshCw, Users } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSites, getPosts, getMedia, getGroups, getGroupPosts, applyConfigToGroup } from '../services/sites';
import { getLayouts, getLayout } from '../services/layouts';
import { getPostConfig, updatePostConfig, createSchedule, updateSchedule, deleteSchedule } from '../services/display';
import { startSync } from '../services/sync';
import ScheduleModal from '../components/ScheduleModal';
import SyncProgressModal from '../components/SyncProgressModal';
import { extractDetailMessage } from '../services/api';

const ZONE_COLORS = [
  { bg: 'rgba(59,130,246,0.3)', border: '#3b82f6' },
  { bg: 'rgba(16,185,129,0.3)', border: '#10b981' },
  { bg: 'rgba(245,158,11,0.3)', border: '#f59e0b' },
  { bg: 'rgba(239,68,68,0.3)', border: '#ef4444' },
  { bg: 'rgba(168,85,247,0.3)', border: '#a855f7' },
  { bg: 'rgba(20,184,166,0.3)', border: '#14b8a6' },
  { bg: 'rgba(244,114,182,0.3)', border: '#f472b6' },
  { bg: 'rgba(99,102,241,0.3)', border: '#6366f1' },
];

export default function DisplayConfig() {
  const { logout, user, canAccessZone } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [sites, setSites] = useState([]);
  const [posts, setPosts] = useState([]);
  const [mediaList, setMediaList] = useState([]);
  const [layouts, setLayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);

  const [selectedMedia, setSelectedMedia] = useState(null);
  const [selectedPostId, setSelectedPostId] = useState(null);
  const [expandedSites, setExpandedSites] = useState({});
  const [mediaSearch, setMediaSearch] = useState('');

  const [targetType, setTargetType] = useState('post'); // 'post' | 'group'
  const [groups, setGroups] = useState([]);
  const [selectedGroupId, setSelectedGroupId] = useState(null);

  const [config, setConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [layoutsDetail, setLayoutsDetail] = useState([]);

  const [scheduleModal, setScheduleModal] = useState(null);
  const [syncJobId, setSyncJobId] = useState(null);
  const [showSyncModal, setShowSyncModal] = useState(false);

  const init = useCallback(async () => {
    setLoading(true);
    const [sitesRes, postsRes, mediaRes, layoutsRes, groupsRes] = await Promise.all([
      getSites(),
      getPosts(),
      getMedia(),
      getLayouts(),
      getGroups(),
    ]);
    if (sitesRes.ok && sitesRes.data) {
      setSites(sitesRes.data);
      const expanded = {};
      sitesRes.data.forEach(s => { expanded[s.site_id] = true; });
      setExpandedSites(expanded);
    }
    if (postsRes.ok && postsRes.data) setPosts(postsRes.data);
    if (mediaRes.ok && mediaRes.data) setMediaList(mediaRes.data);
    if (layoutsRes.ok && layoutsRes.data) {
      setLayouts(layoutsRes.data);
      const details = await Promise.all(
        layoutsRes.data.map(l => getLayout(l.layout_id))
      );
      setLayoutsDetail(details.filter(r => r.ok && r.data).map(r => r.data));
    }
    if (groupsRes.ok && groupsRes.data) setGroups(groupsRes.data);
    setLoading(false);
  }, []);

  useEffect(() => { init(); }, [init]);

  useEffect(() => {
    function handleFocus() { init(); }
    window.addEventListener('focus', handleFocus);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') init();
    });
    return () => {
      window.removeEventListener('focus', handleFocus);
    };
  }, [init]);

  const loadConfig = useCallback(async (postId) => {
    setConfigLoading(true);
    const result = await getPostConfig(postId);
    if (result.ok && result.data) {
      setConfig(result.data);
    }
    setConfigLoading(false);
  }, []);

  useEffect(() => {
    if (selectedPostId) loadConfig(selectedPostId);
  }, [selectedPostId, loadConfig]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  }

  function toggleSite(siteId) {
    setExpandedSites(prev => ({ ...prev, [siteId]: !prev[siteId] }));
  }

  function selectPost(postId) {
    setSelectedPostId(postId);
    setConfig(null);
  }

  async function handleGroupSelect(groupId) {
    setSelectedGroupId(groupId || null);
    if (groupId) {
      const res = await getGroupPosts(groupId);
      // Le premier poste sert de proxy d'édition ; l'enregistrement cible le groupe.
      if (res.ok && res.data && res.data.length > 0) {
        setSelectedPostId(res.data[0].post_id);
      }
    }
  }

  const urlPostId = Number(searchParams.get('post_id') || 0);
  const urlPost = posts.find(p => p.post_id === urlPostId);

  useEffect(() => {
    if (urlPost && selectedPostId !== urlPost.post_id) {
      selectPost(urlPost.post_id);
    }
  }, [urlPost, selectedPostId]);

  function selectMediaForZone(zoneNumber) {
    if (!selectedMedia) {
      showNotif('error', 'Sélectionnez d\'abord un média dans la colonne de gauche.');
      return;
    }
    const m = mediaList.find(ml => ml.media_id === selectedMedia);
    if (!m) return;
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) {
          const playlist = z.media_playlist || (z.media ? [z.media] : []);
          const exists = playlist.find(p => p.media_id === m.media_id);
          if (exists) return z;
          const entry = { media_id: m.media_id, name: m.name, media_type: m.media_type, duration_seconds: m.media_type === 'VIDEO' ? null : 10 };
          const newPlaylist = [...playlist, entry];
          return { ...z, media: newPlaylist[0], media_playlist: newPlaylist };
        }
        return z;
      });
      return { ...prev, zones };
    });
  }

  function removeMediaFromZone(zoneNumber, mediaId) {
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) {
          const playlist = (z.media_playlist || []).filter(p => p.media_id !== mediaId);
          return { ...z, media: playlist[0] || null, media_playlist: playlist };
        }
        return z;
      });
      return { ...prev, zones };
    });
  }

  function updatePlaylistDuration(zoneNumber, mediaId, duration) {
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) {
          const playlist = (z.media_playlist || []).map(p =>
            p.media_id === mediaId ? { ...p, duration_seconds: duration } : p
          );
          return { ...z, media_playlist: playlist };
        }
        return z;
      });
      return { ...prev, zones };
    });
  }

  function moveMediaInPlaylist(zoneNumber, index, direction) {
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) {
          const playlist = [...(z.media_playlist || [])];
          const target = index + direction;
          if (target < 0 || target >= playlist.length) return z;
          [playlist[index], playlist[target]] = [playlist[target], playlist[index]];
          return { ...z, media: playlist[0], media_playlist: playlist };
        }
        return z;
      });
      return { ...prev, zones };
    });
  }

  function updateConfigField(field, value) {
    setConfig(prev => prev ? { ...prev, [field]: value } : prev);
  }

  async function handleLayoutSelect(layoutId) {
    if (!layoutId) {
      setConfig(prev => ({ ...prev, layout: null, zones: [] }));
      return;
    }
    const detail = layoutsDetail.find(l => l.layout_id === layoutId);
    if (detail) {
      setConfig(prev => ({
        ...prev,
        layout: detail,
        zones: detail.zones.map(z => {
          const existing = prev?.zones?.find(ez => ez.zone_number === z.zone_number);
          return {
            ...z,
            media: existing?.media || null,
            media_playlist: existing?.media_playlist || (existing?.media ? [existing.media] : []),
          };
        }),
      }));
    }
  }

  function handleZoneParamChange(zoneNumber, field, value) {
    setConfig(prev => {
      if (!prev) return prev;
      const num = parseFloat(value) || 0;
      const clamped = Math.min(100, Math.max(0, num));
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) return { ...z, [field]: clamped };
        return z;
      });
      const layout = prev.layout ? { ...prev.layout, zones } : null;
      return { ...prev, layout, zones };
    });
  }

  function handleZoneActiveToggle(zoneNumber) {
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) return { ...z, is_active: !z.is_active };
        return z;
      });
      const layout = prev.layout ? { ...prev.layout, zones } : null;
      return { ...prev, layout, zones };
    });
  }

  async function handleSave() {
    if (!selectedPostId || !config) return;
    setSaving(true);

    const layoutId = config.layout?.layout_id || null;

    if (layoutId && config.layout?.zones) {
      const { updateLayout } = await import('../services/layouts');
      await updateLayout(layoutId, {
        is_active: true,
        zones: config.layout.zones
          .filter(z => canAccessZone(z.zone_number))
          .map(z => ({
            zone_number: z.zone_number,
            position_x: z.position_x,
            position_y: z.position_y,
            width: z.width,
            height: z.height,
            is_active: z.is_active,
          })),
      });
    }

    const payload = {
      layout_id: layoutId,
      loop_enabled: config.loop_enabled,
      schedule_enabled: config.schedule_enabled,
      display_enabled: config.display_enabled,
      zones: config.zones
        .filter(z => canAccessZone(z.zone_number))
        .flatMap(z => {
        const playlist = z.media_playlist || (z.media ? [z.media] : []);
        if (playlist.length === 0) {
          return [{ zone_number: z.zone_number, media_id: null }];
        }
        return playlist.map((m, idx) => ({
          zone_number: z.zone_number,
          media_id: m.media_id,
          display_order: idx + 1,
          duration_seconds: m.duration_seconds ?? null,
        }));
      }),
    };

    const result = await updatePostConfig(selectedPostId, payload);
    if (result.ok) {
      showNotif('success', 'Configuration enregistrée.');
      await loadConfig(selectedPostId);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.'));
    }
    setSaving(false);
  }

  async function handleSync() {
    if (!selectedPostId || !config) {
      showNotif('error', 'Sélectionnez un poste configuré.');
      return;
    }
    if (!config.layout?.layout_id) {
      showNotif('error', 'Aucun layout assigné à ce poste.');
      return;
    }
    const result = await startSync(selectedPostId);
    if (result.ok && result.data) {
      setSyncJobId(result.data.sync_job_id);
      setShowSyncModal(true);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Impossible de lancer la synchronisation.'));
    }
  }

  async function handleSaveGroup() {
    if (targetType !== 'group' || !selectedGroupId || !config) {
      showNotif('error', 'Sélectionnez un groupe et une configuration.');
      return;
    }
    setSaving(true);

    const layoutId = config.layout?.layout_id || null;
    if (layoutId && config.layout?.zones) {
      const { updateLayout } = await import('../services/layouts');
      await updateLayout(layoutId, {
        is_active: true,
        zones: config.layout.zones
          .filter(z => canAccessZone(z.zone_number))
          .map(z => ({
            zone_number: z.zone_number,
            position_x: z.position_x,
            position_y: z.position_y,
            width: z.width,
            height: z.height,
            is_active: z.is_active,
          })),
      });
    }

    const zones = (config.zones || [])
      .filter(z => canAccessZone(z.zone_number))
      .flatMap(z => {
      const playlist = z.media_playlist || (z.media ? [z.media] : []);
      if (playlist.length === 0) {
        return [{ zone_number: z.zone_number, media_id: null }];
      }
      return playlist.map((m, idx) => ({
        zone_number: z.zone_number,
        media_id: m.media_id,
        display_order: idx + 1,
        duration_seconds: m.duration_seconds ?? null,
      }));
    });

    const payload = {
      layout_id: layoutId,
      loop_enabled: config.loop_enabled,
      schedule_enabled: config.schedule_enabled,
      display_enabled: config.display_enabled,
      zones,
      sync: true,
    };

    const result = await applyConfigToGroup(selectedGroupId, payload);
    if (result.ok && result.data) {
      const { success_count, synced_post_ids, failed_post_ids } = result.data;
      showNotif(
        failed_post_ids.length ? 'error' : 'success',
        `Configuration appliquée à ${success_count} poste(s), ${synced_post_ids.length} synchronisé(s).` +
          (failed_post_ids.length ? ` Échecs: ${failed_post_ids.length}` : '')
      );
      if (selectedPostId) await loadConfig(selectedPostId);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de l\'application au groupe.'));
    }
    setSaving(false);
  }

  async function handleSaveSchedule(data) {
    if (!selectedPostId) return;
    try {
      let result;
      if (scheduleModal?.schedule_id) {
        result = await updateSchedule(scheduleModal.schedule_id, data);
      } else {
        result = await createSchedule(selectedPostId, data);
      }
      if (result.ok) {
        showNotif('success', scheduleModal?.schedule_id ? 'Planning mis à jour.' : 'Planning créé.');
        setScheduleModal(null);
        await loadConfig(selectedPostId);
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.'));
      }
    } catch {
      showNotif('error', 'Erreur de connexion.');
    }
  }

  async function handleDeleteSchedule(scheduleId) {
    const result = await deleteSchedule(scheduleId);
    if (result.ok) {
      showNotif('success', 'Planning supprimé.');
      await loadConfig(selectedPostId);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.'));
    }
  }

  const filteredMedia = mediaSearch
    ? mediaList.filter(m => m.name.toLowerCase().includes(mediaSearch.toLowerCase()))
    : mediaList;

  const sitesWithPosts = sites.map(s => ({
    ...s,
    posts: posts.filter(p => p.site_id === s.site_id),
  }));

  const selectedPost = posts.find(p => p.post_id === selectedPostId);
  const currentLayout = config?.layout;
  const currentZones = config?.zones || [];
  const editableZones = currentZones.filter(z => canAccessZone(z.zone_number));
  const selectedGroup = groups.find(g => g.group_id === selectedGroupId) || null;

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

      {scheduleModal !== null && (
        <ScheduleModal schedule={scheduleModal} onSave={handleSaveSchedule} onClose={() => setScheduleModal(null)} />
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

        <main className="flex-1 px-8 py-6 overflow-hidden">
          <div className="flex items-center gap-3 mb-6">
            <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
              <ArrowLeft className="w-4 h-4" /> Retour
            </button>
            <h2 className="text-white text-lg font-semibold">Configuration de l'affichage</h2>
          </div>

          {loading ? (
            <span className="text-[#a0a7b3] text-sm">Chargement...</span>
          ) : (
            <div className="flex gap-4" style={{ height: 'calc(100vh - 180px)' }}>
              {/* Left: Media Library */}
              <div className="w-64 shrink-0 flex flex-col">
                <h3 className="text-white text-sm font-semibold mb-3">Médiathèque</h3>
                <div className="mb-2 relative">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]" />
                  <input type="text" value={mediaSearch} onChange={e => setMediaSearch(e.target.value)}
                    placeholder="Rechercher..."
                    className="w-full bg-[#111418]/80 border border-white/10 rounded pl-8 pr-3 py-1.5 text-xs text-white focus:border-[#f6c200] focus:outline-none" />
                </div>
                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden flex-1">
                  <div className="max-h-full overflow-y-auto">
                    {filteredMedia.length === 0 ? (
                      <p className="px-4 py-6 text-center text-[#a0a7b3] text-xs">Aucun média.</p>
                    ) : (
                      filteredMedia.map(m => (
                        <div key={m.media_id}
                          onClick={() => setSelectedMedia(m.media_id === selectedMedia ? null : m.media_id)}
                          className={`flex items-center gap-3 px-4 py-2.5 border-b border-white/5 cursor-pointer transition-colors ${selectedMedia === m.media_id ? 'bg-[#f6c200]/10 border-l-2 border-l-[#f6c200]' : 'hover:bg-white/[0.02]'}`}>
                          <div className="min-w-0">
                            <p className="text-sm text-white truncate">{m.name}</p>
                            <p className="text-xs text-[#a0a7b3]">{m.media_type || '-'}</p>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Center: Sites/Posts Tree */}
              <div className="w-64 shrink-0 flex flex-col">
                <h3 className="text-white text-sm font-semibold mb-3">Cible de l'affichage</h3>

                {/* Type de cible */}
                <div className="flex gap-1 p-1 rounded-lg bg-[#111418]/80 border border-white/10 mb-3">
                  <button onClick={() => { setTargetType('post'); setSelectedGroupId(null); }}
                    className={`flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex-1 ${targetType === 'post' ? 'text-[#111418]' : 'text-[#a0a7b3] hover:text-white'}`}
                    style={targetType === 'post' ? { background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' } : {}}>
                    <Monitor className="w-3.5 h-3.5" /> Poste
                  </button>
                  <button onClick={() => { setTargetType('group'); setSelectedPostId(null); setConfig(null); }}
                    className={`flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors flex-1 ${targetType === 'group' ? 'text-[#111418]' : 'text-[#a0a7b3] hover:text-white'}`}
                    style={targetType === 'group' ? { background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' } : {}}>
                    <Users className="w-3.5 h-3.5" /> Groupe
                  </button>
                </div>

                {targetType === 'group' && (
                  <div className="mb-3">
                    <label className="text-xs text-[#a0a7b3] block mb-1.5">Groupe d'écrans</label>
                    <select value={selectedGroupId || ''} onChange={e => handleGroupSelect(Number(e.target.value) || null)}
                      className="w-full px-3 py-2 text-sm rounded-md bg-[#111418]/80 border border-white/10 text-white focus:outline-none focus:border-[#f6c200]/50">
                      <option value="">— Sélectionner —</option>
                      {groups.map(g => (
                        <option key={g.group_id} value={g.group_id}>
                          {g.name} ({g.post_count})
                        </option>
                      ))}
                    </select>
                    {selectedGroup && (
                      <p className="text-[10px] text-[#a0a7b3] mt-1.5">
                        La configuration sera appliquée aux {selectedGroup.post_count} poste(s) du groupe, puis synchronisée.
                      </p>
                    )}
                  </div>
                )}

                <h3 className="text-white text-sm font-semibold mb-3">Sites / Postes</h3>
                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden flex-1">
                  <div className="max-h-full overflow-y-auto">
                    {sitesWithPosts.length === 0 ? (
                      <p className="px-4 py-6 text-center text-[#a0a7b3] text-xs">Aucun site.</p>
                    ) : (
                      sitesWithPosts.map(s => (
                        <div key={s.site_id}>
                          <button onClick={() => toggleSite(s.site_id)}
                            className="w-full flex items-center gap-2 px-4 py-2.5 border-b border-white/5 hover:bg-white/[0.02] transition-colors text-left">
                            {expandedSites[s.site_id] ? <ChevronDown className="w-3.5 h-3.5 text-[#a0a7b3]" /> : <ChevronRight className="w-3.5 h-3.5 text-[#a0a7b3]" />}
                            <Building2 className="w-3.5 h-3.5 text-[#a0a7b3] shrink-0" />
                            <span className="text-sm text-white truncate">{s.name}</span>
                            <span className="ml-auto text-xs text-[#a0a7b3]">{s.posts.length}</span>
                          </button>
                          {expandedSites[s.site_id] && s.posts.map(p => (
                            <button key={p.post_id} onClick={() => selectPost(p.post_id)}
                              className={`w-full flex items-center gap-2 pl-10 pr-4 py-2 border-b border-white/5 transition-colors text-left ${selectedPostId === p.post_id ? 'bg-[#f6c200]/10 border-l-2 border-l-[#f6c200]' : 'hover:bg-white/[0.02]'}`}>
                              <Monitor className="w-3.5 h-3.5 text-[#a0a7b3] shrink-0" />
                              <span className="text-sm text-white truncate">{p.code}</span>
                              <span className="text-xs text-[#a0a7b3] truncate">{p.name}</span>
                            </button>
                          ))}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Right: Configuration Panel */}
              <div className="flex-1 flex flex-col min-w-0">
                {!selectedPostId ? (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-[#a0a7b3] text-sm">
                      {targetType === 'group'
                        ? 'Sélectionnez un groupe contenant au moins un poste'
                        : 'Sélectionnez un poste pour configurer'}
                    </p>
                  </div>
                ) : configLoading ? (
                  <div className="flex-1 flex items-center justify-center">
                    <span className="text-[#a0a7b3] text-sm">Chargement de la configuration...</span>
                  </div>
                ) : config ? (
                  <div className="flex-1 overflow-y-auto space-y-4">
                    {/* Post Header */}
                    <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-white font-semibold text-sm">
                            {targetType === 'group' ? (selectedGroup?.name || 'Groupe') : `${config.code} — ${config.name}`}
                          </h3>
                          <p className="text-[#a0a7b3] text-xs mt-0.5">
                            {targetType === 'group'
                              ? `Configuration appliquée à ${selectedGroup?.post_count ?? 0} poste(s) du groupe`
                              : 'Configuration du poste'}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          {targetType !== 'group' && (
                            <>
                              <button onClick={() => navigate(`/preview/${selectedPostId}`)}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[#1a1f24] border border-white/10 text-[#a0a7b3] hover:text-white transition-colors">
                                <Eye className="w-3.5 h-3.5" /> Aperçu
                              </button>
                              <button onClick={handleSync} disabled={saving}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-[#1a1f24] border border-white/10 text-[#a0a7b3] hover:text-[#f6c200] hover:border-[#f6c200]/30 transition-colors">
                                <RefreshCw className="w-3.5 h-3.5" /> Synchroniser
                              </button>
                            </>
                          )}
                          <button onClick={targetType === 'group' ? handleSaveGroup : handleSave} disabled={saving}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg disabled:opacity-50"
                            style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                            <Save className="w-3.5 h-3.5 text-[#111418]" />
                            <span className="text-[#111418]">
                              {saving
                                ? 'Enregistrement...'
                                : (targetType === 'group'
                                    ? `Appliquer au groupe (${selectedGroup?.post_count ?? 0})`
                                    : 'Enregistrer')}
                            </span>
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Layout Selection - Visual Cards */}
                    <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4">
                      <label className="block text-[#a0a7b3] text-xs font-semibold uppercase mb-3">Modèle de découpage</label>
                      <div className="grid grid-cols-3 gap-3">
                        {layoutsDetail.map(l => {
                          const isActive = currentLayout?.layout_id === l.layout_id;
                          return (
                            <button key={l.layout_id} onClick={() => handleLayoutSelect(l.layout_id)}
                              className={`relative rounded-lg border-2 overflow-hidden transition-all ${isActive ? 'border-[#f6c200] shadow-lg shadow-[#f6c200]/10' : 'border-white/10 hover:border-white/20'}`}>
                              <div className="bg-[#1a1a1a] p-2" style={{ aspectRatio: '16/9' }}>
                                <div className="relative w-full h-full">
                                  {(l.zones || []).map((zone, i) => {
                                    if (!zone.is_active) return null;
                                    const color = ZONE_COLORS[i % ZONE_COLORS.length];
                                    return (
                                      <div key={zone.zone_number}
                                        style={{
                                          position: 'absolute',
                                          left: `${zone.position_x}%`,
                                          top: `${zone.position_y}%`,
                                          width: `${zone.width}%`,
                                          height: `${zone.height}%`,
                                          backgroundColor: color.bg,
                                          border: `1px solid ${color.border}`,
                                        }}>
                                        <span className="text-white text-[8px] font-bold bg-black/40 px-1 rounded absolute top-0.5 left-0.5">Z{zone.zone_number}</span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                              <div className="px-2 py-1.5 bg-[#111418]">
                                <p className="text-[10px] text-white font-medium truncate">Layout #{l.layout_id}</p>
                                <p className="text-[9px] text-[#a0a7b3]">{l.active_zone_count} zones</p>
                              </div>
                              {isActive && (
                                <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-[#f6c200] flex items-center justify-center">
                                  <span className="text-[#111418] text-[8px] font-bold">✓</span>
                                </div>
                              )}
                            </button>
                          );
                        })}
                        {layoutsDetail.length === 0 && (
                          <p className="col-span-3 text-xs text-[#a0a7b3] text-center py-4">Aucun modèle disponible. Créez-en dans Découpage.</p>
                        )}
                      </div>
                    </div>

                    {/* General Settings */}
                    <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4">
                      <label className="block text-[#a0a7b3] text-xs font-semibold uppercase mb-3">Paramètres généraux</label>
                      <div className="space-y-3">
                        <label className="flex items-center gap-3 cursor-pointer">
                          <input type="checkbox" checked={config.loop_enabled} onChange={e => updateConfigField('loop_enabled', e.target.checked)}
                            className="w-4 h-4 rounded accent-[#f6c200] cursor-pointer" style={{ accentColor: '#f6c200' }} />
                          <span className="text-sm text-white">Boucle</span>
                        </label>
                        <label className="flex items-center gap-3 cursor-pointer">
                          <input type="checkbox" checked={config.display_enabled} onChange={e => updateConfigField('display_enabled', e.target.checked)}
                            className="w-4 h-4 rounded accent-[#f6c200] cursor-pointer" style={{ accentColor: '#f6c200' }} />
                          <span className="text-sm text-white">Actif</span>
                        </label>
                        <label className="flex items-center gap-3 cursor-pointer">
                          <input type="checkbox" checked={config.schedule_enabled} onChange={e => updateConfigField('schedule_enabled', e.target.checked)}
                            className="w-4 h-4 rounded accent-[#f6c200] cursor-pointer" style={{ accentColor: '#f6c200' }} />
                          <span className="text-sm text-white">Planifier</span>
                        </label>
                      </div>

                      {config.schedule_enabled && (
                        <div className="mt-3 pt-3 border-t border-white/5">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-xs text-[#a0a7b3]">Plannings</span>
                            <button onClick={() => setScheduleModal({})}
                              className="flex items-center gap-1 text-xs text-[#f6c200] hover:underline">
                              <Plus className="w-3 h-3" /> Ajouter
                            </button>
                          </div>
                          {config.schedules?.length === 0 ? (
                            <p className="text-xs text-[#a0a7b3]">Aucun planning.</p>
                          ) : (
                            <div className="space-y-2">
                              {(config.schedules || []).map(s => (
                                <div key={s.schedule_id} className="flex items-center justify-between bg-[#1a1f24] border border-white/5 rounded px-3 py-2">
                                  <div>
                                    <p className="text-xs text-white">{s.name}</p>
                                    <p className="text-[10px] text-[#a0a7b3]">
                                      {s.start_date || '?'} → {s.end_date || '?'} | {s.start_time || '?'} - {s.end_time || '?'}
                                    </p>
                                    {s.days_of_week && (
                                      <p className="text-[10px] text-[#a0a7b3]">{s.days_of_week}</p>
                                    )}
                                  </div>
                                  <div className="flex gap-1">
                                    <button onClick={() => setScheduleModal(s)} className="p-1 text-[#a0a7b3] hover:text-[#f6c200] transition-colors">
                                      <Pencil className="w-3 h-3" />
                                    </button>
                                    <button onClick={() => handleDeleteSchedule(s.schedule_id)} className="p-1 text-[#a0a7b3] hover:text-red-400 transition-colors">
                                      <Trash2 className="w-3 h-3" />
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Zone Parameters & Media Assignment */}
                    {currentZones.length > 0 && (
                      <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                        <div className="px-4 py-3 border-b border-white/10">
                          <h3 className="text-[#a0a7b3] text-xs font-semibold uppercase">Paramètres des zones et affectation des médias</h3>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b border-white/10">
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Zone</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Aff</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">X (%)</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Y (%)</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">L (%)</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">H (%)</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Média</th>
                                <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {editableZones.map((zone, i) => {
                                const color = ZONE_COLORS[i % ZONE_COLORS.length];
                                return (
                                  <tr key={zone.zone_number}
                                    className={`border-b border-white/5 transition-colors ${zone.is_active ? 'bg-white/[0.02]' : 'opacity-40'}`}>
                                    <td className="px-3 py-2 text-center">
                                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-white">
                                        <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color.border }} />
                                        Z-{zone.zone_number}
                                      </span>
                                    </td>
                                    <td className="px-3 py-2 text-center">
                                      <input type="checkbox" checked={zone.is_active}
                                        onChange={() => handleZoneActiveToggle(zone.zone_number)}
                                        className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200] cursor-pointer" />
                                    </td>
                                    {['position_x', 'position_y', 'width', 'height'].map(field => (
                                      <td key={field} className="px-3 py-2 text-center">
                                        <input type="number" min={0} max={100} step={0.5}
                                          value={zone[field]}
                                          onChange={e => handleZoneParamChange(zone.zone_number, field, e.target.value)}
                                          disabled={!zone.is_active}
                                          className="w-16 bg-[#1a1f24] border border-white/10 rounded px-2 py-1 text-xs text-white text-center focus:border-[#f6c200] focus:outline-none disabled:opacity-30" />
                                      </td>
                                    ))}
                                    <td className="px-3 py-2 text-xs text-[#a0a7b3]">
                                      {(zone.media_playlist || (zone.media ? [zone.media] : [])).length === 0 ? (
                                        <span className="text-[#6b7280]">Aucun</span>
                                      ) : (
                                        <div className="space-y-1 max-w-[200px]">
                                          {(zone.media_playlist || (zone.media ? [zone.media] : [])).map((m, idx) => (
                                            <div key={m.media_id} className="flex items-center gap-1.5 bg-[#1a1f24] border border-white/5 rounded px-2 py-1">
                                              <span className="text-[10px] text-[#a0a7b3] w-4">{idx + 1}.</span>
                                              <span className="text-xs text-white truncate flex-1">{m.name}</span>
                                              {m.media_type !== 'VIDEO' && (
                                                <input
                                                  type="number"
                                                  min={3}
                                                  max={60}
                                                  value={m.duration_seconds ?? 10}
                                                  onChange={e => updatePlaylistDuration(zone.zone_number, m.media_id, parseInt(e.target.value) || 10)}
                                                  title="Durée d'affichage (secondes)"
                                                  className="w-12 bg-[#0f1217] border border-white/10 rounded px-1 py-0.5 text-[10px] text-white text-center focus:border-[#f6c200] focus:outline-none"
                                                />
                                              )}
                                              <span className="text-[9px] text-[#6b7280] w-8 text-right">s</span>
                                              <button onClick={() => moveMediaInPlaylist(zone.zone_number, idx, -1)}
                                                disabled={idx === 0}
                                                className="text-[#a0a7b3] hover:text-[#f6c200] disabled:opacity-20 transition-colors" title="Monter">
                                                ↑
                                              </button>
                                              <button onClick={() => moveMediaInPlaylist(zone.zone_number, idx, 1)}
                                                disabled={idx === (zone.media_playlist || [zone.media]).length - 1}
                                                className="text-[#a0a7b3] hover:text-[#f6c200] disabled:opacity-20 transition-colors" title="Descendre">
                                                ↓
                                              </button>
                                              <button onClick={() => removeMediaFromZone(zone.zone_number, m.media_id)}
                                                className="text-[#a0a7b3] hover:text-red-400 transition-colors" title="Retirer">
                                                ✕
                                              </button>
                                            </div>
                                          ))}
                                        </div>
                                      )}
                                    </td>
                                    <td className="px-3 py-2 text-center">
                                      <button onClick={() => selectMediaForZone(zone.zone_number)}
                                        className="px-2 py-1 text-[10px] rounded bg-[#f6c200]/10 text-[#f6c200] hover:bg-[#f6c200]/20 transition-colors border border-[#f6c200]/20"
                                        title="Ajouter le média sélectionné à la playlist">
                                        Ajouter
                                      </button>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-[#a0a7b3] text-sm">Impossible de charger la configuration.</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {showSyncModal && syncJobId && (
        <SyncProgressModal jobId={syncJobId} onClose={() => { setShowSyncModal(false); setSyncJobId(null); }} />
      )}
    </div>
  );
}
