import { useState } from 'react';
import { X, Shield, Key } from 'lucide-react';
import { verifyAccessPassword } from '../services/settings';

export default function SettingsAccessModal({ onSuccess, onCancel, expired }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await verifyAccessPassword(password);
      if (result.ok && result.data?.valid) {
        onSuccess();
      } else {
        setError('Mot de passe incorrect.');
      }
    } catch {
      setError('Erreur de connexion.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-[#111418] border border-white/10 rounded-xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
            <h3 className="text-white font-semibold text-sm flex items-center gap-2">
            <Shield className="w-4 h-4 text-[#f6c200]" /> Authentification requise
          </h3>
          <button onClick={onCancel} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-[#a0a7b3] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <p className="text-xs text-[#a0a7b3]">
            Saisissez votre mot de passe de connexion pour ouvrir les paramètres.
          </p>
          <div className="relative">
            <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#a0a7b3]" />
            <input
              type="password"
              value={password}
              onChange={e => { setPassword(e.target.value); setError(''); }}
              autoFocus
              maxLength={64}
              autoComplete="current-password"
              placeholder="Mot de passe"
              className="w-full pl-10 pr-4 py-2.5 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm tracking-[0.3em] text-center font-mono focus:outline-none focus:border-[#f6c200]/50 transition-colors"
            />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onCancel} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
            <button type="submit" disabled={password.trim().length === 0 || loading} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
              <span className="text-[#111418]">{loading ? 'Vérification...' : 'Valider'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
