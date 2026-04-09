import {
  ArrowRight,
  Bookmark,
  Building2,
  Calendar,
  Crown,
  Eye,
  ExternalLink,
  Heart,
  Languages,
  LoaderCircle,
  Lock,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.js'
import { fetchArticle, fetchArticleSummary, fetchArticleTranslation, submitArticleReaction } from '../api/index.js'
import AutoHeightPreviewFrame from '../components/shared/AutoHeightPreviewFrame.jsx'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { formatDate } from '../utils/formatters.js'

const ACCESS_LABELS = {
  zh: {
    public: '公开',
    member: '会员',
    paid: '付费',
  },
  en: {
    public: 'Public',
    member: 'Member',
    paid: 'Paid',
  },
}

const MEMBERSHIP_LABELS = {
  zh: {
    guest: '游客',
    free_member: '免费会员',
    paid_member: '付费会员',
    admin: '管理员',
  },
  en: {
    guest: 'Guest',
    free_member: 'Free Member',
    paid_member: 'Paid Member',
    admin: 'Admin',
  },
}

const MEMBERSHIP_STATUS_LABELS = {
  zh: {
    anonymous: '未登录',
    active: '有效',
    expired: '已过期',
  },
  en: {
    anonymous: 'Not signed in',
    active: 'Active',
    expired: 'Expired',
  },
}

function getAccessMessage(access, language) {
  if (!access?.locked) return ''
  if (language !== 'en') return access.message || ''
  if (access.access_level === 'paid') {
    return 'This article is currently available to paid members. Guests and free members can only preview the visible opening section.'
  }
  if (access.access_level === 'member') {
    return 'This article is currently available to members. Guests can preview only the visible opening section.'
  }
  return 'This article is partially restricted in the current environment.'
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`(.+?)`/g, '<code>$1</code>')
  return html
}

function renderMarkdownToHtml(markdown) {
  const lines = String(markdown || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')

  const blocks = []
  let paragraph = []
  let list = null

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push({ type: 'paragraph', text: paragraph.join(' ').trim() })
    paragraph = []
  }

  const flushList = () => {
    if (!list?.items?.length) return
    blocks.push(list)
    list = null
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      flushList()
      continue
    }

    if (/^-{3,}$/.test(line)) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'hr' })
      continue
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2].trim() })
      continue
    }

    const bullet = line.match(/^[-*+]\s+(.+)$/)
    if (bullet) {
      flushParagraph()
      if (!list || list.type !== 'ul') {
        flushList()
        list = { type: 'ul', items: [] }
      }
      list.items.push(bullet[1].trim())
      continue
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/)
    if (ordered) {
      flushParagraph()
      if (!list || list.type !== 'ol') {
        flushList()
        list = { type: 'ol', items: [] }
      }
      list.items.push(ordered[1].trim())
      continue
    }

    const strongOnly = line.match(/^\*\*(.+?)\*\*$/)
    if (strongOnly) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'label', text: strongOnly[1].trim() })
      continue
    }

    paragraph.push(line)
  }

  flushParagraph()
  flushList()

  return blocks
    .map((block) => {
      if (block.type === 'heading') {
        const safeText = renderInlineMarkdown(block.text)
        if (block.level <= 2) {
          return `<h2 style="margin: 34px 0 18px; text-align: center; color: #4E8FEA; font-family: Georgia, 'Times New Roman', 'PingFang SC', serif; font-size: 22px; line-height: 1.45; font-weight: 800;">${safeText}</h2>`
        }
        return `<h3 style="margin: 28px 0 14px; color: #1F3251; font-family: Georgia, 'Times New Roman', 'PingFang SC', serif; font-size: 18px; line-height: 1.5; font-weight: 700;">${safeText}</h3>`
      }
      if (block.type === 'label') {
        return `<p style="margin: 0 0 18px; color: #1F3251; font-size: 15px; line-height: 1.85; font-weight: 700;">${renderInlineMarkdown(block.text)}</p>`
      }
      if (block.type === 'hr') {
        return '<p style="margin: 18px 0 24px; border-top: 1px solid #D9E4F2; height: 0;"></p>'
      }
      if (block.type === 'ul' || block.type === 'ol') {
        const tag = block.type
        const items = block.items
          .map((item) => `<li style="margin: 0 0 10px; color: #475569; font-size: 15px; line-height: 1.88;">${renderInlineMarkdown(item)}</li>`)
          .join('')
        return `<${tag} style="margin: 0 0 26px; padding-left: 24px;">${items}</${tag}>`
      }
      return `<p style="margin: 0 0 28px; color: #475569; font-size: 15px; line-height: 1.92; letter-spacing: 0.01em;">${renderInlineMarkdown(block.text)}</p>`
    })
    .join('')
}

