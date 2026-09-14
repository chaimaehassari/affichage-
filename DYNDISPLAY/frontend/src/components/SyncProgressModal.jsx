import { useState, useEffect, useRef } from 'react';
import { X, CheckCircle, XCircle, Loader, AlertCircle } from 'lucide-react';
import { getSyncJob } from '../services/sync';

export default function SyncProgressModal({ jobId, onClose }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;

    async function fetchJob() {
      const result = await getSyncJob(jobId);
      if (result.ok && result.data) {
        setJob(result.data);
        setLoading(false);

        if (result.data.status === 'COMPLETED' || result.data.status === 'FAILED') {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      }
    }

    fetchJob();
    intervalRef.current = setInterval(fetchJob, 2000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [jobId]);

  function getStatusColor(status) {
    switch (status) {
      case 'COMPLETED': return 'text-green-400';
      case 'FAILED': return 'text-red-400';
      case 'RUNNING': return 'text-[#f6c200]';
      default: return 'text-[#a0a7b3]';
    }
  }

  function getStatusLabel(status) {
    switch (status) {
      case 'PENDING': return 'En attente...';
      case 'RUNNING': return 'En cours...';
      case 'COMPLETED': return 'Synchronisation terminée';
      case 'FAILED': return 'Échoué';
      default: return status;
    }
  }

  function getItemIcon(status) {
    switch (status) {
      case 'COMPLETED': return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'FAILED': return <XCircle className="w-4 h-4 text-red-400" />;
      case 'UPLOADING': return <Loader className="w-4 h-4 text-[#f6c200] animate-spin" />;
      default: return <div className="w-4 h-4 rounded-full border border-[#a0a7b3]" />;
    }
  }

  function getItemLabel(item) {
    if (item.item_type === 'CONFIG') return 'config.json';
    const parts = (item.item_path || '').split('/');
    return parts[parts.length - 1] || item.item_path;
  }

  const isDone = job && (job.status === 'COMPLETED' || job.status === 'FAILED');
  const canClose = isDone;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="bg-[#111418] border border-white/10 rounded-xl w-full max-w-lg mx-4 overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <div>
            <h3 className="text-white font-semibold text-sm">Synchronisation</h3>
            {job && (
              <p className={`text-xs mt-0.5 ${getStatusColor(job.status)}`}>
                {getStatusLabel(job.status)}
              </p>
            )}
          </div>
          {canClose && (
            <button onClick={onClose} className="text-[#a0a7b3] hover:text-white transition-colors">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        <div className="px-5 py-5">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader className="w-6 h-6 text-[#f6c200] animate-spin" />
              <span className="text-[#a0a7b3] text-sm ml-3">Chargement...</span>
            </div>
          ) : job ? (
            <>
              <div className="mb-5">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[#a0a7b3] text-xs">Progression</span>
                  <span className="text-white text-xs font-semibold">{job.progress_percent}%</span>
                </div>
                <div className="w-full h-3 bg-[#1a1f24] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${job.progress_percent}%`,
                      background: job.status === 'FAILED'
                        ? 'linear-gradient(90deg, #ef4444, #dc2626)'
                        : job.status === 'COMPLETED'
                          ? 'linear-gradient(90deg, #22c55e, #16a34a)'
                          : 'linear-gradient(90deg, #f6c200, #ffdb4d)',
                    }}
                  />
                </div>
              </div>

              {(job.status === 'RUNNING' || job.status === 'PENDING') && job.transfer_speed > 0 && (
                <div className="flex items-center gap-6 mb-5">
                  <div>
                    <span className="text-[#a0a7b3] text-[10px] uppercase">Vitesse</span>
                    <p className="text-white text-sm font-medium">{job.transfer_speed} Ko/s</p>
                  </div>
                  {job.estimated_remaining_seconds != null && job.estimated_remaining_seconds > 0 && (
                    <div>
                      <span className="text-[#a0a7b3] text-[10px] uppercase">Temps restant</span>
                      <p className="text-white text-sm font-medium">
                        {job.estimated_remaining_seconds < 60
                          ? `${job.estimated_remaining_seconds}s`
                          : `${Math.floor(job.estimated_remaining_seconds / 60)}m ${job.estimated_remaining_seconds % 60}s`
                        }
                      </p>
                    </div>
                  )}
                </div>
              )}

              {job.error_message && (
                <div className="flex items-start gap-2 mb-5 p-3 bg-red-950/50 border border-red-500/20 rounded-lg">
                  <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                  <p className="text-red-300 text-xs">{job.error_message}</p>
                </div>
              )}

              {job.items && job.items.length > 0 && (
                <div>
                  <span className="text-[#a0a7b3] text-[10px] uppercase mb-2 block">Fichiers</span>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    {job.items.map(item => (
                      <div key={item.sync_item_id}
                        className="flex items-center gap-2.5 px-3 py-2 bg-[#1a1f24] border border-white/5 rounded-lg">
                        {getItemIcon(item.status)}
                        <span className="text-white text-xs truncate flex-1">{getItemLabel(item)}</span>
                        <span className={`text-[10px] font-medium ${item.status === 'COMPLETED' ? 'text-green-400' : item.status === 'FAILED' ? 'text-red-400' : item.status === 'UPLOADING' ? 'text-[#f6c200]' : 'text-[#a0a7b3]'}`}>
                          {item.status === 'COMPLETED' ? 'OK' : item.status === 'FAILED' ? 'Erreur' : item.status === 'UPLOADING' ? `${item.progress_percent}%` : '...'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {isDone && (
                <button onClick={onClose}
                  className="w-full mt-5 py-2.5 text-sm font-semibold rounded-lg transition-colors"
                  style={{
                    background: job.status === 'COMPLETED'
                      ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                      : 'linear-gradient(135deg, #ef4444, #dc2626)',
                    color: 'white',
                  }}>
                  {job.status === 'COMPLETED' ? 'Synchronisation terminée' : 'Fermer'}
                </button>
              )}
            </>
          ) : (
            <p className="text-[#a0a7b3] text-sm text-center py-4">Aucune donnée.</p>
          )}
        </div>
      </div>
    </div>
  );
}
