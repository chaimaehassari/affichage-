import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Monitor, Lock, User, KeySquare, Eye, EyeOff } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import AccountActivation from '../components/AccountActivation';

export default function Login() {
  const { login, isAuthenticated, error } = useAuth();
  const [username, setUsername] = useState('');
  const [clientCode, setClientCode] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [pendingActivation, setPendingActivation] = useState(null);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (pendingActivation) {
    return (
      <AccountActivation
        login={pendingActivation.username}
        password={pendingActivation.password}
        clientCode={pendingActivation.clientCode}
        accountCode={pendingActivation.accountCode}
        onCancel={() => setPendingActivation(null)}
      />
    );
  }

  const canSubmit = username.trim() !== '' && password !== '' && !submitting;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    const result = await login(username.trim(), password, clientCode.trim());
    setSubmitting(false);
    if (result && result.needsActivation) {
      setPendingActivation({
        username: username.trim(),
        password,
        clientCode: clientCode.trim(),
        accountCode: result.accountCode,
      });
    }
  }

  function handleCancel() {
    setUsername('');
    setClientCode('');
    setPassword('');
    setShowPassword(false);
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute top-4 right-4 z-50">
        <ThemeToggle />
      </div>
      {/* Background layers */}
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
        <div
          className="absolute inset-0 theme-pattern"
          style={{
            backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 150px, rgba(246,194,0,0.05) 150px, rgba(246,194,0,0.05) 151px, transparent 151px, transparent 300px)`,
          }}
        />
        <div
          className="absolute inset-0 theme-pattern"
          style={{
            backgroundImage: `repeating-linear-gradient(-45deg, transparent 0px, transparent 200px, rgba(246,194,0,0.03) 200px, rgba(246,194,0,0.03) 201px, transparent 201px, transparent 400px)`,
          }}
        />
        <div
          className="absolute inset-0 opacity-80 theme-vignette"
          style={{ background: 'radial-gradient(ellipse at center, transparent 30%, #0b0d10 100%)' }}
        />
        <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#f6c200] to-transparent opacity-5" />
      </div>

      {/* Login Card */}
      <div className="relative z-10 w-[420px] max-w-[95%] bg-[#111418] rounded-2xl border border-white/10 shadow-2xl p-8">
        {/* Card Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2">
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
          <p className="text-[#a0a7b3] text-xs mt-2 ml-[42px]">
            Gestion centralisée d'affichage dynamique
          </p>
        </div>

        {/* Gold separator */}
        <div className="h-px bg-gradient-to-r from-transparent via-[#f6c200]/30 to-transparent mb-7" />

        {/* Title Area */}
        <div className="text-center mb-7">
          <div className="w-11 h-11 bg-[#f6c200]/10 rounded-full flex items-center justify-center mx-auto mb-3">
            <Lock className="w-5 h-5 text-[#f6c200]" />
          </div>
          <h1 className="text-white text-lg font-semibold mb-1">Authentification</h1>
          <p className="text-[#a0a7b3] text-sm">Veuillez vous connecter à votre compte</p>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-950/40 border border-red-800/50 rounded-lg px-4 py-2.5 mb-4 text-sm text-red-300 text-center">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-3.5">
          {/* Username Field */}
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <User className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Nom d'utilisateur"
              autoComplete="username"
              autoFocus
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
          </div>

          {/* Client Code Field */}
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <KeySquare className="w-4 h-4" />
            </div>
            <input
              type="text"
              value={clientCode}
              onChange={(e) => setClientCode(e.target.value)}
              placeholder="Code client"
              autoComplete="off"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-4 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
            />
          </div>

          {/* Password Field */}
          <div className="relative">
            <div className="absolute left-0 top-0 bottom-0 w-1 bg-[#f6c200] rounded-l-lg" />
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[#a0a7b3]">
              <Lock className="w-4 h-4" />
            </div>
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mot de passe"
              autoComplete="current-password"
              disabled={submitting}
              className="w-full bg-[#1a1f24] text-white placeholder-[#a0a7b3] pl-10 pr-10 py-3 rounded-lg border border-white/6 focus:border-[#f6c200] focus:outline-none focus:ring-1 focus:ring-[#f6c200]/50 transition-all text-sm disabled:opacity-50"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && canSubmit) handleSubmit(e);
              }}
            />
            <button
              type="button"
              tabIndex={-1}
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[#a0a7b3] hover:text-white transition-colors"
              aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>

          {/* Buttons */}
          <div className="flex gap-2.5 pt-1">
            <button
              type="button"
              onClick={handleCancel}
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
              {submitting ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Connexion...
                </span>
              ) : (
                'Valider'
              )}
            </button>
          </div>
        </form>

        {/* Footer */}
        <div className="text-center mt-7 pt-5 border-t border-white/5">
          <p className="text-[#a0a7b3] text-[11px]">
            &copy; 2025 Gesto - DynDisplay. Tous droits réservés.
          </p>
        </div>
      </div>
    </div>
  );
}
