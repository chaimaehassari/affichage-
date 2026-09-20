import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function SuperAdminRoute({ children }) {
  const { user, isSuperAdmin } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!isSuperAdmin) {
    return <Navigate to="/" replace />;
  }

  return children;
}