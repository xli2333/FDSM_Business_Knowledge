import { Outlet } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext.js'
import ChatPanel from '../shared/ChatPanel.jsx'
import Footer from './Footer.jsx'
import Navbar from './Navbar.jsx'

function SiteLayout() {
  const { authMessage, authError, canUseAiAssistant } = useAuth()
  return (
    <div className="min-h-screen">
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
