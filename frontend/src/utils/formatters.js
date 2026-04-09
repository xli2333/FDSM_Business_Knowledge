export function formatDate(value) {
  if (!value) return ''
  try {
    const [year, month, day] = value.split('-')
    return `${year}.${month}.${day}`
  } catch {
    return value
  }
}

export function truncate(text, limit = 120) {
  if (!text) return ''
  if (text.length <= limit) return text
  return `${text.slice(0, limit).trim()}...`
}

export function encodeRoutePart(value) {
  return encodeURIComponent(value)
}

export function formatTopicType(value, isEnglish = false) {
  switch (value) {
    case 'seed':
      return isEnglish ? 'Core topic' : '主线专题'
    case 'auto':
      return isEnglish ? 'Auto topic' : '自动专题'
    case 'editorial':
      return isEnglish ? 'Editorial topic' : '编辑精选'
    case 'timeline':
      return isEnglish ? 'Timeline' : '时间线'
    default:
      return value || (isEnglish ? 'Topic' : '专题')
  }
}
