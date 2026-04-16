import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext.js'
import ChatPanel from '../shared/ChatPanel.jsx'
import Footer from './Footer.jsx'
import Navbar from './Navbar.jsx'

function RouteScrollReset() {
  const location = useLocation()

  useEffect(() => {
    if (typeof window === 'undefined' || !window.history) return undefined
    if (!('scrollRestoration' in window.history)) return undefined
    const previous = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    return () => {
      window.history.scrollRestoration = previous
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    document.documentElement.scrollTop = 0
    document.body.scrollTop = 0
  }, [location.pathname])

  return null
}

function SiteLayout() {
  const { authMessage, authError, canUseAiAssistant } = useAuth()
  return (
    <div className="min-h-screen">
      <RouteScrollReset />
      <Navbar />
      {authMessage ? <div className="bg-emerald-50 px-4 py-3 text-center text-sm text-emerald-700">{authMessage}</div> : null}
      {authError ? <div className="bg-red-50 px-4 py-3 text-center text-sm text-red-600">{authError}</div> : null}
      <main className="min-h-[calc(100vh-180px)]">
        <Outlet />
      </main>
      <Footer />
      {canUseAiAssistant ? <ChatPanel variant="floating" /> : null}
    </div>
  )
}

export default SiteLayout
