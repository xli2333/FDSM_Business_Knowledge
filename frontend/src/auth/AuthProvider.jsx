import { useEffect, useState } from 'react'
import { fetchAuthStatus, loginWithPassword } from '../api/index.js'
import { useLanguage } from '../i18n/LanguageContext.js'
import AuthDialog from './AuthDialog.jsx'
import { AuthContext } from './AuthContext.js'
import { clearDebugAuth, loadDebugAuth, saveDebugAuth } from './debugAuth.js'

const GUEST_MEMBERSHIP = {
  tier: 'guest',
  tier_label: '访客',
  status: 'anonymous',
  status_label: '未登录',
  is_authenticated: false,
  is_admin: false,
  can_access_member: false,
  can_access_paid: false,
  user_id: null,
  email: null,
  note: null,
  started_at: null,
  expires_at: null,
  benefits: [],
}

const GUEST_BUSINESS_PROFILE = {
  user_id: null,
  email: null,
  display_name: '访客',
  title: '公开访客',
  organization: null,
  bio: null,
  tier: 'guest',
  tier_label: '访客',
  status: 'anonymous',
  status_label: '未登录',
  role_home_path: '/',
  auth_source: 'guest',
  locale: 'zh-CN',
  is_seed: false,
  is_authenticated: false,
  is_admin: false,
}

function buildLocalSession(account) {
  if (!account?.user_id) return null
  return {
    access_token: '',
    user: {
      id: account.user_id,
      email: account.email || null,
    },
  }
}

function buildLocalUser(account) {
  if (!account?.user_id) return null
  return {
    id: account.user_id,
    email: account.email || null,
    user_metadata: {
      display_name: account.display_name || '',
    },
  }
}

export function AuthProvider({ children }) {
  const { isEnglish } = useLanguage()
  const [session, setSession] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [authMessage, setAuthMessage] = useState('')
  const [authError, setAuthError] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [membership, setMembership] = useState(GUEST_MEMBERSHIP)
  const [businessProfile, setBusinessProfile] = useState(GUEST_BUSINESS_PROFILE)
  const [backendAuthEnabled, setBackendAuthEnabled] = useState(false)
  const [roleHomePath, setRoleHomePath] = useState('/')
  const [authMode, setAuthMode] = useState('password')

  const syncStatus = async () => {
    try {
      const payload = await fetchAuthStatus('')
      setBackendAuthEnabled(Boolean(payload.enabled))
      setMembership(payload.membership || GUEST_MEMBERSHIP)
      setBusinessProfile(payload.business_profile || GUEST_BUSINESS_PROFILE)
      setRoleHomePath(payload.role_home_path || payload.business_profile?.role_home_path || '/')
      setAuthMode(payload.auth_mode || 'password')
      return payload
    } catch {
      setBackendAuthEnabled(false)
      setMembership(GUEST_MEMBERSHIP)
      setBusinessProfile(GUEST_BUSINESS_PROFILE)
      setRoleHomePath('/')
      setAuthMode('password')
      throw new Error('auth-status-failed')
    }
  }

  useEffect(() => {
    const debugAuth = loadDebugAuth()
    if (debugAuth) {
      setUser(buildLocalUser(debugAuth))
      setSession(buildLocalSession(debugAuth))
    }

    syncStatus()
      .catch(() => {})
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const signInWithPassword = async ({ email, password }) => {
    setSubmitting(true)
    setAuthError('')
    setAuthMessage('')

    try {
      const payload = await loginWithPassword({ email, password })
      const account = {
        user_id: payload.user?.id,
        email: payload.user?.email || payload.business_profile?.email || '',
        display_name: payload.business_profile?.display_name || '',
        tier: payload.membership?.tier || 'free_member',
      }
      saveDebugAuth(account)
      setUser(buildLocalUser(account))
      setSession(buildLocalSession(account))
      setBackendAuthEnabled(true)
      setMembership(payload.membership || GUEST_MEMBERSHIP)
      setBusinessProfile(payload.business_profile || GUEST_BUSINESS_PROFILE)
      setRoleHomePath(payload.role_home_path || payload.business_profile?.role_home_path || '/')
      setAuthMode(payload.auth_mode || 'password')
      await syncStatus()
      setDialogOpen(false)
    } catch (error) {
      if (error?.status === 401) {
        setAuthError(isEnglish ? 'Incorrect email or password.' : '邮箱或密码不正确。')
      } else {
        setAuthError(isEnglish ? 'Unable to sign in at the moment.' : '登录暂不可用。')
      }
      throw error
    } finally {
      setSubmitting(false)
    }
  }

  const signOut = () => {
    clearDebugAuth()
    setSession(null)
    setUser(null)
    setMembership(GUEST_MEMBERSHIP)
    setBusinessProfile(GUEST_BUSINESS_PROFILE)
    setRoleHomePath('/')
    setAuthMessage('')
    setAuthError('')
  }

  const canUseAiAssistant = Boolean(user) && (Boolean(membership?.can_access_paid) || Boolean(membership?.is_admin))
  const authEnabled = backendAuthEnabled || loading

  const value = {
    authEnabled,
    backendAuthEnabled,
    loading,
    submitting,
    user,
    session,
    accessToken: session?.access_token || '',
    isAuthenticated: Boolean(user),
    membership,
    businessProfile,
    roleHomePath,
    authMode,
    isGuest: !user,
    isMember: Boolean(membership?.can_access_member),
    isPaidMember: Boolean(membership?.can_access_paid),
    isAdmin: Boolean(membership?.is_admin),
    canUseAiAssistant,
    authMessage,
    authError,
    openAuthDialog: () => setDialogOpen(true),
    closeAuthDialog: () => setDialogOpen(false),
    signInWithPassword,
    signOut,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
      <AuthDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onSubmit={signInWithPassword} loading={submitting} authEnabled={authEnabled} />
    </AuthContext.Provider>
  )
}
