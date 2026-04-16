import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { normalizeChatMarkdown } from '../../lib/chatMarkdown.js'

function TableShell({ children }) {
  return (
    <div className="mt-4 overflow-x-auto rounded-[0.95rem] border border-slate-200 bg-white">
      <table className="min-w-full border-collapse text-left text-sm leading-7 text-slate-700">{children}</table>
    </div>
  )
}

function AssistantMarkdown({ content, className = '', dataScope }) {
  const normalizedContent = normalizeChatMarkdown(content)

  if (!normalizedContent) {
    return null
  }

  return (
    <div
      className={['assistant-markdown text-sm leading-7 text-slate-700 [&_*]:break-words', className].filter(Boolean).join(' ')}
      data-assistant-markdown={dataScope || 'assistant'}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ node, ...props }) => <p className="mt-3 first:mt-0" {...props} />,
          h1: ({ node, ...props }) => <h2 className="mt-5 font-serif text-2xl font-black leading-tight text-fudan-blue first:mt-0" {...props} />,
          h2: ({ node, ...props }) => <h2 className="mt-5 font-serif text-2xl font-black leading-tight text-fudan-blue first:mt-0" {...props} />,
          h3: ({ node, ...props }) => <h3 className="mt-4 text-sm font-semibold uppercase tracking-[0.16em] text-fudan-orange first:mt-0" {...props} />,
          h4: ({ node, ...props }) => <h4 className="mt-4 text-sm font-semibold text-fudan-blue first:mt-0" {...props} />,
          strong: ({ node, ...props }) => <strong className="font-semibold text-fudan-blue" {...props} />,
          em: ({ node, ...props }) => <em className="italic text-slate-500" {...props} />,
          ul: ({ node, ...props }) => <ul className="mt-3 list-disc space-y-2 pl-5 first:mt-0" {...props} />,
          ol: ({ node, ...props }) => <ol className="mt-3 list-decimal space-y-2 pl-5 first:mt-0" {...props} />,
          li: ({ node, ...props }) => <li className="pl-1 marker:text-fudan-orange" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="mt-4 border-l-2 border-fudan-orange/35 bg-fudan-orange/5 px-4 py-3 text-sm leading-7 text-slate-600 first:mt-0"
              {...props}
            />
          ),
          a: ({ node, ...props }) => <a className="font-medium text-fudan-blue underline underline-offset-4" {...props} />,
          hr: ({ node, ...props }) => <hr className="my-5 border-0 border-t border-slate-200" {...props} />,
          table: ({ node, ...props }) => <TableShell {...props} />,
          thead: ({ node, ...props }) => <thead className="bg-slate-50" {...props} />,
          tbody: ({ node, ...props }) => <tbody {...props} />,
          tr: ({ node, isHeader, ...props }) => <tr className={!isHeader ? 'border-t border-slate-200' : ''} {...props} />,
          th: ({ node, align, ...props }) => (
            <th
              className="border-b border-slate-200 px-4 py-3 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
              style={align ? { textAlign: align } : undefined}
              {...props}
            />
          ),
          td: ({ node, align, ...props }) => (
            <td className="px-4 py-3 align-top text-sm leading-7 text-slate-700" style={align ? { textAlign: align } : undefined} {...props} />
          ),
          code: ({ inline, node, className: codeClassName, ...props }) =>
            inline ? (
              <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.92em] text-fudan-blue" {...props} />
            ) : (
              <code className={['block rounded-[1rem] bg-slate-950/95 px-4 py-3 text-sm leading-7 text-slate-100', codeClassName].filter(Boolean).join(' ')} {...props} />
            ),
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  )
}

export default AssistantMarkdown
