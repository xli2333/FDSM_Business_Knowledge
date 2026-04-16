import { BookOpen, Bookmark, Eye, Heart, Lock, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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

const LIBRARY_TABS = ['all', 'bookmarks', 'likes', 'history']

function LibrarySection({ sectionKey, title, icon, items, emptyText, highlighted = false }) {
  return (
    <section id={`library-${sectionKey}`} className="space-y-5" data-library-section={sectionKey}>
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">{icon}</div>
        <h2 className="font-serif text-3xl font-black text-fudan-blue">{title}</h2>
      </div>
      {items.length === 0 ? (
        <div className="rounded-[1.5rem] border border-dashed border-slate-300 bg-white p-6 text-sm leading-7 text-slate-500">
          {emptyText}
        </div>
      ) : (
        <div
          className={[
            'grid gap-6 md:grid-cols-2 xl:grid-cols-3',
            highlighted ? 'rounded-[1.6rem] border border-fudan-blue/15 bg-fudan-blue/5 p-5' : '',
          ].join(' ')}
        >
          {items.map((article) => (
            <ArticleCard key={`${sectionKey}-${article.id}`} article={article} />
          ))}
        </div>
      )}
    </section>
  )
}

function KnowledgeWorkspaceCard({ canUseAiAssistant, dashboard, isEnglish }) {
  const themeCount = dashboard?.asset_summary?.knowledge_theme_count ?? 0
  const articleCount = dashboard?.asset_summary?.knowledge_article_count ?? 0

  return (
    <section className="fudan-panel overflow-hidden">
      <div className="grid gap-6 bg-[linear-gradient(135deg,rgba(13,7,131,0.96),rgba(10,5,96,0.88)_60%,rgba(234,107,0,0.2))] px-8 py-8 text-white lg:grid-cols-[1.05fr_0.95fr]">
        <div>
          <div className="section-kicker !text-white/70">{isEnglish ? 'My Knowledge Base' : '我的知识库'}</div>
          <h2 className="font-serif text-3xl font-black leading-tight text-white md:text-4xl">
            {canUseAiAssistant ? (isEnglish ? 'Build private themes from saved articles' : '把收藏文章沉淀成自己的主题知识库') : isEnglish ? 'Upgrade to unlock private theme knowledge bases' : '升级后开启自己的主题知识库'}
          </h2>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-white/84">
            {canUseAiAssistant
              ? isEnglish
                ? 'This workspace follows the stock-portfolio knowledge-base pattern, rebuilt in the Fudan visual language: create private themes, file articles into them, then ask AI only inside that curated set.'
                : '这个工作台沿用了 stock portfolio 的知识库模式，但整体收口成复旦知识库的配色和布局：先创建私有主题，再把文章归档进去，最后只在这组材料里继续问 AI。'
              : isEnglish
                ? 'Knowledge themes are reserved for paid members and admins. After upgrading, you can create your own named themes and keep AI working only inside those saved article sets.'
                : '主题知识库只向付费会员和管理员开放。升级后你可以创建自己的命名主题，并让 AI 只围绕这些已保存的文章继续工作。'}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              to={canUseAiAssistant ? '/me/knowledge' : '/membership'}
              className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:bg-slate-100"
            >
              <BookOpen size={16} />
              {canUseAiAssistant ? (isEnglish ? 'Open my knowledge base' : '打开我的知识库') : isEnglish ? 'Upgrade membership' : '升级会员'}
            </Link>
            {!canUseAiAssistant ? (
              <div className="inline-flex items-center gap-2 rounded-full border border-white/18 bg-white/10 px-4 py-3 text-sm font-semibold text-white">
                <Sparkles size={15} />
                {isEnglish ? 'Paid member only' : '仅限付费会员'}
              </div>
            ) : null}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
            <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Themes' : '主题数'}</div>
            <div className="mt-3 font-serif text-3xl font-black text-white">{themeCount}</div>
            <div className="mt-2 text-sm leading-7 text-white/76">{isEnglish ? 'Private themes under this account' : '当前账号下已经创建的私有主题'}</div>
          </div>
          <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
            <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Stored articles' : '收录文章'}</div>
            <div className="mt-3 font-serif text-3xl font-black text-white">{articleCount}</div>
            <div className="mt-2 text-sm leading-7 text-white/76">{isEnglish ? 'Articles already filed into your themes' : '已经被归档进主题知识库的文章数量'}</div>
          </div>
        </div>
      </div>
    </section>
  )
}

function MyLibraryPage() {
  const { accessToken, authEnabled, businessProfile, canUseAiAssistant, isAuthenticated, membership } = useAuth()
  const { isEnglish } = useLanguage()
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState({ bookmarks: [], likes: [], recent_views: [] })
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')

  const roleTier = resolveRoleTier({ membership, isAuthenticated })
  const roleExperience = useMemo(() => getRoleExperience(roleTier, isEnglish), [isEnglish, roleTier])

  const activeTab = LIBRARY_TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : 'all'

  useEffect(() => {
    if (!isAuthenticated) {
      fetchMyDashboard(accessToken).then(setDashboard).catch(() => {})
      return
    }
    Promise.all([fetchMyDashboard(accessToken), fetchMyLibrary(accessToken, 18)])
      .then(([dashboardPayload, libraryPayload]) => {
        setDashboard(dashboardPayload)
        setData(libraryPayload)
      })
      .catch(() => setError(isEnglish ? 'Failed to load your library.' : '个人资料库加载失败。'))
  }, [accessToken, isAuthenticated, isEnglish])

  useEffect(() => {
    if (activeTab === 'all') return
    const timer = window.setTimeout(() => {
      const target = document.querySelector(`[data-library-section="${activeTab}"]`)
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 120)
    return () => window.clearTimeout(timer)
  }, [activeTab])

  const setActiveTab = (nextTab) => {
    const nextParams = new URLSearchParams(searchParams)
    if (nextTab === 'all') {
      nextParams.delete('tab')
    } else {
      nextParams.set('tab', nextTab)
    }
    setSearchParams(nextParams, { replace: true })
  }

  const tabCopy = {
    all: isEnglish ? 'All flows' : '全部资产流',
    bookmarks: isEnglish ? 'Bookmarks' : '收藏',
    likes: isEnglish ? 'Likes' : '点赞',
    history: isEnglish ? 'History' : '历史',
  }

  const sections = [
    {
      key: 'bookmarks',
      title: isEnglish ? 'My bookmarks' : '我的收藏',
      icon: <Bookmark size={20} />,
      items: data.bookmarks || [],
      emptyText: isEnglish
        ? 'No bookmarked article yet. Save important stories here to build a durable reading shelf.'
        : '你还没有收藏文章。把重要内容加入收藏后，这里会逐步形成你的长期阅读清单。',
    },
    {
      key: 'likes',
      title: isEnglish ? 'My likes' : '我的点赞',
      icon: <Heart size={20} />,
      items: data.likes || [],
      emptyText: isEnglish
        ? 'No liked article yet. Likes help the product understand what you care about.'
        : '你还没有点赞文章。点赞会帮助平台理解你更关心的话题。',
    },
    {
      key: 'history',
      title: isEnglish ? 'Recent reading' : '最近阅读',
      icon: <Eye size={20} />,
      items: data.recent_views || [],
      emptyText: isEnglish
        ? 'Your recent reading is still empty. Keep browsing and this area will become your reading trail.'
        : '最近阅读记录还是空的。继续浏览文章后，这里会逐步沉淀你的阅读轨迹。',
    },
  ]

  const visibleSections = activeTab === 'all' ? sections : sections.filter((section) => section.key === activeTab)

  const assetCards = [
    {
      label: isEnglish ? 'Bookmarks' : '收藏',
      value: dashboard?.asset_summary?.bookmark_count ?? 0,
      detail: isEnglish ? 'Open your long-term reading shelf' : '打开你的长期阅读清单',
      tab: 'bookmarks',
    },
    {
      label: isEnglish ? 'Likes' : '点赞',
      value: dashboard?.asset_summary?.like_count ?? 0,
      detail: isEnglish ? 'Open articles you endorsed' : '打开你点过赞的文章流',
      tab: 'likes',
    },
    {
      label: isEnglish ? 'History' : '历史',
      value: dashboard?.asset_summary?.recent_view_count ?? 0,
      detail: isEnglish ? 'Return to your reading trail' : '回到你的阅读历史流',
      tab: 'history',
    },
    {
      label: isEnglish ? 'Following' : '关注',
      value: dashboard?.asset_summary?.follow_count ?? 0,
      detail: isEnglish ? 'Tracked tags and topics' : '关注的标签与专题',
      href: '/following',
    },
    {
      label: isEnglish ? 'Knowledge themes' : '知识库主题',
      value: dashboard?.asset_summary?.knowledge_theme_count ?? 0,
      detail: isEnglish ? 'Private theme collections' : '私有主题收藏集',
      href: '/me/knowledge',
    },
    {
      label: isEnglish ? 'Knowledge articles' : '知识库文章',
      value: dashboard?.asset_summary?.knowledge_article_count ?? 0,
      detail: isEnglish ? 'Articles filed into themes' : '已归档进主题的文章',
      href: '/me/knowledge',
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
          <div className="mt-6 flex flex-wrap gap-3">
            {LIBRARY_TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={[
                  'rounded-full px-4 py-2 text-sm font-semibold transition',
                  activeTab === tab ? 'bg-fudan-blue text-white' : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
                ].join(' ')}
                data-library-tab={tab}
              >
                {tabCopy[tab]}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-2">
          {assetCards.map((item) =>
            item.tab ? (
              <button
                key={item.label}
                type="button"
                onClick={() => setActiveTab(item.tab)}
                className={[
                  'fudan-panel p-6 text-left transition',
                  activeTab === item.tab ? 'border border-fudan-blue/20 bg-fudan-blue/5' : 'hover:border-fudan-blue/20',
                ].join(' ')}
                data-library-summary-card={item.tab}
              >
                <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{item.label}</div>
                <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{item.value}</div>
                <div className="mt-2 text-sm leading-7 text-slate-600">{item.detail}</div>
              </button>
            ) : (
              <Link key={item.label} to={item.href} className="fudan-panel p-6 transition hover:border-fudan-blue/20">
                <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{item.label}</div>
                <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{item.value}</div>
                <div className="mt-2 text-sm leading-7 text-slate-600">{item.detail}</div>
              </Link>
            ),
          )}
        </div>
      </section>

      <div className="mt-10 space-y-12">
        <KnowledgeWorkspaceCard canUseAiAssistant={canUseAiAssistant} dashboard={dashboard} isEnglish={isEnglish} />

        <section className="fudan-panel p-6 md:p-8">
          <div className="section-kicker">{isEnglish ? 'Reading flows' : '阅读资产流'}</div>
          <h2 className="font-serif text-3xl font-black text-fudan-blue">
            {activeTab === 'all' ? (isEnglish ? 'Bookmarks, likes, and history in one place' : '收藏、点赞与历史放在同一个回流页') : tabCopy[activeTab]}
          </h2>
          <p className="mt-4 text-sm leading-7 text-slate-600">
            {isEnglish
              ? 'Open a flow, browse the article cards, then click any card to return to the original article page.'
              : '打开某一类资产流后，继续浏览文章卡片；点击任意卡片，就能回到对应文章详情页。'}
          </p>
        </section>

        {visibleSections.map((section) => (
          <LibrarySection
            key={section.key}
            sectionKey={section.key}
            title={section.title}
            icon={section.icon}
            items={section.items}
            emptyText={section.emptyText}
            highlighted={activeTab === section.key}
          />
        ))}
      </div>
    </div>
  )
}

export default MyLibraryPage
