import { getOrCreateVisitorId } from '../lib/visitor.js'
import { getDebugAuthHeaders } from '../auth/debugAuth.js'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, '')

function extractErrorMessage(detail, fallback) {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item.trim()
        if (item && typeof item.message === 'string') return item.message.trim()
        return ''
      })
      .filter(Boolean)
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message.trim()
    if (Array.isArray(detail.issues)) {
      const messages = detail.issues
        .map((item) => (item && typeof item.message === 'string' ? item.message.trim() : ''))
        .filter(Boolean)
      if (messages.length) return messages.join('；')
    }
  }
  return fallback
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData
  const visitorId = typeof window !== 'undefined' ? getOrCreateVisitorId() : null
  const authToken = options.authToken
  const debugAuthHeaders = authToken ? {} : getDebugAuthHeaders()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(visitorId ? { 'X-Visitor-Id': visitorId } : {}),
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...debugAuthHeaders,
      ...(options.headers || {}),
    },
    ...options,
  })

  if (!response.ok) {
    let message = `Request failed: ${response.status}`
    try {
      const payload = await response.clone().json()
      message = extractErrorMessage(payload?.detail, message)
    } catch {
      try {
        const text = (await response.text()).trim()
        if (text) message = text
      } catch {
        // noop
      }
    }
    const error = new Error(message)
    error.status = response.status
    throw error
  }

  return response.json()
}

export function resolveApiUrl(url) {
  if (!url) return null
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  return `${API_ORIGIN}${url}`
}

export function fetchHomeFeed(language = 'zh') {
  return request(`/home/feed?language=${encodeURIComponent(language)}`)
}

export function fetchCommerceOverview() {
  return request('/commerce/overview')
}

export function fetchAnalyticsOverview(authToken = '') {
  return request('/analytics/overview', {
    authToken,
  })
}

export function fetchAdminOverview(authToken = '') {
  return request('/admin/overview', {
    authToken,
  })
}

export function fetchAdminContentOperations(authToken = '') {
  return request('/admin/content-ops', {
    authToken,
  })
}

export function fetchAdminRagOverview(authToken = '', assetLimit = 12, jobLimit = 12, eventLimit = 8) {
  const params = new URLSearchParams()
  params.set('asset_limit', String(assetLimit))
  params.set('job_limit', String(jobLimit))
  params.set('event_limit', String(eventLimit))
  return request(`/admin/rag?${params.toString()}`, {
    authToken,
  })
}

export function fetchAdminContentCandidates(entityType, query = '', limit = 12, authToken = '') {
  const params = new URLSearchParams()
  params.set('entity_type', entityType)
  params.set('limit', String(limit))
  if (query) params.set('query', query)
  return request(`/admin/content-ops/candidates?${params.toString()}`, {
    authToken,
  })
}

