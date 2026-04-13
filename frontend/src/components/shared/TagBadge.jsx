import { Link } from 'react-router-dom'
import { encodeRoutePart } from '../../utils/formatters.js'

const CATEGORY_STYLES = {
  industry: 'border-fudan-orange/30 bg-fudan-orange/10 text-fudan-orange',
  topic: 'border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue',
  type: 'border-indigo-200 bg-indigo-50 text-indigo-700',
  entity: 'border-slate-200 bg-slate-100 text-slate-600',
  series: 'border-purple-200 bg-purple-50 text-purple-700',
}

const VARIANT_STYLES = {
  default: '',
  inverse: 'border-white/20 bg-white/10 text-white hover:border-white/35 hover:bg-white/16',
}

function TagBadge({ tag, clickable = true, variant = 'default' }) {
  const className = [
    'inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold transition',
    variant === 'inverse' ? VARIANT_STYLES.inverse : CATEGORY_STYLES[tag.category] || CATEGORY_STYLES.topic,
  ].join(' ')

  if (!clickable) {
    return <span className={className}>{tag.name}</span>
  }

  return (
    <Link to={`/tag/${encodeRoutePart(tag.slug)}`} className={`${className} hover:-translate-y-0.5`}>
      {tag.name}
    </Link>
  )
}

export default TagBadge
