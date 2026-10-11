import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  getMe,
  loginRequest,
  logoutRequest,
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
      // getMe() bénéficie du renouvellement automatique : si le token
      // d'accès a expiré pendant que l'onglet était fermé, apiService tente
      // un refresh verrouillé puis rejoue l'appel. L'utilisateur n'est
      // déconnecté que si ce refresh échoue lui aussi.
      const result = await getMe();
      if (result.ok && result.data) {
        setUser(result.data);
      } else if (result.status === 401) {
        // Échec définitif du refresh : la session est réellement terminée.
        apiService.clearToken();
        setUser(null);
      }
      // Autre erreur (réseau, 5xx) : on ne détruit PAS la session, on
      // recharge simplement. Effacer le token sur un timeout réseau
      // déconnectait l'utilisateur pour une panne passagère.
    } catch {
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
        // Le refresh token permet de renouveler un accès expiré sans
        // ressaisir le mot de passe. S'il est absent (serveur non mis à jour),
        // l'apiService fonctionnera comme avant.
        apiService.setRefreshToken(result.data.refresh_token);
        setUser(result.data.user);
        setLoading(false);
        return { success: true };
      }

      const detail = result.data?.detail;
      const message = detail || 'Identifiant ou mot de passe incorrect.';
      setError(getErrorMessage(result.data));
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

  const applySession = (token, userData, refreshToken) => {
    apiService.setToken(token);
    if (refreshToken) apiService.setRefreshToken(refreshToken);
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
    isAuthenticated: !!user,
    isAdmin: user?.profile_name === 'Administrateur',
    isSuperAdmin: user?.profile_name === 'Administrateur' && !!user?.is_superadmin,
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
