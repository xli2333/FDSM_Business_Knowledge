import { ArrowRight, CalendarDays, Sparkles, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../../i18n/LanguageContext.js'
import { formatDate, truncate } from '../../utils/formatters.js'

function KnowledgeThemeCard({ theme, onRequestDelete, deleting = false }) {
  const { isEnglish } = useLanguage()
  const previewArticles = (theme.preview_articles || []).slice(0, 2)
  const watermark = String(theme.title || 'K').trim().slice(0, 1).toUpperCase()

  return (
    <article className="knowledge-console-card group min-h-[18.5rem]" data-knowledge-theme-card={theme.slug}>
      <div className="pointer-events-none absolute bottom-0 right-4 font-serif text-[7rem] font-black leading-none text-slate-100">
        {watermark}
      </div>

      {onRequestDelete ? (
        <button
          type="button"
          onClick={() => onRequestDelete(theme)}
          disabled={deleting}
          className="absolute right-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 opacity-0 shadow-sm transition hover:border-rose-300 hover:text-rose-600 group-hover:opacity-100 group-focus-within:opacity-100 disabled:cursor-not-allowed disabled:opacity-60"
          aria-label={isEnglish ? `Delete ${theme.title}` : `删除 ${theme.title}`}
          data-knowledge-theme-delete-button={theme.slug}
        >
          <X size={15} />
        </button>
      ) : null}

      <div className="relative flex h-full flex-col">
        <div className="flex items-start gap-4">
          <div className="min-w-0 flex-1 pr-3">
            <h2 className="font-serif text-[2.15rem] font-black leading-tight text-fudan-blue">{theme.title}</h2>
            {theme.description ? <p className="mt-4 max-w-[26rem] text-base leading-8 text-slate-600">{truncate(theme.description, 120)}</p> : null}
          </div>

          <div className="ml-auto flex h-[7rem] w-[7rem] shrink-0 flex-col items-center justify-center rounded-[1rem] border border-slate-200 bg-slate-50 text-center">
            <div className="knowledge-console-label">{isEnglish ? 'Articles' : '文章数'}</div>
            <div className="mt-2 font-serif text-4xl font-black leading-none text-fudan-orange">{theme.article_count || 0}</div>
          </div>
        </div>

        <div className="mt-6 flex-1">
          <div className="knowledge-console-label">{isEnglish ? 'Articles' : '文章'}</div>
          {previewArticles.length ? (
            <div className="mt-3 space-y-3">
              {previewArticles.map((item) => (
                <Link
                  key={`${theme.slug}-${item.id}`}
                  to={`/article/${item.id}`}
                  className="block rounded-[0.8rem] border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm transition hover:border-fudan-blue/25 hover:bg-white"
                >
                  <div className="line-clamp-2 text-base font-semibold leading-7 text-slate-700">{item.title}</div>
                  <div className="mt-2 text-[11px] uppercase tracking-[0.16em] text-slate-400">{formatDate(item.publish_date)}</div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="mt-3 rounded-[0.8rem] border border-dashed border-slate-300 bg-slate-50 px-4 py-4 text-sm leading-7 text-slate-500">
              <span className="inline-flex items-center gap-2 text-fudan-orange">
                <Sparkles size={14} />
                {isEnglish ? 'No article filed yet. Start from an article page.' : '还没有收录文章，先去文章详情页把内容加入主题。'}
              </span>
            </div>
          )}
        </div>

        <div className="knowledge-console-divider mt-5 pt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-slate-400">
              <CalendarDays size={14} />
              {formatDate(theme.latest_publish_date || theme.updated_at?.slice(0, 10)) || '--'}
            </div>

            <Link to={`/me/knowledge/${theme.slug}`} className="knowledge-console-tool-button border-fudan-blue/15 bg-fudan-blue/[0.04] text-fudan-blue hover:bg-fudan-blue hover:text-white">
              {isEnglish ? 'Open theme' : '进入主题库'}
              <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      </div>
    </article>
  )
}

export default KnowledgeThemeCard
