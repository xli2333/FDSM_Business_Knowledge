import { ArrowRight, Film, Headphones, LockKeyhole } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fetchHomeFeed, fetchLatestArticles, fetchTrendingArticles, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import SearchBar from '../components/shared/SearchBar.jsx'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { formatTopicType } from '../utils/formatters.js'

const twoLineClampStyle = {
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
}

const threeLineClampStyle = {
  display: '-webkit-box',
  WebkitLineClamp: 3,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
}

function HomePage() {
  const { isEnglish } = useLanguage()
  const { isAuthenticated, membership, businessProfile, canUseAiAssistant } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [latestArticles, setLatestArticles] = useState([])
  const [trendingArticles, setTrendingArticles] = useState([])
  const [trendingWindow, setTrendingWindow] = useState('week')
  const [loadingTrending, setLoadingTrending] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMoreLatest, setHasMoreLatest] = useState(true)

  useEffect(() => {
    fetchHomeFeed(isEnglish ? 'en' : 'zh')
      .then((payload) => {
        setData(payload)
        setLatestArticles(payload.latest || [])
        setTrendingArticles(payload.trending || [])
        setTrendingWindow(payload.trending_window || 'week')
        setHasMoreLatest((payload.latest || []).length >= 12)
      })
      .catch(() => setError(isEnglish ? 'Failed to load the homepage feed.' : '首页数据加载失败'))
  }, [isEnglish])

  const handleSearch = (query, mode) => {
    navigate(`/search?q=${encodeURIComponent(query)}&mode=${mode}`)
  }

  const handleLoadMoreLatest = async () => {
    setLoadingMore(true)
    try {
      const items = await fetchLatestArticles(12, latestArticles.length, isEnglish ? 'en' : 'zh')
      setLatestArticles((current) => [...current, ...items])
      if (items.length < 12) {
        setHasMoreLatest(false)
      }
    } finally {
      setLoadingMore(false)
    }
  }

  const handleTrendingWindowChange = async (nextWindow) => {
    if (!nextWindow || nextWindow === trendingWindow) return
    setLoadingTrending(true)
    try {
      const items = await fetchTrendingArticles(6, 0, nextWindow, isEnglish ? 'en' : 'zh')
      setTrendingArticles(items)
      setTrendingWindow(nextWindow)
    } finally {
      setLoadingTrending(false)
    }
  }

  const heroQuickTags = (data?.quick_tags || data?.hot_tags || []).slice(0, 6)
  const heroQuickTopics = (data?.topic_starters || data?.topics || []).slice(0, 2)
  const editorPicks = (data?.editors_picks || []).slice(0, 4)
  const topicSquare = data?.topic_square || data?.topics || []
  const trendingWindows = data?.trending_windows || ['day', 'week', 'month']
  const canReadTopics = Boolean(membership?.can_access_paid) || Boolean(membership?.is_admin)
  const defaultSearchMode = canReadTopics ? 'smart' : 'exact'
  const currentTierLabel = isEnglish
    ? {
        guest: 'Guest',
        free_member: 'Free Member',
        paid_member: 'Paid Member',
        admin: 'Admin',
      }[membership?.tier || 'guest']
    : membership?.tier_label || '访客'

  const topicAccessCard = canReadTopics
    ? isEnglish
      ? ['Topic', 'Topic Reading', 'Enter structured reading paths built around AI, ESG, leadership, and more.', '/topics']
      : ['专题', '专题阅读', '围绕 AI、ESG、领导力等议题进入结构化阅读路径。', '/topics']
    : isEnglish
      ? ['Membership', 'Unlock topic reading', 'Topic reading is available to paid members and admins. Upgrade to open structured topic routes.', isAuthenticated ? '/membership' : '/login']
      : ['会员', '解锁专题阅读', '专题阅读仅对付费会员和管理员开放，可升级后进入结构化专题路径。', isAuthenticated ? '/membership' : '/login']

  const productCards = isEnglish
    ? [
        ['Teaching & Research', 'Use structured articles and topics for class prep, case study, and research references.'],
        ['Executive Insight', 'Follow business topics, leadership thinking, and alumni insight in one place.'],
        ['Member Reading', 'Extend the archive into premium columns, reports, and recurring member reading.'],
      ]
    : [
        ['教学与研究', '适合备课、案例检索和围绕议题的结构化阅读。'],
        ['管理者洞察', '在一个入口里持续跟踪商业话题、管理观点和校友洞察。'],
        ['会员阅读', '把文章档案延展成会员专栏、专题报告和持续更新的阅读服务。'],
      ]

  const assistantCard = canUseAiAssistant
    ? isEnglish
      ? ['Assistant', 'AI Assistant', 'Ask questions, compare topics, and synthesize timelines around the knowledge base.', '/chat']
      : ['助手', 'AI 助理', '围绕知识库提问、比较主题并快速整理时间线。', '/chat']
    : membership?.tier === 'free_member'
      ? isEnglish
        ? ['Upgrade', 'Unlock AI Assistant', 'AI Assistant is available to paid members and admins. Upgrade when you need synthesis and dialogue.', '/membership']
        : ['升级', '解锁 AI 助理', 'AI 助理对付费会员和管理员开放。需要总结和对话能力时可升级。', '/membership']
      : isEnglish
        ? ['Membership', 'Unlock AI Assistant', 'Sign in and move into paid membership to use the assistant inside the product.', isAuthenticated ? '/membership' : '/login']
        : ['会员', '解锁 AI 助理', '登录后进入会员体系，再升级到付费会员即可使用 AI 助理。', isAuthenticated ? '/membership' : '/login']

  const experienceCards = isEnglish
    ? [
        ['Search', 'Unified Search', 'Search the business article library by topic, person, or concept.', `/search?q=AI&mode=${defaultSearchMode}`],
        assistantCard,
        topicAccessCard,
        ['Archive', 'Time Machine', 'Jump across dates and revisit historical content through the archive.', '/time-machine'],
        ['Membership', 'Membership Access', 'Articles and audio support public, member, and paid visibility.', '/membership'],
      ]
    : [
        ['搜索', '统一搜索', '从主题、人物和概念切入，快速找到商业文章内容。', `/search?q=AI&mode=${defaultSearchMode}`],
        assistantCard,
        topicAccessCard,
        ['归档', '时光机', '按日期回看历史内容，从档案里重新进入文章。', '/time-machine'],
        ['会员', '会员访问', '文章和音频已经支持公开、会员和付费可见性。', '/membership'],
      ]

  const assistantCta = canUseAiAssistant
    ? {
        to: '/chat',
        label: isEnglish ? 'Open AI Assistant' : '进入 AI 助理',
      }
    : {
        to: isAuthenticated ? '/membership' : '/login',
        label: isEnglish ? 'Unlock AI Assistant' : '解锁 AI 助理',
      }

  const rolePanel = isAuthenticated
    ? membership?.tier === 'admin'
      ? {
          kicker: isEnglish ? 'For admins' : '管理员入口',
          title: isEnglish ? 'Manage members, content, and review from one dashboard' : '在一个控制台里管理成员、内容和审核',
          body: isEnglish
            ? 'After sign-in, admins go straight to memberships, editorial work, and audit review.'
            : '登录后，管理员会直接进入会员管理、编辑工作、媒体后台和审计查看。',
          ctaLabel: isEnglish ? 'Open admin console' : '进入管理控制台',
          ctaPath: '/admin',
        }
      : membership?.tier === 'paid_member'
        ? {
          kicker: isEnglish ? 'For paid members' : '付费会员入口',
          title: isEnglish ? 'Start with benefits, full articles, audio, and video' : '从权益、完整正文、音频和视频开始',
          body: isEnglish
              ? 'Paid members land where their subscription matters most: full-text reading, full audio and video playback, and account benefits.'
              : '付费会员会优先看到完整正文、完整音频视频和当前订阅权益。',
          ctaLabel: isEnglish ? 'Open membership' : '进入会员空间',
          ctaPath: '/membership',
        }
        : {
            kicker: isEnglish ? 'For free members' : '免费会员入口',
            title: isEnglish ? 'Keep your library, media previews, and upgrade options in one place' : '把资料库、媒体预览和升级选择放在一个页面里',
            body: isEnglish
              ? 'Free members can continue from bookmarks, likes, reading history, followed topics, and one-minute media previews, then upgrade when deeper access is needed.'
              : '免费会员可以从收藏、点赞、阅读历史、关注话题和 1 分钟媒体预览继续阅读，并在需要更深层权限时升级。',
            ctaLabel: isEnglish ? 'Open my library' : '进入我的资料库',
            ctaPath: '/me',
          }
    : {
        kicker: isEnglish ? 'For guests' : '访客入口',
        title: isEnglish ? 'Start with public reading and media previews' : '先从公开阅读和媒体预览开始',
        body: isEnglish
          ? 'Guests can search, read public articles, and open audio or video previews before deciding whether to sign in or upgrade.'
          : '访客可以先搜索、阅读公开文章，并先试听试看音频视频，再决定是否登录或升级。',
        ctaLabel: isEnglish ? 'Open login page' : '进入登录页',
        ctaPath: '/login',
      }

  const roleQuickLinks = isAuthenticated
    ? membership?.tier === 'admin'
      ? [
          { label: isEnglish ? 'Media Studio' : '媒体后台', href: '/media-studio', icon: Film, tone: 'plain' },
          { label: isEnglish ? 'Membership Admin' : '会员管理', href: '/admin/memberships', icon: LockKeyhole, tone: 'plain' },
          { label: isEnglish ? 'Audio' : '音频', href: '/audio', icon: Headphones, tone: 'plain' },
          { label: isEnglish ? 'Video' : '视频', href: '/video', icon: Film, tone: 'plain' },
        ]
      : membership?.tier === 'paid_member'
        ? [
            { label: isEnglish ? 'Membership' : '会员空间', href: '/membership', icon: LockKeyhole, tone: 'primary' },
            { label: isEnglish ? 'Audio' : '音频', href: '/audio', icon: Headphones, tone: 'plain' },
            { label: isEnglish ? 'Video' : '视频', href: '/video', icon: Film, tone: 'plain' },
          ]
        : [
            { label: isEnglish ? 'Audio' : '音频', href: '/audio', icon: Headphones, tone: 'primary' },
            { label: isEnglish ? 'Video' : '视频', href: '/video', icon: Film, tone: 'plain' },
            { label: isEnglish ? 'My Library' : '我的资料库', href: '/me', icon: LockKeyhole, tone: 'plain' },
            { label: isEnglish ? 'Upgrade' : '升级会员', href: '/membership', icon: LockKeyhole, tone: 'accent' },
          ]
    : [
        { label: isEnglish ? 'Audio' : '音频', href: '/audio', icon: Headphones, tone: 'primary' },
        { label: isEnglish ? 'Video' : '视频', href: '/video', icon: Film, tone: 'plain' },
        { label: isEnglish ? 'Login' : '登录', href: '/login', icon: LockKeyhole, tone: 'accent' },
      ]

  const mediaEntryCards = [
    {
      key: 'audio',
      href: '/audio',
      icon: Headphones,
      kicker: isEnglish ? 'Audio Entry' : '音频入口',
      title:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Open the full audio stream'
            : '进入完整音频流'
          : isEnglish
            ? 'Start with a one-minute audio preview'
            : '先从 1 分钟音频试听开始',
      body:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Paid members and admins can open the full audio stream directly from the homepage.'
            : '付费会员和管理员可以直接从首页进入完整音频流。'
          : membership?.tier === 'free_member'
            ? isEnglish
              ? 'Free members can preview the current audio stream here and upgrade when full playback is needed.'
              : '免费会员可以先在这里试听当前音频流，需要完整收听时再升级。'
            : isEnglish
              ? 'Guests can start with the audio preview stream here before deciding whether to sign in or upgrade.'
              : '访客可以先从这里进入音频试听流，再决定是否登录或升级。',
      badge:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Full audio'
            : '完整音频'
          : isEnglish
            ? '1 min preview'
            : '1 分钟试听',
    },
    {
      key: 'video',
      href: '/video',
      icon: Film,
      kicker: isEnglish ? 'Video Entry' : '视频入口',
      title:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Open the video stream'
            : '进入视频流'
          : isEnglish
            ? 'Browse public and preview video'
            : '浏览公开视频与试看内容',
      body:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Use the same homepage header area to continue into the video stream without detouring through other pages.'
            : '直接从首页这一区域继续进入视频流，不再需要绕到其他页面。'
          : membership?.tier === 'free_member'
            ? isEnglish
              ? 'Free members can continue into public and preview-first video cards here.'
              : '免费会员可以从这里继续进入公开视频和优先试看的视频卡片。'
            : isEnglish
              ? 'Guests can open the public and preview-first video page here as part of the same first-screen route.'
              : '访客可以从这里直接进入公开视频和试看优先的视频页，保持同一条首屏路径。',
      badge:
        isAuthenticated && (membership?.tier === 'paid_member' || membership?.tier === 'admin')
          ? isEnglish
            ? 'Role-based access'
            : '按身份解锁'
          : isEnglish
            ? 'Public + preview'
            : '公开 + 试看',
    },
  ]

  return (
    <div className="pb-12">
      <section className="page-shell pt-12 md:pt-16">
        <div className={`grid items-start gap-8 ${isEnglish ? 'lg:grid-cols-[1fr_1fr] xl:grid-cols-[1.06fr_0.94fr]' : 'lg:grid-cols-[1.2fr_0.8fr]'}`}>
          <div className="space-y-8">
            <div className="space-y-5">
              <div className="section-kicker">Business-only Knowledge Base</div>
              <h1
                className={[
                  'font-serif font-black text-fudan-blue',
                  isEnglish ? 'text-[3.05rem] leading-[0.95] tracking-[-0.03em] md:text-[3.55rem] xl:text-[4.05rem] 2xl:text-[4.45rem]' : 'text-5xl leading-tight md:text-7xl',
                ].join(' ')}
              >
                {isEnglish ? (
                  <>
                    Insight for action
                    <br />
                    <span className="block text-[0.93em] text-fudan-orange md:whitespace-nowrap">New ground for change</span>
                  </>
                ) : (
                  <>
                    洞见商业
                    <br />
                    <span className="ml-[1.1em] text-fudan-orange">理解变化</span>
                  </>
                )}
              </h1>
              <p className="max-w-2xl text-base leading-8 text-slate-600 md:text-lg">
                {isEnglish
                  ? 'Built on 2,142 curated articles from the Fudan business archive, this platform brings together columns, topics, search, and AI support for structured reading.'
                  : '基于复旦商业内容库中的 2142 篇文章，这个平台把栏目、专题、搜索和 AI 支持组织成一套连续的阅读体验。'}
              </p>
            </div>
            <SearchBar onSearch={handleSearch} />
            {heroQuickTags.length || heroQuickTopics.length ? (
              <div className="grid gap-4 rounded-[1.75rem] border border-white/70 bg-white/85 p-5 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur md:grid-cols-[1.1fr_0.9fr]">
                {heroQuickTags.length ? (
                  <div>
                    <div className="section-kicker">{isEnglish ? 'Quick Tags' : '快速入口'}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {heroQuickTags.map((tag) => (
                        <TagBadge key={`hero-${tag.slug}`} tag={tag} />
                      ))}
                    </div>
                  </div>
                ) : null}
                {heroQuickTopics.length ? (
                  <div className="space-y-3">
                    <div className="section-kicker">{isEnglish ? 'Start With a Topic' : '专题起读'}</div>
                    {heroQuickTopics.map((topic) => (
                      <Link
                        key={`hero-topic-${topic.slug}`}
                        to={`/topic/${topic.slug}`}
                        className="block rounded-[1.25rem] border border-slate-200/70 bg-slate-50/70 p-4 transition hover:border-fudan-orange/30 hover:bg-white"
                      >
                        <div className="text-[11px] uppercase tracking-[0.22em] text-fudan-orange">{formatTopicType(topic.type, isEnglish)}</div>
                        <div className="mt-2 font-serif text-xl font-bold text-fudan-blue">{topic.title}</div>
                        <div className="mt-2 text-sm leading-6 text-slate-600" style={twoLineClampStyle}>
                          {topic.description}
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="fudan-panel overflow-hidden p-4 lg:self-end">
            <div className="section-kicker">{isEnglish ? "Editor's Picks" : '编辑精选'}</div>
            <div className="space-y-2.5">
              {editorPicks.map((article) => (
                <Link
                  key={article.id}
                  to={`/article/${article.id}`}
                  className="block rounded-[1.1rem] border border-slate-200/70 p-3 transition hover:border-fudan-blue/30 hover:bg-slate-50"
                >
                  <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{article.publish_date}</div>
                  <div className="mt-1.5 font-serif text-lg font-bold leading-7 text-fudan-blue" style={twoLineClampStyle}>
                    {article.title}
                  </div>
                  <div className="mt-1.5 text-sm leading-6 text-slate-600" style={threeLineClampStyle}>
                    {article.excerpt}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="page-shell mt-8 text-sm text-red-500">{error}</div> : null}

      {data?.hero ? (
        <section className="page-shell mt-12">
          <div className="fudan-panel grid overflow-hidden lg:grid-cols-[1.15fr_0.85fr]">
            <div className="p-8 md:p-10">
              <div className="section-kicker">{isEnglish ? 'Lead Story' : '头条文章'}</div>
              <h2 className="mt-2 font-serif text-4xl font-black leading-tight md:text-5xl">{data.hero.title}</h2>
              <p className="mt-5 max-w-3xl text-base leading-8 text-slate-600">{data.hero.excerpt}</p>
              <div className="mt-6 flex flex-wrap gap-2">
                {(data.hero.tags || []).slice(0, 4).map((tag) => (
                  <TagBadge key={tag.slug} tag={tag} />
                ))}
              </div>
              <div className="mt-8">
                <Link to={`/article/${data.hero.id}`} className="inline-flex items-center gap-2 text-sm font-semibold tracking-[0.18em] text-fudan-orange">
                  {isEnglish ? 'Open article' : '阅读全文'}
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>

            <div className="min-h-[320px] bg-slate-100">
              {data.hero.cover_url ? (
                <img src={resolveApiUrl(data.hero.cover_url)} alt={data.hero.title} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full items-end bg-[linear-gradient(135deg,rgba(13,7,131,0.95),rgba(10,5,96,0.72)_55%,rgba(234,107,0,0.52))] p-8">
                  <div className="max-w-sm rounded-[1.4rem] border border-white/15 bg-white/10 p-5 text-white/90">
                    <div className="text-xs uppercase tracking-[0.24em] text-white/65">Featured Story</div>
                    <div className="mt-3 font-serif text-2xl font-bold">{data.hero.main_topic || (isEnglish ? 'Business knowledge feature' : '商业知识精选')}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}

      <section className="page-shell mt-12">
        <div className="fudan-panel mb-6 grid gap-6 overflow-hidden p-8 lg:grid-cols-[1.02fr_0.98fr]">
          <div>
            <div className="section-kicker">{rolePanel.kicker}</div>
            <h2 className="section-title">{rolePanel.title}</h2>
            <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">{rolePanel.body}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              {roleQuickLinks.map((item) => {
                const Icon = item.icon
                const className =
                  item.tone === 'primary'
                    ? 'border border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue hover:bg-fudan-blue/15'
                    : item.tone === 'accent'
                      ? 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15'
                      : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30'
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    className={`inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-semibold transition ${className}`}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </div>
          <div className="flex items-center justify-start lg:justify-end">
            <div className="rounded-[1.5rem] border border-slate-200/70 bg-slate-50 p-5">
              <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{isEnglish ? 'Current account' : '当前身份'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">
                {isAuthenticated ? `${businessProfile?.display_name || ''} / ${currentTierLabel || ''}` : isEnglish ? 'Guest' : '访客'}
              </div>
              <Link
                to={rolePanel.ctaPath}
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold tracking-[0.16em] text-fudan-orange"
              >
                {rolePanel.ctaLabel}
                <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        </div>

        <div className="mb-6 grid gap-4 md:grid-cols-2">
          {mediaEntryCards.map((card) => {
            const Icon = card.icon
            return (
              <Link
                key={card.key}
                to={card.href}
                className="fudan-card p-6 transition hover:-translate-y-1 hover:border-fudan-blue/30"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="section-kicker">{card.kicker}</div>
                    <div className="mt-2 font-serif text-3xl font-black leading-tight text-fudan-blue">{card.title}</div>
                  </div>
                  <div className="rounded-full bg-fudan-blue/10 p-4 text-fudan-blue">
                    <Icon size={18} />
                  </div>
                </div>
                <p className="mt-4 text-sm leading-7 text-slate-600">{card.body}</p>
                <div className="mt-5 flex items-center justify-between gap-4">
                  <span className="rounded-full bg-fudan-orange/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-fudan-orange">
                    {card.badge}
                  </span>
                  <span className="inline-flex items-center gap-2 text-sm font-semibold text-fudan-orange">
                    {isEnglish ? 'Open' : '进入'}
                    <ArrowRight size={16} />
                  </span>
                </div>
              </Link>
            )
          })}
        </div>

        <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="fudan-panel p-8">
            <div className="section-kicker">{isEnglish ? 'Product Value' : '产品价值'}</div>
            <h2 className="section-title">{isEnglish ? 'Structured business reading in one place' : '把结构化商业阅读放在一个入口里'}</h2>
            <p className="mt-5 text-base leading-8 text-slate-600">
              {isEnglish
                ? 'Articles, topics, columns, search, AI support, and membership access work together in one continuous reading experience.'
                : '文章、专题、栏目、搜索、AI 支持和会员权限被组织在同一套连续阅读体验里。'}
            </p>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {productCards.map(([title, desc]) => (
                <div key={title} className="rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-4">
                  <div className="font-serif text-xl font-bold text-fudan-blue">{title}</div>
                  <div className="mt-2 text-sm leading-7 text-slate-600">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="fudan-panel p-8">
            <div className="section-kicker">{isEnglish ? 'Try It Now' : '立即体验'}</div>
            <div className="grid gap-4 md:grid-cols-2">
              {experienceCards.map(([eyebrow, title, desc, href]) => (
                <Link key={href} to={href} className="rounded-[1.5rem] border border-slate-200/70 bg-white p-5 transition hover:-translate-y-1 hover:border-fudan-blue/30">
                  <div className="text-xs uppercase tracking-[0.24em] text-fudan-orange">{eyebrow}</div>
                  <div className="mt-3 font-serif text-2xl font-black text-fudan-blue">{title}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">{desc}</div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="page-shell mt-12">
        <div className="fudan-panel grid gap-6 overflow-hidden p-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="section-kicker">{isEnglish ? 'Partnerships' : '合作与方案'}</div>
            <h2 className="section-title">
              {isEnglish ? 'For executive education, branded programs, and institutional partnerships' : '适用于高管教育、品牌内容项目和机构合作'}
            </h2>
            <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
              {isEnglish
                ? 'Use the commercial page to review product capabilities, partnership information, and contact details for follow-up discussions.'
                : '你可以在商业页面查看产品能力、合作信息和联系入口，用于进一步沟通。'}
            </p>
          </div>
          <div className="flex items-center justify-start gap-4 lg:justify-end">
            <Link
              to="/commercial"
              className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-6 py-4 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-fudan-dark"
            >
              {isEnglish ? 'View commercial plan' : '查看合作方案'}
              <ArrowRight size={16} />
            </Link>
            <Link
              to={assistantCta.to}
              className="inline-flex items-center gap-2 rounded-full border border-fudan-orange/30 bg-fudan-orange/10 px-6 py-4 text-sm font-semibold tracking-[0.16em] text-fudan-orange transition hover:bg-fudan-orange/15"
            >
              {assistantCta.label}
            </Link>
          </div>
        </div>
      </section>

      {trendingArticles.length ? (
        <section className="page-shell mt-14">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div className="section-kicker">{isEnglish ? 'Trending Articles' : '热门文章'}</div>
            <h2 className="section-title">{isEnglish ? 'Chosen by readers through views, likes, and bookmarks' : '由浏览、点赞和收藏共同推高的内容'}</h2>
            <div className="flex flex-wrap gap-2">
              {trendingWindows.map((window) => (
                <button
                  key={window}
                  type="button"
                  onClick={() => handleTrendingWindowChange(window)}
                  disabled={loadingTrending}
                  className={[
                    'rounded-full px-4 py-2 text-sm font-semibold transition',
                    trendingWindow === window
                      ? 'bg-fudan-blue text-white'
                      : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
                  ].join(' ')}
                >
                  {window}
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {trendingArticles.map((article) => (
              <ArticleCard key={`trending-${article.id}`} article={article} />
            ))}
          </div>
        </section>
      ) : null}

      <section className="page-shell mt-14">
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <div className="section-kicker">{isEnglish ? 'Column Navigation' : '栏目导航'}</div>
            <h2 className="section-title">{isEnglish ? 'Enter structured reading through columns' : '从栏目进入结构化阅读'}</h2>
          </div>
          <Link to="/topics" className="text-sm font-semibold tracking-[0.16em] text-fudan-orange">
            {isEnglish ? 'Browse all topics' : '查看全部专题'}
          </Link>
        </div>
        <div className="grid gap-6 xl:grid-cols-4">
          {(data?.column_previews || []).map((preview) => (
            <div key={preview.column.slug} className="fudan-panel p-5">
              <div className="text-xs uppercase tracking-[0.24em]" style={{ color: preview.column.accent_color }}>
                {preview.column.name}
              </div>
              <p className="mt-3 text-sm leading-7 text-slate-600">{preview.column.description}</p>
              <div className="mt-5 space-y-4">
                {preview.items.map((item) => (
                  <Link key={item.id} to={`/article/${item.id}`} className="block rounded-[1.1rem] border border-slate-200/70 p-4 transition hover:bg-slate-50">
                    <div className="font-serif text-lg font-bold text-fudan-blue">{item.title}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">{item.excerpt}</div>
                  </Link>
                ))}
              </div>
              <Link to={`/column/${preview.column.slug}`} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-fudan-orange">
                {isEnglish ? 'Open column' : '进入栏目'}
                <ArrowRight size={15} />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {topicSquare.length ? (
        <section className="page-shell mt-14">
          <div className="mb-8">
            <div className="section-kicker">{isEnglish ? 'Topic Square' : '专题广场'}</div>
            <h2 className="section-title">{isEnglish ? 'Read by topic, not just one article at a time' : '围绕议题阅读，而不是只看单篇'}</h2>
          </div>
          <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {topicSquare.map((topic) => (
              <Link key={topic.slug} to={`/topic/${topic.slug}`} className="fudan-card p-6">
                <div className="text-xs uppercase tracking-[0.24em] text-fudan-orange">{formatTopicType(topic.type, isEnglish)}</div>
                <h3 className="mt-3 font-serif text-2xl font-black text-fudan-blue">{topic.title}</h3>
                <p className="mt-4 text-sm leading-7 text-slate-600">{topic.description}</p>
                <div className="mt-5 flex flex-wrap gap-2">
                  {(topic.tags || []).slice(0, 3).map((tag) => (
                    <TagBadge key={`${topic.slug}-${tag.slug}`} tag={tag} />
                  ))}
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <section className="page-shell mt-14">
        <div className="mb-8">
          <div className="section-kicker">{isEnglish ? 'Latest Articles' : '最新文章'}</div>
          <h2 className="section-title">{isEnglish ? 'A continuously updated business reading stream' : '持续更新的商业阅读流'}</h2>
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {latestArticles.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
        {hasMoreLatest && latestArticles.length >= 12 ? (
          <div className="mt-8 flex justify-center">
            <button
              type="button"
              onClick={handleLoadMoreLatest}
              disabled={loadingMore}
              className="rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:border-fudan-blue/30 disabled:cursor-not-allowed disabled:text-slate-400"
            >
              {loadingMore ? (isEnglish ? 'Loading...' : '加载中...') : isEnglish ? 'Load more' : '继续加载'}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  )
}

export default HomePage
