import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function PermissionRoute({ permission, children }) {
  const { user, hasPermission } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!hasPermission(permission)) {
    return <Navigate to="/" replace />;
  }

  return children;
}