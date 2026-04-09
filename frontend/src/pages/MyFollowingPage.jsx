import { Sparkles, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchFollows, fetchWatchlist, toggleFollow } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

const WATCHLIST_LIMIT = 24

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function buildFollowKey(item) {
  return `${item.entity_type}:${item.entity_slug}`
}

function formatFollowType(entityType, isEnglish) {
  if (entityType === 'tag') return byLanguage(isEnglish, '标签', 'Tag')
  if (entityType === 'topic') return byLanguage(isEnglish, '专题', 'Topic')
  return byLanguage(isEnglish, '栏目', 'Column')
}

function MyFollowingPage() {
  const { isAuthenticated, accessToken, openAuthDialog } = useAuth()
  const { isEnglish } = useLanguage()
  const [follows, setFollows] = useState([])
  const [selectedFollowKey, setSelectedFollowKey] = useState('')
  const [articles, setArticles] = useState([])
  const [articleTotal, setArticleTotal] = useState(0)
  const [loadingFollows, setLoadingFollows] = useState(false)
  const [loadingArticles, setLoadingArticles] = useState(false)
  const [error, setError] = useState('')

  const selectedFollow = follows.find((item) => buildFollowKey(item) === selectedFollowKey) || null

  useEffect(() => {
    if (!isAuthenticated) {
      setFollows([])
      setSelectedFollowKey('')
      setArticles([])
      setArticleTotal(0)
      setLoadingFollows(false)
      setLoadingArticles(false)
      return
    }

    let mounted = true
    setLoadingFollows(true)
    setError('')

    fetchFollows(accessToken)
      .then((payload) => {
        if (!mounted) return
        setFollows(payload.items || [])
      })
      .catch(() => {
        if (!mounted) return
        setError(byLanguage(isEnglish, '关注页加载失败', 'Failed to load your follows.'))
        setFollows([])
      })
      .finally(() => {
        if (mounted) setLoadingFollows(false)
      })

    return () => {
      mounted = false
    }
  }, [accessToken, isAuthenticated, isEnglish])

  useEffect(() => {
    if (!follows.length) {
      if (selectedFollowKey) setSelectedFollowKey('')
      return
    }

    if (!follows.some((item) => buildFollowKey(item) === selectedFollowKey)) {
      setSelectedFollowKey(buildFollowKey(follows[0]))
    }
  }, [follows, selectedFollowKey])

  useEffect(() => {
    if (!isAuthenticated || !selectedFollow) {
      setArticles([])
      setArticleTotal(0)
      setLoadingArticles(false)
      return
    }

    let mounted = true
    setLoadingArticles(true)
    setError('')

    fetchWatchlist(accessToken, WATCHLIST_LIMIT, {
      entityType: selectedFollow.entity_type,
      entitySlug: selectedFollow.entity_slug,
    })
      .then((payload) => {
        if (!mounted) return
        setArticles(payload.items || [])
        setArticleTotal(payload.total || 0)
      })
      .catch(() => {
        if (!mounted) return
        setError(byLanguage(isEnglish, '关注文章加载失败', 'Failed to load followed articles.'))
        setArticles([])
        setArticleTotal(0)
      })
      .finally(() => {
        if (mounted) setLoadingArticles(false)
      })

    return () => {
      mounted = false
    }
  }, [accessToken, isAuthenticated, isEnglish, selectedFollow])

  const handleUnfollow = async (item) => {
    try {
      await toggleFollow(
        {
          entity_type: item.entity_type,
          entity_slug: item.entity_slug,
          active: false,
        },
        accessToken,
      )

      const removedKey = buildFollowKey(item)
      const nextFollows = follows.filter((follow) => buildFollowKey(follow) !== removedKey)
      setFollows(nextFollows)
      if (selectedFollowKey === removedKey) {
        setSelectedFollowKey(nextFollows[0] ? buildFollowKey(nextFollows[0]) : '')
      }
    } catch {
      setError(byLanguage(isEnglish, '取消关注失败', 'Failed to remove follow.'))
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="page-shell py-16">
        <div className="fudan-panel p-8 text-center">
          <div className="section-kicker">Following</div>
          <h1 className="section-title">{byLanguage(isEnglish, '登录后查看你的关注', 'Sign in to view your follows')}</h1>
          <p className="mt-4 text-base leading-8 text-slate-600">
            {byLanguage(isEnglish, '关注标签、专题和栏目后，这里会聚合它们的最新内容。', 'Follow tags, topics, and columns, then review them here.')}
          </p>
          <button
            type="button"
            onClick={openAuthDialog}
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
          >
            <Sparkles size={16} />
            {byLanguage(isEnglish, '登录并开始关注', 'Sign in and start following')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel p-8 md:p-10">
        <div className="section-kicker">Personal Watchlist</div>
        <h1 className="section-title">{byLanguage(isEnglish, '我的关注', 'My follows')}</h1>
        <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
          {byLanguage(
            isEnglish,
            '左侧选择你要继续追踪的标签、专题或栏目，右侧只显示该关注对象对应的文章。删除操作独立放在卡片右上角。',
            'Choose a followed tag, topic, or column on the left, and the right side will only show articles for that selection.',
          )}
        </p>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      <section className="mt-8 grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <div className="fudan-panel p-6">
          <div className="section-kicker">{byLanguage(isEnglish, '已关注对象', 'Followed items')}</div>
          <div className="mt-4 space-y-3">
            {loadingFollows ? (
              <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                {byLanguage(isEnglish, '正在加载关注列表...', 'Loading follows...')}
              </div>
            ) : follows.length ? (
              follows.map((item) => {
                const followKey = buildFollowKey(item)
                const isSelected = selectedFollowKey === followKey

                return (
                  <div key={followKey} className="relative">
                    <button
                      type="button"
                      onClick={() => setSelectedFollowKey(followKey)}
                      className={[
                        'w-full rounded-[1.2rem] border px-4 py-4 text-left transition',
                        isSelected
                          ? 'border-fudan-blue/35 bg-fudan-blue/10 shadow-[0_14px_40px_rgba(13,7,131,0.10)]'
                          : 'border-slate-200 bg-white hover:border-fudan-blue/20 hover:bg-slate-50',
                      ].join(' ')}
                    >
                      <div className="pr-10">
                        <div className={`text-[11px] font-semibold uppercase tracking-[0.22em] ${isSelected ? 'text-fudan-blue' : 'text-slate-400'}`}>
                          {formatFollowType(item.entity_type, isEnglish)}
                        </div>
                        <div className={`mt-2 text-sm font-semibold ${isSelected ? 'text-fudan-blue' : 'text-slate-700'}`}>{item.entity_label}</div>
                        <div className="mt-2 text-xs leading-6 text-slate-500">
                          {isSelected
                            ? byLanguage(isEnglish, '当前正在查看这个关注对象的文章。', 'Currently showing articles for this follow.')
                            : byLanguage(isEnglish, '点击后在右侧查看对应文章。', 'Select to view matching articles on the right.')}
                        </div>
                      </div>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleUnfollow(item)}
                      className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-400 shadow-sm transition hover:border-red-200 hover:text-red-500"
                      aria-label={byLanguage(isEnglish, `取消关注 ${item.entity_label}`, `Unfollow ${item.entity_label}`)}
                    >
                      <X size={14} />
                    </button>
                  </div>
                )
              })
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                {byLanguage(isEnglish, '你还没有关注任何标签、专题或栏目。', 'You are not following any tags, topics, or columns yet.')}
              </div>
            )}
          </div>
        </div>

        <div className="fudan-panel p-6">
          {selectedFollow ? (
            <>
              <div className="flex flex-col gap-4 border-b border-slate-200 pb-5 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="section-kicker">{byLanguage(isEnglish, '当前关注内容', 'Current selection')}</div>
                  <h2 className="font-serif text-2xl font-black text-fudan-blue">{selectedFollow.entity_label}</h2>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
                    {byLanguage(
                      isEnglish,
                      `右侧仅显示与“${selectedFollow.entity_label}”相关的最新文章。`,
                      `Only articles related to "${selectedFollow.entity_label}" are shown here.`,
                    )}
                  </p>
                </div>
                <div className="inline-flex items-center rounded-full border border-fudan-blue/15 bg-fudan-blue/8 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-fudan-blue">
                  {formatFollowType(selectedFollow.entity_type, isEnglish)} · {articleTotal} {byLanguage(isEnglish, '篇文章', 'articles')}
                </div>
              </div>

              {loadingArticles ? (
                <div className="mt-6 rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {byLanguage(isEnglish, '正在加载相关文章...', 'Loading articles...')}
                </div>
              ) : articles.length ? (
                <div className="mt-6 grid gap-6 md:grid-cols-2">
                  {articles.map((item) => (
                    <ArticleCard key={item.id} article={item} />
                  ))}
                </div>
              ) : (
                <div className="mt-6 rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {byLanguage(isEnglish, '当前关注对象下还没有可显示的文章。', 'No articles are available for this follow yet.')}
                </div>
              )}
            </>
          ) : (
            <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
              {byLanguage(isEnglish, '先在左侧选择一个关注对象，右侧再显示对应文章。', 'Select a followed item on the left to view matching articles here.')}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

export default MyFollowingPage
