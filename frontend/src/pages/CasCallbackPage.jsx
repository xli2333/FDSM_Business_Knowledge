import { useEffect } from 'react'
import { saveCasAuthToken } from '../api/index.js'

function readFragmentParams() {
  const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
  return new URLSearchParams(hash)
}

function normalizeRedirect(value) {
  if (!value || !value.startsWith('/') || value.startsWith('//')) return '/'
  return value
}

function CasCallbackPage() {
  useEffect(() => {
    const params = readFragmentParams()
    const token = params.get('token') || ''
    const redirect = normalizeRedirect(params.get('redirect') || '/')
    if (!token) {
      window.location.replace('/login?cas_error=missing_token')
      return
    }
    saveCasAuthToken(token)
    window.history.replaceState({}, '', window.location.pathname)
    window.location.replace(redirect)
  }, [])

  return <div className="page-shell py-16 text-sm text-slate-500">正在完成登录...</div>
}

export default CasCallbackPage
