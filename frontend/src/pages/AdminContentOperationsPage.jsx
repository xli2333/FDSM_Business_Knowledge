import { LoaderCircle, RefreshCw, Save, Search, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  fetchAdminContentCandidates,
  fetchAdminContentOperations,
  updateAdminContentSection,
  updateAdminTrendingConfig,
} from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const SLOT_ORDER = ['hero', 'editors_picks', 'quick_tags', 'topic_starters', 'column_navigation', 'topic_square']

const SLOT_COPY = {
  zh: {
    hero: { title: '头条文章', desc: '首页主视觉文章，只保留 1 篇。' },
    editors_picks: { title: '编辑推荐', desc: '首页右上推荐文章，按顺序展示。' },
    quick_tags: { title: '快速入口标签', desc: '首页首屏快速入口标签。' },
    topic_starters: { title: '专题起读', desc: '首页首屏优先引导进入的专题。' },
    column_navigation: { title: '栏目导航', desc: '首页栏目区显示哪些栏目，以及顺序。' },
    topic_square: { title: '专题广场', desc: '首页专题广场显示哪些专题，以及顺序。' },
  },
  en: {
    hero: { title: 'Lead story', desc: 'Homepage hero article. Keep one item only.' },
    editors_picks: { title: "Editor's picks", desc: 'The homepage recommendation list shown in order.' },
    quick_tags: { title: 'Quick tags', desc: 'Fast-entry tags shown in the first screen.' },
    topic_starters: { title: 'Topic starters', desc: 'Topics highlighted in the first screen.' },
    column_navigation: { title: 'Column navigation', desc: 'Which columns appear on the homepage and in what order.' },
    topic_square: { title: 'Topic square', desc: 'Which topics appear in the homepage topic square.' },
  },
}

function normalizeSections(sections) {
  const map = {}
  for (const section of sections || []) {
    map[section.slot_key] = {
      slot_key: section.slot_key,
      entity_type: section.entity_type,
      max_items: section.max_items,
      items: Array.isArray(section.items) ? section.items : [],
    }
  }
  return map
}

function candidateKey(item) {
  return `${item?.entity_type || 'item'}:${item?.id ?? ''}:${item?.slug ?? ''}`
}

