import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Monitor, LayoutGrid } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getPostConfig } from '../services/display';
import apiService, { extractDetailMessage } from '../services/api';

function PdfZone({ media, className, style }) {
  const pages = media?.pdf_pages || [];
  const [currentPage, setCurrentPage] = useState(0);
  const intervalRef = useRef(null);

  useEffect(() => {
    setCurrentPage(0);
    if (pages.length > 1) {
      intervalRef.current = setInterval(() => {
        setCurrentPage(prev => (prev + 1) % pages.length);
      }, 10000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [pages.length, media?.media_id]);

  if (!pages.length) {
    return (
      <div className={`${className} flex items-center justify-center bg-[#1a1f24]`} style={style}>
        <span className="text-[#a0a7b3] text-xs">PDF (Aucune page)</span>
      </div>
    );
  }

  return (
    <div className={`${className} relative`} style={style}>
      {pages.map((url, i) => (
        <img
          key={`${media.media_id}-p${i}`}
          src={apiService.withMediaToken(url)}
          alt={`${media.name} page ${i + 1}`}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${i === currentPage ? 'opacity-100' : 'opacity-0'}`}
          onError={(e) => { e.target.style.display = 'none'; }}
        />
      ))}
      {pages.length > 1 && (
        <span className="absolute bottom-1 left-1.5 px-1.5 py-0.5 bg-black/60 text-[10px] text-white/70 rounded font-mono">
          {currentPage + 1}/{pages.length}
        </span>
      )}
    </div>
  );
}

function ZoneSlideshow({ playlist, zoneNumber, zoneStyle, color }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const intervalRef = useRef(null);

  const playlistRef = useRef(playlist);
  playlistRef.current = playlist;

  useEffect(() => {
    setCurrentIndex(0);
    if (intervalRef.current) clearInterval(intervalRef.current);
    const validItems = playlistRef.current.filter(m => m && m.media_id);
    if (validItems.length > 1) {
      intervalRef.current = setInterval(() => {
        setCurrentIndex(prev => {
          const items = playlistRef.current.filter(m => m && m.media_id);
          return (prev + 1) % items.length;
        });
      }, 10000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playlist.map(m => m?.media_id).join(',')]);

  const validItems = playlist.filter(m => m && m.media_id);
  if (!validItems.length) {
    return (
      <div className="absolute border border-white/20" style={zoneStyle}>
        <div className="w-full h-full flex items-center justify-center bg-[#1a1f24]/80">
          <span className="text-[#a0a7b3] text-sm">Zone {zoneNumber}</span>
        </div>
        <span className="absolute bottom-1 right-1.5 px-1.5 py-0.5 bg-black/60 text-[10px] text-white/70 rounded font-mono">
          Z-{zoneNumber}
        </span>
      </div>
    );
  }

  const media = validItems[currentIndex % validItems.length];
  const mediaUrl = media.url ? apiService.withMediaToken(media.url) : null;

  return (
    <div className="absolute border border-white/20" style={zoneStyle}>
      {mediaUrl ? (
        media.media_type === 'VIDEO' ? (
          <video
            key={`v-${zoneNumber}-${media.media_id}`}
            src={mediaUrl}
            autoPlay
            muted
            loop
            className="w-full h-full object-cover"
          />
        ) : media.media_type === 'PDF' ? (
          <PdfZone media={media} className="w-full h-full" />
        ) : (
          <img
            key={`i-${zoneNumber}-${media.media_id}`}
            src={mediaUrl}
            alt={media.name}
            className="w-full h-full object-cover"
          />
        )
      ) : (
        <div className="w-full h-full flex items-center justify-center bg-[#1a1f24]/80">
          <span className="text-[#a0a7b3] text-sm">Zone {zoneNumber}</span>
        </div>
      )}
      {validItems.length > 1 && (
        <span className="absolute bottom-1 left-1.5 px-1.5 py-0.5 bg-black/60 text-[10px] text-white/70 rounded font-mono">
          {(currentIndex % validItems.length) + 1}/{validItems.length}
        </span>
      )}
      <span className="absolute bottom-1 right-1.5 px-1.5 py-0.5 bg-black/60 text-[10px] text-white/70 rounded font-mono">
        Z-{zoneNumber}
      </span>
    </div>
  );
}

const ZONE_COLORS = [
  { bg: 'rgba(59,130,246,0.3)', border: '#3b82f6' },
  { bg: 'rgba(16,185,129,0.3)', border: '#10b981' },
  { bg: 'rgba(245,158,11,0.3)', border: '#f59e0b' },
  { bg: 'rgba(239,68,68,0.3)', border: '#ef4444' },
  { bg: 'rgba(168,85,247,0.3)', border: '#a855f7' },
  { bg: 'rgba(20,184,166,0.3)', border: '#14b8a6' },
  { bg: 'rgba(244,114,182,0.3)', border: '#f472b6' },
  { bg: 'rgba(99,102,241,0.3)', border: '#6366f1' },
];

export default function PostPreview() {
  const { postId } = useParams();
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await getPostConfig(postId);
        if (cancelled) return;
        if (result.ok && result.data) {
          setConfig(result.data);
        } else {
          setError(extractDetailMessage(result.data?.detail, 'Impossible de charger la configuration.'));
        }
      } catch {
        if (!cancelled) setError('Erreur de connexion au serveur.');
      }
      if (!cancelled) setLoading(false);
    }
    load();
    return () => { cancelled = true; };
  }, [postId]);

  const layout = config?.layout || null;
  const layoutZones = layout?.zones || [];
  const activeZones = config?.zones || [];

  const mediaByZone = {};
  activeZones.forEach(z => { mediaByZone[z.zone_number] = z.media_playlist || (z.media ? [z.media] : []); });

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b0d10] flex items-center justify-center">
        <span className="text-[#a0a7b3] text-sm">Chargement de la prévisualisation...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#0b0d10] flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 text-sm mb-3">{error}</p>
          <button onClick={() => navigate(-1)} className="text-[#a0a7b3] hover:text-white text-sm underline">Retour</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0b0d10] relative overflow-hidden">
      <div className="absolute inset-0">
        <div className="absolute inset-0 bg-gradient-to-br from-[#0b0d10] via-[#0f1217] to-[#0b0d10]" />
        <div className="absolute inset-0 opacity-80 theme-vignette bg-[radial-gradient(ellipse_at_center,transparent_30%,#0b0d10_100%)]" />
      </div>

      <div className="relative z-10 flex flex-col min-h-screen">
        <header className="px-8 py-2 flex items-center justify-between border-b border-white/5 bg-[#111418]/60">
          <h1 onClick={() => navigate('/')} className="text-[#f6c200] text-3xl font-bold tracking-wider cursor-pointer">DynDisplay</h1>
          <div className="flex items-center gap-4">
            <ThemeToggle />
            {user && <span className="text-[#a0a7b3] text-xs">{user.login} — {user.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        <NavBar />

        <main className="flex-1 px-8 py-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/sites-posts')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                <ArrowLeft className="w-4 h-4" /> Retour
              </button>
              <div>
                <h2 className="text-white text-lg font-semibold flex items-center gap-2">
                  <Monitor className="w-5 h-5 text-[#f6c200]" />
                  Prévisualisation — {config?.code} : {config?.name}
                </h2>
                {!layout && (
                  <p className="text-[#a0a7b3] text-xs mt-0.5">Aucun layout assigné à ce poste.</p>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-center">
            <div className="w-full" style={{ maxWidth: '1200px' }}>
              {layoutZones.length > 0 ? (
                <div className="relative bg-black rounded-lg overflow-hidden shadow-2xl" style={{ aspectRatio: '16/9' }}>
                  {layoutZones.map((zone, i) => {
                    if (!zone.is_active) return null;
                    const playlist = mediaByZone[zone.zone_number] || [];
                    const color = ZONE_COLORS[i % ZONE_COLORS.length];

                    return (
                      <ZoneSlideshow
                        key={zone.zone_number}
                        playlist={playlist}
                        zoneNumber={zone.zone_number}
                        color={color}
                        zoneStyle={{
                          left: `${zone.position_x}%`,
                          top: `${zone.position_y}%`,
                          width: `${zone.width}%`,
                          height: `${zone.height}%`,
                          backgroundColor: color.bg,
                        }}
                      />
                    );
                  })}
                </div>
              ) : (
                <div className="relative bg-black rounded-lg overflow-hidden shadow-2xl flex items-center justify-center" style={{ aspectRatio: '16/9' }}>
                  <div className="text-center">
                    <LayoutGrid className="w-10 h-10 text-[#a0a7b3] mx-auto mb-3 opacity-50" />
                    <p className="text-[#a0a7b3] text-sm">Aucun layout assigné à ce poste.</p>
                    <p className="text-[#a0a7b3] text-xs mt-1">Configurez l'affichage pour définir un layout.</p>
                  </div>
                </div>
              )}

              <div className="mt-4 flex items-center justify-between text-xs text-[#a0a7b3]">
                <span>Layout : {layout ? `#${layout.layout_id}` : 'Aucun'}</span>
                <span>Zones actives : {activeZones.filter(z => (z.media_playlist || z.media)).length}/{layoutZones.filter(z => z.is_active).length}</span>
                <span>Boucle : {config?.loop_enabled ? 'Oui' : 'Non'}</span>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
