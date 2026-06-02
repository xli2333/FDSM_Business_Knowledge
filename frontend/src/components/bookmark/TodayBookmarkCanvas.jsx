import { useMemo } from 'react'

const BOOKMARK_WIDTH = 430
const BOOKMARK_HEIGHT = 1180
const QR_LABEL = '知识库入口'

const STOPWORD_PATTERN =
  /(什么|为何|为什么|如何|看到|出现|不是|然而|但是|因为|这个|那个|一种|一场|一位|一个|今天|公司|专题|观察|研究|前沿|趋势|洞察|观点|管理|影响|解释|说明|分析|文章|内容|阅读|知识库|复旦观点|案例决策|产业圆桌|热点拆解|管理视野|复理学堂|专题广场|复旦管院|老师|同学|企业家|有了|这种|而是|如果|以及|我们|你们|他们|帮忙|正在|已经|简单|复杂|只是|不是|这样|那个|这个)/

const HERO_SLOTS = [
  { x: 216, y: 258, size: 28, tone: 'orange', align: 'center' },
  { x: 184, y: 300, size: 52, tone: 'orange', align: 'center' },
  { x: 182, y: 352, size: 60, tone: 'orange', align: 'center' },
  { x: 334, y: 356, size: 44, tone: 'blue', align: 'center' },
  { x: 86, y: 396, size: 28, tone: 'orange', align: 'center' },
  { x: 152, y: 412, size: 50, tone: 'orange', align: 'center' },
  { x: 328, y: 410, size: 38, tone: 'blue', align: 'center' },
  { x: 382, y: 394, size: 18, tone: 'orange', align: 'center' },
  { x: 50, y: 470, size: 16, tone: 'blue', vertical: true },
  { x: 78, y: 484, size: 20, tone: 'blue', vertical: true },
  { x: 108, y: 520, size: 18, tone: 'blue', vertical: true },
  { x: 142, y: 560, size: 16, tone: 'blue', vertical: true },
  { x: 322, y: 494, size: 18, tone: 'blue', vertical: true },
  { x: 350, y: 464, size: 22, tone: 'blue', vertical: true },
  { x: 382, y: 518, size: 18, tone: 'orange', vertical: true },
  { x: 394, y: 582, size: 16, tone: 'orange', vertical: true },
  { x: 72, y: 620, size: 38, tone: 'orange', align: 'center' },
  { x: 122, y: 654, size: 22, tone: 'blue', align: 'center' },
  { x: 202, y: 668, size: 20, tone: 'blue', align: 'center' },
  { x: 304, y: 624, size: 24, tone: 'orange', align: 'center' },
  { x: 350, y: 654, size: 40, tone: 'blue', align: 'center' },
  { x: 92, y: 704, size: 22, tone: 'orange', align: 'center' },
  { x: 318, y: 708, size: 22, tone: 'orange', align: 'center' },
  { x: 58, y: 760, size: 18, tone: 'blue', align: 'center' },
  { x: 100, y: 786, size: 18, tone: 'blue', align: 'center' },
  { x: 196, y: 790, size: 46, tone: 'blue', align: 'center' },
  { x: 314, y: 792, size: 26, tone: 'blue', align: 'center' },
  { x: 368, y: 784, size: 16, tone: 'blue', align: 'center' },
  { x: 214, y: 846, size: 62, tone: 'blue', align: 'center' },
  { x: 82, y: 878, size: 26, tone: 'blue', align: 'center' },
  { x: 350, y: 882, size: 22, tone: 'orange', align: 'center' },
  { x: 62, y: 924, size: 18, tone: 'blue', align: 'center' },
  { x: 92, y: 950, size: 16, tone: 'blue', align: 'center' },
  { x: 214, y: 960, size: 66, tone: 'orange', align: 'center' },
  { x: 356, y: 956, size: 22, tone: 'orange', align: 'center' },
  { x: 62, y: 1004, size: 18, tone: 'blue', align: 'center' },
  { x: 140, y: 1018, size: 18, tone: 'blue', align: 'center' },
  { x: 206, y: 1044, size: 22, tone: 'blue', align: 'center' },
  { x: 304, y: 1048, size: 58, tone: 'blue', align: 'center' },
  { x: 94, y: 1088, size: 18, tone: 'orange', align: 'center' },
  { x: 202, y: 1102, size: 20, tone: 'blue', align: 'center' },
  { x: 314, y: 1098, size: 18, tone: 'blue', align: 'center' },
]

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function normalizeDisplayToken(raw) {
  const value = String(raw || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[^A-Za-z0-9\u4e00-\u9fff&+#.-]+|[^A-Za-z0-9\u4e00-\u9fff&+#.-]+$/g, '')
  if (!value) return ''
  const hasCjk = /[\u4e00-\u9fff]/.test(value)
  if (value.length < 2) return ''
  if (hasCjk && value.length > 8) return ''
  if (!hasCjk && value.length > 18) return ''
  if (STOPWORD_PATTERN.test(value)) return ''
  if (/^\d+$/.test(value)) return ''
  return value
}

function extractDisplayPhrases(text) {
  const source = String(text || '').replace(/\s+/g, ' ').trim()
  if (!source) return []

  const tokens = new Set()
  const push = (value) => {
    const normalized = normalizeDisplayToken(value)
    if (normalized) tokens.add(normalized)
  }

  push(source)

  source
    .split(/[|/，,、；;：:]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      push(item)
      item
        .split(/(?<=[\u4e00-\u9fffA-Za-z0-9])(?:的|与|和|及|在|向|从)(?=[\u4e00-\u9fffA-Za-z0-9])/)
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach(push)
    })

  source
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach(push)

  return [...tokens]
}

function estimateWidth(text, fontSize, vertical) {
  if (vertical) return Math.round(fontSize * 1.05)
  const hasCjk = /[\u4e00-\u9fff]/.test(text)
  const perChar = hasCjk ? fontSize * 0.94 : fontSize * 0.56
  return Math.round(text.length * perChar)
}

function buildThemeKeywords(theme, headlineTheme, themeHints) {
  const keywords = new Set()
  const register = (value) => {
    const normalized = normalizeDisplayToken(value)
    if (!normalized) return
    keywords.add(normalized)
    if (/[\u4e00-\u9fff]/.test(normalized)) {
      if (normalized.length >= 4) {
        keywords.add(normalized.slice(0, 2))
        keywords.add(normalized.slice(-2))
        keywords.add(normalized.slice(0, 4))
        keywords.add(normalized.slice(-4))
      }
      if (normalized.length >= 6) keywords.add(normalized.slice(2, 4))
    }
    String(normalized)
      .split(/[&/、，,；;：:\s]+/)
      .map((item) => normalizeDisplayToken(item))
      .filter(Boolean)
      .forEach((item) => keywords.add(item))
  }

  register(theme)
  register(headlineTheme)
  ;(themeHints || []).slice(0, 8).forEach((item) => register(item?.label || ''))
  return [...keywords]
}

function buildDisplayItems(phrases, theme, headlineTheme, themeHints) {
  const registry = new Map()
  const slotLimit = buildPosterSlots().length
  const themeKeywords = buildThemeKeywords(theme, headlineTheme, themeHints)

  const register = (token, phrase, index) => {
    const normalized = normalizeDisplayToken(token)
    if (!normalized) return
    if (normalized === theme || normalized === headlineTheme) return
    if (phrase.emphasis < 3 && (/[\s]/.test(normalized) || normalized.length > 4)) return
    if (/[。.，,；;！!？?]/.test(normalized)) return
    if (normalized.includes(theme) && normalized.length > Math.max(String(theme || '').length + 2, 4)) return
    const current = registry.get(normalized)
    const themeHit = themeKeywords.some((keyword) => keyword && (normalized.includes(keyword) || keyword.includes(normalized)))
    if (!themeHit && Number(phrase.emphasis || 2) < 3) return
    if (!themeHit && /^[A-Za-z0-9 .&+-]+$/.test(normalized)) return
    if (!themeHit && /[\u4e00-\u9fff]/.test(normalized) && normalized.length > 4) return
    if (!themeHit && !/[\u4e00-\u9fff]/.test(normalized) && normalized.length > 10) return
    const lengthBoost = normalized.length <= 2 ? 4 : normalized.length <= 4 ? 3 : normalized.length <= 6 ? 2 : 0
    const emphasis = clamp(Number(phrase.emphasis || 2) + lengthBoost + (themeHit ? 3 : 0), 1, 5)
    const score = emphasis * 12 + (index < 12 ? 8 : 0) - Math.max(0, normalized.length - 5)

    if (current) {
      current.score += score
      current.emphasis = Math.max(current.emphasis, emphasis)
      return
    }

    registry.set(normalized, {
      text: normalized,
      emphasis,
      score,
      tone: phrase.tone === 'slate' ? (index % 3 === 0 ? 'orange' : 'blue') : phrase.tone,
    })
  }

  phrases.forEach((phrase, index) => {
    extractDisplayPhrases(phrase.text).forEach((token) => register(token, phrase, index))
  })

  const ranked = [...registry.values()].sort((left, right) => {
    if (right.score !== left.score) return right.score - left.score
    if (right.emphasis !== left.emphasis) return right.emphasis - left.emphasis
    return left.text.length - right.text.length
  })

  const limited = []
  const seen = new Set()
  const seenFirstChar = new Map()

  for (const item of ranked) {
    const key = item.text.toLowerCase()
    if (seen.has(key)) continue
    const firstChar = item.text.slice(0, 1)
    const firstCharCount = seenFirstChar.get(firstChar) || 0
    if (item.text.length <= 2 && firstCharCount >= 2) continue
    if (item.text.length >= 4 && limited.some((entry) => entry.text.includes(item.text) || item.text.includes(entry.text))) {
      continue
    }
    seen.add(key)
    seenFirstChar.set(firstChar, firstCharCount + 1)
    limited.push(item)
    if (limited.length >= slotLimit) break
  }

  if (limited.length < slotLimit) {
    themeKeywords.forEach((keyword, index) => {
      const normalized = normalizeDisplayToken(keyword)
      if (!normalized) return
      if (normalized === theme || normalized === headlineTheme) return
      if (limited.some((item) => item.text === normalized)) return
      limited.push({
        text: normalized,
        emphasis: normalized.length <= 2 ? 4 : 3,
        score: 12 - index,
        tone: index % 2 === 0 ? 'blue' : 'orange',
      })
    })
  }

  return limited
}

function buildPosterSlots() {
  const fillers = []
  const rows = [
    { y: 452, xs: [44, 98, 154, 316, 370], size: 15, tone: 'blue' },
    { y: 496, xs: [26, 138, 292, 392], size: 14, tone: 'orange' },
    { y: 548, xs: [28, 166, 284, 392], size: 14, tone: 'blue' },
    { y: 602, xs: [30, 146, 286, 388], size: 14, tone: 'orange' },
    { y: 676, xs: [36, 152, 276, 384], size: 15, tone: 'blue' },
    { y: 736, xs: [34, 160, 270, 384], size: 14, tone: 'orange' },
    { y: 812, xs: [28, 146, 280, 390], size: 15, tone: 'blue' },
    { y: 900, xs: [28, 152, 278, 388], size: 14, tone: 'orange' },
    { y: 990, xs: [28, 144, 284, 386], size: 14, tone: 'blue' },
    { y: 1070, xs: [40, 154, 276, 378], size: 14, tone: 'orange' },
  ]

  rows.forEach((row, rowIndex) => {
    row.xs.forEach((x, columnIndex) => {
      const tone = (rowIndex + columnIndex) % 2 === 0 ? row.tone : row.tone === 'blue' ? 'orange' : 'blue'
      fillers.push({ x, y: row.y, size: row.size + ((rowIndex + columnIndex) % 2), tone, align: 'center' })
    })
  })

  return [...HERO_SLOTS, ...fillers]
}

function splitThemeRows(theme) {
  const value = String(theme || '').trim()
  if (!value) return ['AI']
  const compact = value.replace(/\s+/g, '')
  if (/^[A-Za-z0-9&+-]+$/.test(compact)) return [compact]
  const chars = Array.from(compact)
  if (chars.length <= 2) return [compact]
  if (chars.length === 3) return [chars.slice(0, 2).join(''), chars.slice(2).join('')]
  return [chars.slice(0, 2).join(''), chars.slice(2, 4).join('')]
}

function createQrCells(seed) {
  const cells = []
  let cursor = 0
  const source = String(seed || 'fdsm-bookmark')
  for (let row = 0; row < 21; row += 1) {
    for (let col = 0; col < 21; col += 1) {
      const protectedCorner = (row < 5 && col < 5) || (row < 5 && col > 15) || (row > 15 && col < 5)
      const block = protectedCorner
        ? row === 0 || row === 4 || col === 0 || col === 4 || (row >= 2 && row <= 3 && col >= 2 && col <= 3)
        : (source.charCodeAt(cursor % source.length) + row * 11 + col * 13) % 5 <= 1
      cells.push(block)
      cursor += 1
    }
  }
  return cells
}

function BookmarkQrPlaceholder({ seed, label }) {
  const cells = useMemo(() => createQrCells(seed), [seed])
  return (
    <div className="today-bookmark-qr-shell">
      <div className="today-bookmark-qr-grid">
        {cells.map((filled, index) => (
          <span key={`qr-${index}`} className={filled ? 'today-bookmark-qr-cell is-filled' : 'today-bookmark-qr-cell'} />
        ))}
      </div>
      <div className="today-bookmark-qr-label">{label}</div>
    </div>
  )
}

function buildCloudLayout(items) {
  const slots = buildPosterSlots()
  return slots.map((slot, index) => {
    const item = items[index]
    if (!item) return null
    const width = estimateWidth(item.text, slot.size, slot.vertical)
    const left = clamp(
      Math.round(slot.align === 'center' ? slot.x - width / 2 : slot.x),
      18,
      BOOKMARK_WIDTH - width - 18,
    )
    return {
      key: `${item.text}-${index}`,
      text: item.text,
      left,
      top: slot.y,
      fontSize: slot.size,
      fontWeight: slot.size >= 56 ? 800 : slot.size >= 40 ? 700 : 600,
      tone: slot.tone || item.tone,
      vertical: Boolean(slot.vertical),
    }
  }).filter(Boolean)
}

function toneClass(tone) {
  return tone === 'orange' ? 'today-bookmark-token is-orange' : 'today-bookmark-token is-blue'
}

function ThemeOverlay({ theme }) {
  const rows = splitThemeRows(theme)
  const isLatin = rows.every((row) => /^[A-Za-z0-9&+-]+$/.test(row))
  const className = [
    rows.length === 1 ? 'today-bookmark-theme-word is-single' : 'today-bookmark-theme-word is-multi',
    isLatin ? 'is-latin' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div className={className}>
      <div className="today-bookmark-theme-shadow" aria-hidden="true">
        {rows.map((row, index) => (
          <div key={`shadow-${row}-${index}`} className="today-bookmark-theme-row">
            {row}
          </div>
        ))}
      </div>
      <div className="today-bookmark-theme-main" aria-hidden="true">
        {rows.map((row, index) => (
          <div key={`main-${row}-${index}`} className="today-bookmark-theme-row">
            {row}
          </div>
        ))}
      </div>
    </div>
  )
}

function TodayBookmarkCanvas({ bookmark }) {
  const headlineTheme = bookmark?.headline_theme || bookmark?.primary_theme || ''
  const items = useMemo(
    () =>
      buildDisplayItems(bookmark?.phrases || [], bookmark?.primary_theme || '', headlineTheme, bookmark?.theme_hints || []),
    [bookmark?.phrases, bookmark?.primary_theme, headlineTheme, bookmark?.theme_hints],
  )
  const placements = useMemo(() => buildCloudLayout(items), [items])

  return (
    <div className="today-bookmark-shell">
      <div className="today-bookmark-canvas" style={{ width: BOOKMARK_WIDTH, height: BOOKMARK_HEIGHT }}>
        <div className="today-bookmark-noise" />

        <div className="today-bookmark-header">
          <div className="today-bookmark-date">
            {bookmark.date_label} {bookmark.weekday_label}
          </div>
          <div className="today-bookmark-heading-label">今日主题：</div>
          <div className="today-bookmark-heading-text">{headlineTheme}</div>
        </div>

        <div className="today-bookmark-flow-layer">
          {placements.map((item) => (
            <span
              key={item.key}
              className={item.vertical ? `${toneClass(item.tone)} is-vertical` : toneClass(item.tone)}
              style={{
                left: item.left,
                top: item.top,
                fontSize: `${item.fontSize}px`,
                fontWeight: item.fontWeight,
              }}
            >
              {item.text}
            </span>
          ))}
        </div>

        <div className="today-bookmark-theme-overlay">
          <ThemeOverlay theme={bookmark.primary_theme || 'AI'} />
        </div>

        <div className="today-bookmark-footer">
          <BookmarkQrPlaceholder seed={bookmark.source_hash} label={bookmark.qr_label || QR_LABEL} />
        </div>
      </div>
    </div>
  )
}

export default TodayBookmarkCanvas