export function updateAdminContentSection(slotKey, payload, authToken = '') {
  return request(`/admin/content-ops/sections/${encodeURIComponent(slotKey)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function updateAdminTrendingConfig(payload, authToken = '') {
  return request('/admin/content-ops/trending', {
    method: 'PUT',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function submitDemoRequest(payload) {
  return request('/commerce/demo-request', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchDemoRequests(limit = 50) {
  return request(`/commerce/demo-requests?limit=${limit}`)
}

export function fetchEditorialArticles(limit = 40, status = '', workflowStatus = '', draftBoxState = 'active') {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (status) params.set('status', status)
  if (workflowStatus) params.set('workflow_status', workflowStatus)
  if (draftBoxState) params.set('draft_box_state', draftBoxState)
  return request(`/editorial/articles?${params.toString()}`)
}

export function fetchEditorialSourceArticles(query = '', limit = 12) {
  const querySuffix = query ? `&query=${encodeURIComponent(query)}` : ''
  return request(`/editorial/source-articles?limit=${limit}${querySuffix}`)
}

export function fetchEditorialSourceAiOutput(articleId) {
  return request(`/editorial/source-articles/${articleId}/ai-output`)
}

export function fetchEditorialTopics(query = '', limit = 12) {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (query) params.set('query', query)
  return request(`/editorial/topics?${params.toString()}`)
}

export function importEditorialSourceAi(articleId, payload = {}) {
  return request(`/editorial/source-articles/${articleId}/import-ai`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function reopenEditorialSourceArticle(articleId) {
  return request(`/editorial/source-articles/${articleId}/reopen-draft`, {
    method: 'POST',
  })
}

export function fetchEditorialDashboard(limit = 6) {
  return request(`/editorial/dashboard?limit=${limit}`)
}

export function fetchEditorialArticle(id) {
  return request(`/editorial/articles/${id}`)
}

export function createEditorialArticle(payload) {
  return request('/editorial/articles', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateEditorialArticle(id, payload) {
  return request(`/editorial/articles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteEditorialArticle(id) {
  return request(`/editorial/articles/${id}`, {
    method: 'DELETE',
  })
}

export function autoFormatEditorialArticle(id, payload) {
  return request(`/editorial/articles/${id}/auto-format`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function autoSummarizeEditorialArticle(id) {
  return request(`/editorial/articles/${id}/auto-summary`, {
    method: 'POST',
  })
}

export function autoTranslateEditorialArticle(id) {
  return request(`/editorial/articles/${id}/auto-translate`, {
    method: 'POST',
  })
}

export function uploadEditorialFile(file, options = {}) {
  const formData = new FormData()
  formData.append('usage', options?.usage || 'source')
  if (options?.editorialId) formData.append('editorial_id', String(options.editorialId))
  formData.append('file', file)
  return request('/editorial/upload', {
    method: 'POST',
    body: formData,
  })
}

export function autotagEditorialArticle(id) {
  return request(`/editorial/articles/${id}/autotag`, {
    method: 'POST',
  })
}

export function updateEditorialWorkflow(id, payload) {
  return request(`/editorial/articles/${id}/workflow`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function renderEditorialHtml(id) {
  return request(`/editorial/articles/${id}/render-html`, {
    method: 'POST',
  })
}

export function publishEditorialArticle(id) {
  return request(`/editorial/articles/${id}/publish`, {
    method: 'POST',
  })
}

export function searchArticles(payload, authToken = '') {
  return request('/search', {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchSuggestions(query, language = 'zh') {
  return request(`/suggest?query=${encodeURIComponent(query)}&language=${encodeURIComponent(language)}`)
}

export function fetchArticle(id, authToken = '') {
  return request(`/article/${id}`, {
    authToken,
  })
}

export function fetchArticleSummary(id, authToken = '') {
  return request(`/summarize_article/${id}`, {
    authToken,
  })
}

export function fetchArticleTranslation(id, lang = 'en', authToken = '') {
  return request(`/article/${id}/translation?lang=${encodeURIComponent(lang)}`, {
    authToken,
  })
}

export function fetchArticleEngagement(id, authToken = '') {
  return request(`/article/${id}/engagement`, {
    authToken,
  })
}

export function submitArticleReaction(id, payload, authToken = '') {
  return request(`/article/${id}/reaction`, {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchLatestArticles(limit = 12, offset = 0, language = 'zh') {
  return request(`/articles/latest?limit=${limit}&offset=${offset}&language=${encodeURIComponent(language)}`)
}

export function fetchTrendingArticles(limit = 12, offset = 0, window = 'week', language = 'zh') {
  return request(
    `/articles/trending?limit=${limit}&offset=${offset}&window=${encodeURIComponent(window)}&language=${encodeURIComponent(language)}`,
  )
}

export function fetchColumns() {
  return request('/columns')
}

export function fetchColumnArticles(slug, page = 1, pageSize = 12) {
  return request(`/columns/${encodeURIComponent(slug)}/articles?page=${page}&page_size=${pageSize}`)
}

export function fetchOrganizations(limit = 60) {
  return request(`/organizations?limit=${limit}`)
}

export function fetchOrganization(slug, page = 1, pageSize = 12) {
  return request(`/organizations/${encodeURIComponent(slug)}?page=${page}&page_size=${pageSize}`)
}

export function fetchTags() {
  return request('/tags')
}

export function fetchTagArticles(slug, page = 1, pageSize = 12) {
  return request(`/tags/${encodeURIComponent(slug)}/articles?page=${page}&page_size=${pageSize}`)
}

export function fetchTopics(authToken = '') {
  return request('/topics', {
    authToken,
  })
}

export function fetchTopic(slug, page = 1, pageSize = 12, authToken = '') {
  return request(`/topics/${encodeURIComponent(slug)}?page=${page}&page_size=${pageSize}`, {
    authToken,
  })
}

export function fetchTopicTimeline(topicId, authToken = '') {
  return request(`/topics/${topicId}/timeline`, {
    authToken,
  })
}

export function fetchTopicInsights(topicId, authToken = '') {
  return request(`/topics/${topicId}/insights`, {
    authToken,
  })
}

export function fetchTimeMachine(targetDate = '', language = 'zh') {
  const params = new URLSearchParams()
  if (targetDate) params.set('date', targetDate)
  params.set('language', language)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request(`/time_machine${suffix}`)
}

export function sendChatMessage(payload) {
  return request('/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchChatSessions() {
  return request('/chat/sessions')
}

export function fetchChatSession(sessionId) {
  return request(`/chat/session/${encodeURIComponent(sessionId)}`)
}

export function deleteChatSession(sessionId) {
  return request(`/chat/session/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

export function fetchAuthStatus(authToken = '') {
  return request('/auth/status', {
    authToken,
  })
}

export function loginWithPassword(payload) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchMembershipProfile(authToken = '') {
  return request('/membership/me', {
    authToken,
  })
}

export function fetchBillingPlans(language = 'zh') {
  return request(`/billing/plans?language=${encodeURIComponent(language)}`)
}

export function fetchBillingProfile(authToken = '', language = 'zh') {
  return request(`/billing/me?language=${encodeURIComponent(language)}`, {
    authToken,
  })
}

export function createBillingCheckoutIntent(payload, authToken = '') {
  return request('/billing/checkout-intent', {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchMediaHub(kind, authToken = '', limit = 24) {
  return request(`/media/${encodeURIComponent(kind)}?limit=${limit}`, {
    authToken,
  })
}

export function fetchMediaItemDetail(kind, slug, authToken = '') {
  return request(`/media/${encodeURIComponent(kind)}/${encodeURIComponent(slug)}`, {
    authToken,
  })
}

export function fetchMediaAdminItems(kind = '', status = '', limit = 60, workflowStatus = '', draftBoxState = 'active') {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (kind) params.set('kind', kind)
  if (status) params.set('status', status)
  if (workflowStatus) params.set('workflow_status', workflowStatus)
  if (draftBoxState) params.set('draft_box_state', draftBoxState)
  return request(`/media/admin/items?${params.toString()}`)
}

export function fetchMediaAdminItem(id) {
  return request(`/media/admin/items/${id}`)
}

export function createMediaAdminItem(payload) {
  return request('/media/admin/items', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateMediaAdminItem(id, payload) {
  return request(`/media/admin/items/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteMediaAdminItem(id) {
  return request(`/media/admin/items/${id}`, {
    method: 'DELETE',
  })
}

export function generateMediaAdminCopy(id) {
  return request(`/media/admin/items/${id}/generate-copy`, {
    method: 'POST',
  })
}

export function rewriteMediaAdminChapters(id) {
  return request(`/media/admin/items/${id}/rewrite-chapters`, {
    method: 'POST',
  })
}

export function publishMediaAdminItem(id) {
  return request(`/media/admin/items/${id}/publish`, {
    method: 'POST',
  })
}

export function editPublishedMediaItem(mediaItemId, authToken = '') {
  return request(`/media/admin/published-items/${mediaItemId}/edit-draft`, {
    method: 'POST',
    authToken,
  })
}

export function uploadMediaAdminFile(file, kind, usage = 'media', options = {}) {
  const formData = new FormData()
  formData.append('kind', kind)
  formData.append('usage', usage)
  if (options?.draftId) formData.append('draft_id', String(options.draftId))
  if (Number.isFinite(options?.durationSeconds) && Number(options.durationSeconds) > 0) {
    formData.append('duration_seconds', String(Math.max(0, Math.round(Number(options.durationSeconds)))))
  }
  formData.append('file', file)
  return request('/media/admin/upload', {
    method: 'POST',
    body: formData,
  })
}

export function fetchAdminMemberships(authToken = '', limit = 100, query = '') {
  const suffix = query ? `&query=${encodeURIComponent(query)}` : ''
  return request(`/admin/memberships?limit=${limit}${suffix}`, {
    authToken,
  })
}

export function updateAdminMembership(userId, payload, authToken = '') {
  return request(`/admin/memberships/${encodeURIComponent(userId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchAdminBillingOrders(authToken = '', limit = 100, query = '') {
  const suffix = query ? `&query=${encodeURIComponent(query)}` : ''
  return request(`/admin/billing/orders?limit=${limit}${suffix}`, {
    authToken,
  })
}

export function fetchMyLibrary(authToken = '', limit = 12) {
  return request(`/me/library?limit=${limit}`, {
    authToken,
  })
}

export function fetchMyKnowledgeThemes(authToken = '', articleId = null) {
  const params = new URLSearchParams()
  if (Number.isFinite(articleId) && Number(articleId) > 0) params.set('article_id', String(Number(articleId)))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request(`/me/knowledge/themes${suffix}`, {
    authToken,
  })
}

export function createMyKnowledgeTheme(payload, authToken = '') {
  return request('/me/knowledge/themes', {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchMyKnowledgeThemeDetail(slug, authToken = '', page = 1, pageSize = 24) {
  return request(`/me/knowledge/themes/${encodeURIComponent(slug)}?page=${page}&page_size=${pageSize}`, {
    authToken,
  })
}

export function updateMyKnowledgeTheme(slug, payload, authToken = '') {
  return request(`/me/knowledge/themes/${encodeURIComponent(slug)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function deleteMyKnowledgeTheme(slug, authToken = '') {
  return request(`/me/knowledge/themes/${encodeURIComponent(slug)}`, {
    method: 'DELETE',
    authToken,
  })
}

export function addArticleToMyKnowledgeTheme(themeId, articleId, authToken = '') {
  return request(`/me/knowledge/themes/${encodeURIComponent(themeId)}/articles`, {
    method: 'POST',
    body: JSON.stringify({ article_id: articleId }),
    authToken,
  })
}

export function removeArticleFromMyKnowledgeTheme(themeId, articleId, authToken = '') {
  return request(`/me/knowledge/themes/${encodeURIComponent(themeId)}/articles/${encodeURIComponent(articleId)}`, {
    method: 'DELETE',
    authToken,
  })
}

export function chatWithMyKnowledgeTheme(slug, payload, authToken = '') {
  return request(`/me/knowledge/themes/${encodeURIComponent(slug)}/chat`, {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchMyDashboard(authToken = '') {
  return request('/me/dashboard', {
    authToken,
  })
}

export function fetchFollows(authToken = '') {
  return request('/follows', {
    authToken,
  })
}

export function toggleFollow(payload, authToken = '') {
  return request('/follows', {
    method: 'POST',
    body: JSON.stringify(payload),
    authToken,
  })
}

export function fetchWatchlist(authToken = '', limit = 24, filters = {}) {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (filters.entityType) params.set('entity_type', filters.entityType)
  if (filters.entitySlug) params.set('entity_slug', filters.entitySlug)
  return request(`/follows/watchlist?${params.toString()}`, {
    authToken,
  })
}
