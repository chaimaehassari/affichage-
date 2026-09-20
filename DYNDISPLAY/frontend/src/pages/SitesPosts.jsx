import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Plus, Pencil, Trash2, Eye, Search } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getSites, createSite, updateSite, deleteSite, getPosts, createPost, updatePost, deletePost } from '../services/sites';
import { extractDetailMessage } from '../services/api';

export default function SitesPosts() {
  const { logout, user, hasPermission } = useAuth();
  const isAdmin = user?.profile_name === 'Administrateur';
  const navigate = useNavigate();

  const [sites, setSites] = useState([]);
  const [posts, setPosts] = useState([]);
  const [selectedSite, setSelectedSite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { type: 'site', id } or { type: 'post', id }

  const [showSiteModal, setShowSiteModal] = useState(false);
  const [showPostModal, setShowPostModal] = useState(false);
  const [editingSite, setEditingSite] = useState(null);
  const [editingPost, setEditingPost] = useState(null);

  const [siteForm, setSiteForm] = useState({ code: '', name: '', address: '', description: '', is_active: true });
  const [postForm, setPostForm] = useState({ code: '', name: '', player_type: 'Windows', ip_address: '', is_active: true, site_id: '' });
  const [saving, setSaving] = useState(false);

  const [siteSearch, setSiteSearch] = useState('');
  const [postSearch, setPostSearch] = useState('');

  const filteredSites = sites.filter(s => {
    const t = siteSearch.trim().toLowerCase();
    if (!t) return true;
    return (`${s.code} ${s.name}`).toLowerCase().includes(t);
  });

  const filteredPosts = posts.filter(p => {
    const t = postSearch.trim().toLowerCase();
    if (!t) return true;
    return (`${p.code} ${p.name}`).toLowerCase().includes(t);
  });

  const fetchSites = useCallback(async () => {
    const result = await getSites();
    if (result.ok && result.data) setSites(result.data);
  }, []);

  const fetchPosts = useCallback(async (siteId) => {
    if (!siteId) { setPosts([]); return; }
    const result = await getPosts(siteId);
    if (result.ok && result.data) setPosts(result.data);
  }, []);

  useEffect(() => {
    async function init() {
      setLoading(true);
      await fetchSites();
      setLoading(false);
    }
    init();
  }, [fetchSites]);

  useEffect(() => {
    fetchPosts(selectedSite?.site_id);
  }, [selectedSite, fetchPosts]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 3000);
  }

  // --- Site CRUD ---
  function openNewSite() {
    setEditingSite(null);
    setSiteForm({ code: '', name: '', address: '', description: '', is_active: true, client_code: '' });
    setShowSiteModal(true);
  }

  function openEditSite(site) {
    setEditingSite(site);
    setSiteForm({ code: site.code, name: site.name, address: site.address || '', description: site.description || '', is_active: site.is_active, client_code: site.client_code || '' });
    setShowSiteModal(true);
  }

  async function handleSaveSite(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...siteForm };
      let result;
      if (editingSite) {
        result = await updateSite(editingSite.site_id, payload);
      } else {
        result = await createSite(payload);
      }
      if (result.ok) {
        showNotif('success', editingSite ? 'Site modifié.' : 'Site créé.');
        setShowSiteModal(false);
        await fetchSites();
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur.'));
      }
    } catch {
      showNotif('error', 'Erreur de connexion.');
    }
    setSaving(false);
  }

  async function handleDeleteSite() {
    if (!deleteConfirm) return;
    const result = await deleteSite(deleteConfirm.id);
    if (result.ok) {
      showNotif('success', 'Site supprimé.');
      if (selectedSite?.site_id === deleteConfirm.id) setSelectedSite(null);
      await fetchSites();
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.'));
    }
    setDeleteConfirm(null);
  }

  // --- Post CRUD ---
  function openNewPost() {
    setEditingPost(null);
    setPostForm({ code: '', name: '', player_type: 'Windows', ip_address: '', is_active: true, site_id: selectedSite?.site_id || '' });
    setShowPostModal(true);
  }

  function openEditPost(post) {
    setEditingPost(post);
    setPostForm({ code: post.code, name: post.name, player_type: post.player_type || 'Windows', ip_address: post.ip_address || '', is_active: post.is_active, site_id: post.site_id });
    setShowPostModal(true);
  }

  async function handleSavePost(e) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...postForm, site_id: parseInt(postForm.site_id) };
      let result;
      if (editingPost) {
        result = await updatePost(editingPost.post_id, payload);
      } else {
        result = await createPost(payload);
      }
      if (result.ok) {
        showNotif('success', editingPost ? 'Poste modifié.' : 'Poste créé.');
        setShowPostModal(false);
        await fetchPosts(selectedSite?.site_id);
        await fetchSites();
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur.'));
      }
    } catch {
      showNotif('error', 'Erreur de connexion.');
    }
    setSaving(false);
  }

  async function handleDeletePost(postId) {
    const result = await deletePost(postId);
    if (result.ok) {
      showNotif('success', 'Poste supprimé.');
      await fetchPosts(selectedSite?.site_id);
      await fetchSites();
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur.'));
    }
    setDeleteConfirm(null);
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

      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-2">Confirmation de suppression</h3>
            <p className="text-[#a0a7b3] text-sm mb-6">Voulez-vous vraiment supprimer cet élément ?</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
              <button onClick={() => {
                if (deleteConfirm.type === 'site') {
                  handleDeleteSite();
                } else {
                  handleDeletePost(deleteConfirm.id);
                }
              }} className="px-4 py-2 bg-red-700 text-white text-sm rounded-lg hover:bg-red-600">Supprimer</button>
            </div>
          </div>
        </div>
      )}

      {/* Site Modal */}
      {showSiteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-[480px] shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-4">{editingSite ? 'Modifier le site' : 'Nouveau site'}</h3>
            <form onSubmit={handleSaveSite} className="space-y-3">
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Code <span className="text-red-400">*</span></label>
                <input type="text" value={siteForm.code} onChange={(e) => setSiteForm(p => ({ ...p, code: e.target.value }))} required
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Nom <span className="text-red-400">*</span></label>
                <input type="text" value={siteForm.name} onChange={(e) => setSiteForm(p => ({ ...p, name: e.target.value }))} required
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Adresse</label>
                <input type="text" value={siteForm.address} onChange={(e) => setSiteForm(p => ({ ...p, address: e.target.value }))}
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Description</label>
                <textarea value={siteForm.description} onChange={(e) => setSiteForm(p => ({ ...p, description: e.target.value }))} rows={3}
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50 resize-none" />
              </div>
              {isAdmin && (
                <div>
                  <label className="block text-xs text-[#a0a7b3] mb-1">N° client propriétaire</label>
                  <input type="text" value={siteForm.client_code || ''} onChange={(e) => setSiteForm(p => ({ ...p, client_code: e.target.value }))}
                    placeholder="Laisser vide pour un site global"
                    className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                </div>
              )}
              <div className="flex items-center gap-3">
                <button type="button" onClick={() => setSiteForm(p => ({ ...p, is_active: !p.is_active }))}
                  className={`w-10 h-5 rounded-full transition-colors relative ${siteForm.is_active ? 'bg-[#f6c200]' : 'bg-[#2a2f36]'}`}>
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${siteForm.is_active ? 'left-5.5' : 'left-0.5'}`} />
                </button>
                <span className="text-sm text-white">{siteForm.is_active ? 'Actif' : 'Inactif'}</span>
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button type="button" onClick={() => setShowSiteModal(false)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
                <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Post Modal */}
      {showPostModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-[480px] shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-4">{editingPost ? 'Modifier le poste' : 'Nouveau poste'}</h3>
            <form onSubmit={handleSavePost} className="space-y-3">
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Site <span className="text-red-400">*</span></label>
                <select value={postForm.site_id} onChange={(e) => setPostForm(p => ({ ...p, site_id: e.target.value }))} required
                  className="w-full bg-[#111418] text-white px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50 appearance-none">
                  <option value="">-- Sélectionner --</option>
                  {sites.map(s => <option key={s.site_id} value={s.site_id}>{s.code} - {s.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Code <span className="text-red-400">*</span></label>
                <input type="text" value={postForm.code} onChange={(e) => setPostForm(p => ({ ...p, code: e.target.value }))} required
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Nom <span className="text-red-400">*</span></label>
                <input type="text" value={postForm.name} onChange={(e) => setPostForm(p => ({ ...p, name: e.target.value }))} required
                  className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-[#a0a7b3] mb-1">Type player</label>
                  <select value={postForm.player_type} onChange={(e) => setPostForm(p => ({ ...p, player_type: e.target.value }))}
                    className="w-full bg-[#111418] text-white px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50 appearance-none">
                    <option value="Windows">Windows</option>
                    <option value="Android">Android</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-[#a0a7b3] mb-1">Adresse IP</label>
                  <input type="text" value={postForm.ip_address} onChange={(e) => setPostForm(p => ({ ...p, ip_address: e.target.value }))}
                    className="w-full bg-[#111418] text-white placeholder-[#a0a7b3] px-3 py-2.5 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button type="button" onClick={() => setPostForm(p => ({ ...p, is_active: !p.is_active }))}
                  className={`w-10 h-5 rounded-full transition-colors relative ${postForm.is_active ? 'bg-[#f6c200]' : 'bg-[#2a2f36]'}`}>
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${postForm.is_active ? 'left-5.5' : 'left-0.5'}`} />
                </button>
                <span className="text-sm text-white">{postForm.is_active ? 'Actif' : 'Inactif'}</span>
              </div>
              <div className="flex gap-3 justify-end pt-2">
                <button type="button" onClick={() => setShowPostModal(false)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
                <button type="submit" disabled={saving} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                  <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
                </button>
              </div>
            </form>
          </div>
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

        <main className="flex-1 px-8 py-6">
          <div className="flex items-center gap-3 mb-6">
            <button onClick={() => navigate('/')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
              <ArrowLeft className="w-4 h-4" /> Retour
            </button>
            <h2 className="text-white text-lg font-semibold">Sites & Postes</h2>
          </div>

          {loading ? (
            <span className="text-[#a0a7b3] text-sm">Chargement...</span>
          ) : (
            <div className="flex gap-6" style={{ minHeight: '60vh' }}>
              {/* Left: Sites */}
              <div className="w-80 shrink-0">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-white text-sm font-semibold">Sites</h3>
                  {hasPermission('create_site') && (
                    <button onClick={openNewSite} className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                      <Plus className="w-3 h-3 text-[#111418]" /> <span className="text-[#111418]">Nouveau</span>
                    </button>
                  )}
                </div>
                <div className="relative mb-3">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
                  <input type="text" value={siteSearch} onChange={(e) => setSiteSearch(e.target.value)}
                    placeholder="Rechercher un site..."
                    className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-2 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                </div>
                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                  <div className="max-h-[55vh] overflow-y-auto">
                    {filteredSites.length === 0 ? (
                      <p className="px-4 py-6 text-center text-[#a0a7b3] text-sm">{siteSearch ? 'Aucun site trouvé.' : 'Aucun site.'}</p>
                    ) : (
                      filteredSites.map(s => (
                        <div key={s.site_id}
                          onClick={() => setSelectedSite(s)}
                          className={`flex items-center justify-between px-4 py-3 cursor-pointer border-b border-white/5 transition-colors ${selectedSite?.site_id === s.site_id ? 'bg-[#f6c200]/10 border-l-2 border-l-[#f6c200]' : 'hover:bg-white/[0.02]'}`}>
                          <div className="min-w-0">
                            <p className="text-sm text-white truncate">{s.code}</p>
                            <p className="text-xs text-[#a0a7b3] truncate">{s.name}</p>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            {hasPermission('update_site') && (
                              <button onClick={(e) => { e.stopPropagation(); openEditSite(s); }} className="p-1 text-[#a0a7b3] hover:text-[#f6c200] transition-colors" title="Modifier">
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                            )}
                            {hasPermission('delete_site') && (
                              <button onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ type: 'site', id: s.site_id }); }} className="p-1 text-[#a0a7b3] hover:text-red-400 transition-colors" title="Supprimer">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Right: Posts */}
              <div className="flex-1">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-white text-sm font-semibold">
                    {selectedSite ? `Postes — ${selectedSite.name}` : 'Sélectionnez un site'}
                  </h3>
                  {selectedSite && hasPermission('create_post') && (
                    <button onClick={openNewPost} className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                      <Plus className="w-3 h-3 text-[#111418]" /> <span className="text-[#111418]">Nouveau</span>
                    </button>
                  )}
                </div>
                <div className="relative mb-3">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
                  <input type="text" value={postSearch} onChange={(e) => setPostSearch(e.target.value)}
                    placeholder="Rechercher un poste..."
                    className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-2 rounded-lg border border-white/10 text-sm focus:outline-none focus:border-[#f6c200]/50" />
                </div>
                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                  {!selectedSite ? (
                    <p className="px-4 py-8 text-center text-[#a0a7b3] text-sm">Sélectionnez un site pour voir ses postes.</p>
                  ) : filteredPosts.length === 0 ? (
                    <p className="px-4 py-8 text-center text-[#a0a7b3] text-sm">{postSearch ? 'Aucun poste trouvé.' : 'Aucun poste pour ce site.'}</p>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-white/10">
                          <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Code</th>
                          <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Nom</th>
                          <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Type</th>
                          <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">IP</th>
                          <th className="text-left px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Statut</th>
                          <th className="text-right px-4 py-3 text-xs font-semibold text-[#a0a7b3] uppercase">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPosts.map(p => (
                          <tr key={p.post_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                            <td className="px-4 py-3 text-sm text-white">{p.code}</td>
                            <td className="px-4 py-3 text-sm text-[#a0a7b3]">{p.name}</td>
                            <td className="px-4 py-3 text-sm text-[#a0a7b3]">{p.player_type || '-'}</td>
                            <td className="px-4 py-3 text-sm text-[#a0a7b3]">{p.ip_address || '-'}</td>
                            <td className="px-4 py-3">
                              <span className={`inline-flex items-center text-xs font-medium px-2.5 py-1 rounded-full border ${p.is_active ? 'bg-emerald-500/15 border-emerald-500/20 text-emerald-300' : 'bg-zinc-500/15 border-zinc-500/20 text-zinc-400'}`}>
                                {p.is_active ? 'Actif' : 'Inactif'}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <button onClick={() => navigate(`/preview/${p.post_id}`)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Aperçu">
                                  <Eye className="w-4 h-4" />
                                </button>
                                {hasPermission('update_post') && (
                                  <button onClick={() => openEditPost(p)} className="p-1.5 text-[#a0a7b3] hover:text-[#f6c200] transition-colors rounded hover:bg-white/5" title="Modifier">
                                    <Pencil className="w-4 h-4" />
                                  </button>
                                )}
                                {hasPermission('delete_post') && (
                                  <button onClick={() => setDeleteConfirm({ type: 'post', id: p.post_id })} className="p-1.5 text-[#a0a7b3] hover:text-red-400 transition-colors rounded hover:bg-white/5" title="Supprimer">
                                    <Trash2 className="w-4 h-4" />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
