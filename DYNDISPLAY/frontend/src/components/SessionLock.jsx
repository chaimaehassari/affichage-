import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getSettings } from '../services/settings';

export default function SessionLock() {
  const { user, logout, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [enabled, setEnabled] = useState(false);
  const [timeoutMinutes, setTimeoutMinutes] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await getSettings();
      if (!cancelled && result.ok && result.data) {
        const minutes = parseInt(result.data.session_timeout_minutes || 0, 10);
        setTimeoutMinutes(minutes);
        setEnabled(minutes > 0);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!isAuthenticated || !enabled || timeoutMinutes <= 0) return;

    function resetTimer() {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        logout();
        navigate('/login', { replace: true });
      }, timeoutMinutes * 60 * 1000);
    }

    const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'];
    events.forEach((ev) => window.addEventListener(ev, resetTimer));
    resetTimer();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      events.forEach((ev) => window.removeEventListener(ev, resetTimer));
    };
  }, [isAuthenticated, enabled, timeoutMinutes, logout, navigate]);

  return null;
}
