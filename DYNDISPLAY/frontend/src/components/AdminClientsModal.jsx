import { useState, useEffect } from 'react';
import apiService, { extractDetailMessage } from '../services/api';

export default function AdminClientsModal({ adminId, adminLabel, onClose, onSaved }) {
  const [clients, setClients] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      const [clientsRes, adminRes] = await Promise.all([
        apiService.get('/api/v1/clients'),
        apiService.get(`/api/v1/admins/${adminId}`),
      ]);
      if (clientsRes.ok) setClients(clientsRes.data?.clients || []);
      if (adminRes.ok && adminRes.data) setSelected(adminRes.data.client_codes || []);
      setLoading(false);
    }
    load();
  }, [adminId]);

  function toggle(code) {
    setSelected(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);
  }

  function toggleAll(select) {
    setSelected(select ? clients.map(c => c.client_code) : []);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    const adminRes = await apiService.get(`/api/v1/admins/${adminId}`);
    if (!adminRes.ok || !adminRes.data) {
      setError('Impossible de recharger cet admin.');
      setSaving(false);
      return;
    }
    const a = adminRes.data;
    const result = await apiService.put(`/api/v1/admins/${adminId}`, {
      user_code: a.user_code || null,
      login: a.login,
      email: a.email || null,
      is_active: a.is_active,
      client_codes: selected,
    });
    setSaving(false);
    if (result.ok) {
      onSaved?.();
      onClose();
    } else {
      setError(extractDetailMessage(result.data?.detail, 'Erreur lors de l\'enregistrement.'));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-[560px] shadow-2xl max-h-[80vh] flex flex-col">
        <h3 className="text-white font-semibold text-sm mb-1">Clients affectés — {adminLabel}</h3>
        <p className="text-[11px] text-[#a0a7b3] mb-4">
          Cet admin n'aura accès qu'aux clients sélectionnés (leurs sites, postes, médias et utilisateurs).
        </p>

        {error && (
          <div className="mb-4 px-3 py-2 rounded text-sm border bg-red-950/80 border-red-700/50 text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <p className="text-sm text-[#a0a7b3] py-6 text-center">Chargement...</p>
        ) : clients.length === 0 ? (
          <p className="text-sm text-[#a0a7b3] py-6 text-center">Aucun client disponible. Créez d'abord des utilisateurs avec un code client.</p>
        ) : (
          <>
            <div className="flex gap-3 mb-3">
              <button type="button" onClick={() => toggleAll(true)} className="text-xs text-[#f6c200] hover:underline">Tout sélectionner</button>
              <span className="text-[#a0a7b3] text-xs">|</span>
              <button type="button" onClick={() => toggleAll(false)} className="text-xs text-[#a0a7b3] hover:text-white hover:underline">Tout désélectionner</button>
            </div>
            <div className="grid grid-cols-2 gap-3 overflow-y-auto pr-1">
              {clients.map(c => (
                <label key={c.client_code} className="flex items-center gap-2 cursor-pointer group">
                  <input type="checkbox" checked={selected.includes(c.client_code)} onChange={() => toggle(c.client_code)}
                    className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
                  <span className="text-sm text-[#a0a7b3] group-hover:text-white transition-colors">
                    {c.client_code}{c.client_name ? ` — ${c.client_name}` : ''}
                  </span>
                </label>
              ))}
            </div>
          </>
        )}

        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onClose} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
            Annuler
          </button>
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
            <span className="text-[#111418]">{saving ? 'Enregistrement...' : 'Enregistrer'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}