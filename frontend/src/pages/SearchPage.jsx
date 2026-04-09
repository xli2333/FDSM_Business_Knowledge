import { Clock3, Funnel, SlidersHorizontal, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { fetchColumns, fetchTags, searchArticles } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import SearchBar from '../components/shared/SearchBar.jsx'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

const SEARCH_HISTORY_KEY = 'fdsm-search-history'

function readSearchHistory() {
  try {
    const payload = window.localStorage.getItem(SEARCH_HISTORY_KEY)
    return payload ? JSON.parse(payload) : []
  } catch {
    return []
  }
}

function writeSearchHistory(query) {
  try {
    const current = readSearchHistory().filter((item) => item !== query)
    const next = [query, ...current].slice(0, 8)
    window.localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(next))
    return next
  } catch {
    return []
  }
}

function SearchPage() {
  const { isEnglish } = useLanguage()
  const { accessToken, isAdmin, isAuthenticated, isPaidMember, openAuthDialog } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const query = searchParams.get('q') || ''
  const mode = searchParams.get('mode') || 'smart'
  const sort = searchParams.get('sort') || 'relevance'
  const startDate = searchParams.get('start_date') || ''
  const endDate = searchParams.get('end_date') || ''
  const rawTags = searchParams.get('tags') || ''
  const rawColumns = searchParams.get('columns') || ''
  const tagSlugs = useMemo(() => rawTags.split(',').filter(Boolean), [rawTags])
  const columnSlugs = useMemo(() => rawColumns.split(',').filter(Boolean), [rawColumns])

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [tagsData, setTagsData] = useState({ groups: [], hot: [] })
  const [columns, setColumns] = useState([])
  const [history, setHistory] = useState([])

  const hasSmartSearchAccess = isPaidMember || isAdmin
  const showSmartSearchNotice = !hasSmartSearchAccess

  useEffect(() => {
    fetchTags().then(setTagsData).catch(() => {})
    fetchColumns().then(setColumns).catch(() => {})
    setHistory(readSearchHistory())
  }, [])

  const tagLookup = useMemo(() => {
    const map = new Map()
    for (const group of tagsData.groups || []) {
      for (const tag of group.items || []) {
        map.set(tag.slug, tag)
      }
    }
    for (const tag of tagsData.hot || []) {
      if (!map.has(tag.slug)) {
        map.set(tag.slug, tag)
      }
    }
    return map
  }, [tagsData])

  const selectedTags = useMemo(() => tagSlugs.map((slug) => tagLookup.get(slug)).filter(Boolean), [tagLookup, tagSlugs])
  const selectedColumns = useMemo(
    () => columnSlugs.map((slug) => columns.find((item) => item.slug === slug)).filter(Boolean),
    [columnSlugs, columns],
  )

  const buildSearchUrl = (nextQuery, nextMode, overrides = {}) => {
    const params = new URLSearchParams()
    if (nextQuery) params.set('q', nextQuery)
    if (nextMode) params.set('mode', nextMode)
    if ((overrides.sort ?? sort) && (overrides.sort ?? sort) !== 'relevance') {
      params.set('sort', overrides.sort ?? sort)
    }
    if (overrides.start_date ?? startDate) {
      params.set('start_date', overrides.start_date ?? startDate)
    }
    if (overrides.end_date ?? endDate) {
      params.set('end_date', overrides.end_date ?? endDate)
    }

    const nextTags = overrides.tags ?? tagSlugs
    const nextColumns = overrides.columns ?? columnSlugs

    if (nextTags.length) params.set('tags', nextTags.join(','))
    if (nextColumns.length) params.set('columns', nextColumns.join(','))

    return `/search?${params.toString()}`
  }

  useEffect(() => {
    if (mode !== 'smart' || hasSmartSearchAccess) return
    const params = new URLSearchParams()
    if (query) params.set('q', query)
    params.set('mode', 'exact')
    if (sort && sort !== 'relevance') params.set('sort', sort)
    if (startDate) params.set('start_date', startDate)
    if (endDate) params.set('end_date', endDate)
    if (rawTags) params.set('tags', rawTags)
    if (rawColumns) params.set('columns', rawColumns)
    navigate(`/search?${params.toString()}`, { replace: true })
  }, [hasSmartSearchAccess, mode, navigate, query, sort, startDate, endDate, rawTags, rawColumns])

  useEffect(() => {
    if (!query) {
      setData(null)
      setSearchError('')
      return
    }

    let cancelled = false

    const load = async () => {
      await Promise.resolve()
      if (cancelled) return
      setLoading(true)
      setSearchError('')

      try {
        const payload = await searchArticles(
          {
            query,
            mode: mode === 'smart' && !hasSmartSearchAccess ? 'exact' : mode,
            language: isEnglish ? 'en' : 'zh',
            sort,
            page: 1,
            page_size: 18,
            filters: {
              start_date: startDate || null,
              end_date: endDate || null,
              tags: selectedTags.map((tag) => tag.name),
              columns: columnSlugs,
            },
          },
          accessToken,
        )

        if (!cancelled) {
          setData(payload)
          setHistory(writeSearchHistory(query))
        }
      } catch (error) {
        if (cancelled) return
        setData(null)
        if (error?.status === 401) {
          setSearchError(isEnglish ? 'Smart search requires sign-in and a paid membership.' : '\u667a\u80fd\u641c\u7d22\u9700\u8981\u5148\u767b\u5f55\u5e76\u5f00\u901a\u4ed8\u8d39\u4f1a\u5458\u3002')
        } else if (error?.status === 403) {
          setSearchError(isEnglish ? 'Smart search is available to paid members only.' : '\u667a\u80fd\u641c\u7d22\u4ec5\u5bf9\u4ed8\u8d39\u4f1a\u5458\u5f00\u653e\u3002')
        } else {
          setSearchError(isEnglish ? 'Search is temporarily unavailable.' : '\u641c\u7d22\u6682\u65f6\u4e0d\u53ef\u7528\u3002')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load().catch(() => {})
    return () => {
      cancelled = true
    }
  }, [query, mode, sort, startDate, endDate, selectedTags, columnSlugs, isEnglish, hasSmartSearchAccess, accessToken])

  const handleSearch = (nextQuery, nextMode) => {
    const resolvedMode = nextMode === 'smart' && !hasSmartSearchAccess ? 'exact' : nextMode
    navigate(buildSearchUrl(nextQuery, resolvedMode))
  }

  const toggleTag = (slug) => {
    const next = tagSlugs.includes(slug) ? tagSlugs.filter((item) => item !== slug) : [...tagSlugs, slug]
    navigate(buildSearchUrl(query, mode, { tags: next }))
  }

  const toggleColumn = (slug) => {
    const next = columnSlugs.includes(slug) ? columnSlugs.filter((item) => item !== slug) : [...columnSlugs, slug]
    navigate(buildSearchUrl(query, mode, { columns: next }))
  }

  const clearFilters = () => {
    navigate(buildSearchUrl(query, mode, { tags: [], columns: [], start_date: '', end_date: '', sort: 'relevance' }))
  }

  const hasActiveFilters = Boolean(tagSlugs.length || columnSlugs.length || startDate || endDate || sort !== 'relevance')
  const showEmptyState = !loading && query && data && data.items.length === 0
  const showExactModeHint = Boolean(showEmptyState && mode === 'exact')

  return (
    <div className="page-shell py-12">
      <div className="mb-8">
        <div className="section-kicker">{isEnglish ? 'Unified Search' : '\u7edf\u4e00\u641c\u7d22'}</div>
        <h1 className="section-title">{isEnglish ? 'Search across the knowledge base' : '\u5728\u77e5\u8bc6\u5e93\u91cc\u641c\u7d22\u6587\u7ae0\u3001\u4e3b\u9898\u4e0e\u4eba\u7269'}</h1>
      </div>

      <SearchBar initialQuery={query} initialMode={mode} onSearch={handleSearch} variant="compact" />

      {showSmartSearchNotice ? (
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-[1.4rem] border border-fudan-orange/20 bg-fudan-orange/5 px-5 py-4 text-sm text-slate-600">
          <div>
            {isEnglish
              ? 'Smart RAG search is reserved for paid members. The current tier can continue with exact keyword search.'
              : '\u667a\u80fd RAG \u641c\u7d22\u4ec5\u5bf9\u4ed8\u8d39\u4f1a\u5458\u5f00\u653e\uff0c\u5f53\u524d\u8eab\u4efd\u53ef\u7ee7\u7eed\u4f7f\u7528\u7cbe\u786e\u5173\u952e\u8bcd\u641c\u7d22\u3002'}
          </div>
          <button
            type="button"
            onClick={isAuthenticated ? () => navigate('/membership') : openAuthDialog}
            className="rounded-full bg-fudan-blue px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white transition hover:bg-fudan-dark"
          >
            {isAuthenticated ? (isEnglish ? 'Upgrade membership' : '\u5347\u7ea7\u4f1a\u5458') : isEnglish ? 'Sign in' : '\u7acb\u5373\u767b\u5f55'}
          </button>
        </div>
      ) : null}

      <div className="mt-8 grid gap-6 xl:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="space-y-5">
          <section className="fudan-panel p-5">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-fudan-orange">
              <Funnel size={14} />
              {isEnglish ? 'Filters' : '\u7b5b\u9009\u5668'}
            </div>

            <div className="mt-5 space-y-5">
              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">{isEnglish ? 'Sort' : '\u6392\u5e8f'}</div>
                <select
                  value={sort}
                  onChange={(event) => navigate(buildSearchUrl(query, mode, { sort: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                >
                  <option value="relevance">{isEnglish ? 'Relevance first' : '\u76f8\u5173\u5ea6\u4f18\u5148'}</option>
                  <option value="date">{isEnglish ? 'Newest first' : '\u6700\u65b0\u4f18\u5148'}</option>
                  <option value="popularity">{isEnglish ? 'Most popular' : '\u70ed\u5ea6\u4f18\u5148'}</option>
                </select>
              </div>

              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">{isEnglish ? 'Date' : '\u65e5\u671f'}</div>
                <div className="space-y-3">
                  <input
                    type="date"
                    value={startDate}
                    onChange={(event) => navigate(buildSearchUrl(query, mode, { start_date: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                  />
                  <input
                    type="date"
                    value={endDate}
                    onChange={(event) => navigate(buildSearchUrl(query, mode, { end_date: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                  />
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">{isEnglish ? 'Columns' : '\u680f\u76ee'}</div>
                <div className="flex flex-wrap gap-2">
                  {columns.map((column) => (
                    <button
                      key={column.slug}
                      type="button"
                      onClick={() => toggleColumn(column.slug)}
                      className={[
                        'rounded-full border px-3 py-2 text-xs font-semibold transition',
                        columnSlugs.includes(column.slug)
                          ? 'border-fudan-blue bg-fudan-blue text-white'
                          : 'border-slate-200 bg-white text-slate-500',
                      ].join(' ')}
                    >
                      {column.name}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs uppercase tracking-[0.2em] text-slate-400">{isEnglish ? 'Hot tags' : '\u70ed\u95e8\u6807\u7b7e'}</div>
                <div className="flex flex-wrap gap-2">
                  {(tagsData.hot || []).slice(0, 12).map((tag) => (
                    <button key={tag.slug} type="button" onClick={() => toggleTag(tag.slug)}>
                      <TagBadge tag={tag} clickable={false} />
                    </button>
                  ))}
                </div>
              </div>

              {hasActiveFilters ? (
                <button
                  type="button"
                  onClick={clearFilters}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500"
                >
                  <X size={14} />
                  {isEnglish ? 'Clear filters' : '\u6e05\u7a7a\u7b5b\u9009'}
                </button>
              ) : null}
            </div>
          </section>

          {history.length ? (
            <section className="fudan-panel p-5">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-fudan-orange">
                <Clock3 size={14} />
                {isEnglish ? 'Search history' : '\u641c\u7d22\u5386\u53f2'}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {history.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => navigate(buildSearchUrl(item, mode))}
                    className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600"
                  >
                    {item}
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </aside>

        <div>
          <div className="flex items-center justify-between gap-4">
            <div className="text-sm text-slate-500">
              {query
                ? isEnglish
                  ? `Results for "${query}"`
                  : `\u5173\u4e8e\u201c${query}\u201d\u7684\u641c\u7d22\u7ed3\u679c`
                : isEnglish
                  ? 'Enter a search term'
                  : '\u8bf7\u8f93\u5165\u641c\u7d22\u8bcd'}
            </div>
            {data ? (
              <div className="inline-flex items-center gap-2 text-sm text-slate-500">
                <SlidersHorizontal size={15} />
                {isEnglish ? `${data.total} results` : `\u5171 ${data.total} \u6761\u7ed3\u679c`}
              </div>
            ) : null}
          </div>

          {selectedTags.length || selectedColumns.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {selectedTags.map((tag) => (
                <button key={tag.slug} type="button" onClick={() => toggleTag(tag.slug)}>
                  <TagBadge tag={tag} clickable={false} />
                </button>
              ))}
              {selectedColumns.map((column) => (
                <button
                  key={column.slug}
                  type="button"
                  onClick={() => toggleColumn(column.slug)}
                  className="rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-3 py-1 text-xs font-semibold text-fudan-blue"
                >
                  {column.name}
                </button>
              ))}
            </div>
          ) : null}

          {loading ? <div className="mt-10 text-sm text-slate-500">{isEnglish ? 'Searching...' : '\u641c\u7d22\u4e2d...'}</div> : null}

          {!loading && searchError ? <div className="mt-10 rounded-[1.4rem] border border-red-200 bg-red-50 p-5 text-sm text-red-600">{searchError}</div> : null}

          {!loading && data?.items?.length ? (
            <div className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
              {data.items.map((item) => (
                <ArticleCard key={item.id} article={item} />
              ))}
            </div>
          ) : null}

          {showEmptyState ? (
            <div className="mt-16 fudan-panel p-10 text-center text-slate-500">
              <div>
                {showExactModeHint
                  ? isEnglish
                    ? `No exact matches were found for "${query}". Exact search only matches the full phrase.`
                    : `\u6ca1\u6709\u627e\u5230\u4e0e\u201c${query}\u201d\u5b8c\u5168\u5339\u914d\u7684\u7ed3\u679c\u3002\u7cbe\u786e\u641c\u7d22\u53ea\u4f1a\u5339\u914d\u5b8c\u6574\u77ed\u8bed\u3002`
                  : isEnglish
                    ? `No articles were found for "${query}". Try a more specific topic, company, or person name.`
                    : `\u6ca1\u6709\u627e\u5230\u4e0e\u201c${query}\u201d\u8db3\u591f\u76f8\u5173\u7684\u6587\u7ae0\uff0c\u5efa\u8bae\u6362\u4e00\u4e2a\u66f4\u5177\u4f53\u7684\u4e3b\u9898\u8bcd\u3001\u516c\u53f8\u540d\u6216\u4eba\u7269\u540d\u3002`}
              </div>

              {showExactModeHint ? (
                showSmartSearchNotice ? (
                  <button
                    type="button"
                    onClick={isAuthenticated ? () => navigate('/membership') : openAuthDialog}
                    className="mt-5 inline-flex items-center rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
                  >
                    {isAuthenticated ? (isEnglish ? 'Upgrade for smart search' : '\u5347\u7ea7\u540e\u4f7f\u7528\u667a\u80fd\u641c\u7d22') : isEnglish ? 'Sign in for smart search' : '\u767b\u5f55\u540e\u4f7f\u7528\u667a\u80fd\u641c\u7d22'}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => navigate(buildSearchUrl(query, 'smart'))}
                    className="mt-5 inline-flex items-center rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
                  >
                    {isEnglish ? 'Switch to smart search' : '\u5207\u6362\u5230\u667a\u80fd\u641c\u7d22'}
                  </button>
                )
              ) : null}

              {hasActiveFilters ? (
                <div className="mt-4">
                  <button
                    type="button"
                    onClick={clearFilters}
                    className="inline-flex items-center rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
                  >
                    {isEnglish ? 'Clear filters and retry' : '\u6e05\u7a7a\u7b5b\u9009\u540e\u91cd\u8bd5'}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default SearchPage
