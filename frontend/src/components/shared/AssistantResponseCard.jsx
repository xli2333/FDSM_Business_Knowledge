import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import AssistantMarkdown from './AssistantMarkdown.jsx'

function AssistantResponseCard({
  label,
  content,
  dataScope = 'assistant',
  sources = [],
  showSources = false,
  sourceTitle = '',
  openArticleLabel = '',
  className = '',
  wrapperProps = {},
}) {
  const visibleSources = Array.isArray(sources) ? sources.filter((item) => item && item.id) : []

  return (
    <div
      className={['rounded-[1rem] border border-slate-200 bg-white p-5 shadow-[0_8px_24px_rgba(15,23,42,0.04)]', className].filter(Boolean).join(' ')}
      {...wrapperProps}
    >
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-fudan-orange">{label}</div>
      <div className="knowledge-markdown text-base leading-8" data-assistant-response-content={dataScope}>
        <AssistantMarkdown content={content} className="text-base leading-8" dataScope={dataScope} />
      </div>

      {showSources && visibleSources.length ? (
        <div className="mt-5 border-t border-slate-200 pt-4" data-assistant-response-sources={dataScope}>
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">{sourceTitle}</div>
          <ol className="divide-y divide-slate-200 overflow-hidden rounded-[0.9rem] border border-slate-200 bg-slate-50/60">
            {visibleSources.map((item, index) => (
              <li key={`${dataScope}-${item.id}`}>
                <Link
                  to={`/article/${item.id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-3 px-4 py-3 text-sm text-slate-600 transition hover:bg-white hover:text-fudan-blue"
                  title={openArticleLabel || item.title}
                >
                  <span className="w-8 shrink-0 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-semibold leading-6 text-fudan-blue">{item.title}</span>
                  <ArrowUpRight size={14} className="shrink-0 text-slate-400" />
                </Link>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  )
}

export default AssistantResponseCard
