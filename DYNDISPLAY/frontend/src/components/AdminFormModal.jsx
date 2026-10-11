import { useState } from 'react';

const pwOk = (v) => v && v.length >= 8 && v.length <= 14 && /[A-Za-z]/.test(v) && /\d/.test(v) && /[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~]/.test(v);

export default function AdminFormModal({ admin, clients, onSave, onCancel }) {
  const [login, setLogin] = useState(admin?.login || '');
  const [userCode, setUserCode] = useState(admin?.user_code || '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isActive, setIsActive] = useState(admin ? admin.is_active : true);
  const [selected, setSelected] = useState(admin?.client_codes || []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const editing = !!admin;

  function toggle(code) {
    setSelected(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);
  }

  function toggleAll(select) {
    setSelected(select ? clients.map(c => c.client_code) : []);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    if (!login.trim()) {
      setError('Le login est obligatoire.');
      setSaving(false);
      return;
    }
    if (!editing) {
      if (password !== confirmPassword) {
        setError('Les mots de passe ne correspondent pas.');
        setSaving(false);
        return;
      }
      if (!pwOk(password)) {
        setError('Le mot de passe doit comporter 8 à 14 caractères, au moins une lettre, un chiffre et un caractère spécial.');
        setSaving(false);
        return;
      }
    }
    const payload = {
      user_code: userCode.trim() || null,
      login: login.trim(),
      is_active: isActive,
      client_codes: selected,
    };
    if (!editing) {
      payload.password = password;
      payload.password_confirm = confirmPassword;
    }
    const res = await onSave(payload, admin?.user_id || null);
    setSaving(false);
    if (res.ok) {
      onCancel();
    } else {
      setError(res.error || 'Erreur lors de l\'enregistrement.');
    }
  }

  const inputClass = 'w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-[#1a1f24] border border-white/10 rounded-lg p-6 w-[560px] shadow-2xl max-h-[85vh] flex flex-col overflow-y-auto">
        <h3 className="text-white font-semibold text-sm mb-4">
          {editing ? `Modifier l'admin — ${admin.login}` : 'Nouvel admin'}
        </h3>

        {error && (
          <div className="mb-4 px-3 py-2 rounded text-sm border bg-red-950/80 border-red-700/50 text-red-300">
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-[#a0a7b3] mb-1">Login</label>
            <input type="text" value={login} onChange={e => setLogin(e.target.value)}
              className={inputClass} />
          </div>
          <div>
            <label className="block text-xs text-[#a0a7b3] mb-1">Code admin</label>
            <input type="text" value={userCode} onChange={e => setUserCode(e.target.value)}
              className={inputClass} />
          </div>
          {!editing && (
            <>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Mot de passe</label>
                <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                  className={inputClass} />
              </div>
              <div>
                <label className="block text-xs text-[#a0a7b3] mb-1">Confirmer le mot de passe</label>
                <input type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                  className={inputClass} />
              </div>
            </>
          )}
          <label className="col-span-2 flex items-center gap-2 cursor-pointer mt-1">
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)}
              className="w-4 h-4 rounded border-white/20 bg-[#1a1f24] text-[#f6c200] focus:ring-[#f6c200]/50" />
            <span className="text-sm text-[#a0a7b3]">Admin actif</span>
          </label>
        </div>

        <div className="mt-4 border-t border-white/5 pt-4">
          <h4 className="text-white font-semibold text-sm mb-1">Clients affectés</h4>
          <p className="text-[11px] text-[#a0a7b3] mb-3">
            Cet admin n'aura accès qu'aux clients sélectionnés (leurs sites, postes, médias et utilisateurs).
            Sans sélection, il sera rattaché à son propre code client.
          </p>
          {clients.length === 0 ? (
            <p className="text-sm text-[#a0a7b3] py-4 text-center">Aucun client disponible. Créez d'abord des utilisateurs avec un code client.</p>
          ) : (
            <>
              {selected.length === 0 && (
                <p className="mb-3 px-3 py-2 rounded text-xs border bg-amber-950/60 border-amber-700/40 text-amber-300">
                  Aucun client sélectionné : l'admin sera rattaché automatiquement au client
                  {userCode.trim() ? ` « ${userCode.trim().toUpperCase()} »` : ' par défaut'}.
                  Sans client, il ne pourra créer ni voir aucun utilisateur.
                </p>
              )}
              <div className="flex gap-3 mb-3">
                <button type="button" onClick={() => toggleAll(true)} className="text-xs text-[#f6c200] hover:underline">Tout sélectionner</button>
                <span className="text-[#a0a7b3] text-xs">|</span>
                <button type="button" onClick={() => toggleAll(false)} className="text-xs text-[#a0a7b3] hover:text-white hover:underline">Tout désélectionner</button>
              </div>
              <div className="grid grid-cols-2 gap-3 max-h-[24vh] overflow-y-auto pr-1">
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
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button onClick={onCancel} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
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