import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, Key, ShieldCheck, Building2 } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { changePassword } from '../services/settings';
import { extractDetailMessage } from '../services/api';

export default function ClientSettings() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [notification, setNotification] = useState(null);

  function notify(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 3500);
  }

  const pwOk = (v) => v && v.length >= 8 && v.length <= 14 && /[A-Za-z]/.test(v) && /\d/.test(v) && /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~]/.test(v);

  async function handleChangePassword() {
    if (!currentPassword || !newPassword) {
      notify('error', 'Veuillez remplir tous les champs.');
      return;
    }
    if (newPassword !== confirmPassword) {
      notify('error', 'Les mots de passe ne correspondent pas.');
      return;
    }
    if (!pwOk(newPassword)) {
      notify('error', 'Le mot de passe doit comporter 8 à 14 caractères, au moins une lettre, un chiffre et un caractère spécial.');
      return;
    }
    setChangingPassword(true);
    try {
      const result = await changePassword(currentPassword, newPassword);
      if (result.ok) {
        notify('success', 'Mot de passe modifié avec succès.');
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        notify('error', extractDetailMessage(result.data?.detail, 'Erreur lors du changement de mot de passe.'));
      }
    } catch {
      notify('error', 'Erreur de connexion.');
    }
    setChangingPassword(false);
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 opacity-80 bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded text-sm border ${notification.type === 'success' ? 'bg-green-950/80 border-green-700/50 text-green-300' : 'bg-red-950/80 border-red-700/50 text-red-300'}`}>
          {notification.text}
        </div>
      )}

      <div className="relative z-10 flex flex-col min-h-screen">
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">DynDisplay</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <span className="text-[#a0a7b3] text-xs">{user.login} — {user.profile_name}</span>
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        <NavBar />

        <main className="flex-1 px-8 py-6 overflow-y-auto">
          <div className="max-w-2xl mx-auto">
            <div className="flex items-center gap-3 mb-6">
              <ShieldCheck className="w-5 h-5 text-[#f6c200]" />
              <h2 className="text-white text-lg font-semibold">Mes paramètres</h2>
            </div>

            <div className="space-y-6">
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-5">
                <h3 className="text-[#f6c200] text-sm font-semibold uppercase tracking-wider mb-4 pb-2 border-b border-white/5">
                  Informations de ma licence
                </h3>
                <div className="grid grid-cols-1 gap-4">
                  <div className="flex items-center justify-between p-3 bg-[#0f1217] border border-white/5 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Building2 className="w-4 h-4 text-[#f6c200]" />
                      <span className="text-[#a0a7b3] text-sm">Numéro client</span>
                    </div>
                    <span className="text-white font-mono">{user.user_code}</span>
                  </div>
                </div>
                <p className="text-[#a0a7b3] text-xs mt-4">
                  Le numéro client ne peut pas être modifié.
                </p>
              </div>

              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-5">
                <h3 className="text-[#f6c200] text-sm font-semibold uppercase tracking-wider mb-4 pb-2 border-b border-white/5">
                  Mot de passe
                </h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1">Mot de passe actuel</label>
                    <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)}
                      className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1">Nouveau mot de passe</label>
                    <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                      className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                  <div>
                    <label className="block text-xs text-[#a0a7b3] mb-1">Confirmer le mot de passe</label>
                    <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                      className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50" />
                  </div>
                  <button onClick={handleChangePassword} disabled={changingPassword}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-[#f6c200] border border-[#f6c200]/30 rounded-lg hover:bg-[#f6c200]/10 transition-colors disabled:opacity-50">
                    <Key className="w-4 h-4" />
                    {changingPassword ? 'Modification...' : 'Changer le mot de passe'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}