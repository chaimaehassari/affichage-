import { useState, useEffect, useCallback } from 'react';
import { WifiOff, Wifi } from 'lucide-react';
import apiService from '../services/api';

let listeners = [];
function notifyListeners(state) {
  listeners.forEach((l) => l(state));
}
export function emitServerStatus(status) {
  notifyListeners(status);
}
export function subscribeServerStatus(fn) {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

export default function ConnectionBanner() {
  const [serverOnline, setServerOnline] = useState(null);
  const [checking, setChecking] = useState(false);

  const checkHealth = useCallback(async () => {
    setChecking(true);
    const res = await apiService.healthCheck();
    const online = res.ok && res.status !== 0;
    setServerOnline(online);
    emitServerStatus(online);
    setChecking(false);
  }, []);

  useEffect(() => {
    const onOnline = () => { setServerOnline(null); checkHealth(); };
    const onOffline = () => { setServerOnline(false); emitServerStatus(false); };

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    checkHealth();
    const interval = setInterval(checkHealth, 30000);

    const unsub = subscribeServerStatus((s) => setServerOnline(s));

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      clearInterval(interval);
      unsub();
    };
  }, [checkHealth]);

  if (serverOnline === null) return null;
  if (serverOnline) {
    return (
      <div className="fixed bottom-4 right-4 z-[60] flex items-center gap-2 px-3 py-1.5 rounded-lg bg-green-950/90 border border-green-700/40 text-green-300 text-xs shadow-xl">
        <Wifi className="w-3.5 h-3.5" />
        Serveur connecté
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex items-center gap-2 px-3 py-1.5 rounded-lg bg-red-950/90 border border-red-700/40 text-red-300 text-xs shadow-xl">
      <WifiOff className="w-3.5 h-3.5" />
      {checking ? 'Vérification...' : 'Serveur inaccessible — mode hors ligne'}
    </div>
  );
}
