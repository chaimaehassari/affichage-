import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  LogOut, ArrowLeft, Plus, Minus, Users, Monitor, Save, Trash2, Pencil,
  MonitorPlay, X,
} from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import {
  getGroups, createGroup, updateGroup, deleteGroup,
  getGroupComposition, setGroupMembership,
} from '../services/sites';
import { extractDetailMessage } from '../services/api';

export default function BatchAssign() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [groups, setGroups] = useState([]);
  const [selectedGroupId, setSelectedGroupId] = useState(null);
  const [composition, setComposition] = useState(null);
  const [compositionLoading, setCompositionLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);

  const [nameModal, setNameModal] = useState(null); // { mode: 'create' | 'edit', group }
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showAddPicker, setShowAddPicker] = useState(false);



  const init = useCallback(async () => {
    setLoading(true);
    const groupsRes = await getGroups();
    if (groupsRes.ok && groupsRes.data) setGroups(groupsRes.data);
    setLoading(false);
  }, []);

  useEffect(() => { init(); }, [init]);

  useEffect(() => {
    if (selectedGroupId) loadComposition(selectedGroupId);
    else setComposition(null);
  }, [selectedGroupId]);

  const loadComposition = useCallback(async (groupId) => {
    setCompositionLoading(true);
    const res = await getGroupComposition(groupId);
    if (res.ok && res.data) setComposition(res.data);
    setCompositionLoading(false);
  }, []);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 5000);
  }

  const selectedGroup = groups.find(g => g.group_id === selectedGroupId) || null;

  function togglePost(siteId, postId) {
    if (!composition) return;
    setComposition(prev => {
      const sites = prev.sites.map(s => {
        if (s.site_id !== siteId) return s;
        return {
          ...s,
          posts: s.posts.map(p =>
            p.post_id === postId ? { ...p, in_group: !p.in_group } : p
          ),
        };
      });
      const count = sites.flatMap(s => s.posts).filter(p => p.in_group).length;
      return { ...prev, sites, post_count: count };
    });
  }

  function toggleAllInSite(siteId, select) {
    if (!composition) return;
    setComposition(prev => {
      const sites = prev.sites.map(s => {
        if (s.site_id !== siteId) return s;
        return { ...s, posts: s.posts.map(p => ({ ...p, in_group: select })) };
      });
      const count = sites.flatMap(s => s.posts).filter(p => p.in_group).length;
      return { ...prev, sites, post_count: count };
    });
  }

  function selectedPostIds() {
    return (composition?.sites || []).flatMap(s => s.posts).filter(p => p.in_group).map(p => p.post_id);
  }

  const availableCount = (composition?.sites || [])
    .flatMap(s => s.posts).filter(p => !p.in_group).length;

  async function handleCreateGroup(data) {
    const res = await createGroup(data);
    if (res.ok && res.data) {
      showNotif('success', `Groupe « ${res.data.name} » créé.`);
      setNameModal(null);
      const fres = await getGroups();
      if (fres.ok) setGroups(fres.data);
      setSelectedGroupId(res.data.group_id);
    } else {
      showNotif('error', extractDetailMessage(res.data?.detail, 'Erreur lors de la création.'));
    }
  }

  async function handleEditGroup(data) {
    if (!nameModal.group) return;
    const res = await updateGroup(nameModal.group.group_id, data);
    if (res.ok && res.data) {
      showNotif('success', 'Groupe modifié.');
      setNameModal(null);
      const fres = await getGroups();
      if (fres.ok) setGroups(fres.data);
      setSelectedGroupId(nameModal.group.group_id);
    } else {
      showNotif('error', extractDetailMessage(res.data?.detail, 'Erreur lors de la modification.'));
    }
  }

  async function handleSaveMembership() {
    if (!selectedGroupId) return;
    const ids = selectedPostIds();
    const res = await setGroupMembership(selectedGroupId, ids);
    if (res.ok && res.data) {
      setComposition(res.data);
      showNotif('success', `Composition enregistrée (${res.data.post_count} poste(s)).`);
      const fres = await getGroups();
      if (fres.ok) setGroups(fres.data);
    } else {
      showNotif('error', extractDetailMessage(res.data?.detail, 'Erreur lors de l\'enregistrement.'));
    }
  }

  async function handleDeleteGroup() {
    if (!selectedGroupId) return;
    const res = await deleteGroup(selectedGroupId);
    if (res.ok) {
      showNotif('success', 'Groupe supprimé.');
      setConfirmDelete(false);
      setSelectedGroupId(null);
      const fres = await getGroups();
      if (fres.ok) setGroups(fres.data);
    } else {
      showNotif('error', extractDetailMessage(res.data?.detail, 'Erreur lors de la suppression.'));
    }
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      {nameModal && (
        <GroupNameModal
          group={nameModal.group}
          onCreate={handleCreateGroup}
          onEdit={handleEditGroup}
          onClose={() => setNameModal(null)}
        />
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-xl p-6 w-96">
            <h3 className="text-white font-semibold mb-3">Supprimer le groupe</h3>
            <p className="text-[#a0a7b3] text-sm mb-5">
              Confirmez la suppression du groupe « {selectedGroup?.name || ''} » ? Cette action est irréversible.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-2 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg transition-colors">
                Annuler
              </button>
              <button onClick={handleDeleteGroup} className="px-4 py-2 text-sm font-semibold rounded-lg text-white bg-red-600 hover:bg-red-500 transition-colors">
                Supprimer
              </button>
            </div>
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
            <h2 className="text-white text-lg font-semibold">Groupes d'écrans</h2>
          </div>

          {loading ? (
            <span className="text-[#a0a7b3] text-sm">Chargement...</span>
          ) : (
            <div className="grid grid-cols-12 gap-4" style={{ minHeight: '60vh' }}>
              {/* Left: group list */}
              <div className="col-span-3">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-white text-sm font-semibold">Groupes</h3>
                  <button onClick={() => setNameModal({ mode: 'create', group: null })}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md text-[#111418]"
                    style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                    <Plus className="w-3.5 h-3.5" /> Créer
                  </button>
                </div>
                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                  <div className="max-h-[50vh] overflow-y-auto">
                    {groups.length === 0 ? (
                      <p className="px-4 py-4 text-center text-[#a0a7b3] text-xs">Aucun groupe.</p>
                    ) : (
                      groups.map(g => (
                        <button key={g.group_id} onClick={() => setSelectedGroupId(g.group_id)}
                          className={`w-full flex flex-col gap-1 px-4 py-2.5 border-b border-white/5 text-left transition-colors ${selectedGroupId === g.group_id ? 'bg-[#f6c200]/10 border-l-2 border-l-[#f6c200]' : 'hover:bg-white/[0.02]'}`}>
                          <span className="flex items-center gap-2 text-sm text-white">
                            <Users className="w-3.5 h-3.5 opacity-60" /> <span className="truncate">{g.name}</span>
                          </span>
                          <span className="text-xs text-[#a0a7b3]">{g.post_count} poste(s)</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Center: composition */}
              <div className="col-span-9">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-white text-sm font-semibold">
                    Composition {selectedGroup ? `— ${selectedGroup.name}` : ''} ({composition?.post_count ?? 0})
                  </h3>
                  <div className="flex gap-2">
                    {selectedGroup && (
                      <>
                        <button onClick={() => setNameModal({ mode: 'edit', group: selectedGroup })}
                          className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-white/10 text-[#a0a7b3] hover:text-white transition-colors">
                          <Pencil className="w-3.5 h-3.5" /> Renommer
                        </button>
                        <button onClick={() => setConfirmDelete(true)}
                          className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-red-700/40 text-red-300 hover:bg-red-600/10 transition-colors">
                          <Trash2 className="w-3.5 h-3.5" /> Supprimer
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                  {!selectedGroup ? (
                    <p className="px-4 py-10 text-center text-[#a0a7b3] text-sm">
                      Sélectionnez un groupe ou créez-en un.
                    </p>
                  ) : compositionLoading ? (
                    <p className="px-4 py-10 text-center text-[#a0a7b3] text-sm">Chargement...</p>
                  ) : !composition ? (
                    <p className="px-4 py-10 text-center text-[#a0a7b3] text-sm">Groupe introuvable.</p>
                  ) : showAddPicker ? (
                    <AddMembersPicker
                      composition={composition}
                      onToggle={togglePost}
                      onToggleSite={toggleAllInSite}
                      onDone={() => setShowAddPicker(false)}
                    />
                  ) : (
                    <div className="max-h-[50vh] overflow-y-auto">
                      {selectedPostIds().length === 0 ? (
                        <div className="px-4 py-10 text-center">
                          <p className="text-[#a0a7b3] text-sm mb-2">Ce groupe ne contient aucun poste.</p>
                          <button onClick={() => setShowAddPicker(true)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg text-[#111418]"
                            style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                            <Plus className="w-3.5 h-3.5" /> Ajouter des postes
                          </button>
                        </div>
                      ) : (
                        composition.sites.map(site => {
                          const siteMembers = site.posts.filter(p => p.in_group);
                          if (siteMembers.length === 0) return null;
                          return (
                            <div key={site.site_id} className="border-b border-white/5">
                              <div className="flex items-center gap-2 px-4 py-2.5 bg-white/[0.02]">
                                <Building2Icon />
                                <span className="text-sm font-medium text-white">{site.name}</span>
                                <span className="text-xs text-[#a0a7b3]">{siteMembers.length} poste(s)</span>
                              </div>
                              <div className="px-4 py-1">
                                {siteMembers.map(p => (
                                  <div key={p.post_id} className="flex items-center justify-between gap-2 px-2 py-1.5 hover:bg-white/[0.02] transition-colors">
                                    <div className="flex items-center gap-3 min-w-0">
                                      <Monitor className="w-3.5 h-3.5 opacity-50 shrink-0" />
                                      <span className="text-sm text-white">{p.code}</span>
                                      <span className="text-xs text-[#a0a7b3] truncate">{p.name}</span>
                                    </div>
                                    <button onClick={() => togglePost(site.site_id, p.post_id)}
                                      title="Retirer du groupe"
                                      className="flex items-center justify-center w-6 h-6 rounded-md text-[#a0a7b3] hover:text-red-400 hover:bg-red-600/10 transition-colors">
                                      <X className="w-4 h-4" />
                                    </button>
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>

                {selectedGroup && !showAddPicker && (
                  <div className="flex justify-end mt-3">
                    {selectedPostIds().length > 0 && availableCount > 0 && (
                      <button onClick={() => setShowAddPicker(true)}
                        className="flex items-center gap-2 px-3 py-2 mr-2 text-sm font-medium rounded-lg border border-white/10 text-[#a0a7b3] hover:text-white hover:bg-white/5 transition-colors">
                        <Plus className="w-3.5 h-3.5" /> Ajouter des postes
                      </button>
                    )}
                    <button onClick={handleSaveMembership} disabled={!selectedGroup}
                      className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-white/10 text-[#a0a7b3] hover:text-white hover:bg-white/5 transition-colors">
                      <Save className="w-3.5 h-3.5" /> Enregistrer la composition
                    </button>
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

function Building2Icon() {
  return <MonitorPlay className="w-3.5 h-3.5 text-[#f6c200]/70" />;
}

function AddMembersPicker({ composition, onToggle, onToggleSite, onDone }) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 bg-white/[0.02]">
        <span className="text-sm font-medium text-white">Ajouter des postes</span>
        <button onClick={onDone}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-md text-[#111418]"
          style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
          Terminé
        </button>
      </div>
      <div className="max-h-[50vh] overflow-y-auto">
        {composition.sites.length === 0 ? (
          <p className="px-4 py-6 text-center text-[#a0a7b3] text-xs">Aucun site.</p>
        ) : composition.sites.map(site => {
          const allSel = site.posts.length > 0 && site.posts.every(p => p.in_group);
          return (
            <div key={site.site_id} className="border-b border-white/5">
              <div className="flex items-center gap-3 px-4 py-2.5 bg-white/[0.02]">
                <input type="checkbox"
                  checked={allSel}
                  onChange={() => onToggleSite(site.site_id, !allSel)}
                  className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                <button onClick={() => onToggleSite(site.site_id, !allSel)}
                  className="flex items-center gap-2 text-sm font-medium text-white cursor-pointer">
                  <Building2Icon /> <span>{site.name}</span>
                  <span className="text-xs text-[#a0a7b3]">({site.posts.filter(p => p.in_group).length}/{site.posts.length})</span>
                </button>
              </div>
              <div className="pl-10 pr-4 pb-1">
                {site.posts.length === 0 ? (
                  <p className="py-2 text-xs text-[#a0a7b3]">Aucun poste.</p>
                ) : site.posts.map(p => (
                  <label key={p.post_id} className="flex items-center gap-3 px-2 py-1.5 cursor-pointer hover:bg-white/[0.02] transition-colors">
                    <input type="checkbox" checked={p.in_group} onChange={() => onToggle(site.site_id, p.post_id)}
                      className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                    <Monitor className="w-3.5 h-3.5 opacity-50" />
                    <span className="text-sm text-white">{p.code}</span>
                    <span className="text-xs text-[#a0a7b3] truncate">{p.name}</span>
                  </label>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GroupNameModal({ group, onCreate, onEdit, onClose }) {
  const [name, setName] = useState(group?.name || '');
  const [description, setDescription] = useState(group?.description || '');
  const isEdit = !!group;

  async function submit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    const data = { name: name.trim(), description: description.trim() || null, is_active: true };
    if (isEdit) await onEdit(data);
    else await onCreate(data);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <form onSubmit={submit} className="bg-[#1a1f24] border border-white/10 rounded-xl p-6 w-96">
        <h3 className="text-white font-semibold mb-4">{isEdit ? 'Modifier le groupe' : 'Créer un groupe'}</h3>
        <label className="text-xs text-[#a0a7b3] block mb-1.5">Nom du groupe</label>
        <input value={name} onChange={e => setName(e.target.value)} autoFocus
          placeholder="Ex. Groupe Casablanca"
          className="w-full px-3 py-2 text-sm rounded-md bg-[#0b0d10] border border-white/10 text-white focus:outline-none focus:border-[#f6c200]/50 mb-3" />
        <label className="text-xs text-[#a0a7b3] block mb-1.5">Description</label>
        <textarea value={description} onChange={e => setDescription(e.target.value)}
          rows={2} placeholder="Optionnel"
          className="w-full px-3 py-2 text-sm rounded-md bg-[#0b0d10] border border-white/10 text-white focus:outline-none focus:border-[#f6c200]/50 mb-5" />
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-[#a0a7b3] hover:text-white border border-white/10 rounded-lg transition-colors">
            Annuler
          </button>
          <button type="submit" disabled={!name.trim()}
            className="px-4 py-2 text-sm font-semibold rounded-lg text-[#111418] disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
            {isEdit ? 'Enregistrer' : 'Créer'}
          </button>
        </div>
      </form>
    </div>
  );
}