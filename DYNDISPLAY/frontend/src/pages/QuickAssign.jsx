import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ChevronRight, ChevronDown, Building2, Monitor, ArrowLeft, Save, Search, ArrowRight, X } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSites, getPosts, getMedia } from '../services/sites';
import { getPostConfig, updatePostZones } from '../services/display';
import { extractDetailMessage } from '../services/api';

export default function QuickAssign() {
  const { logout, user, canAccessZone } = useAuth();
  const navigate = useNavigate();

  const [sites, setSites] = useState([]);
  const [posts, setPosts] = useState([]);
  const [mediaList, setMediaList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);

  const [selectedMedia, setSelectedMedia] = useState(null);
  const [selectedPostId, setSelectedPostId] = useState(null);
  const [expandedSites, setExpandedSites] = useState({});
  const [mediaSearch, setMediaSearch] = useState('');

  const [config, setConfig] = useState(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const init = useCallback(async () => {
    setLoading(true);
    const [sitesRes, postsRes, mediaRes] = await Promise.all([
      getSites(),
      getPosts(),
      getMedia(),
    ]);
    if (sitesRes.ok && sitesRes.data) {
      setSites(sitesRes.data);
      const expanded = {};
      sitesRes.data.forEach(s => { expanded[s.site_id] = true; });
      setExpandedSites(expanded);
    }
    if (postsRes.ok && postsRes.data) setPosts(postsRes.data);
    if (mediaRes.ok && mediaRes.data) setMediaList(mediaRes.data);
    setLoading(false);
  }, []);

  useEffect(() => { init(); }, [init]);

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

  function assignMediaToZone(zoneNumber) {
    if (!selectedMedia) {
      showNotif('error', 'Sélectionnez d\'abord un média dans la colonne de gauche.');
      return;
    }
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) {
          const m = mediaList.find(ml => ml.media_id === selectedMedia);
          return { ...z, media: m ? { media_id: m.media_id, name: m.name, media_type: m.media_type } : null };
        }
        return z;
      });
      return { ...prev, zones };
    });
  }

  function removeMediaFromZone(zoneNumber) {
    setConfig(prev => {
      if (!prev) return prev;
      const zones = prev.zones.map(z => {
        if (z.zone_number === zoneNumber) return { ...z, media: null };
        return z;
      });
      return { ...prev, zones };
    });
  }

  async function handleSave() {
    if (!selectedPostId || !config) return;
    setSaving(true);

    const zones = config.zones
      .filter(z => canAccessZone(z.zone_number))
      .map(z => ({
        zone_number: z.zone_number,
        media_id: z.media?.media_id || null,
      }));

    const result = await updatePostZones(selectedPostId, zones);
    if (result.ok) {
      showNotif('success', 'Affectations enregistrées.');
      await loadConfig(selectedPostId);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.'));
    }
    setSaving(false);
  }

  const filteredMedia = mediaSearch
    ? mediaList.filter(m => m.name.toLowerCase().includes(mediaSearch.toLowerCase()))
    : mediaList;

  const sitesWithPosts = sites.map(s => ({
    ...s,
    posts: posts.filter(p => p.site_id === s.site_id),
  }));

  const selectedPost = posts.find(p => p.post_id === selectedPostId);
  const currentZones = config?.zones || [];
  const editableZones = currentZones.filter(z => canAccessZone(z.zone_number));

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
            <h2 className="text-white text-lg font-semibold">Affectation rapide des médias</h2>
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

              {/* Right: Zone Assignments */}
              <div className="flex-1 flex flex-col min-w-0">
                {!selectedPostId ? (
                  <div className="flex-1 flex items-center justify-center">
                    <p className="text-[#a0a7b3] text-sm">Sélectionnez un poste pour affecter des médias</p>
                  </div>
                ) : configLoading ? (
                  <div className="flex-1 flex items-center justify-center">
                    <span className="text-[#a0a7b3] text-sm">Chargement...</span>
                  </div>
                ) : config ? (
                  <div className="flex-1 flex flex-col">
                    <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4 mb-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-white font-semibold text-sm">{config.code} — {config.name}</h3>
                          <p className="text-[#a0a7b3] text-xs mt-0.5">
                            {config.layout ? `Layout #${config.layout.layout_id}` : 'Aucun layout'} — {currentZones.length} zone(s)
                          </p>
                        </div>
                        <button onClick={handleSave} disabled={saving}
                          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50"
                          style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                          <Save className="w-4 h-4 text-[#111418]" />
                          <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
                        </button>
                      </div>
                    </div>

                    {currentZones.length === 0 ? (
                      <div className="flex-1 flex items-center justify-center">
                        <p className="text-[#a0a7b3] text-sm">Aucune zone active. Configurez d'abord le layout du poste.</p>
                      </div>
                    ) : (
                      <div className="flex-1 overflow-y-auto space-y-2">
                        {editableZones.map(zone => (
                          <div key={zone.zone_number}
                            className="bg-[#111418]/80 border border-white/10 rounded-lg p-3 flex items-center gap-4">
                            <span className="text-sm font-semibold text-white w-16 shrink-0">Z-{zone.zone_number}</span>
                            <div className="flex-1 min-w-0">
                              {zone.media ? (
                                <div className="flex items-center gap-2">
                                  <span className="text-sm text-white truncate">{zone.media.name}</span>
                                  <span className="text-xs text-[#a0a7b3]">({zone.media.media_type})</span>
                                </div>
                              ) : (
                                <span className="text-sm text-[#a0a7b3]">Aucun média</span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <button onClick={() => assignMediaToZone(zone.zone_number)}
                                className="p-2 rounded bg-[#f6c200]/10 text-[#f6c200] hover:bg-[#f6c200]/20 transition-colors border border-[#f6c200]/20"
                                title="Affecter le média sélectionné">
                                <ArrowRight className="w-4 h-4" />
                              </button>
                              {zone.media && (
                                <button onClick={() => removeMediaFromZone(zone.zone_number)}
                                  className="p-2 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors border border-red-500/20"
                                  title="Retirer le média">
                                  <X className="w-4 h-4" />
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
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
    </div>
  );
}
