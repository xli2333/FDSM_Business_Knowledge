import { BellPlus, BellRing } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchFollows, fetchTopic, toggleFollow } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

const PAGE_SIZE = 12

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function TopicPage() {
  const { slug } = useParams()
  const { isEnglish } = useLanguage()
  const { isAuthenticated, isPaidMember, isAdmin, accessToken, openAuthDialog } = useAuth()
  const [topic, setTopic] = useState(null)
  const [loading, setLoading] = useState(true)
  const [errorStatus, setErrorStatus] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [isFollowing, setIsFollowing] = useState(false)

  useEffect(() => {
    if (!slug) return
    let mounted = true
    fetchTopic(slug, 1, PAGE_SIZE, accessToken)
      .then((payload) => {
        if (!mounted) return
        setTopic(payload)
        setErrorStatus(0)
      })
      .catch((error) => {
        if (!mounted) return
        setErrorStatus(error?.status || 500)
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [accessToken, isAdmin, isAuthenticated, isPaidMember, slug])

  useEffect(() => {
    if (!slug || !isAuthenticated) {
      setIsFollowing(false)
      return
    }
    fetchFollows(accessToken).then((payload) => {
      setIsFollowing((payload.items || []).some((item) => item.entity_type === 'topic' && item.entity_slug === slug))
    })
  }, [accessToken, isAuthenticated, slug])

  const handleLoadMore = async () => {
    if (!slug || !topic) return
      setLoadingMore(true)
    try {
      const nextPage = topic.page + 1
      const payload = await fetchTopic(slug, nextPage, PAGE_SIZE, accessToken)
      setTopic((current) => ({
        ...payload,
        articles: [...(current?.articles || []), ...payload.articles],
      }))
    } finally {
      setLoadingMore(false)
    }
  }

  const handleFollow = async () => {
    if (!slug) return
    if (!isAuthenticated) {
      openAuthDialog()
      return
    }
    await toggleFollow(
      {
        entity_type: 'topic',
        entity_slug: slug,
        active: !isFollowing,
      },
      accessToken,
    )
    setIsFollowing((current) => !current)
  }

  if (loading || (topic && topic.slug !== slug)) {
    return <div className="page-shell py-16 text-sm text-slate-500">{byLanguage(isEnglish, '专题加载中...', 'Loading topic...')}</div>
  }

  if (errorStatus === 401 || errorStatus === 403) {
    const requiresLogin = errorStatus === 401 && !isAuthenticated
    return (
      <div className="page-shell py-12">
        <section className="fudan-panel p-8">
          <div className="section-kicker">{byLanguage(isEnglish, '专题权限', 'Topic access')}</div>
          <h1 className="section-title">
            {requiresLogin
              ? byLanguage(isEnglish, '登录后可继续查看专题', 'Sign in to continue')
              : byLanguage(isEnglish, '专题阅读仅对付费会员开放', 'Topic reading is reserved for paid members')}
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
            {requiresLogin
              ? byLanguage(isEnglish, '专题详情页已收紧到付费会员与管理员。登录后系统会自动判断你的阅读权限。', 'Topic detail pages now require paid-member or admin access. Sign in so the product can evaluate your access.')
              : byLanguage(isEnglish, '当前账号还没有专题阅读权限。升级为付费会员后即可查看专题详情、时间线和 AI 洞察。', 'This account does not have topic-reading access yet. Upgrade to a paid membership to unlock topic details, timelines, and AI insights.')}
          </p>
          <div className="mt-6">
            {requiresLogin ? (
              <button
                type="button"
                onClick={openAuthDialog}
                className="inline-flex items-center rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
              >
                {byLanguage(isEnglish, '立即登录', 'Sign in now')}
              </button>
            ) : (
              <Link
                to="/membership"
                className="inline-flex items-center rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
              >
                {byLanguage(isEnglish, '升级到付费会员', 'Upgrade to paid membership')}
              </Link>
            )}
          </div>
        </section>
      </div>
    )
  }

  if (!topic) {
    return <div className="page-shell py-16 text-sm text-slate-500">{byLanguage(isEnglish, '专题加载失败。', 'Failed to load the topic.')}</div>
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="bg-[linear-gradient(135deg,rgba(13,7,131,0.96),rgba(10,5,96,0.8)_60%,rgba(234,107,0,0.55))] px-8 py-12 text-white md:px-10">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="section-kicker !text-white/70">专题阅读</div>
              <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{topic.title}</h1>
              <p className="mt-5 max-w-4xl text-base leading-8 text-white/82">{topic.description}</p>
              <div className="mt-6 flex flex-wrap gap-2">
                {(topic.tags || []).map((tag) => (
                  <TagBadge key={tag.slug} tag={tag} variant="inverse" />
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={handleFollow}
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/15"
            >
              {isFollowing ? <BellRing size={16} /> : <BellPlus size={16} />}
              {isFollowing ? '已关注专题' : '关注专题'}
            </button>
          </div>
        </div>

        <div className="grid gap-8 p-8 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div>
            <div className="section-kicker">相关文章</div>
            <div className="mt-6 grid gap-6 md:grid-cols-2">
              {(topic.articles || []).map((article) => (
                <ArticleCard key={article.id} article={article} />
              ))}
            </div>
            {topic.articles.length < topic.total ? (
              <div className="mt-8 flex justify-center">
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:border-fudan-blue/30 disabled:cursor-not-allowed disabled:text-slate-400"
                >
                  {loadingMore ? '加载中...' : '继续加载'}
                </button>
              </div>
            ) : null}
          </div>

          <aside className="space-y-6">
            <section className="rounded-[1.6rem] border border-slate-200/70 bg-slate-50 p-6">
              <div className="section-kicker">时间线</div>
              <div className="mt-4 space-y-4">
                {(topic.timeline || []).map((item) => (
                  <Link key={`${item.article_id}-${item.date}`} to={`/article/${item.article_id}`} className="block border-l-2 border-fudan-orange pl-4">
                    <div className="text-xs uppercase tracking-[0.22em] text-slate-400">{item.date}</div>
                    <div className="mt-1 font-serif text-lg font-bold text-fudan-blue">{item.title}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">{item.excerpt}</div>
                  </Link>
                ))}
              </div>
            </section>

            <section className="rounded-[1.6rem] border border-slate-200/70 bg-white p-6">
              <div className="section-kicker">AI 洞察</div>
              <ul className="mt-4 space-y-3 text-sm leading-7 text-slate-600">
                {(topic.insights || []).map((insight) => (
                  <li key={insight}>{insight}</li>
                ))}
              </ul>
            </section>
          </aside>
        </div>
      </section>
    </div>
  )
}

export default TopicPage
