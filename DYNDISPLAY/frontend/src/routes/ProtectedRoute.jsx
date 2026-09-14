import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import LoadingSpinner from '../components/common/LoadingSpinner';
import MustChangePassword from '../components/MustChangePassword';
import SessionLock from '../components/SessionLock';
import ActivationScreen from '../components/ActivationScreen';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-dark-50">
        <LoadingSpinner />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (user?.is_activated === false) {
    return <ActivationScreen />;
  }

  if (user?.must_change_password) {
    return <MustChangePassword />;
  }

  return (
    <>
      <SessionLock />
      {children}
    </>
  );
}
