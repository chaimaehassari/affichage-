import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

export default function FtpProfileModal({ profile, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: '', server_address: '', port: 21, username: '', password: '',
    security_mode: 'NONE', transfer_mode: 'BINARY', passive_mode: true, timeout: 30,
    anonymous: false, ignore_cert_errors: false,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (profile) {
      setForm({
        name: profile.name || '',
        server_address: profile.server_address || '',
        port: profile.port || 21,
        username: profile.username || '',
        password: '',
        security_mode: profile.security_mode || 'NONE',
        transfer_mode: profile.transfer_mode || 'BINARY',
        passive_mode: profile.passive_mode ?? true,
        timeout: profile.timeout || 30,
        anonymous: profile.anonymous ?? false,
        ignore_cert_errors: profile.ignore_cert_errors ?? false,
      });
    }
  }, [profile]);

  function update(field, value) {
    setForm(prev => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name || !form.server_address || (!form.anonymous && !form.username)) {
      setError('Nom, adresse et utilisateur sont requis.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = { ...form };
      if (profile && !data.password) delete data.password;
      await onSave(data);
    } catch (err) {
      setError(err.message || 'Erreur lors de la sauvegarde.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-[#111418] border border-white/10 rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm">{profile ? 'Modifier le profil FTP' : 'Nouveau profil FTP'}</h3>
          <button onClick={onCancel} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-[#a0a7b3] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto flex-1">
          <div className="grid grid-cols-2 gap-4">
            <Field label="Nom" value={form.name} onChange={v => update('name', v)} placeholder="Mon profil" />
            <Field label="Adresse serveur" value={form.server_address} onChange={v => update('server_address', v)} placeholder="192.168.1.100" />
            <Field label="Port" type="number" value={form.port} onChange={v => update('port', parseInt(v) || 21)} />
            <Field label="Utilisateur" value={form.username} onChange={v => update('username', v)} placeholder="utilisateur" disabled={form.anonymous} />
            <Field label="Mot de passe" type="password" value={form.password} onChange={v => update('password', v)} placeholder={profile ? 'Laisser vide pour conserver' : ''} disabled={form.anonymous} />
            <div>
              <label className="block text-xs text-[#a0a7b3] mb-1">Mode sécurité</label>
              <select value={form.security_mode} onChange={e => update('security_mode', e.target.value)}
                className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50">
                <option value="NONE">NONE</option>
                <option value="FTP">FTP</option>
                <option value="FTPS">FTPS</option>
                <option value="FTPES">FTPES</option>
                <option value="SFTP">SFTP</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-[#a0a7b3] mb-1">Mode transfert</label>
              <select value={form.transfer_mode} onChange={e => update('transfer_mode', e.target.value)}
                className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50">
                <option value="BINARY">BINARY</option>
                <option value="ASCII">ASCII</option>
              </select>
            </div>
            <Field label="Timeout (s)" type="number" value={form.timeout} onChange={v => update('timeout', parseInt(v) || 30)} />
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.passive_mode} onChange={e => update('passive_mode', e.target.checked)}
                  className="w-4 h-4 rounded border-white/20 bg-[#0f1217] text-[#f6c200] focus:ring-[#f6c200]/50" />
                <span className="text-sm text-white">Mode passif</span>
              </label>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.anonymous} onChange={e => update('anonymous', e.target.checked)}
                  className="w-4 h-4 rounded border-white/20 bg-[#0f1217] text-[#f6c200] focus:ring-[#f6c200]/50" />
                <span className="text-sm text-white">Connexion anonyme</span>
              </label>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.ignore_cert_errors} onChange={e => update('ignore_cert_errors', e.target.checked)}
                  className="w-4 h-4 rounded border-white/20 bg-[#0f1217] text-[#f6c200] focus:ring-[#f6c200]/50" />
                <span className="text-sm text-white">Ignorer les erreurs de certificat</span>
              </label>
            </div>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onCancel} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">Annuler</button>
            <button type="submit" disabled={loading} className="px-4 py-2 text-sm font-semibold rounded-lg disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #f6c200, #ffdb4d)' }}>
              <span className="text-[#111418]">{loading ? 'Enregistrement...' : 'Enregistrer'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, type = 'text', value, onChange, placeholder = '', disabled = false }) {
  return (
    <div>
      <label className="block text-xs text-[#a0a7b3] mb-1">{label}</label>
      <input type={type} value={value} onChange={e => onChange(type === 'number' ? e.target.value : e.target.value)} placeholder={placeholder} disabled={disabled}
        className="w-full px-3 py-2 bg-[#0f1217] border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-[#f6c200]/50 transition-colors disabled:opacity-50" />
    </div>
  );
}
