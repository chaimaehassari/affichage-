import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Monitor, Lock, KeySquare, LogOut, ShieldCheck, CheckCircle2 } from 'lucide-react';
import ThemeToggle from './ThemeToggle';

function formatCode(value) {
  const cleaned = value.toUpperCase().replace(/[^A-Z0-9]/g, '');
  return cleaned.replace(/(.{5})/g, '$1-').replace(/-$/, '');
}

export default function ActivationScreen() {
  const { user, error, activate, logout } = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const canSubmit = code.replace(/[^A-Z0-9]/g, '').length >= 8 && !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    const result = await activate(code.replace(/[^A-Z0-9]/g, ''));
    setSubmitting(false);
    if (result.success) {
      setSuccess(true);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute top-4 right-4 z-50">
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
      </div>

      <div className="relative z-10 w-[440px] max-w-[95%] bg-[#111418] rounded-2xl border border-white/10 shadow-2xl p-8">
        <div className="flex items-center gap-2 mb-6">
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

        {success ? (
          <div className="text-center py-8">
            <CheckCircle2 className="w-14 h-14 text-green-400 mx-auto mb-4" />
            <h1 className="text-white text-lg font-semibold mb-2">Compte activé</h1>
            <p className="text-[#a0a7b3] text-sm mb-6">
              Votre espace est maintenant accessible.
            </p>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="w-full flex items-center justify-center gap-2 text-[#111418] px-4 py-2.5 rounded-lg font-semibold text-sm transition-all hover:shadow-lg hover:shadow-[#f6c200]/25"
              style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
            >
              Accéder à mon espace
            </button>
          </div>
        ) : (
          <div className="text-center mb-6">
            <div className="w-12 h-12 bg-[#f6c200]/10 rounded-full flex items-center justify-center mx-auto mb-3">
              <ShieldCheck className="w-5 h-5 text-[#f6c200]" />
            </div>
            <h1 className="text-white text-lg font-semibold mb-1">Activation du compte</h1>
            <p className="text-[#a0a7b3] text-sm">
              Saisissez le code de sérialisation fourni avec votre installation.
            </p>
            <p className="text-[#a0a7b3] text-xs mt-2">
              Compte client : <span className="text-[#f6c200] font-mono">{user?.user_code || user?.login}</span>
            </p>
          </div>
        )}

        {!success && (
          <>
            {error && (
              <div className="bg-red-950/40 border border-red-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300 text-center">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="relative">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
                  <KeySquare className="w-4 h-4" />
                </div>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(formatCode(e.target.value))}
                  placeholder="XXXXX-XXXXX-XXXXX-XXXXX"
                  autoComplete="off"
                  autoFocus
                  disabled={submitting}
                  className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm font-mono tracking-wide disabled:opacity-50"
                />
              </div>

              <div className="flex gap-2.5 pt-1">
                <button
                  type="button"
                  onClick={async () => { await logout(); navigate('/login'); }}
                  disabled={submitting}
                  className="flex-1 bg-[#2a2f36] text-white/80 px-4 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 hover:bg-[#3a3646] transition-colors border border-white/5 disabled:opacity-50"
                >
                  <LogOut className="w-4 h-4" />
                  Deconnexion
                </button>
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className="flex-1 text-[#111418] px-4 py-2.5 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 transition-all hover:shadow-lg hover:shadow-[#f6c200]/25 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none"
                  style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}
                >
                  {submitting ? (
                    <svg className="animate-spin w-4 h-4 text-[#111418]" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  ) : (
                    <>
                      <ShieldCheck className="w-4 h-4 text-[#111418]" />
                      Activer
                    </>
                  )}
                </button>
              </div>
            </form>
          </>
        )}

        <div className="text-center mt-7 pt-5 border-t border-white/5">
          <p className="text-[#a0a7b3] text-[11px]">
            Le code de sérialisation est généré par l'application mobile au moment de l'installation.
          </p>
          <div className="flex justify-center mt-3">
            <Lock className="w-3.5 h-3.5 text-[#a0a7b3]" />
          </div>
        </div>
      </div>
    </div>
  );
}