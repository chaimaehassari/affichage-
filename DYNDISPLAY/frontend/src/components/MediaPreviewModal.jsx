import { useState, useEffect } from 'react';
import { X, Download, Film, Image as ImageIcon, Calendar, HardDrive, FileType, AlertCircle } from 'lucide-react';
import { getMediaById } from '../services/sites';
import apiService, { extractDetailMessage } from '../services/api';
import useSignedMediaUrl from '../hooks/useSignedMediaUrl';

function formatSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / 1048576).toFixed(1)} Mo`;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export default function MediaPreviewModal({ mediaId, onClose }) {
  const [media, setMedia] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fileMissing, setFileMissing] = useState(false);

  useEffect(() => {
    if (!mediaId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setFileMissing(false);
    getMediaById(mediaId).then((res) => {
      if (cancelled) return;
      if (res.ok && res.data) {
        setMedia(res.data);
      } else {
        setError(extractDetailMessage(res.data?.detail, 'Impossible de charger les informations du média.'));
      }
    }).catch(() => {
      if (!cancelled) setError('Erreur de connexion au serveur.');
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [mediaId]);

  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const sftpPath = media?.sftp_path || null;
  const fileUrl = useSignedMediaUrl(sftpPath);
  const isVideo = media?.media_type === 'VIDEO';
  const isImage = media?.media_type === 'IMAGE';

  function handleDownload() {
    if (!fileUrl) return;
    const a = document.createElement('a');
    a.href = fileUrl;
    a.download = media.original_filename || media.name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />

      <div
        className="relative bg-[#111418] border border-white/10 rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm truncate pr-4">
            {loading ? 'Chargement...' : media?.name || 'Aperçu du média'}
          </h3>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-[#a0a7b3] hover:text-white transition-colors shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="w-8 h-8 border-2 border-[#f6c200] border-t-transparent rounded-full animate-spin" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-64 gap-3">
              <AlertCircle className="w-12 h-12 text-red-400" />
              <p className="text-red-300 text-sm text-center">{error}</p>
            </div>
          ) : (
            <>
              <div className="bg-[#0b0d10] rounded-lg overflow-hidden flex items-center justify-center mb-5" style={{ minHeight: '200px', maxHeight: '50vh' }}>
                {fileMissing ? (
                  <div className="flex flex-col items-center gap-3 p-8">
                    <AlertCircle className="w-12 h-12 text-[#a0a7b3]" />
                    <p className="text-[#a0a7b3] text-sm">Fichier introuvable</p>
                  </div>
                ) : isImage && fileUrl ? (
                  <img
                    src={fileUrl}
                    alt={media.name}
                    className="max-w-full max-h-[50vh] object-contain"
                    onError={() => setFileMissing(true)}
                  />
                ) : isVideo && fileUrl ? (
                  <video
                    src={fileUrl}
                    controls
                    autoPlay
                    className="max-w-full max-h-[50vh]"
                    onError={() => setFileMissing(true)}
                  />
                ) : (
                  <div className="flex flex-col items-center gap-3 p-8">
                    {isVideo ? <Film className="w-16 h-16 text-purple-400/50" /> : <ImageIcon className="w-16 h-16 text-blue-400/50" />}
                    <p className="text-[#a0a7b3] text-sm">Aperçu non disponible</p>
                  </div>
                )}
              </div>

              <div className="space-y-2.5 text-sm">
                <InfoRow icon={FileType} label="Nom" value={media.original_filename || media.name} />
                <InfoRow icon={isVideo ? Film : ImageIcon} label="Type" value={media.media_type} badge={media.media_type} />
                <InfoRow icon={HardDrive} label="Taille" value={formatSize(media.file_size)} />
                <InfoRow icon={Calendar} label="Importé le" value={formatDate(media.created_at)} />
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-3 border-t border-white/10">
          {!loading && !error && fileUrl && (
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-white/10 text-[#a0a7b3] hover:text-white hover:bg-white/5 transition-colors"
            >
              <Download className="w-4 h-4" />
              Télécharger
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-[#2a2f36] text-white/80 hover:bg-[#3a3646] border border-white/5 transition-colors"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon: Icon, label, value, badge }) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="w-4 h-4 text-[#a0a7b3] shrink-0" />
      <span className="text-[#a0a7b3] w-24 shrink-0">{label}</span>
      {badge ? (
        <span className={`text-xs px-2 py-0.5 rounded border ${badge === 'IMAGE' ? 'bg-blue-500/10 border-blue-500/20 text-blue-300' : 'bg-purple-500/10 border-purple-500/20 text-purple-300'}`}>
          {value}
        </span>
      ) : (
        <span className="text-white truncate">{value}</span>
      )}
    </div>
  );
}
