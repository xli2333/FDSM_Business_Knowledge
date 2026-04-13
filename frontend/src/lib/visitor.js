const VISITOR_STORAGE_KEY = 'fdsm-visitor-id'

function generateVisitorId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `visitor-${crypto.randomUUID()}`
  }
  return `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function getOrCreateVisitorId() {
  if (typeof window === 'undefined') return null
  const existing = window.localStorage.getItem(VISITOR_STORAGE_KEY)
  if (existing) return existing
  const next = generateVisitorId()
  window.localStorage.setItem(VISITOR_STORAGE_KEY, next)
  return next
}

export function getStoredVisitorId() {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(VISITOR_STORAGE_KEY)
}
