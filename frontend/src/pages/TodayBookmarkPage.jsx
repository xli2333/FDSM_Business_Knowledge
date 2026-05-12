import { ArrowLeft, BookOpen, RefreshCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchTodayBookmark } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import TodayBookmarkCanvas from '../components/bookmark/TodayBookmarkCanvas.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

function TodayBookmarkPage() {
  const { accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [bookmark, setBookmark] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')
  const displayTheme = bookmark?.headline_theme || bookmark?.primary_theme || (isEnglish ? 'Pending' : '待生成')

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      try {
        const payload = await fetchTodayBookmark(accessToken, { language: isEnglish ? 'en' : 'zh' })
        if (!active) return
        setBookmark(payload)
        setError('')
      } catch (loadError) {
        if (!active) return
        setError(loadError.message || (isEnglish ? 'Failed to load today bookmark.' : '今日书签加载失败。'))
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [accessToken, isEnglish])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const payload = await fetchTodayBookmark(accessToken, {
        language: isEnglish ? 'en' : 'zh',
        forceRefresh: true,
      })
      setBookmark(payload)
      setError('')
    } catch (loadError) {
      setError(loadError.message || (isEnglish ? 'Failed to regenerate today bookmark.' : '重新生成今日书签失败。'))
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_56%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.04fr_0.96fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Daily Bookmark' : '今日书签'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
              {isEnglish ? 'Turn today’s reading into a personal bookmark' : '把今天的阅读变成一张个人书签'}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'Everything here comes from articles you actually read today. The system compresses them into one dominant theme, then lets you drag that theme and watch the surrounding phrases reflow.'
                : '系统会把你今天真实看过的文章压缩成一个主主题，再把当天阅读里的文字排成一张可拖动主题词的书签。'}
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/me?tab=history" className="knowledge-console-tool-button border-white/20 bg-white/10 text-white hover:bg-white hover:text-fudan-blue">
                <ArrowLeft size={16} />
                {isEnglish ? 'Back to library' : '回到资料库'}
              </Link>
              <button type="button" onClick={handleRefresh} className="knowledge-console-tool-button border-white/20 bg-white/10 text-white hover:bg-white hover:text-fudan-blue">
                <RefreshCcw size={16} className={refreshing ? 'animate-spin' : ''} />
                {refreshing ? (isEnglish ? 'Refreshing' : '重新生成中') : isEnglish ? 'Regenerate' : '重新生成'}
              </button>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Date' : '日期'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{bookmark?.date_label || '--'}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">{bookmark?.weekday_label || '--'}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Theme' : '主题'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{displayTheme}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">{bookmark?.theme_reason || (isEnglish ? 'Waiting for your reading today.' : '等待今天的阅读生成。')}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Articles today' : '今日文章'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{bookmark?.article_count || 0}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish ? 'Distinct articles included in this bookmark.' : '被纳入这张书签的今日阅读文章数。'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      {loading ? (
        <div className="mt-8 fudan-panel p-8 text-sm text-slate-500">{isEnglish ? 'Building today bookmark…' : '正在生成今日书签…'}</div>
      ) : bookmark?.available ? (
        <div className="mt-8 grid gap-8 xl:grid-cols-[0.72fr_0.28fr]">
          <section className="fudan-panel p-6 md:p-8">
            <div className="section-kicker">{isEnglish ? 'Visual bookmark' : '视觉书签'}</div>
            <h2 className="font-serif text-3xl font-black text-fudan-blue">{isEnglish ? 'Drag the core theme' : '拖动中心主题词'}</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              {isEnglish
                ? 'Move the theme block inside the bookmark. The surrounding phrases come only from what you read today and reflow in real time.'
                : '你可以在书签内部拖动中心主题。周围所有短语都来自今天的阅读，并会实时重新绕排。'}
            </p>
            <div className="mt-8 flex justify-center">
              <TodayBookmarkCanvas bookmark={bookmark} />
            </div>
          </section>

          <div className="space-y-6">
            <section className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Theme hints' : '主题线索'}</div>
              <h3 className="font-serif text-2xl font-black text-fudan-blue">{isEnglish ? 'Signals behind today theme' : '支撑今日主题的线索'}</h3>
              <div className="mt-4 flex flex-wrap gap-2">
                {(bookmark.theme_hints || []).map((item) => (
                  <span key={`${item.label}-${item.weight}`} className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/12 bg-fudan-blue/[0.04] px-3 py-2 text-sm font-semibold text-fudan-blue">
                    {item.label}
                    <span className="text-xs text-slate-400">{item.weight}</span>
                  </span>
                ))}
              </div>
            </section>

            <section className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Source articles' : '来源文章'}</div>
              <h3 className="font-serif text-2xl font-black text-fudan-blue">{isEnglish ? 'Included from today’s reading' : '今天被纳入书签的文章'}</h3>
              <div className="mt-4 space-y-3">
                {(bookmark.source_articles || []).map((article, index) => (
                  <Link key={`bookmark-source-${article.id}`} to={`/article/${article.id}`} className="block rounded-[1.2rem] border border-slate-200 bg-white px-4 py-4 transition hover:border-fudan-blue/30 hover:bg-slate-50">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">
                      {String(index + 1).padStart(2, '0')} / {article.publish_date}
                    </div>
                    <div className="mt-2 text-base font-semibold leading-7 text-slate-800">{article.title}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-500">{article.excerpt}</div>
                  </Link>
                ))}
              </div>
              <div className="mt-5">
                <Link to="/me/knowledge" className="knowledge-console-secondary">
                  <BookOpen size={16} />
                  {isEnglish ? 'Open knowledge base' : '打开知识库'}
                </Link>
              </div>
            </section>
          </div>
        </div>
      ) : (
        <section className="mt-8 fudan-panel p-8">
          <div className="section-kicker">{isEnglish ? 'No reading yet' : '暂无书签'}</div>
          <h2 className="font-serif text-3xl font-black text-fudan-blue">
            {bookmark?.empty_message || (isEnglish ? 'Read first, then come back.' : '先阅读，再回来。')}
          </h2>
          <p className="mt-4 text-sm leading-7 text-slate-600">
            {isEnglish
              ? 'This bookmark is generated only from articles you actually opened today.'
              : '今日书签只会基于你今天真实打开过的文章生成。'}
          </p>
        </section>
      )}
    </div>
  )
}

export default TodayBookmarkPage
