import ReactMarkdown from 'react-markdown'

const VARIANT_CLASS = {
  card: {
    root: 'text-sm text-slate-600',
    paragraph: 'mt-3 text-sm leading-7 text-slate-600 first:mt-0',
    heading2: 'mt-4 font-serif text-xl font-black leading-tight text-fudan-blue first:mt-0',
    heading3: 'mt-4 text-sm font-semibold uppercase tracking-[0.16em] text-fudan-orange first:mt-0',
  },
  panel: {
    root: 'text-sm text-slate-600',
    paragraph: 'mt-3 text-sm leading-7 text-slate-600 first:mt-0',
    heading2: 'mt-5 font-serif text-2xl font-black leading-tight text-fudan-blue first:mt-0',
    heading3: 'mt-4 text-sm font-semibold uppercase tracking-[0.16em] text-fudan-orange first:mt-0',
  },
}

function MediaMarkdownBlock({ content, variant = 'panel', className = '', dataScope }) {
  const styles = VARIANT_CLASS[variant] || VARIANT_CLASS.panel

  if (!String(content || '').trim()) {
    return null
  }

  return (
    <div
      data-media-markdown={dataScope || variant}
      className={[styles.root, '[&_*]:break-words', className].filter(Boolean).join(' ')}
    >
      <ReactMarkdown
        components={{
          p: ({ node, ...props }) => <p className={styles.paragraph} {...props} />,
          h1: ({ node, ...props }) => <h2 className={styles.heading2} {...props} />,
          h2: ({ node, ...props }) => <h2 className={styles.heading2} {...props} />,
          h3: ({ node, ...props }) => <h3 className={styles.heading3} {...props} />,
          strong: ({ node, ...props }) => <strong className="font-semibold text-fudan-blue" {...props} />,
          em: ({ node, ...props }) => <em className="italic text-slate-500" {...props} />,
          ul: ({ node, ...props }) => <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-slate-600 first:mt-0" {...props} />,
          ol: ({ node, ...props }) => <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-7 text-slate-600 first:mt-0" {...props} />,
          li: ({ node, ...props }) => <li className="pl-1 marker:text-fudan-orange" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote
              className="mt-4 border-l-2 border-fudan-orange/35 bg-fudan-orange/5 px-4 py-3 text-sm leading-7 text-slate-600 first:mt-0"
              {...props}
            />
          ),
          a: ({ node, ...props }) => <a className="font-medium text-fudan-blue underline underline-offset-4" {...props} />,
          code: ({ inline, node, ...props }) =>
            inline ? (
              <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.92em] text-fudan-blue" {...props} />
            ) : (
              <code className="block rounded-[1rem] bg-slate-950/95 px-4 py-3 text-sm leading-7 text-slate-100" {...props} />
            ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default MediaMarkdownBlock
