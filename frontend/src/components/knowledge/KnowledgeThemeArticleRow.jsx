import { Check, ExternalLink, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

function KnowledgeThemeArticleRow({ article, checked = false, removing = false, onToggleChecked, onRemove, copy }) {
  const source = article.columns?.[0]?.name || article.source || article.article_type || copy.defaultSource

  return (
    <div
      className={[
        'group border-b border-slate-200 px-4 py-4 transition last:border-b-0 md:px-5',
        checked ? 'bg-slate-950 text-white' : 'bg-white hover:bg-slate-50',
      ].join(' ')}
      data-knowledge-article-row={article.id}
    >
      <div className="flex items-start gap-4">
        <button
          type="button"
          onClick={onToggleChecked}
          className={[
            'mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[0.75rem] border transition',
            checked
              ? 'border-white/18 bg-white/12 text-white'
              : 'border-slate-300 bg-white text-transparent group-hover:border-fudan-blue/35 group-hover:text-fudan-blue',
          ].join(' ')}
          aria-label={checked ? copy.unselectArticle : copy.selectArticle}
          title={checked ? copy.unselectArticle : copy.selectArticle}
          data-knowledge-article-toggle={article.id}
        >
          <Check size={15} />
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className={['text-lg font-semibold leading-8', checked ? 'text-white' : 'text-slate-800'].join(' ')}>{article.title}</div>
              <div className={['mt-2 text-sm', checked ? 'text-white/64' : 'text-slate-400'].join(' ')}>
                {copy.columnLabel} · {source}
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2 pt-0.5">
              <Link
                to={`/article/${article.id}`}
                className={[
                  'inline-flex h-9 w-9 items-center justify-center rounded-[0.8rem] border transition',
                  checked
                    ? 'border-white/16 text-white/78 hover:bg-white/10 hover:text-white'
                    : 'border-slate-200 text-slate-500 hover:border-fudan-blue/30 hover:text-fudan-blue',
                ].join(' ')}
                aria-label={copy.openArticle}
                title={copy.openArticle}
              >
                <ExternalLink size={16} />
              </Link>

              <button
                type="button"
                onClick={onRemove}
                disabled={removing}
                className={[
                  'inline-flex h-9 w-9 items-center justify-center rounded-[0.8rem] border transition disabled:cursor-not-allowed disabled:opacity-55',
                  checked
                    ? 'border-white/16 text-white/78 hover:bg-white/10 hover:text-white'
                    : 'border-slate-200 text-slate-500 hover:border-rose-300 hover:text-rose-600',
                ].join(' ')}
                aria-label={copy.removeArticle}
                title={copy.removeArticle}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default KnowledgeThemeArticleRow
