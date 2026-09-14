import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { LogOut, ArrowLeft, Save } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import NavBar from '../components/NavBar';
import { getLayout, createLayout, updateLayout } from '../services/layouts';
import { extractDetailMessage } from '../services/api';

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

const DEFAULT_ZONES = Array.from({ length: 8 }, (_, i) => ({
  zone_number: i + 1,
  position_x: 0,
  position_y: 0,
  width: 0,
  height: 0,
  is_active: false,
}));

export default function LayoutEditor() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const { logout, user } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: '',
    is_active: true,
    zones: DEFAULT_ZONES.map(z => ({ ...z })),
  });
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [notification, setNotification] = useState(null);

  const fetchLayout = useCallback(async () => {
    if (!isEdit) return;
    setLoading(true);
    const result = await getLayout(id);
    if (result.ok && result.data) {
      const layout = result.data;
      const zones = DEFAULT_ZONES.map(z => {
        const existing = layout.zones?.find(ez => ez.zone_number === z.zone_number);
        return existing ? { ...existing } : { ...z };
      });
      setForm({
        name: layout.name || '',
        is_active: layout.is_active,
        zones,
      });
    }
    setLoading(false);
  }, [id, isEdit]);

  useEffect(() => { fetchLayout(); }, [fetchLayout]);

  function showNotif(type, text) {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  }

  function handleZoneChange(index, field, value) {
    setForm(prev => {
      const zones = [...prev.zones];
      if (field === 'is_active') {
        zones[index] = { ...zones[index], is_active: value };
      } else {
        const num = parseFloat(value) || 0;
        zones[index] = { ...zones[index], [field]: Math.min(100, Math.max(0, num)) };
      }
      return { ...prev, zones };
    });
  }

  async function handleSave() {
    if (!form.name.trim()) {
      showNotif('error', 'Le nom du modèle est requis.');
      return;
    }
    const activeZones = form.zones.filter(z => z.is_active);
    if (activeZones.length === 0) {
      showNotif('error', 'Activez au moins une zone.');
      return;
    }

    setSaving(true);
    const payload = {
      name: form.name.trim(),
      is_active: form.is_active,
      zones: activeZones.map(z => ({
        zone_number: z.zone_number,
        position_x: z.position_x,
        position_y: z.position_y,
        width: z.width,
        height: z.height,
        is_active: z.is_active,
      })),
    };

    let result;
    if (isEdit) {
      result = await updateLayout(id, payload);
    } else {
      result = await createLayout(payload);
    }

    if (result.ok) {
      showNotif('success', isEdit ? 'Modèle mis à jour.' : 'Modèle créé.');
      setTimeout(() => navigate('/layouts'), 1500);
    } else {
      showNotif('error', extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.'));
    }
    setSaving(false);
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
            {user && <span className="text-[#a0a7b3] text-xs">{user.login} — {user.profile_name}</span>}
            <button onClick={async () => { await logout(); navigate('/login'); }} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-xs transition-colors">
              <LogOut className="w-3.5 h-3.5" /> Déconnexion
            </button>
          </div>
        </header>

        <NavBar />

        <main className="flex-1 px-8 py-6 overflow-auto">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/layouts')} className="flex items-center gap-1.5 text-[#a0a7b3] hover:text-white text-sm transition-colors">
                <ArrowLeft className="w-4 h-4" /> Retour
              </button>
              <h2 className="text-white text-lg font-semibold">{isEdit ? 'Modifier le modèle' : 'Nouveau modèle'}</h2>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => navigate('/layouts')} className="px-4 py-2 text-sm text-[#a0a7b3] bg-[#1a1f24] border border-white/10 rounded-lg hover:bg-[#2a2f36]">
                Annuler
              </button>
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
                <Save className="w-4 h-4 text-[#111418]" />
                <span className="text-[#111418]">{saving ? 'Enregistrement...' : (isEdit ? 'Mettre à jour' : 'Enregistrer le modèle')}</span>
              </button>
            </div>
          </div>

          {loading ? (
            <span className="text-[#a0a7b3] text-sm">Chargement du modèle...</span>
          ) : (
            <div className="space-y-6 max-w-5xl">
              {/* Name field */}
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4">
                <label className="block text-[#a0a7b3] text-xs mb-1">Nom du modèle</label>
                <input type="text" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                  placeholder="Ex : Layout Standard"
                  className="w-full bg-[#1a1f24] border border-white/10 rounded px-3 py-2 text-sm text-white focus:border-[#f6c200] focus:outline-none transition-colors" />
              </div>

              {/* Visual preview */}
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg p-4">
                <h3 className="text-[#a0a7b3] text-xs font-semibold uppercase mb-3">Aperçu visuel</h3>
                <div className="relative w-full bg-[#1a1a1a] border border-white/10 rounded overflow-hidden" style={{ aspectRatio: '16/9' }}>
                  {form.zones.map((zone, i) => {
                    if (!zone.is_active) return null;
                    const color = ZONE_COLORS[i];
                    return (
                      <div key={zone.zone_number}
                        style={{
                          position: 'absolute',
                          left: `${zone.position_x}%`,
                          top: `${zone.position_y}%`,
                          width: `${zone.width}%`,
                          height: `${zone.height}%`,
                          backgroundColor: color.bg,
                          border: `2px solid ${color.border}`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}>
                        <span className="text-white text-xs font-bold bg-black/40 px-2 py-0.5 rounded">Z-{zone.zone_number}</span>
                      </div>
                    );
                  })}
                  {form.zones.every(z => !z.is_active) && (
                    <div className="absolute inset-0 flex items-center justify-center text-[#555] text-sm">
                      Activez au moins une zone pour la prévisualisation
                    </div>
                  )}
                </div>
              </div>

              {/* Zone parameters table */}
              <div className="bg-[#111418]/80 border border-white/10 rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b border-white/10">
                  <h3 className="text-[#a0a7b3] text-xs font-semibold uppercase">Paramètres des zones</h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Zone</th>
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Aff</th>
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">X (%)</th>
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">Y (%)</th>
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">L (%)</th>
                        <th className="px-3 py-2 text-xs font-semibold text-[#a0a7b3] text-center uppercase">H (%)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {form.zones.map((zone, i) => {
                        const color = ZONE_COLORS[i];
                        return (
                          <tr key={zone.zone_number}
                            className={`border-b border-white/5 transition-colors ${zone.is_active ? 'bg-white/[0.02]' : 'opacity-40'}`}>
                            <td className="px-3 py-2 text-center">
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-white">
                                <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color.border }} />
                                Z-{zone.zone_number}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-center">
                              <input type="checkbox" checked={zone.is_active}
                                onChange={e => handleZoneChange(i, 'is_active', e.target.checked)}
                                className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200] cursor-pointer" />
                            </td>
                            {['position_x', 'position_y', 'width', 'height'].map(field => (
                              <td key={field} className="px-3 py-2 text-center">
                                <input type="number" min={0} max={100} step={0.5}
                                  value={zone[field]}
                                  onChange={e => handleZoneChange(i, field, e.target.value)}
                                  disabled={!zone.is_active}
                                  className="w-16 bg-[#1a1f24] border border-white/10 rounded px-2 py-1 text-xs text-white text-center focus:border-[#f6c200] focus:outline-none disabled:opacity-30" />
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
