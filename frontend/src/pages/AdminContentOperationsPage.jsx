import { LoaderCircle, RefreshCw, Save, Search, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  fetchAdminColumnArticles,
  fetchAdminContentCandidates,
  fetchAdminContentOperations,
  fetchAdminTopicArticles,
  updateAdminColumnArticles,
  updateAdminContentSection,
  updateAdminTopicArticles,
  updateAdminTrendingConfig,
} from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const SLOT_ORDER = ['hero', 'editors_picks', 'quick_tags', 'topic_starters', 'column_navigation', 'topic_square']
const COLLECTION_INITIAL_VISIBLE_COUNT = 6
const COLLECTION_VISIBLE_STEP = 6

const SLOT_COPY = {
  zh: {
    hero: { title: '头条文章', desc: '首页主视觉文章，只保留 1 篇。' },
    editors_picks: { title: '编辑推荐', desc: '首页右上推荐文章，按顺序展示。' },
    quick_tags: { title: '快速入口标签', desc: '首页首屏快速入口标签。' },
    topic_starters: { title: '专题起读', desc: '首页首屏优先引导进入的专题。' },
    column_navigation: { title: '板块导航', desc: '首页板块区显示哪些板块，以及顺序。' },
    topic_square: { title: '专题广场', desc: '首页专题广场显示哪些专题，以及顺序。' },
  },
  en: {
    hero: { title: 'Lead story', desc: 'Homepage hero article. Keep one item only.' },
    editors_picks: { title: "Editor's picks", desc: 'The homepage recommendation list shown in order.' },
    quick_tags: { title: 'Quick tags', desc: 'Fast-entry tags shown in the first screen.' },
    topic_starters: { title: 'Topic starters', desc: 'Topics highlighted in the first screen.' },
    column_navigation: { title: 'Section navigation', desc: 'Which sections appear on the homepage and in what order.' },
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
  const [contentLanguage, setContentLanguage] = useState(isEnglish ? 'en' : 'zh')
  const [sections, setSections] = useState({})
  const [trending, setTrending] = useState({
    default_window: 'week',
    windows: ['day', 'week', 'month'],
    view_weight: 1,
    like_weight: 4,
    bookmark_weight: 6,
  })
  const [searchState, setSearchState] = useState({})
  const [columnOptions, setColumnOptions] = useState([])
  const [selectedColumnSlug, setSelectedColumnSlug] = useState('')
  const [columnArticleCollection, setColumnArticleCollection] = useState({ target: null, items: [] })
  const [columnArticleSearch, setColumnArticleSearch] = useState({ query: '', results: [] })
  const [topicOptions, setTopicOptions] = useState([])
  const [topicOptionSearch, setTopicOptionSearch] = useState('')
  const [selectedTopicSlug, setSelectedTopicSlug] = useState('')
  const [topicArticleCollection, setTopicArticleCollection] = useState({ target: null, items: [] })
  const [topicArticleSearch, setTopicArticleSearch] = useState({ query: '', results: [] })
  const [collectionVisibleCounts, setCollectionVisibleCounts] = useState({
    column: COLLECTION_INITIAL_VISIBLE_COUNT,
    topic: COLLECTION_INITIAL_VISIBLE_COUNT,
  })
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
        contentLanguage: 'Homepage language',
        languageZh: 'Chinese page',
        languageEn: 'English page',
        currentScope: 'You are editing the homepage distribution for this language only.',
        trendingScope: 'Trending rules remain global and are shared by Chinese and English homepages.',
        sectionArticlesTitle: 'Section articles',
        sectionArticlesDesc: 'Manage which articles appear inside each of the six public sections and their order.',
        topicArticlesTitle: 'Topic page articles',
        topicArticlesDesc: 'Choose a published topic, then manage the articles shown on that topic page.',
        chooseSection: 'Choose section',
        chooseTopic: 'Choose topic',
        searchTopics: 'Search topics',
        articleSearchPlaceholder: 'Search articles to add',
        currentArticles: 'Current articles',
        saveArticles: 'Save articles',
        showMoreArticles: 'Show more',
        collapseArticles: 'Collapse',
        showingArticles: 'Showing',
        ofArticles: 'of',
        articlesUnit: 'articles',
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
        contentLanguage: '编排页面',
        languageZh: '中文首页',
        languageEn: '英文首页',
        currentScope: '当前仅编辑所选语言首页的内容分布。',
        trendingScope: '热门榜规则仍为全局共享，中文与英文首页共用一套。',
        sectionArticlesTitle: '板块文章编排',
        sectionArticlesDesc: '管理六大对外板块里的文章进出和展示顺序。',
        topicArticlesTitle: '专题页文章编排',
        topicArticlesDesc: '选择已发布专题后，管理该专题页展示的文章和顺序。',
        chooseSection: '选择板块',
        chooseTopic: '选择专题',
        searchTopics: '搜索专题',
        articleSearchPlaceholder: '搜索要加入的文章',
        currentArticles: '当前文章',
        saveArticles: '保存文章列表',
        showMoreArticles: '展开更多',
        collapseArticles: '收起',
        showingArticles: '已显示',
        ofArticles: '/',
        articlesUnit: '篇',
      }

  const orderedSections = useMemo(() => SLOT_ORDER.map((slotKey) => sections[slotKey]).filter(Boolean), [sections])

  useEffect(() => {
    fetchAdminContentOperations(accessToken, contentLanguage)
      .then((payload) => {
        setSections(normalizeSections(payload.sections))
        setTrending(payload.trending)
      })
      .catch(() => setError(isEnglish ? 'Failed to load content operations.' : '内容运营后台加载失败。'))
  }, [accessToken, contentLanguage, isEnglish])

  useEffect(() => {
    setSearchState({})
    setColumnArticleSearch({ query: '', results: [] })
    setTopicArticleSearch({ query: '', results: [] })
    setCollectionVisibleCounts({
      column: COLLECTION_INITIAL_VISIBLE_COUNT,
      topic: COLLECTION_INITIAL_VISIBLE_COUNT,
    })
  }, [contentLanguage])

  useEffect(() => {
    let active = true
    fetchAdminContentCandidates('column', '', 12, accessToken, contentLanguage)
      .then((payload) => {
        if (!active) return
        setColumnOptions(payload)
        setSelectedColumnSlug((current) => {
          if (current && payload.some((item) => item.slug === current)) return current
          return payload[0]?.slug || ''
        })
      })
      .catch(() => setError(isEnglish ? 'Failed to load section options.' : '板块候选加载失败。'))

    fetchAdminContentCandidates('topic', '', 24, accessToken, contentLanguage)
      .then((payload) => {
        if (!active) return
        setTopicOptions(payload)
        setSelectedTopicSlug((current) => {
          if (current && payload.some((item) => item.slug === current)) return current
          return payload[0]?.slug || ''
        })
      })
      .catch(() => setError(isEnglish ? 'Failed to load topic options.' : '专题候选加载失败。'))

    return () => {
      active = false
    }
  }, [accessToken, contentLanguage, isEnglish])

  useEffect(() => {
    if (!selectedColumnSlug) {
      setColumnArticleCollection({ target: null, items: [] })
      return
    }
    setCollectionVisibleCounts((current) => ({ ...current, column: COLLECTION_INITIAL_VISIBLE_COUNT }))
    let active = true
    fetchAdminColumnArticles(selectedColumnSlug, accessToken, contentLanguage)
      .then((payload) => {
        if (active) setColumnArticleCollection(payload)
      })
      .catch(() => setError(isEnglish ? 'Failed to load section articles.' : '板块文章加载失败。'))
    return () => {
      active = false
    }
  }, [accessToken, contentLanguage, isEnglish, selectedColumnSlug])

  useEffect(() => {
    if (!selectedTopicSlug) {
      setTopicArticleCollection({ target: null, items: [] })
      return
    }
    setCollectionVisibleCounts((current) => ({ ...current, topic: COLLECTION_INITIAL_VISIBLE_COUNT }))
    let active = true
    fetchAdminTopicArticles(selectedTopicSlug, accessToken, contentLanguage)
      .then((payload) => {
        if (active) setTopicArticleCollection(payload)
      })
      .catch(() => setError(isEnglish ? 'Failed to load topic articles.' : '专题文章加载失败。'))
    return () => {
      active = false
    }
  }, [accessToken, contentLanguage, isEnglish, selectedTopicSlug])

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
    const results = await fetchAdminContentCandidates(section.entity_type, query, 12, accessToken, contentLanguage)
    setSearchState((current) => ({
      ...current,
      [slotKey]: {
        ...(current[slotKey] || {}),
        results,
      },
    }))
  }

  function updateCollectionItems(kind, updater) {
    const setCollection = kind === 'column' ? setColumnArticleCollection : setTopicArticleCollection
    setCollection((current) => ({
      ...current,
      items: updater(Array.isArray(current.items) ? current.items : []),
    }))
  }

  function moveCollectionItem(kind, index, direction) {
    updateCollectionItems(kind, (items) => {
      const next = [...items]
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= next.length) return next
      ;[next[index], next[targetIndex]] = [next[targetIndex], next[index]]
      return next
    })
  }

  function appendArticleCandidate(kind, candidate) {
    const currentCollection = kind === 'column' ? columnArticleCollection : topicArticleCollection
    const currentItems = Array.isArray(currentCollection.items) ? currentCollection.items : []
    const nextLength = currentItems.some((item) => candidateKey(item) === candidateKey(candidate)) ? currentItems.length : currentItems.length + 1
    updateCollectionItems(kind, (items) => {
      const exists = items.some((item) => candidateKey(item) === candidateKey(candidate))
      return exists ? items : [...items, candidate]
    })
    setCollectionVisibleCounts((current) => ({
      ...current,
      [kind]: Math.max(current[kind] || COLLECTION_INITIAL_VISIBLE_COUNT, nextLength),
    }))
  }

  async function searchCollectionArticles(kind) {
    const search = kind === 'column' ? columnArticleSearch : topicArticleSearch
    const setSearch = kind === 'column' ? setColumnArticleSearch : setTopicArticleSearch
    const results = await fetchAdminContentCandidates('article', search.query || '', 18, accessToken, contentLanguage)
    setSearch((current) => ({ ...current, results }))
  }

  async function searchTopicOptions() {
    const results = await fetchAdminContentCandidates('topic', topicOptionSearch, 24, accessToken, contentLanguage)
    setTopicOptions(results)
    if (results.length && !results.some((item) => item.slug === selectedTopicSlug)) {
      setSelectedTopicSlug(results[0].slug || '')
    }
  }

  async function saveColumnArticles() {
    if (!selectedColumnSlug) return
    const payload = await updateAdminColumnArticles(
      selectedColumnSlug,
      { items: columnArticleCollection.items || [] },
      accessToken,
      contentLanguage,
    )
    setColumnArticleCollection(payload)
    setMessage(isEnglish ? 'Section articles saved.' : '板块文章已保存。')
  }

  async function saveTopicArticles() {
    if (!selectedTopicSlug) return
    const payload = await updateAdminTopicArticles(
      selectedTopicSlug,
      { items: topicArticleCollection.items || [] },
      accessToken,
      contentLanguage,
    )
    setTopicArticleCollection(payload)
    setMessage(isEnglish ? 'Topic articles saved.' : '专题文章已保存。')
  }

  function renderArticleCollectionManager({
    kind,
    title,
    description,
    options,
    selectedSlug,
    onSelect,
    collection,
    articleSearch,
    setArticleSearch,
    onSave,
    optionLabel,
    topicSearch = false,
  }) {
    const items = Array.isArray(collection.items) ? collection.items : []
    const results = Array.isArray(articleSearch.results) ? articleSearch.results : []
    const visibleCount = Math.min(collectionVisibleCounts[kind] || COLLECTION_INITIAL_VISIBLE_COUNT, items.length)
    const visibleItems = items.slice(0, visibleCount)
    const hiddenCount = Math.max(items.length - visibleCount, 0)
    const nextExpandCount = Math.min(COLLECTION_VISIBLE_STEP, hiddenCount)
    return (
      <section className="fudan-panel p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="section-kicker">{title}</div>
            <p className="mt-2 text-sm leading-7 text-slate-500">{description}</p>
          </div>
          <button
            type="button"
            onClick={() => run(`save-${kind}-articles`, onSave)}
            className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-2 text-sm font-semibold text-fudan-blue"
          >
            {busy === `save-${kind}-articles` ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
            {copy.saveArticles}
          </button>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <label className="space-y-2 text-sm text-slate-600">
            <span className="block">{optionLabel}</span>
            <select
              value={selectedSlug}
              onChange={(event) => onSelect(event.target.value)}
              className="w-full rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 outline-none"
            >
              {options.map((item) => (
                <option key={candidateKey(item)} value={item.slug || ''}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          {topicSearch ? (
            <div className="flex items-end gap-2">
              <input
                value={topicOptionSearch}
                onChange={(event) => setTopicOptionSearch(event.target.value)}
                placeholder={copy.chooseTopic}
                className="min-w-[180px] rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <button
                type="button"
                onClick={() => run('search-topic-options', searchTopicOptions)}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue"
              >
                {busy === 'search-topic-options' ? <LoaderCircle size={15} className="animate-spin" /> : <Search size={15} />}
                {copy.searchTopics}
              </button>
            </div>
          ) : null}
        </div>

        <div className="mt-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{copy.currentArticles}</div>
            {items.length ? (
              <div className="text-xs font-semibold text-slate-400">
                {isEnglish
                  ? `${copy.showingArticles} ${visibleCount} ${copy.ofArticles} ${items.length} ${copy.articlesUnit}`
                  : `${copy.showingArticles} ${visibleCount} ${copy.ofArticles} ${items.length} ${copy.articlesUnit}`}
              </div>
            ) : null}
          </div>
          <div className="mt-3 space-y-3">
            {items.length ? (
              visibleItems.map((item, index) => (
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
                        onClick={() => moveCollectionItem(kind, index, -1)}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500"
                      >
                        {copy.moveUp}
                      </button>
                      <button
                        type="button"
                        onClick={() => moveCollectionItem(kind, index, 1)}
                        className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-500"
                      >
                        {copy.moveDown}
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          updateCollectionItems(kind, (currentItems) =>
                            currentItems.filter((candidate) => candidateKey(candidate) !== candidateKey(item)),
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
          {items.length > COLLECTION_INITIAL_VISIBLE_COUNT ? (
            <div className="mt-4 flex flex-wrap gap-3">
              {hiddenCount ? (
                <button
                  type="button"
                  onClick={() =>
                    setCollectionVisibleCounts((current) => ({
                      ...current,
                      [kind]: Math.min((current[kind] || COLLECTION_INITIAL_VISIBLE_COUNT) + COLLECTION_VISIBLE_STEP, items.length),
                    }))
                  }
                  className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-fudan-blue"
                >
                  {copy.showMoreArticles}
                  {isEnglish ? ` (${nextExpandCount})` : `（再显示 ${nextExpandCount} 篇）`}
                </button>
              ) : null}
              {visibleCount > COLLECTION_INITIAL_VISIBLE_COUNT ? (
                <button
                  type="button"
                  onClick={() =>
                    setCollectionVisibleCounts((current) => ({
                      ...current,
                      [kind]: COLLECTION_INITIAL_VISIBLE_COUNT,
                    }))
                  }
                  className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-500"
                >
                  {copy.collapseArticles}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="mt-6 rounded-[1.2rem] border border-slate-200/70 bg-white p-4">
          <div className="flex flex-wrap gap-3">
            <input
              value={articleSearch.query}
              onChange={(event) => setArticleSearch((current) => ({ ...current, query: event.target.value }))}
              placeholder={copy.articleSearchPlaceholder}
              className="min-w-[220px] flex-1 rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
            />
            <button
              type="button"
              onClick={() => run(`search-${kind}-articles`, async () => searchCollectionArticles(kind))}
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue"
            >
              {busy === `search-${kind}-articles` ? <LoaderCircle size={15} className="animate-spin" /> : <Search size={15} />}
              {copy.search}
            </button>
          </div>

          <div className="mt-4">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{copy.results}</div>
            <div className="mt-3 space-y-3">
              {results.length ? (
                results.map((item) => {
                  const exists = items.some((candidate) => candidateKey(candidate) === candidateKey(item))
                  return (
                    <div key={candidateKey(item)} className="flex items-start justify-between gap-4 rounded-[1rem] border border-slate-200 bg-slate-50 p-3">
                      <div>
                        <div className="font-semibold text-fudan-blue">{item.title}</div>
                        {item.subtitle ? <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{item.subtitle}</div> : null}
                        {item.description ? <div className="mt-2 text-sm leading-6 text-slate-600">{item.description}</div> : null}
                      </div>
                      <button
                        type="button"
                        disabled={exists}
                        onClick={() => appendArticleCandidate(kind, item)}
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
      </section>
    )
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
                const payload = await fetchAdminContentOperations(accessToken, contentLanguage)
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
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <span className="text-sm font-semibold text-slate-500">{copy.contentLanguage}</span>
          <div className="inline-flex rounded-full border border-slate-200 bg-slate-50 p-1">
            {[
              { value: 'zh', label: copy.languageZh },
              { value: 'en', label: copy.languageEn },
            ].map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  setContentLanguage(option.value)
                  setMessage('')
                  setError('')
                }}
                className={[
                  'rounded-full px-4 py-2 text-sm font-semibold transition',
                  contentLanguage === option.value ? 'bg-fudan-blue text-white shadow-sm' : 'text-slate-500 hover:text-fudan-blue',
                ].join(' ')}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="text-sm text-slate-500">{copy.currentScope}</div>
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
                      const payload = await updateAdminContentSection(section.slot_key, { items: section.items }, accessToken, contentLanguage)
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

      <section className="mt-8 grid gap-6 xl:grid-cols-2">
        {renderArticleCollectionManager({
          kind: 'column',
          title: copy.sectionArticlesTitle,
          description: copy.sectionArticlesDesc,
          options: columnOptions,
          selectedSlug: selectedColumnSlug,
          onSelect: setSelectedColumnSlug,
          collection: columnArticleCollection,
          articleSearch: columnArticleSearch,
          setArticleSearch: setColumnArticleSearch,
          onSave: saveColumnArticles,
          optionLabel: copy.chooseSection,
        })}
        {renderArticleCollectionManager({
          kind: 'topic',
          title: copy.topicArticlesTitle,
          description: copy.topicArticlesDesc,
          options: topicOptions,
          selectedSlug: selectedTopicSlug,
          onSelect: setSelectedTopicSlug,
          collection: topicArticleCollection,
          articleSearch: topicArticleSearch,
          setArticleSearch: setTopicArticleSearch,
          onSave: saveTopicArticles,
          optionLabel: copy.chooseTopic,
          topicSearch: true,
        })}
      </section>

      <section className="mt-8 fudan-panel p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="section-kicker">{copy.trendingTitle}</div>
            <p className="mt-2 text-sm leading-7 text-slate-500">{copy.trendingDesc}</p>
            <p className="mt-2 text-sm leading-7 text-slate-400">{copy.trendingScope}</p>
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
