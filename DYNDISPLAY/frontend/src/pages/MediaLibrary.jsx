import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Image, Film, Trash2, Upload, HardDrive, Eye, FileText } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getMedia, uploadMedia, deleteMedia } from '../services/sites';
import apiService, { extractDetailMessage } from '../services/api';
import MediaPreviewModal from '../components/MediaPreviewModal';

const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'mp4', 'avi', 'mkv', 'mov', 'webm', 'pdf'];
const MAX_SIZE = 500 * 1024 * 1024;

function formatSize(bytes) {
  if (!bytes) return '-';
  if (bytes < 1024) return bytes + ' o';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' Ko';
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' Go';
}

export default function MediaLibrary() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [allMedia, setAllMedia] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [hoveredId, setHoveredId] = useState(null);
  const [previewMediaId, setPreviewMediaId] = useState(null);

  const fetchMedia = useCallback(async () => {
    setLoading(true);
    const result = await getMedia();
    if (result.ok && result.data) {
      setAllMedia(result.data);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchMedia(); }, [fetchMedia]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  }

  function handleFileSelect(e) {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    uploadFiles(files);
    e.target.value = '';
  }

  function openPicker() {
    if (fileInputRef.current) fileInputRef.current.click();
  }

  async function uploadFiles(files) {
    for (const file of files) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        showNotif('error', `Extension non autorisée : .${ext}`);
        continue;
      }
      if (file.size > MAX_SIZE) {
        showNotif('error', `Fichier trop volumineux : ${file.name} (${formatSize(file.size)})`);
        continue;
      }

      setUploading(true);
      setUploadProgress(0);
      const result = await uploadMedia(file, (p) => setUploadProgress(p));
      setUploading(false);

      if (result.ok) {
        showNotif('success', `"${file.name}" importé avec succès.`);
      } else {
        showNotif('error', extractDetailMessage(result.data?.detail, `Erreur lors de l'import de "${file.name}".`));
      }
    }
    await fetchMedia();
  }

  async function handleDelete() {
    if (!deleteConfirm) return;
    const result = await deleteMedia(deleteConfirm);
    if (result.ok) {
      showNotif('success', 'Média supprimé.');
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de la suppression.'));
    }
    setDeleteConfirm(null);
    await fetchMedia();
  }

  const total = allMedia.length;
  const imageCount = allMedia.filter(m => m.media_type === 'IMAGE').length;
  const videoCount = allMedia.filter(m => m.media_type === 'VIDEO').length;
  const pdfCount = allMedia.filter(m => m.media_type === 'PDF').length;

  const images = allMedia.filter(m => m.media_type === 'IMAGE');
  const videos = allMedia.filter(m => m.media_type === 'VIDEO');
  const pdfs = allMedia.filter(m => m.media_type === 'PDF');

  const renderMediaCard = (m) => (
    <div key={m.media_id}
      className="group bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden hover:border-[#f6c200]/30 transition-all duration-200"
      onMouseEnter={() => setHoveredId(m.media_id)}
      onMouseLeave={() => setHoveredId(null)}>
      <div className="aspect-square bg-[#0f1217] flex items-center justify-center overflow-hidden relative">
        {m.media_type === 'IMAGE' && m.sftp_path ? (
          <img
            src={apiService.mediaUrl(m.sftp_path)}
            alt={m.name}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }}
          />
        ) : null}
        <div className={`${m.media_type === 'IMAGE' && m.sftp_path ? 'hidden' : 'flex'} flex-col items-center justify-center gap-2`}>
          {m.media_type === 'VIDEO' ? <Film className="w-10 h-10 text-[#f6c200]/50" /> :
           m.media_type === 'PDF' ? <FileText className="w-10 h-10 text-red-400/50" /> :
           <Image className="w-10 h-10 text-[#a0a7b3]/50" />}
          <span className="text-[10px] text-[#a0a7b3] uppercase font-medium">{m.file_extension}</span>
          {m.media_type === 'PDF' && m.page_count && (
            <span className="text-[10px] text-red-400/70">{m.page_count} page(s)</span>
          )}
        </div>

        {hoveredId === m.media_id && (
          <div className="absolute inset-0 bg-black/60 flex items-center justify-center gap-3 transition-opacity duration-200">
            <button onClick={() => setPreviewMediaId(m.media_id)}
              className="w-10 h-10 flex items-center justify-center bg-blue-600 hover:bg-blue-500 rounded-full transition-colors shadow-lg">
              <Eye className="w-5 h-5 text-white" />
            </button>
            <button onClick={() => setDeleteConfirm(m.media_id)}
              className="w-10 h-10 flex items-center justify-center bg-red-600 hover:bg-red-500 rounded-full transition-colors shadow-lg">
              <Trash2 className="w-5 h-5 text-white" />
            </button>
          </div>
        )}
      </div>
      <div className="p-2.5">
        <p className="text-xs text-white truncate" title={m.name}>{m.name}</p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
            m.media_type === 'IMAGE' ? 'bg-blue-500/10 border-blue-500/20 text-blue-300' :
            m.media_type === 'PDF' ? 'bg-red-500/10 border-red-500/20 text-red-300' :
            'bg-purple-500/10 border-purple-500/20 text-purple-300'
          }`}>
            {m.media_type}
          </span>
          <span className="text-[10px] text-[#a0a7b3]">{formatSize(m.file_size)}</span>
        </div>
      </div>
    </div>
  );

  const renderMediaSection = (title, icon, items, emptyText) => (
    <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
        <h3 className="flex items-center gap-2 text-white text-sm font-semibold">
          {icon}
          {title}
        </h3>
        <span className="text-xs text-[#a0a7b3]">{items.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3" style={{ maxHeight: '65vh' }}>
        {loading ? (
          <span className="text-[#a0a7b3] text-sm">Chargement...</span>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-14">
            {icon}
            <p className="text-[#a0a7b3] text-sm mt-3">{emptyText}</p>
            <button onClick={() => openPicker()} className="mt-3 text-xs text-[#f6c200] hover:underline">Importer un fichier</button>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {items.map(renderMediaCard)}
          </div>
        )}
      </div>
    </div>
  );

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
            <p className="text-[#a0a7b3] text-sm mb-6">Êtes-vous sûr de vouloir supprimer ce média ?</p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
              <button onClick={handleDelete} className="px-4 py-2 bg-red-700 text-white text-sm rounded-lg hover:bg-red-600">Supprimer</button>
            </div>
          </div>
        </div>
      )}

      {uploading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-96 shadow-2xl">
            <h3 className="text-white font-semibold text-sm mb-4">Import en cours...</h3>
            <div className="w-full bg-[#2a2f36] rounded-full h-3 overflow-hidden">
              <div className="h-full rounded-full transition-all duration-300" style={{ width: `${uploadProgress}%`, background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }} />
            </div>
            <p className="text-[#a0a7b3] text-xs mt-2 text-center">{uploadProgress}%</p>
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
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-white text-lg font-semibold">Médiathèque</h2>
            <button onClick={() => openPicker()}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
              <Upload className="w-4 h-4 text-[#111418]" /> <span className="text-[#111418]">Ajouter un média</span>
            </button>
            <input ref={fileInputRef} type="file" accept="image/*,video/*,.pdf" multiple className="hidden" onChange={handleFileSelect} />
          </div>

          <div className="flex items-center gap-4 mb-6">
            <div className="flex items-center gap-2 px-4 py-2.5 bg-[#111418]/80 border border-[#3b82f6]/20 rounded-lg">
              <HardDrive className="w-4 h-4 text-[#3b82f6]" />
              <span className="text-[#a0a7b3] text-sm">Total :</span>
              <span className="text-white font-semibold text-sm">{total}</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2.5 bg-[#111418]/80 border border-[#22c55e]/20 rounded-lg">
              <Image className="w-4 h-4 text-[#22c55e]" />
              <span className="text-[#a0a7b3] text-sm">Images :</span>
              <span className="text-white font-semibold text-sm">{imageCount}</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2.5 bg-[#111418]/80 border border-[#f97316]/20 rounded-lg">
              <Film className="w-4 h-4 text-[#f97316]" />
              <span className="text-[#a0a7b3] text-sm">Videos :</span>
              <span className="text-white font-semibold text-sm">{videoCount}</span>
            </div>
            <div className="flex items-center gap-2 px-4 py-2.5 bg-[#111418]/80 border border-[#ef4444]/20 rounded-lg">
              <FileText className="w-4 h-4 text-[#ef4444]" />
              <span className="text-[#a0a7b3] text-sm">PDF :</span>
              <span className="text-white font-semibold text-sm">{pdfCount}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {renderMediaSection('Images', <Image className="w-4 h-4 text-[#3b82f6]" />, images, 'Aucune image.')}
            {renderMediaSection('Videos', <Film className="w-4 h-4 text-[#f97316]" />, videos, 'Aucune video.')}
            {renderMediaSection('PDF', <FileText className="w-4 h-4 text-[#ef4444]" />, pdfs, 'Aucun PDF.')}
          </div>
        </main>
      </div>

      {previewMediaId && (
        <MediaPreviewModal
          mediaId={previewMediaId}
          onClose={() => setPreviewMediaId(null)}
        />
      )}
    </div>
  );
}
