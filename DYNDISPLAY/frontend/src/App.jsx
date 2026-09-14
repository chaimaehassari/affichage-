import { Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import ResetPassword from './pages/ResetPassword'
import Dashboard from './pages/Dashboard'
import UserList from './pages/UserList'
import UserForm from './pages/UserForm'
import SitesPosts from './pages/SitesPosts'
import BatchAssign from './pages/BatchAssign'
import MediaLibrary from './pages/MediaLibrary'
import PostPreview from './pages/PostPreview'
import LayoutList from './pages/LayoutList'
import LayoutEditor from './pages/LayoutEditor'
import DisplayConfig from './pages/DisplayConfig'
import SyncPage from './pages/SyncPage'
import Supervision from './pages/Supervision'
import Settings from './pages/Settings'
import ProtectedRoute from './routes/ProtectedRoute'
import PermissionRoute from './routes/PermissionRoute'
import ConnectionBanner from './components/ConnectionBanner'

export default function App() {
  return (
    <div className="min-h-screen">
      <ConnectionBanner />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/users" element={<PermissionRoute permission="user_list"><UserList /></PermissionRoute>} />
              <Route path="/users/new" element={<PermissionRoute permission="user_create"><UserForm /></PermissionRoute>} />
              <Route path="/users/:id/edit" element={<PermissionRoute permission="user_update"><UserForm /></PermissionRoute>} />
              <Route path="/sites-posts" element={<PermissionRoute permission="list_sites_posts"><SitesPosts /></PermissionRoute>} />
              <Route path="/batch-assign" element={<PermissionRoute permission="list_sites_posts"><BatchAssign /></PermissionRoute>} />
              <Route path="/media" element={<PermissionRoute permission="menu_media"><MediaLibrary /></PermissionRoute>} />
              <Route path="/preview/:postId" element={<PermissionRoute permission="list_sites_posts"><PostPreview /></PermissionRoute>} />
              <Route path="/layouts" element={<PermissionRoute permission="menu_conception"><LayoutList /></PermissionRoute>} />
              <Route path="/layouts/new" element={<PermissionRoute permission="menu_conception"><LayoutEditor /></PermissionRoute>} />
              <Route path="/layouts/edit/:id" element={<PermissionRoute permission="menu_conception"><LayoutEditor /></PermissionRoute>} />
              <Route path="/display-config" element={<PermissionRoute permission="menu_config"><DisplayConfig /></PermissionRoute>} />
              <Route path="/sync" element={<PermissionRoute permission="menu_sync"><SyncPage /></PermissionRoute>} />
              <Route path="/supervision" element={<PermissionRoute permission="menu_config"><Supervision /></PermissionRoute>} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ProtectedRoute>
        }
      />
    </Routes>
    </div>
  )
}