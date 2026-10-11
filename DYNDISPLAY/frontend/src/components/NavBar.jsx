import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, ChevronDown, Users, MonitorPlay, Building2, LayoutGrid, Monitor, Settings, RefreshCw, Eye, HardDrive, BarChart3, Tv, Shield } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { isNavItemVisible, PLATFORM_NAV_ITEMS } from '../utils/navbarItems';

const fichiersItems = [
  { id: 'users', label: 'Liste des utilisateurs', icon: Users, permission: 'user_list' },
  { id: 'screen-groups', label: 'Groupe d\'écrans', icon: MonitorPlay, permission: 'list_sites_posts' },
  { id: 'sites', label: 'Liste des (Sites / Postes)', icon: Building2, permission: 'list_sites_posts' },
];

const displayItems = [
  { id: 'config', label: 'Configuration', icon: Monitor, route: '/display-config', permission: 'menu_config' },
  { id: 'supervision', label: 'Supervision', icon: Eye, route: '/supervision', permission: 'menu_config' },
  { id: 'diffusion-report', label: 'Rapport de diffusion', icon: Tv, route: '/diffusion-report', permission: 'menu_config' },
];

const mainItems = [
  { id: 'media', label: 'Médiathèque', icon: HardDrive, route: '/media', permission: 'menu_media' },
  { id: 'layouts', label: 'Découpage', icon: LayoutGrid, route: '/layouts', permission: 'menu_conception' },
];

export default function NavBar() {
  const navigate = useNavigate();
  const { user, hasPermission, isSuperAdmin } = useAuth();
  const [openMenu, setOpenMenu] = useState(null);
  const navRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (navRef.current && !navRef.current.contains(e.target)) {
        setOpenMenu(null);
      }
    }
    function handleKey(e) {
      if (e.key === 'Escape') setOpenMenu(null);
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKey);
    };
  }, []);

  function go(route) {
    setOpenMenu(null);
    if (route) navigate(route);
  }

  function toggle(name) {
    setOpenMenu(prev => (prev === name ? null : name));
  }

  // Le menu dépend de l'utilisateur chargé. Tant que le profil n'est pas
  // disponible, on affiche un squelette stable plutôt qu'un menu vide qui
  // « clignote » puis se remplit.
  if (!user) {
    return (
      <nav className="px-8 bg-[#111418]/40 border-b border-white/5">
        <ul className="flex items-center gap-2 py-2.5" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <li key={i} className="h-4 w-24 rounded bg-white/5 animate-pulse" />
          ))}
        </ul>
      </nav>
    );
  }

  const navCtx = { isSuperAdmin, hasPermission };
  const isItemVisible = (item) => isNavItemVisible(item, navCtx);

  const fichiersVisible = fichiersItems.filter(isItemVisible);
  const displayVisible = displayItems.filter(isItemVisible);
  const mainVisible = mainItems.filter(isItemVisible);
  const platformVisible = PLATFORM_NAV_ITEMS.filter(isItemVisible);
  const showParametrage = hasPermission('menu_config') || hasPermission('menu_sync');

  return (
    <nav ref={navRef} className="px-8 bg-[#111418]/40 border-b border-white/5">
      <ul className="flex items-center">
        {fichiersVisible.length > 0 && (
          <li className="relative">
            <button
              type="button"
              onClick={() => toggle('Fichiers')}
              className={`flex items-center gap-1 px-4 py-2.5 text-sm font-medium transition-colors ${openMenu === 'Fichiers' ? 'text-white bg-white/5' : 'text-[#a0a7b3] hover:text-white hover:bg-white/5'}`}
            >
              <FileText className="w-3.5 h-3.5" />
              Fichiers
              <ChevronDown className="w-3 h-3 opacity-50" />
            </button>
            {openMenu === 'Fichiers' && (
              <div className="absolute top-full left-0 w-64 bg-[#1a1f24] border border-white/10 shadow-xl z-50 py-1">
                {fichiersVisible.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => go(item.id === 'users' ? '/users' : item.id === 'screen-groups' ? '/batch-assign' : '/sites-posts')}
                      className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors text-[#a0a7b3] hover:text-[#f6c200] hover:bg-white/5"
                    >
                      <Icon className="w-4 h-4 shrink-0 opacity-70" />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            )}
          </li>
        )}

        {mainVisible.map((tab) => {
          const Icon = tab.icon;
          return (
            <li key={tab.id}>
              <button
                type="button"
                onClick={() => go(tab.route)}
                className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors text-[#a0a7b3] hover:text-white hover:bg-white/5"
              >
                <Icon className="w-3.5 h-3.5" />
                {tab.label}
              </button>
            </li>
          );
        })}

        {platformVisible.map((tab) => (
          <li key={tab.id}>
            <button
              type="button"
              onClick={() => go(tab.route)}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors text-[#a0a7b3] hover:text-white hover:bg-white/5"
            >
              <Shield className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          </li>
        ))}

        {displayVisible.length > 0 && (
        <li className="relative">
          <button
            type="button"
            onClick={() => toggle('Affichage')}
            className={`flex items-center gap-1 px-4 py-2.5 text-sm font-medium transition-colors ${openMenu === 'Affichage' ? 'text-white bg-white/5' : 'text-[#a0a7b3] hover:text-white hover:bg-white/5'}`}
          >
            <Monitor className="w-3.5 h-3.5" />
            Affichage
            <ChevronDown className="w-3 h-3 opacity-50" />
          </button>
          {openMenu === 'Affichage' && (
            <div className="absolute top-full left-0 w-64 bg-[#1a1f24] border border-white/10 shadow-xl z-50 py-1">
              {displayVisible.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => go(item.route)}
                    className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors text-[#a0a7b3] hover:text-[#f6c200] hover:bg-white/5"
                  >
                    <Icon className="w-4 h-4 shrink-0 opacity-70" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          )}
        </li>
        )}

        {showParametrage && (
        <li className="relative">
          <button
            type="button"
            onClick={() => toggle('Parametrage')}
            className={`flex items-center gap-1 px-4 py-2.5 text-sm font-medium transition-colors ${openMenu === 'Parametrage' ? 'text-white bg-white/5' : 'text-[#a0a7b3] hover:text-white hover:bg-white/5'}`}
          >
            <Settings className="w-3.5 h-3.5" />
            Paramétrage
            <ChevronDown className="w-3 h-3 opacity-50" />
          </button>
          {openMenu === 'Parametrage' && (
            <div className="absolute top-full left-0 w-64 bg-[#1a1f24] border border-white/10 shadow-xl z-50 py-1">
              {hasPermission('menu_config') && (
                <button
                  type="button"
                  onClick={() => go('/settings')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors text-[#a0a7b3] hover:text-[#f6c200] hover:bg-white/5"
                >
                  <Settings className="w-4 h-4 shrink-0 opacity-70" />
                  Paramètres
                </button>
              )}
              {hasPermission('menu_sync') && (
                <button
                  type="button"
                  onClick={() => go('/sync')}
                  className="w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors text-[#a0a7b3] hover:text-[#f6c200] hover:bg-white/5"
                >
                  <RefreshCw className="w-4 h-4 shrink-0 opacity-70" />
                  Synchronisation
                </button>
              )}
            </div>
          )}
        </li>
      )}
      </ul>
    </nav>
  );
}
