import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { changePassword } from '../services/settings';
import { extractDetailMessage } from '../services/api';
import { Monitor, Lock, KeyRound, Eye, EyeOff, AlertTriangle, LogOut } from 'lucide-react';
import ThemeToggle from './ThemeToggle';

const PASSWORD_RULES = [
  'Entre 8 et 14 caractères',
  'Au moins une lettre et un chiffre',
  'Au moins un caractère spécial (!@#$%^&*...)',
  'Différent du login',
];

export default function MustChangePassword() {
  const { user, logout, refreshUser } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [show, setShow] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const canSubmit =
    currentPassword !== '' &&
    newPassword !== '' &&
    confirmPassword !== '' &&
    newPassword === confirmPassword &&
    !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const result = await changePassword(currentPassword, newPassword);
    if (result.ok) {
      await refreshUser();
      return;
    }
    setError(extractDetailMessage(result.data?.detail, 'Erreur lors du changement de mot de passe.'));
    setSubmitting(false);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute top-4 right-4 z-50 flex items-center gap-3">
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white transition-colors text-xs"
        >
          <LogOut className="w-3.5 h-3.5" /> Se déconnecter
        </button>
        <ThemeToggle />
      </div>

      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div
          className="absolute inset-0 theme-pattern"
          style={{
            backgroundImage: `
              repeating-linear-gradient(45deg, transparent 0px, transparent 40px, rgba(255,255,255,0.01) 40px, rgba(255,255,255,0.01) 41px, transparent 41px, transparent 80px),
              repeating-linear-gradient(-45deg, transparent 0px, transparent 40px, rgba(255,215,0,0.02) 40px, rgba(255,215,0,0.02) 41px, transparent 41px, transparent 80px)
            `,
          }}
        />
        <div className="absolute inset-0 opacity-80 theme-vignette" style={{ background: 'radial-gradient(ellipse at center, transparent 30%, #0b0d10 100%)' }} />
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#f6c200] to-transparent opacity-5" />
      </div>

      <div className="relative z-10 w-[440px] max-w-[95%] bg-[#111418] rounded-2xl border border-white/10 shadow-2xl p-8">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-8 h-8 bg-[#f6c200] rounded-lg flex items-center justify-center">
            <Monitor className="w-4 h-4 text-[#111418]" strokeWidth={2.5} />
          </div>
          <div className="flex items-center text-sm">
            <span className="text-white font-semibold">Gesto</span>
            <span className="text-white/40 mx-1.5">-</span>
            <span>
              <span className="text-white font-bold">Dyn</span>
              <span className="text-[#f6c200] font-bold">Display</span>
            </span>
          </div>
        </div>
        <div className="h-px bg-gradient-to-r from-transparent via-[#f6c200]/30 to-transparent mb-7" />

        <div className="text-center mb-6">
          <div className="w-11 h-11 bg-[#f6c200]/10 rounded-full flex items-center justify-center mx-auto mb-3">
            <KeyRound className="w-5 h-5 text-[#f6c200]" />
          </div>
          <h1 className="text-white text-lg font-semibold mb-1">Changement de mot de passe obligatoire</h1>
          <p className="text-[#a0a7b3] text-sm">
            Pour votre sécurité, veuillez définir un nouveau mot de passe avant de continuer.
          </p>
        </div>

        <div className="bg-[#f6c200]/10 border border-[#f6c200]/30 rounded-lg px-4 py-3 mb-5">
          <p className="flex items-start gap-2 text-xs text-[#f6c200]">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>Votre mot de passe doit respecter les règles suivantes :</span>
          </p>
          <ul className="mt-2 space-y-1">
            {PASSWORD_RULES.map((rule, i) => (
              <li key={i} className="flex items-center gap-2 text-xs text-[#a0a7b3]">
                <span className="text-[#f6c200]">•</span> {rule}
              </li>
            ))}
          </ul>
        </div>

        {error && (
          <div className="bg-red-950/40 border border-red-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300 text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3.5">
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <Lock className="w-4 h-4" />
            </div>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Mot de passe actuel"
              autoComplete="current-password"
              autoFocus
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
          </div>

          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <KeyRound className="w-4 h-4" />
            </div>
            <input
              type={show ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Nouveau mot de passe"
              autoComplete="new-password"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-10 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShow(!show)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a0a7b3] hover:text-white transition-colors"
              aria-label={show ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
            >
              {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>

          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <KeyRound className="w-4 h-4" />
            </div>
            <input
              type={show ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Confirmer le nouveau mot de passe"
              autoComplete="new-password"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
          </div>

          {newPassword !== '' && confirmPassword !== '' && newPassword !== confirmPassword && (
            <p className="text-xs text-red-400">Les mots de passe ne correspondent pas.</p>
          )}
          {newPassword !== '' && newPassword === user?.login && (
            <p className="text-xs text-red-400">Le mot de passe doit être différent du login.</p>
          )}

          <div className="flex gap-2.5 pt-1">
            <button
              type="button"
              onClick={logout}
              disabled={submitting}
              className="flex-1 bg-[#2a2f36] text-white/80 px-4 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center hover:bg-[#3a3646] transition-colors border border-white/5 disabled:opacity-50"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="flex-1 text-[#111418] px-4 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center transition-all hover:shadow-lg hover:shadow-[#f6c200]/25 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
              style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
            >
              {submitting ? 'Enregistrement...' : 'Valider'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
