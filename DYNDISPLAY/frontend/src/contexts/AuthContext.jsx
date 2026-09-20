import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getMe,
  loginRequest,
  logoutRequest,
  activateAccount,
  activateAccountDevice,
} from '../services/auth';
import apiService, { subscribeUnauthorized } from '../services/api';

const AuthContext = createContext(null);

function getErrorMessage(data) {
  const detail = data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail === 'object' && detail.message) return detail.message;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d.msg || JSON.stringify(d)).filter(Boolean).join('; ');
  }
  return 'Identifiant, mot de passe ou code client incorrect.';
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadUser = useCallback(async () => {
    const token = apiService.getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const result = await getMe();
      if (result.ok && result.data) {
        setUser(result.data);
      } else {
        apiService.clearToken();
        setUser(null);
      }
    } catch {
      apiService.clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    return subscribeUnauthorized(() => {
      setUser(null);
      setError('Votre session a expiré. Veuillez vous reconnecter.');
    });
  }, []);

  const login = async (loginStr, password, clientCode) => {
    setError(null);
    setLoading(true);

    try {
      const result = await loginRequest(loginStr, password, clientCode);

      if (result.ok && result.data) {
        apiService.setToken(result.data.access_token);
        setUser(result.data.user);
        setLoading(false);
        return { success: true };
      }

      const detail = result.data?.detail;
      const message = detail || 'Identifiant ou mot de passe incorrect.';
      setError(getErrorMessage(result.data));
      setLoading(false);

      const gateCode =
        detail && typeof detail === 'object' && !Array.isArray(detail) ? detail.code : null;
      if (gateCode === 'account_activation_required' || gateCode === 'device_change_activation_required') {
        return {
          success: false,
          error: message,
          needsActivation: true,
          gateCode,
          accountCode: detail.account_code || null,
        };
      }
      return { success: false, error: message };
    } catch {
      const message = 'Erreur de connexion au serveur.';
      setError(message);
      setLoading(false);
      return { success: false, error: message };
    }
  };

  const activateDevice = async (loginStr, activationCode, password, clientCode) => {
    setError(null);
    setLoading(true);
    try {
      const result = await activateAccountDevice(loginStr, activationCode);
      if (result.ok && result.data && result.data.success) {
        setLoading(false);
        return await login(loginStr, password, clientCode);
      }
      const detail = result.data?.detail;
      const message =
        typeof detail === 'string' && detail ? detail : "Code d'activation invalide ou expiré.";
      setError(message);
      setLoading(false);
      return { success: false, error: message };
    } catch {
      const message = 'Erreur de connexion au serveur.';
      setError(message);
      setLoading(false);
      return { success: false, error: message };
    }
  };

  const logout = async () => {
    try {
      await logoutRequest();
    } finally {
      apiService.clearToken();
      setUser(null);
      setError(null);
    }
  };

  const refreshUser = async () => {
    try {
      const result = await getMe();
      if (result.ok && result.data) {
        setUser(result.data);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  };

  const activate = async (code) => {
    setError(null);
    try {
      const result = await activateAccount(code);
      if (result.ok && result.data) {
        setUser(result.data);
        return { success: true };
      }
      const detail = result.data?.detail;
      setError(typeof detail === 'string' && detail ? detail : 'Code de sérialisation invalide.');
      return { success: false, error: detail };
    } catch {
      const message = 'Erreur de connexion au serveur.';
      setError(message);
      return { success: false, error: message };
    }
  };

  const applySession = (token, userData) => {
    apiService.setToken(token);
    setUser(userData);
    setError(null);
  };

  const value = {
    user,
    loading,
    error,
    login,
    logout,
    refreshUser,
    applySession,
    activate,
    activateDevice,
    isAuthenticated: !!user,
    isAdmin: user?.profile_name === 'Administrateur',
    isSuperAdmin: user?.profile_name === 'Administrateur' && !!user?.is_superadmin,
    needsActivation: !!user && user.is_activated === false,
    isActivated: !user || user.is_activated === true,
    hasPermission: (code) => {
      if (!user) return false;
      if (user.profile_name === 'Administrateur') return true;
      const perm = user.permissions?.find((p) => p.code === code);
      return !!perm && perm.can_view;
    },
    allowedZones: user?.zones || [],
    canAccessZone: (zoneNumber) => {
      if (!user) return false;
      if (user.profile_name === 'Administrateur') return true;
      return (user.zones || []).includes(Number(zoneNumber));
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
