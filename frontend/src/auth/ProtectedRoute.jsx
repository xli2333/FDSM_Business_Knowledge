import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext.js'

function buildLoginPath(pathname) {
  return `/login?redirect=${encodeURIComponent(pathname || '/')}`
}

function ProtectedRoute({ children, requireAdmin = false, requirePaid = false, requireAiAssistant = false, fallbackPath = '/' }) {
  const location = useLocation()
  const { loading, isAuthenticated, isAdmin, isPaidMember, canUseAiAssistant } = useAuth()

  if (loading) {
    return <div className="page-shell py-16 text-sm text-slate-500">Loading access...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to={buildLoginPath(`${location.pathname}${location.search || ''}`)} replace />
  }

  if (requireAdmin && !isAdmin) {
    return <Navigate to={fallbackPath} replace />
  }

  if (requirePaid && !isPaidMember) {
    return <Navigate to={fallbackPath} replace />
  }

  if (requireAiAssistant && !canUseAiAssistant) {
    return <Navigate to={fallbackPath} replace />
  }

  return children
}

export default ProtectedRoute