function previewHtmlLooksMarkdownLiteral(value) {
  const html = String(value || '')
  if (!html.trim()) return true
  return />\s*##\s/.test(html) || />\s*###\s/.test(html) || />\s*\*\*.+?\*\*/.test(html) || />\s*---\s*</.test(html) || />\s*#\d+\s*/.test(html)
}

function buildFallbackPreviewDoc(text, { compact = false } = {}) {
  const paragraphHtml =
    renderMarkdownToHtml(text) ||
    `<p style="margin: 0; color: #94A3B8; font-size: 15px; line-height: 1.92;">${compact ? 'Summary unavailable.' : 'Content unavailable.'}</p>`

  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; padding: 12px 8px 20px; background: #F8FBFF; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
      .shell { max-width: 760px; margin: 0 auto; background: #FFFFFF; }
      .article { padding: ${compact ? '18px 18px 12px' : '18px 10px 26px'}; background: #FFFFFF; }
      .inner { margin: 0 auto; width: 100%; max-width: 700px; }
      .dots { margin: 0 0 16px 4px; line-height: 0; }
      .dot { display: inline-block; width: 8px; height: 8px; margin-right: 28px; border-radius: 999px; background: #CBD5E1; }
      strong { padding: 0 6px 1px; border-bottom: 1px solid #D3E6FB; background: #EAF3FF; color: #243B5A; font-weight: 700; }
      code { padding: 0 5px; border-radius: 6px; background: #EFF3F8; color: #334155; font-size: 0.94em; }
      em { color: #334155; }
    </style>
  </head>
  <body>
    <div class="shell">
      <section class="article">
        <article class="inner">
          <p class="dots"><span class="dot"></span><span class="dot"></span><span class="dot" style="margin-right:0;"></span></p>
          ${paragraphHtml}
        </article>
      </section>
    </div>
  </body>
</html>`
}

function MetricPill({ icon: Icon, value, tone = 'blue' }) {
  const toneClass =
    tone === 'orange'
      ? 'text-fudan-orange'
      : tone === 'slate'
        ? 'text-slate-500'
        : 'text-fudan-blue'

  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-600 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <Icon size={16} className={toneClass} />
      {value}
    </span>
  )
}

function ArticlePage() {
  const { id } = useParams()
  const { accessToken, authEnabled, isAuthenticated, membership, openAuthDialog } = useAuth()
  const { language, isEnglish, setLanguage, t } = useLanguage()
  const [article, setArticle] = useState(null)
  const [summary, setSummary] = useState('')
  const [summaryHtml, setSummaryHtml] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [busyReaction, setBusyReaction] = useState('')
  const [statusHint, setStatusHint] = useState('')
  const [pageLoading, setPageLoading] = useState(true)
  const [articleError, setArticleError] = useState(false)
  const [translation, setTranslation] = useState(null)
  const [translationLoading, setTranslationLoading] = useState(false)
  const [translationError, setTranslationError] = useState('')
  const [relatedTranslations, setRelatedTranslations] = useState({})
  const [relatedTranslationsLoading, setRelatedTranslationsLoading] = useState(false)
  const [summaryExpanded, setSummaryExpanded] = useState(false)

  useEffect(() => {
    if (!id) return undefined
    let active = true
    setPageLoading(true)
    setArticleError(false)
    setArticle(null)
    setSummary('')
    setSummaryHtml('')
    setSummaryLoading(true)
    setTranslation(null)
    setTranslationError('')
    setRelatedTranslations({})
    setRelatedTranslationsLoading(false)
    setSummaryExpanded(false)

    fetchArticle(id, accessToken)
      .then((articlePayload) => {
        if (!active) return
        setArticle(articlePayload)
      })
      .catch(() => {
        if (!active) return
        setArticleError(true)
      })
      .finally(() => {
        if (active) setPageLoading(false)
      })

    fetchArticleSummary(id, accessToken)
      .then((summaryPayload) => {
        if (!active) return
        setSummary(summaryPayload.summary || '')
        setSummaryHtml(summaryPayload.summary_html || '')
      })
      .catch(() => {
        if (!active) return
        setSummary('')
        setSummaryHtml('')
      })
      .finally(() => {
        if (active) setSummaryLoading(false)
      })

    return () => {
      active = false
    }
  }, [accessToken, id])

  useEffect(() => {
    if (!isEnglish || !id) {
      setTranslationLoading(false)
      setTranslationError('')
      return undefined
    }

    let active = true
    setTranslationLoading(true)
    setTranslationError('')
    setSummaryExpanded(false)

    fetchArticleTranslation(id, 'en', accessToken)
      .then((payload) => {
        if (!active) return
        setTranslation(payload)
      })
      .catch(() => {
        if (!active) return
        setTranslation(null)
        setTranslationError(t('article.translationError'))
      })
      .finally(() => {
        if (active) setTranslationLoading(false)
      })

    return () => {
      active = false
    }
  }, [accessToken, id, isEnglish, t])

  useEffect(() => {
    if (!isEnglish || !article?.related_articles?.length) {
      setRelatedTranslations({})
      setRelatedTranslationsLoading(false)
      return undefined
    }

    let active = true
    setRelatedTranslationsLoading(true)
    setRelatedTranslations({})

    Promise.allSettled(article.related_articles.map((item) => fetchArticleTranslation(item.id, 'en', accessToken)))
      .then((results) => {
        if (!active) return
        const nextTranslations = {}
        results.forEach((result, index) => {
          if (result.status !== 'fulfilled') return
          const item = article.related_articles[index]
          if (!item) return
          nextTranslations[item.id] = {
            title: result.value.title || item.title,
            excerpt: result.value.excerpt || item.excerpt || item.main_topic || '',
          }
        })
        setRelatedTranslations(nextTranslations)
      })
      .finally(() => {
        if (active) setRelatedTranslationsLoading(false)
      })

    return () => {
      active = false
    }
  }, [accessToken, article?.id, article?.related_articles, isEnglish])

  const handleReaction = async (reactionType) => {
    if (!article) return
    if (!isAuthenticated) {
      openAuthDialog()
      setStatusHint(authEnabled ? t('article.loginRequired') : t('article.authUnavailable'))
      return
    }

    const engagement = article.engagement || {}
    const active = reactionType === 'like' ? !engagement.liked_by_me : !engagement.bookmarked_by_me

    setBusyReaction(reactionType)
    setStatusHint('')
    try {
      const nextEngagement = await submitArticleReaction(
        article.id,
        {
          reaction_type: reactionType,
          active,
        },
        accessToken,
      )
      setArticle((current) => ({
        ...current,
        like_count: nextEngagement.like_count,
        bookmark_count: nextEngagement.bookmark_count,
        engagement: nextEngagement,
      }))
    } catch {
      setStatusHint(t('article.reactionFailed'))
    } finally {
      setBusyReaction('')
    }
  }

  if (pageLoading) {
    return <div className="page-shell py-16 text-sm text-slate-500">{t('article.loading')}</div>
  }

  if (!article) {
    return (
      <div className="page-shell py-16 text-sm text-slate-500">
        {articleError ? (isEnglish ? 'This article is temporarily unavailable.' : '当前文章暂时不可用。') : t('article.loading')}
      </div>
    )
  }

  const engagement = article.engagement || {}
  const access = article.access || {}
  const accessMessage = getAccessMessage(access, language)
  const accessLabel = ACCESS_LABELS[language]?.[access.access_level] || article.access_label || t('articleCard.public')
  const membershipLabel = MEMBERSHIP_LABELS[language]?.[membership?.tier] || MEMBERSHIP_LABELS[language]?.guest
  const membershipStatusLabel =
    MEMBERSHIP_STATUS_LABELS[language]?.[membership?.status] || MEMBERSHIP_STATUS_LABELS[language]?.anonymous || ''
  const translatedActive = isEnglish && Boolean(translation)
  const translationPending = isEnglish && translationLoading && !translatedActive
  const visibleTitle = translatedActive ? translation.title : article.title
  const visibleIntro = translatedActive ? translation.excerpt : article.main_topic || article.excerpt
  const visibleSummary = translatedActive ? translation.summary : summary
  const visibleSummaryHtml = translatedActive ? translation?.summary_html : summaryHtml
  const visibleContent = translatedActive ? translation.content : article.content
  const visibleContentHtml = translatedActive ? translation?.html_wechat : article.html_wechat
  const summaryFallback = translatedActive ? '...' : summaryLoading ? (isEnglish ? 'Summary is loading...' : '摘要加载中...') : '...'
  const summaryDoc = !previewHtmlLooksMarkdownLiteral(visibleSummaryHtml)
    ? visibleSummaryHtml
    : buildFallbackPreviewDoc(visibleSummary || summaryFallback, { compact: true })
  const contentDoc = !previewHtmlLooksMarkdownLiteral(visibleContentHtml)
    ? visibleContentHtml
    : buildFallbackPreviewDoc(visibleContent)
  const canCollapseSummary = Boolean(visibleSummary) && visibleSummary.replace(/\s+/g, ' ').trim().length > 280
  const relatedArticles = (article.related_articles || []).map((item) => {
    const translatedItem = relatedTranslations[item.id]
    if (!translatedItem) return item
    return {
      ...item,
      title: translatedItem.title,
      excerpt: translatedItem.excerpt,
    }
  })
  const translatedScopeLabel =
    translation?.content_scope === 'preview' ? t('article.translatedScopePreview') : t('article.translatedScopeFull')

  return (
    <div className="page-shell py-8 md:py-10" data-testid="article-page-shell">
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]" data-testid="article-page-layout">
        <article className="min-w-0 space-y-8" data-testid="article-main-column">
          <section className="fudan-panel overflow-hidden">
            <div className="h-1 w-full bg-[linear-gradient(90deg,rgba(13,7,131,0.98),rgba(13,7,131,0.86)_60%,rgba(234,107,0,0.94))]" />
            <div className="p-6 md:p-8">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-3 text-sm text-slate-400">
                <span className="inline-flex items-center gap-2">
                  <Building2 size={16} className="text-fudan-blue" />
                  {article.primary_org_name || article.source || 'Business'}
                </span>
                <span className="inline-flex items-center gap-2">
                  <Calendar size={15} />
                  {formatDate(article.publish_date)}
                </span>
                {article.link ? (
                  <a href={article.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 text-fudan-blue">
                    {t('article.source')}
                    <ExternalLink size={14} />
                  </a>
                ) : null}
                <span
                  className={[
                    'inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold',
                    access.access_level === 'paid'
                      ? 'bg-fudan-orange/10 text-fudan-orange'
                      : access.access_level === 'member'
                        ? 'bg-fudan-blue/10 text-fudan-blue'
                        : 'bg-slate-100 text-slate-500',
                  ].join(' ')}
                >
                  {accessLabel}
                </span>
              </div>

              <h1 className="mt-5 max-w-5xl font-serif text-4xl font-black leading-[1.14] text-slate-900 md:text-[3.2rem]">
                {visibleTitle}
              </h1>
              {visibleIntro ? <p className="mt-5 max-w-4xl text-[17px] leading-8 text-slate-500">{visibleIntro}</p> : null}

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <div className="inline-flex overflow-hidden rounded-md border border-fudan-blue/15 bg-white">
                  <button
                    type="button"
                    onClick={() => setLanguage('zh')}
                    className={[
                      'px-4 py-2 text-sm font-bold transition',
                      !isEnglish ? 'bg-fudan-blue text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200',
                    ].join(' ')}
                  >
                    中文
                  </button>
                  <button
                    type="button"
                    onClick={() => setLanguage('en')}
                    className={[
                      'px-4 py-2 text-sm font-bold transition',
                      isEnglish ? 'bg-fudan-blue text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200',
                    ].join(' ')}
                  >
                    EN
                  </button>
                </div>

                {translatedActive ? (
                  <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
                    <Languages size={14} />
                    {t('article.translationBadge')}
                  </span>
                ) : null}

                {(article.tags || []).slice(0, 6).map((tag) => (
                  <TagBadge key={tag.slug} tag={tag} />
                ))}
              </div>
            </div>
          </section>

          {access.locked ? (
            <section className="fudan-panel overflow-hidden" data-testid="article-preview-gate">
              <div className="grid gap-6 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(26,69,152,0.92)_58%,rgba(234,107,0,0.22))] px-6 py-7 text-white md:px-8 md:py-8">
                <div>
                  <div className="section-kicker !text-white/70">{t('article.previewTitle')}</div>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-white/84">{accessMessage}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  {!isAuthenticated ? (
                    <button
                      type="button"
                      onClick={openAuthDialog}
                      className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-fudan-blue"
                    >
                      <Lock size={14} />
                      {authEnabled ? t('article.login') : t('navbar.authPending')}
                    </button>
                  ) : null}
                  <Link to="/membership" className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold text-white">
                    <Crown size={14} />
                    {t('article.membershipBenefits')}
                  </Link>
                </div>
              </div>
            </section>
          ) : null}

          <div className="space-y-8">
            {translationPending ? (
              <section className="fudan-panel overflow-hidden" data-testid="article-translation-pending">
                <div className="flex flex-wrap items-center gap-4 border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,251,255,0.98)_0%,rgba(255,255,255,0.92)_100%)] px-5 py-4 md:px-6">
                  <div className="flex h-11 w-11 items-center justify-center rounded-full bg-fudan-blue/10 text-fudan-blue">
                    <LoaderCircle size={20} className="animate-spin" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-serif text-xl font-black text-fudan-blue">{t('article.translating')}</div>
                    <div className="mt-1 text-sm leading-7 text-slate-500">The original article remains available while the English version loads.</div>
                  </div>
                </div>
              </section>
            ) : null}

            <section className="fudan-panel overflow-hidden" data-testid="article-summary-section">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(248,251,255,0.98)_0%,rgba(255,255,255,0.92)_100%)] px-5 py-4 md:px-6">
                <div>
                  <div className="section-kicker !mb-2">{t('article.aiSummary')}</div>
                  <div className="text-sm leading-7 text-slate-500">
                    {translatedActive ? 'Same reading layout, localized into English.' : '沿用站内阅读布局展示 AI 摘要。'}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {translatedActive ? (
                    <div className="rounded-full border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
                      {t('article.translationReady')}
                    </div>
                  ) : null}
                  {translatedActive ? (
                    <div className="rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-2 text-sm font-semibold text-fudan-blue">
                      {translatedScopeLabel}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="bg-[#fbfcff] p-3 md:p-4">
                <div
                  className={[
                    'relative overflow-hidden rounded-[1.35rem] border border-slate-200/70 bg-white shadow-[inset_0_1px_0_rgba(255,255,255,0.68)]',
                    !summaryExpanded && canCollapseSummary ? 'max-h-[23rem]' : '',
                  ].join(' ')}
                >
                  <AutoHeightPreviewFrame
                    title={translatedActive ? 'English summary preview' : 'Chinese summary preview'}
                    srcDoc={summaryDoc}
                    minHeight={220}
                    className="block w-full border-0 bg-white"
                  />
                  {!summaryExpanded && canCollapseSummary ? (
                    <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-[linear-gradient(180deg,rgba(255,255,255,0)_0%,rgba(255,255,255,0.92)_54%,rgba(255,255,255,1)_100%)]" />
                  ) : null}
                </div>
                {canCollapseSummary ? (
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      onClick={() => setSummaryExpanded((current) => !current)}
                      className="inline-flex items-center rounded-full border border-fudan-blue/15 bg-white px-4 py-2 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/35"
                    >
                      {summaryExpanded ? (isEnglish ? 'Collapse summary' : '收起摘要') : isEnglish ? 'Expand summary' : '展开摘要'}
                    </button>
                  </div>
                ) : null}
              </div>

              {translatedActive && (translation?.cached || translation?.model) ? (
                <div className="flex flex-wrap items-center gap-3 border-t border-slate-200/70 bg-white px-5 py-4 md:px-6">
                  {translation?.cached ? (
                    <div className="rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-semibold text-slate-500">Cached</div>
                  ) : null}
                  {translation?.model ? (
                    <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-500">{translation.model}</div>
                  ) : null}
                </div>
              ) : null}
            </section>

            <section className="fudan-panel overflow-hidden" data-testid="article-body-section">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 bg-[linear-gradient(180deg,rgba(255,248,242,0.92)_0%,rgba(255,255,255,0.96)_100%)] px-5 py-4 md:px-6">
                <div>
                  <div className="section-kicker !mb-2">{t('article.fullText')}</div>
                  <div className="text-sm leading-7 text-slate-500">
                    {translatedActive ? 'Template HTML keeps the English article in the same editorial rhythm.' : '正文区仅调整排版，不改变原有页面结构。'}
                  </div>
                </div>
                {access.locked ? (
                  <div className="rounded-full border border-fudan-orange/20 bg-fudan-orange/10 px-4 py-2 text-sm font-semibold text-fudan-orange">
                    {t('article.previewMode')}
                  </div>
                ) : null}
              </div>

              <div className="bg-[#fcfbf8] p-3 md:p-4">
                <div className="overflow-hidden rounded-[1.35rem] border border-slate-200/70 bg-white">
                  <AutoHeightPreviewFrame
                    title={translatedActive ? 'English article preview' : 'Chinese article preview'}
                    srcDoc={contentDoc}
                    minHeight={880}
                    className="block w-full border-0 bg-white"
                  />
                </div>
              </div>

              {access.locked ? (
                <div className="border-t border-slate-200/70 bg-white px-5 py-5 text-sm leading-7 text-slate-600 md:px-6">
                  {translatedActive && translation?.content_scope === 'preview' ? t('article.previewTranslationNote') : t('article.previewNote')}
                </div>
              ) : null}
            </section>
          </div>
        </article>

        <aside className="space-y-6 xl:sticky xl:top-24 xl:self-start" data-testid="article-sidebar">
          <section className="fudan-panel p-6">
            <div className="section-kicker">{t('article.readerPulse')}</div>
            <div className="mt-4 flex flex-wrap gap-3">
              <MetricPill icon={Eye} value={`${engagement.views ?? article.view_count ?? 0} ${t('article.realViews')}`} tone="blue" />
              <MetricPill icon={Heart} value={`${engagement.like_count ?? article.like_count ?? 0} ${t('article.likes')}`} tone="orange" />
              <MetricPill icon={Bookmark} value={`${engagement.bookmark_count ?? article.bookmark_count ?? 0} ${t('article.bookmarks')}`} tone="slate" />
            </div>
            <div className="mt-5 rounded-[1.2rem] border border-fudan-blue/10 bg-[linear-gradient(180deg,#ffffff_0%,#f8fbff_100%)] p-4">
              <div className="text-sm font-semibold text-slate-600">{membershipLabel}</div>
              <div className="mt-1 text-sm text-slate-500">{membershipStatusLabel}</div>
              {access.locked ? <div className="mt-3 text-sm leading-7 text-slate-600">{accessMessage}</div> : null}
            </div>
          </section>

          <section className="fudan-panel p-6">
            <div className="section-kicker">{t('article.interaction')}</div>
            <div className="mt-3 text-sm leading-7 text-slate-600">
              {isAuthenticated ? t('article.interactionLoggedIn') : t('article.interactionGuest')}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => handleReaction('like')}
                disabled={busyReaction === 'like'}
                className={[
                  'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition',
                  engagement.liked_by_me ? 'bg-fudan-orange text-white' : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-orange/40',
                ].join(' ')}
              >
                <Heart size={15} />
                {engagement.liked_by_me ? t('article.liked') : t('article.like')}
              </button>
              <button
                type="button"
                onClick={() => handleReaction('bookmark')}
                disabled={busyReaction === 'bookmark'}
                className={[
                  'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition',
                  engagement.bookmarked_by_me ? 'bg-fudan-blue text-white' : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
                ].join(' ')}
              >
                <Bookmark size={15} />
                {engagement.bookmarked_by_me ? t('article.bookmarked') : t('article.bookmark')}
              </button>
            </div>
            {statusHint ? <div className="mt-3 text-sm text-slate-500">{statusHint}</div> : null}
            {isEnglish ? <div className="mt-3 text-sm leading-7 text-slate-500">{t('article.translationHint')}</div> : null}
            {translationError ? <div className="mt-3 text-sm text-rose-600">{translationError}</div> : null}
            {!isAuthenticated ? (
              <button
                type="button"
                onClick={openAuthDialog}
                className="mt-4 inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-2 text-sm font-semibold text-fudan-blue"
              >
                <Lock size={14} />
                {t('article.login')}
              </button>
            ) : null}
          </section>

          {article.topics?.length ? (
            <section className="fudan-panel p-6">
              <div className="section-kicker">{t('article.relatedTopics')}</div>
              <div className="mt-4 space-y-4">
                {article.topics.map((topic) => (
                  <Link key={topic.slug} to={`/topic/${topic.slug}`} className="block rounded-[1.2rem] border border-slate-200/70 p-4 transition hover:bg-slate-50">
                    <div className="font-serif text-xl font-bold text-fudan-blue">{topic.title}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">{topic.description}</div>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {article.related_articles?.length ? (
            <section className="space-y-4" data-testid="article-related-recommendations">
              <div className="section-kicker">{t('article.relatedRecommendations')}</div>
              {isEnglish && relatedTranslationsLoading && Object.keys(relatedTranslations).length === 0 ? (
                Array.from({ length: Math.min(article.related_articles.length, 3) }, (_, index) => (
                  <div key={`related-loading-${index}`} className="fudan-panel p-6 text-sm text-slate-500">
                    {translationLoading ? 'Loading English recommendations...' : 'Preparing related reads...'}
                  </div>
                ))
              ) : (
                relatedArticles.map((item) => <ArticleCard key={item.id} article={item} compact />)
              )}
            </section>
          ) : null}

          <section className="fudan-panel p-6">
            <div className="section-kicker">{t('article.membershipEntry')}</div>
            <div className="font-serif text-2xl font-black text-fudan-blue">{t('article.membershipEntryTitle')}</div>
            <p className="mt-4 text-sm leading-7 text-slate-600">{t('article.membershipEntryBody')}</p>
            <Link
              to="/membership"
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
            >
              {t('article.membershipBenefits')}
              <ArrowRight size={16} />
            </Link>
          </section>
        </aside>
      </div>
    </div>
  )
}

export default ArticlePage
