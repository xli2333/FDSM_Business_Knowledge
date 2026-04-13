const DEBUG_AUTH_STORAGE_KEY = 'fdsm-debug-auth'

export function loadDebugAuth() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(DEBUG_AUTH_STORAGE_KEY)
    if (!raw) return null
    const payload = JSON.parse(raw)
    if (!payload?.user_id) return null
    return {
      user_id: payload.user_id,
      email: payload.email || '',
      display_name: payload.display_name || '',
      tier: payload.tier || 'free_member',
    }
  } catch {
    return null
  }
}

export function saveDebugAuth(account) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(
    DEBUG_AUTH_STORAGE_KEY,
    JSON.stringify({
      user_id: account.user_id,
      email: account.email || '',
      display_name: account.display_name || '',
      tier: account.tier || 'free_member',
    }),
  )
}

export function clearDebugAuth() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(DEBUG_AUTH_STORAGE_KEY)
}

export function getDebugAuthHeaders() {
  const payload = loadDebugAuth()
  if (!payload?.user_id) return {}
  return {
    'X-Debug-User-Id': payload.user_id,
    ...(payload.email ? { 'X-Debug-User-Email': payload.email } : {}),
  }
}
