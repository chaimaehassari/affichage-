import { useState, useEffect } from 'react';
import { X, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { testFtpConnection } from '../services/settings';

export default function TestFtpModal({ profileId, profileName, onClose }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    testFtpConnection(profileId).then(res => {
      if (res.ok) {
        setResult(res.data);
      } else {
        setResult({ success: false, message: 'Erreur lors du test de connexion.' });
      }
    }).catch(() => {
      setResult({ success: false, message: 'Erreur de connexion au serveur.' });
    }).finally(() => setLoading(false));
  }, [profileId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative bg-[#111418] border border-white/10 rounded-xl shadow-2xl w-full max-w-sm" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
          <h3 className="text-white font-semibold text-sm">Test FTP — {profileName}</h3>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/10 text-[#a0a7b3] hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 flex flex-col items-center gap-4">
          {loading ? (
            <>
              <Loader className="w-10 h-10 text-[#f6c200] animate-spin" />
              <p className="text-[#a0a7b3] text-sm">Test en cours...</p>
            </>
          ) : result ? (
            <>
              {result.success ? (
                <CheckCircle className="w-12 h-12 text-green-400" />
              ) : (
                <AlertCircle className="w-12 h-12 text-red-400" />
              )}
              <p className={`text-sm text-center ${result.success ? 'text-green-300' : 'text-red-300'}`}>{result.message}</p>
            </>
          ) : null}
          <button onClick={onClose} className="px-4 py-2 bg-[#2a2f36] text-white/80 text-sm rounded-lg hover:bg-[#3a3646] border border-white/5">
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}
