import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { resetPassword } from '../services/auth';
import { extractDetailMessage } from '../services/api';
import { Monitor, Lock, KeyRound, Eye, EyeOff } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';

export default function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const { applySession } = useAuth();

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!token) {
      setError('Lien de réinitialisation invalide (jeton manquant).');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas.');
      return;
    }
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const result = await resetPassword(token, newPassword, confirmPassword);
      if (result.ok && result.data) {
        if (result.data.access_token && result.data.user) {
          applySession(result.data.access_token, result.data.user);
          navigate('/', { replace: true });
          return;
        }
        setMessage(result.data.message || 'Mot de passe réinitialisé.');
      } else {
        setError(extractDetailMessage(result.data?.detail, 'Réinitialisation impossible.'));
      }
    } catch {
      setError('Erreur de connexion au serveur.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute top-4 right-4 z-50">
        <ThemeToggle />
      </div>
      <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />

      <div className="relative z-10 w-[420px] max-w-[95%] bg-[#111418] rounded-2xl border border-white/10 shadow-2xl p-8">
        <div className="text-center mb-7">
          <div className="w-11 h-11 bg-[#f6c200]/10 rounded-full flex items-center justify-center mx-auto mb-3">
            <KeyRound className="w-5 h-5 text-[#f6c200]" />
          </div>
          <h1 className="text-white text-lg font-semibold mb-1">Réinitialiser le mot de passe</h1>
          <p className="text-[#a0a7b3] text-sm">Choisissez un nouveau mot de passe</p>
        </div>

        <div className="h-px bg-gradient-to-r from-transparent via-[#f6c200]/30 to-transparent mb-6" />

        {error && (
          <div className="bg-red-950/40 border border-red-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300 text-center">
            {error}
          </div>
        )}
        {message && (
          <div className="bg-green-950/40 border border-green-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-green-300 text-center">
            {message}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <Lock className="w-4 h-4" />
            </div>
            <input
              type={show ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Nouveau mot de passe (8-14 car.)"
              autoComplete="new-password"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
          </div>
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <Lock className="w-4 h-4" />
            </div>
            <input
              type={show ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirmer le mot de passe"
              autoComplete="new-password"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-11 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShow(!show)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a0a7b3] hover:text-white transition-colors"
              aria-label="Afficher/Masquer le mot de passe"
            >
              {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full text-[#111418] px-4 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center transition-all hover:shadow-lg hover:shadow-[#f6c200]/25 disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
          >
            {submitting ? 'Réinitialisation...' : 'Réinitialiser le mot de passe'}
          </button>
        </form>

        <div className="text-center mt-5">
          <button
            onClick={() => navigate('/login')}
            className="text-xs text-[#a0a7b3] hover:text-[#f6c200] transition-colors"
          >
            Retour à la connexion
          </button>
        </div>
      </div>
    </div>
  );
}
