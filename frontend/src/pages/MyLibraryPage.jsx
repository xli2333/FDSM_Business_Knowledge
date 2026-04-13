import { Bookmark, Eye, Heart, Lock } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.js'
import { fetchMyDashboard, fetchMyLibrary } from '../api/index.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { getRoleExperience, resolveRoleTier } from '../lib/roleExperience.js'

const ACTION_CLASSES = {
  primary: 'border border-fudan-blue/15 bg-fudan-blue text-white hover:bg-fudan-dark',
  secondary: 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15',
  plain: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
}

function LibrarySection({ title, icon, items, emptyText }) {
  return (
    <section className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">{icon}</div>
        <h2 className="font-serif text-3xl font-black text-fudan-blue">{title}</h2>
      </div>
      {items.length === 0 ? (
        <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white p-6 text-sm leading-7 text-slate-500">
          {emptyText}
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {items.map((article) => (
            <ArticleCard key={`${title}-${article.id}`} article={article} />
          ))}
        </div>
      )}
    </section>
  )
}

function MyLibraryPage() {
  const { accessToken, isAuthenticated, authEnabled, membership, businessProfile } = useAuth()
  const { isEnglish } = useLanguage()
  const [data, setData] = useState({ bookmarks: [], likes: [], recent_views: [] })
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')

  const roleTier = resolveRoleTier({ membership, isAuthenticated })
  const roleExperience = useMemo(() => getRoleExperience(roleTier, isEnglish), [isEnglish, roleTier])

  useEffect(() => {
    if (!isAuthenticated) {
      fetchMyDashboard(accessToken).then(setDashboard).catch(() => {})
      return
    }
    Promise.all([fetchMyDashboard(accessToken), fetchMyLibrary(accessToken, 12)])
      .then(([dashboardPayload, libraryPayload]) => {
        setDashboard(dashboardPayload)
        setData(libraryPayload)
      })
      .catch(() => setError(isEnglish ? 'Failed to load your library.' : '个人资料库加载失败。'))
  }, [accessToken, isAuthenticated, isEnglish])

  const assetCards = [
    {
      label: isEnglish ? 'Bookmarks' : '收藏',
      value: dashboard?.asset_summary?.bookmark_count ?? 0,
      detail: isEnglish ? 'Long-term reading shelf' : '长期阅读清单',
    },
    {
      label: isEnglish ? 'Likes' : '点赞',
      value: dashboard?.asset_summary?.like_count ?? 0,
      detail: isEnglish ? 'Preference signals' : '阅读偏好信号',
    },
    {
      label: isEnglish ? 'History' : '历史',
      value: dashboard?.asset_summary?.recent_view_count ?? 0,
      detail: isEnglish ? 'Recent reading trail' : '最近阅读轨迹',
    },
    {
      label: isEnglish ? 'Following' : '关注',
      value: dashboard?.asset_summary?.follow_count ?? 0,
      detail: isEnglish ? 'Tracked tags and topics' : '关注的标签与专题',
    },
  ]

  if (!isAuthenticated) {
    return (
      <div className="page-shell py-12">
        <section className="fudan-panel overflow-hidden">
          <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
            <div>
              <div className="section-kicker !text-white/72">{roleExperience.heroKicker}</div>
              <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{roleExperience.heroTitle}</h1>
              <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{roleExperience.heroBody}</p>
              <Link
                to="/login?redirect=%2Fme"
                className="mt-8 inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
              >
                <Lock size={16} />
                {authEnabled ? (isEnglish ? 'Sign in to open my library' : '登录后进入我的资料库') : isEnglish ? 'Sign-in unavailable' : '登录暂不可用'}
              </Link>
            </div>

            <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
              {roleExperience.statCards.map((item) => (
                <div key={`guest-${item.label}`} className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
                  <div className="text-xs uppercase tracking-[0.24em] text-white/65">{item.label}</div>
                  <div className="mt-3 font-serif text-3xl font-black text-white">{item.value}</div>
                  <div className="mt-2 text-sm leading-7 text-white/76">{item.detail}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="mt-8 grid gap-4 md:grid-cols-3">
          {roleExperience.quickActions.map((item) => (
            <Link
              key={`guest-action-${item.path}`}
              to={item.path}
              className={`rounded-[1.35rem] px-6 py-6 text-left text-sm transition ${ACTION_CLASSES[item.tone] || ACTION_CLASSES.plain}`}
            >
              <div className="font-serif text-2xl font-black">{item.label}</div>
              <div className="mt-3 leading-7 opacity-90">{item.description}</div>
            </Link>
          ))}
        </section>
      </div>
    )
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.84)_58%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{roleExperience.heroKicker}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{roleExperience.heroTitle}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{roleExperience.heroBody}</p>
            <div className="mt-6 inline-flex rounded-full border border-white/12 bg-white/10 px-4 py-2 text-sm font-semibold text-white backdrop-blur">
              {businessProfile?.display_name || membership?.email || roleExperience.label} / {roleExperience.label}
            </div>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            {roleExperience.statCards.map((item) => (
              <div key={`${roleTier}-${item.label}`} className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
                <div className="text-xs uppercase tracking-[0.24em] text-white/65">{item.label}</div>
                <div className="mt-3 font-serif text-3xl font-black text-white">{item.value}</div>
                <div className="mt-2 text-sm leading-7 text-white/76">{item.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      <section className="mt-8 grid gap-6 lg:grid-cols-[1.02fr_0.98fr]">
        <div className="fudan-panel p-8">
          <div className="section-kicker">{isEnglish ? 'Your library' : '你的资料库'}</div>
          <h2 className="section-title">{roleExperience.heroTitle}</h2>
          <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">{roleExperience.heroBody}</p>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {roleExperience.quickActions.map((item) => (
              <Link
                key={`${roleTier}-quick-${item.path}`}
                to={item.path}
                className={`rounded-[1.3rem] px-5 py-5 text-left text-sm transition ${ACTION_CLASSES[item.tone] || ACTION_CLASSES.plain}`}
              >
                <div className="font-serif text-2xl font-black">{item.label}</div>
                <div className="mt-3 leading-7 opacity-90">{item.description}</div>
              </Link>
            ))}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-2">
          {assetCards.map((item) => (
            <div key={item.label} className="fudan-panel p-6">
              <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{item.label}</div>
              <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{item.value}</div>
              <div className="mt-2 text-sm leading-7 text-slate-600">{item.detail}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-10 space-y-12">
        <LibrarySection
          title={isEnglish ? 'My bookmarks' : '我的收藏'}
          icon={<Bookmark size={20} />}
          items={data.bookmarks || []}
          emptyText={
            isEnglish
              ? 'No bookmarked article yet. Save important stories here to build a durable reading shelf.'
              : '你还没有收藏文章。把重要内容加入收藏后，这里会逐步形成你的长期阅读清单。'
          }
        />
        <LibrarySection
          title={isEnglish ? 'My likes' : '我的点赞'}
          icon={<Heart size={20} />}
          items={data.likes || []}
          emptyText={
            isEnglish
              ? 'No liked article yet. Likes help the product understand what you care about.'
              : '你还没有点赞文章。点赞会帮助平台理解你更关心的话题。'
          }
        />
        <LibrarySection
          title={isEnglish ? 'Recent reading' : '最近阅读'}
          icon={<Eye size={20} />}
          items={data.recent_views || []}
          emptyText={
            isEnglish
              ? 'Your recent reading is still empty. Keep browsing and this area will become your reading trail.'
              : '最近阅读记录还是空的。继续浏览文章后，这里会逐步沉淀你的阅读轨迹。'
          }
        />
      </div>
    </div>
  )
}

export default MyLibraryPage
