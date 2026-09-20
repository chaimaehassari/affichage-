import { useState } from 'react';
import { X } from 'lucide-react';

export default function ClientLicenseModal({ client, onSave, onClose }) {
  const [sites, setSites] = useState(client?.license_sites ?? 0);
  const [posts, setPosts] = useState(client?.license_posts ?? 0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const s = parseInt(sites, 10);
    const p = parseInt(posts, 10);
    if (!Number.isInteger(s) || s < 0 || !Number.isInteger(p) || p < 0) {
      setError('Les licences doivent être des nombres positifs ou nuls.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await onSave(s, p);
    } catch (err) {
      setError(err.message || 'Erreur lors de la mise à jour.');
    } finally {
      setLoading(false);
    }
  }

  const inputClass = 'w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-[#111418] border border-white/10 rounded-xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm">Licences — {client.client_code}</h3>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-[#a0a7b3] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-[#a0a7b3] mb-1">Licences sites</label>
              <input type="number" min="0" value={sites} onChange={e => { setSites(e.target.value); setError(''); }}
                className={inputClass} />
            </div>
            <div>
              <label className="block text-xs text-[#a0a7b3] mb-1">Licences postes</label>
              <input type="number" min="0" value={posts} onChange={e => { setPosts(e.target.value); setError(''); }}
                className={inputClass} />
            </div>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onClose} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
            <button type="submit" disabled={loading} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
              <span className="text-[#111418]">{loading ? 'Mise à jour...' : 'Enregistrer'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}