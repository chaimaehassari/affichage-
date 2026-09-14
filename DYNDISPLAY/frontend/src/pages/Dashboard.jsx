import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';

export default function Dashboard() {
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div
          className="absolute inset-0 theme-pattern"
          style={{
            backgroundImage: `
              repeating-linear-gradient(45deg, transparent 0px, transparent 60px, rgba(255,255,255,0.01) 60px, rgba(255,255,255,0.01) 61px, transparent 61px, transparent 120px),
              repeating-linear-gradient(-45deg, transparent 0px, transparent 60px, rgba(246,194,0,0.02) 60px, rgba(246,194,0,0.02) 61px, transparent 61px, transparent 120px)
            `,
          }}
        />
        <div
          className="absolute inset-0 theme-pattern"
          style={{
            backgroundImage: `repeating-linear-gradient(45deg, transparent 0px, transparent 200px, rgba(246,194,0,0.04) 200px, rgba(246,194,0,0.04) 201px, transparent 201px, transparent 400px)`,
          }}
        />
        <div className="absolute inset-0 opacity-80 theme-vignette bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#f6c200] rounded-full blur-[150px] opacity-5" />
      </div>

      {/* Content */}
      <div className="relative z-10 flex flex-col min-h-screen">
        {/* Header bar */}
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 className="text-[#f6c200] text-3xl font-bold tracking-wider">
            DynDisplay
          </h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {user && (
              <span className="text-[#a0a7b3] text-xs">
                {user.login} — {user.profile_name}
              </span>
            )}
            <button
              onClick={async () => { await logout(); navigate('/login'); }}
              className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors"
            >
              <LogOut className="w-3.5 h-3.5" />
              Déconnexion
            </button>
          </div>
        </header>

        {/* Menu bar */}
        <NavBar />

        {/* Center content */}
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="flex items-center justify-center gap-4 mb-6">
              <div className="w-16 h-0.5 bg-gradient-to-r from-transparent to-[#f6c200]" />
              <div className="w-3 h-3 bg-[#f6c200] rounded-full shadow-lg shadow-[#f6c200]/30" />
              <div className="w-16 h-0.5 bg-gradient-to-l from-transparent to-[#f6c200]" />
            </div>
            <h2 className="text-7xl md:text-8xl font-bold text-white tracking-wider mb-2">
              GESTO
            </h2>
            <div className="relative inline-block">
              <h3 className="text-5xl md:text-6xl font-bold text-[#f6c200] tracking-widest relative z-10">
                DynDisplay
              </h3>
              <div className="absolute inset-0 blur-2xl bg-[#f6c200]/20 -z-10 scale-110" />
            </div>
            <p className="text-[#a0a7b3] text-sm mt-6 tracking-wider">
              Gestion centralisée d'affichage dynamique
            </p>
          </div>
        </main>

        {/* Footer */}
        <footer className="py-4 text-center">
          <p className="text-[#a0a7b3] text-xs opacity-50">
            &copy; 2025 Gesto - DynDisplay
          </p>
        </footer>
      </div>
    </div>
  );
}
