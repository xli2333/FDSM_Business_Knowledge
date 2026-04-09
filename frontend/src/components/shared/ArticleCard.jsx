import { ArrowRight, Bookmark, Eye, Heart } from 'lucide-react'
import { Link } from 'react-router-dom'
import { resolveApiUrl } from '../../api/index.js'
import { useLanguage } from '../../i18n/LanguageContext.js'
import { formatDate, truncate } from '../../utils/formatters.js'
import TagBadge from './TagBadge.jsx'

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

function ArticleCard({ article, compact = false }) {
  const { language, t } = useLanguage()
  const firstColumn = article.columns?.[0]
  const coverUrl = resolveApiUrl(article.cover_url)
  const accessLabel = ACCESS_LABELS[language]?.[article.access_level] || article.access_label || t('articleCard.public')

  return (
    <article className={`fudan-card overflow-hidden ${compact ? '' : 'h-full'}`}>
      <Link to={`/article/${article.id}`} className="flex h-full flex-col">
        <div className="relative overflow-hidden">
          {coverUrl ? (
            <img src={coverUrl} alt={article.title} className="h-52 w-full object-cover" loading="lazy" />
          ) : (
            <div className="h-52 w-full bg-[linear-gradient(135deg,rgba(13,7,131,0.95),rgba(10,5,96,0.72)_55%,rgba(234,107,0,0.52))]">
              <div className="flex h-full items-end p-6">
                <span className="rounded-full border border-white/30 bg-white/10 px-3 py-1 text-xs uppercase tracking-[0.26em] text-white/80">
                  {article.article_type || 'Business'}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-1 flex-col p-6">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span
              className={[
                'rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em]',
                article.access_level === 'paid'
                  ? 'bg-fudan-orange/10 text-fudan-orange'
                  : article.access_level === 'member'
                    ? 'bg-fudan-blue/10 text-fudan-blue'
                    : 'bg-slate-100 text-slate-500',
              ].join(' ')}
            >
              {accessLabel}
            </span>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {(article.tags || []).slice(0, compact ? 2 : 3).map((tag) => (
              <TagBadge key={`${article.id}-${tag.slug}`} tag={tag} />
            ))}
          </div>

          <h3 className={`font-serif font-black leading-tight text-fudan-blue ${compact ? 'text-xl' : 'text-2xl'}`}>{article.title}</h3>
          <p className="mt-4 flex-1 text-sm leading-7 text-slate-600">
            {truncate(article.excerpt || article.main_topic || '', compact ? 92 : 150)}
          </p>

          <div className="mt-6 paper-divider pt-4">
            <div className="flex items-center justify-between gap-4 text-xs uppercase tracking-[0.24em] text-slate-400">
              <span>{formatDate(article.publish_date)}</span>
              {firstColumn ? <span className="text-fudan-blue">{firstColumn.name}</span> : null}
            </div>
            <div className="mt-3 inline-flex items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400">
              <Eye size={14} />
              {article.view_count || 0} {t('articleCard.views')}
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs uppercase tracking-[0.18em] text-slate-400">
              <span className="inline-flex items-center gap-2">
                <Heart size={14} />
                {article.like_count || 0} {t('articleCard.likes')}
              </span>
              <span className="inline-flex items-center gap-2">
                <Bookmark size={14} />
                {article.bookmark_count || 0} {t('articleCard.bookmarks')}
              </span>
            </div>
            <div className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-fudan-orange">
              {t('articleCard.read')}
              <ArrowRight size={16} />
            </div>
          </div>
        </div>
      </Link>
    </article>
  )
}

export default ArticleCard
