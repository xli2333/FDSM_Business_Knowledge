import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchTopics } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { formatTopicType } from '../utils/formatters.js'

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function TopicsPage() {
  const { isEnglish } = useLanguage()
  const { accessToken, isAuthenticated, isPaidMember, isAdmin, openAuthDialog } = useAuth()
  const [topics, setTopics] = useState([])
  const [loading, setLoading] = useState(true)
  const [errorStatus, setErrorStatus] = useState(0)

  useEffect(() => {
    let mounted = true
    fetchTopics(accessToken)
      .then((payload) => {
        if (!mounted) return
        setTopics(payload)
        setErrorStatus(0)
      })
      .catch((error) => {
        if (!mounted) return
        setTopics([])
        setErrorStatus(error?.status || 500)
      })
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [accessToken, isAdmin, isAuthenticated, isPaidMember])

  if (loading) {
    return <div className="page-shell py-16 text-sm text-slate-500">{byLanguage(isEnglish, '专题加载中...', 'Loading topics...')}</div>
  }

  if (errorStatus === 401 || errorStatus === 403) {
    const requiresLogin = errorStatus === 401 && !isAuthenticated
    return (
      <div className="page-shell py-12">
        <section className="fudan-panel p-8">
          <div className="section-kicker">{byLanguage(isEnglish, '专题权限', 'Topic access')}</div>
          <h1 className="section-title">
            {requiresLogin
              ? byLanguage(isEnglish, '登录后可继续查看专题权限', 'Sign in to continue')
              : byLanguage(isEnglish, '专题阅读仅对付费会员开放', 'Topic reading is reserved for paid members')}
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
            {requiresLogin
              ? byLanguage(isEnglish, '专题页已收紧到付费会员与管理员。登录后系统会按你的当前身份判断是否可读。', 'Topics are now limited to paid members and admins. Sign in so the product can check your access.')
              : byLanguage(isEnglish, '当前账号还没有专题阅读权限。升级为付费会员后可进入专题广场和专题详情页。', 'This account does not have topic-reading access yet. Upgrade to a paid membership to open the topic square and topic detail pages.')}
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

  return (
    <div className="page-shell py-12">
      <div className="mb-8">
        <div className="section-kicker">{isEnglish ? 'Topics' : '专题广场'}</div>
        <h1 className="section-title">{isEnglish ? 'Enter structured business reading through topics' : '按议题进入结构化商业阅读'}</h1>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {topics.map((topic) => (
          <Link key={topic.slug} to={`/topic/${topic.slug}`} className="fudan-card p-6">
            <div className="text-xs uppercase tracking-[0.24em] text-fudan-orange">{formatTopicType(topic.type, isEnglish)}</div>
            <h2 className="mt-3 font-serif text-2xl font-black text-fudan-blue">{topic.title}</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">{topic.description}</p>
            <div className="mt-5 flex flex-wrap gap-2">
              {(topic.tags || []).slice(0, 3).map((tag) => (
                <TagBadge key={`${topic.slug}-${tag.slug}`} tag={tag} />
              ))}
            </div>
            <div className="mt-6 text-xs uppercase tracking-[0.24em] text-slate-400">
              {topic.article_count} {isEnglish ? 'articles' : '篇文章'}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

export default TopicsPage