function AdminContentOperationsPage() {
  const { accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [sections, setSections] = useState({})
  const [trending, setTrending] = useState({
    default_window: 'week',
    windows: ['day', 'week', 'month'],
    view_weight: 1,
    like_weight: 4,
    bookmark_weight: 6,
  })
  const [searchState, setSearchState] = useState({})
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const copy = isEnglish
    ? {
        title: 'Content Operations',
        subtitle: 'Configure homepage slots, topic entry points, and trending rules from one admin page.',
        searchPlaceholder: 'Search candidates',
        search: 'Search',
        add: 'Add',
        save: 'Save section',
        remove: 'Remove',
        moveUp: 'Up',
        moveDown: 'Down',
        empty: 'No items selected yet.',
        results: 'Search results',
        none: 'No matching candidates.',
        trendingTitle: 'Trending rules',
        trendingDesc: 'Switch day / week / month and adjust the engagement weighting formula.',
        defaultWindow: 'Default window',
        viewWeight: 'View weight',
        likeWeight: 'Like weight',
        bookmarkWeight: 'Bookmark weight',
        saveTrending: 'Save trending rules',
        refresh: 'Reload',
      }
    : {
        title: '内容运营后台',
        subtitle: '在一个后台里配置首页槽位、专题推荐入口和热门榜规则。',
        searchPlaceholder: '搜索候选内容',
        search: '搜索',
        add: '加入',
        save: '保存本区块',
        remove: '移除',
        moveUp: '上移',
        moveDown: '下移',
        empty: '当前还没有选择内容。',
        results: '搜索结果',
        none: '没有匹配结果。',
        trendingTitle: '热门榜规则',
        trendingDesc: '配置日榜 / 周榜 / 月榜切换和浏览、点赞、收藏权重。',
        defaultWindow: '默认周期',
        viewWeight: '浏览权重',
        likeWeight: '点赞权重',
        bookmarkWeight: '收藏权重',
        saveTrending: '保存热门榜规则',
        refresh: '刷新',
      }

  const orderedSections = useMemo(() => SLOT_ORDER.map((slotKey) => sections[slotKey]).filter(Boolean), [sections])

  useEffect(() => {
    fetchAdminContentOperations(accessToken)
      .then((payload) => {
        setSections(normalizeSections(payload.sections))
        setTrending(payload.trending)
      })
      .catch(() => setError(isEnglish ? 'Failed to load content operations.' : '内容运营后台加载失败。'))
  }, [accessToken, isEnglish])

  async function run(taskKey, task) {
    setBusy(taskKey)
    setError('')
    setMessage('')
    try {
      await task()
    } catch (taskError) {
      setError(taskError?.message || (isEnglish ? 'Request failed.' : '请求失败。'))
    } finally {
      setBusy('')
    }
  }

  function updateSectionItems(slotKey, updater) {
    setSections((current) => {
      const section = current[slotKey]
      if (!section) return current
      return {
        ...current,
        [slotKey]: {
          ...section,
          items: updater(section.items),
        },
      }
    })
  }

  function moveItem(slotKey, index, direction) {
    updateSectionItems(slotKey, (items) => {
      const next = [...items]
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= next.length) return next
      ;[next[index], next[targetIndex]] = [next[targetIndex], next[index]]
      return next
    })
  }

  function appendCandidate(slotKey, candidate) {
    setSections((current) => {
      const section = current[slotKey]
      if (!section) return current
      const exists = section.items.some((item) => candidateKey(item) === candidateKey(candidate))
      if (exists || section.items.length >= section.max_items) return current
      return {
        ...current,
        [slotKey]: {
          ...section,
          items: [...section.items, candidate],
        },
      }
    })
  }

  async function searchCandidates(slotKey) {
    const section = sections[slotKey]
    if (!section) return
    const query = searchState[slotKey]?.query || ''
    const results = await fetchAdminContentCandidates(section.entity_type, query, 12, accessToken)
    setSearchState((current) => ({
      ...current,
      [slotKey]: {
        ...(current[slotKey] || {}),
        results,
      },
    }))
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="section-kicker">{copy.title}</div>
            <h1 className="section-title">{copy.title}</h1>
            <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">{copy.subtitle}</p>
          </div>
          <button
            type="button"
            onClick={() =>
              run('refresh', async () => {
                const payload = await fetchAdminContentOperations(accessToken)
                setSections(normalizeSections(payload.sections))
                setTrending(payload.trending)
                setMessage(isEnglish ? 'Configuration reloaded.' : '配置已刷新。')
              })
            }
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-fudan-blue"
          >
            {busy === 'refresh' ? <LoaderCircle size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {copy.refresh}
          </button>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {message ? <div className="mt-4 text-sm text-emerald-600">{message}</div> : null}

      <section className="mt-8 grid gap-6 xl:grid-cols-2">
        {orderedSections.map((section) => {
          const sectionCopy = (isEnglish ? SLOT_COPY.en : SLOT_COPY.zh)[section.slot_key]
          const results = searchState[section.slot_key]?.results || []
          const query = searchState[section.slot_key]?.query || ''
          return (
            <div key={section.slot_key} className="fudan-panel p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="section-kicker">{sectionCopy?.title || section.slot_key}</div>
                  <p className="mt-2 text-sm leading-7 text-slate-500">{sectionCopy?.desc}</p>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    run(`save-${section.slot_key}`, async () => {
                      const payload = await updateAdminContentSection(section.slot_key, { items: section.items }, accessToken)
                      setSections(normalizeSections(payload.sections))
                      setTrending(payload.trending)
                      setMessage(isEnglish ? `Saved ${sectionCopy?.title || section.slot_key}.` : `已保存${sectionCopy?.title || section.slot_key}。`)
                    })
                  }
                  className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-2 text-sm font-semibold text-fudan-blue"
                >
                  {busy === `save-${section.slot_key}` ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
                  {copy.save}
                </button>
              </div>

              <div className="mt-5 space-y-3">
                {section.items.length ? (
                  section.items.map((item, index) => (
                    <div key={candidateKey(item)} className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="font-serif text-xl font-bold text-fudan-blue">{item.title}</div>
                          {item.subtitle ? <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{item.subtitle}</div> : null}
                          {item.description ? <div className="mt-2 text-sm leading-7 text-slate-600">{item.description}</div> : null}
                        </div>
                        <div className="flex flex-col gap-2">
                          <button
                            type="button"
                            onClick={() => moveItem(section.slot_key, index, -1)}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500"
                          >
                            {copy.moveUp}
                          </button>
                          <button
                            type="button"
                            onClick={() => moveItem(section.slot_key, index, 1)}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500"
                          >
                            {copy.moveDown}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              updateSectionItems(section.slot_key, (items) =>
                                items.filter((candidate) => candidateKey(candidate) !== candidateKey(item)),
                              )
                            }
                            className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-600"
                          >
                            <Trash2 size={12} />
                            {copy.remove}
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">{copy.empty}</div>
                )}
              </div>

              <div className="mt-6 rounded-[1.2rem] border border-slate-200/70 bg-white p-4">
                <div className="flex flex-wrap gap-3">
                  <input
                    value={query}
                    onChange={(event) =>
                      setSearchState((current) => ({
                        ...current,
                        [section.slot_key]: {
                          ...(current[section.slot_key] || {}),
                          query: event.target.value,
                        },
                      }))
                    }
                    placeholder={copy.searchPlaceholder}
                    className="min-w-[220px] flex-1 rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => run(`search-${section.slot_key}`, async () => searchCandidates(section.slot_key))}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue"
                  >
                    {busy === `search-${section.slot_key}` ? <LoaderCircle size={15} className="animate-spin" /> : <Search size={15} />}
                    {copy.search}
                  </button>
                </div>

                <div className="mt-4">
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{copy.results}</div>
                  <div className="mt-3 space-y-3">
                    {results.length ? (
                      results.map((item) => {
                        const exists = section.items.some((candidate) => candidateKey(candidate) === candidateKey(item))
                        const disabled = exists || section.items.length >= section.max_items
                        return (
                          <div key={candidateKey(item)} className="flex items-start justify-between gap-4 rounded-[1rem] border border-slate-200 bg-slate-50 p-3">
                            <div>
                              <div className="font-semibold text-fudan-blue">{item.title}</div>
                              {item.subtitle ? <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{item.subtitle}</div> : null}
                              {item.description ? <div className="mt-2 text-sm leading-6 text-slate-600">{item.description}</div> : null}
                            </div>
                            <button
                              type="button"
                              disabled={disabled}
                              onClick={() => appendCandidate(section.slot_key, item)}
                              className="rounded-full border border-fudan-orange/20 bg-fudan-orange/10 px-4 py-2 text-sm font-semibold text-fudan-orange disabled:cursor-not-allowed disabled:opacity-40"
                            >
                              {copy.add}
                            </button>
                          </div>
                        )
                      })
                    ) : (
                      <div className="text-sm text-slate-400">{copy.none}</div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </section>

      <section className="mt-8 fudan-panel p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="section-kicker">{copy.trendingTitle}</div>
            <p className="mt-2 text-sm leading-7 text-slate-500">{copy.trendingDesc}</p>
          </div>
          <button
            type="button"
            onClick={() =>
              run('save-trending', async () => {
                const payload = await updateAdminTrendingConfig(trending, accessToken)
                setTrending(payload)
                setMessage(isEnglish ? 'Trending rules saved.' : '热门榜规则已保存。')
              })
            }
            className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-2 text-sm font-semibold text-fudan-blue"
          >
            {busy === 'save-trending' ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
            {copy.saveTrending}
          </button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-4">
          <label className="space-y-2 text-sm text-slate-600">
            <span className="block">{copy.defaultWindow}</span>
            <select
              value={trending.default_window}
              onChange={(event) => setTrending((current) => ({ ...current, default_window: event.target.value }))}
              className="w-full rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
            >
              {(trending.windows || ['day', 'week', 'month']).map((window) => (
                <option key={window} value={window}>
                  {window}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm text-slate-600">
            <span className="block">{copy.viewWeight}</span>
            <input
              type="number"
              step="0.1"
              min="0"
              value={trending.view_weight}
              onChange={(event) => setTrending((current) => ({ ...current, view_weight: Number(event.target.value) }))}
              className="w-full rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-600">
            <span className="block">{copy.likeWeight}</span>
            <input
              type="number"
              step="0.1"
              min="0"
              value={trending.like_weight}
              onChange={(event) => setTrending((current) => ({ ...current, like_weight: Number(event.target.value) }))}
              className="w-full rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-600">
            <span className="block">{copy.bookmarkWeight}</span>
            <input
              type="number"
              step="0.1"
              min="0"
              value={trending.bookmark_weight}
              onChange={(event) => setTrending((current) => ({ ...current, bookmark_weight: Number(event.target.value) }))}
              className="w-full rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
            />
          </label>
        </div>
      </section>
    </div>
  )
}

export default AdminContentOperationsPage
