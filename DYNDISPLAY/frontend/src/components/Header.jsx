import { useAuth } from '../contexts/AuthContext'

export default function Header({ onMenuToggle, apiStatus }) {
  const { user, logout } = useAuth()

  return (
    <header className="sticky top-0 z-20 flex items-center justify-between h-16 px-4 bg-white border-b border-gray-200 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 lg:hidden"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        <h1 className="text-lg font-semibold text-gray-900">Dashboard</h1>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              apiStatus === 'online' ? 'bg-green-500' : apiStatus === 'checking' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'
            }`}
          />
          <span className="text-sm text-gray-500">
            API {apiStatus === 'online' ? 'Online' : apiStatus === 'checking' ? 'Checking...' : 'Offline'}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
          </div>
          {user && (
            <div className="hidden sm:flex flex-col">
              <span className="text-sm font-medium text-gray-900">{user.login}</span>
              <span className="text-xs text-gray-500">{user.profile_name}</span>
            </div>
          )}
          <button
            onClick={logout}
            className="px-3 py-1.5 text-sm text-gray-600 hover:text-red-600 hover:bg-gray-100 rounded-lg transition-colors"
            title="Déconnexion"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
          </button>
        </div>
      </div>
    </header>
  )
}
