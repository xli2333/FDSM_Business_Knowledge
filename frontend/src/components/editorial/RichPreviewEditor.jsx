import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Eraser,
  Italic,
  List,
  ListOrdered,
  Minus,
  Quote,
  Redo2,
  Strikethrough,
  Underline,
  Undo2,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

const MODE_OPTIONS = ['edit', 'preview', 'split']
const COLOR_OPTIONS = ['#1f2937', '#0d0783', '#ea6b00', '#0f766e', '#be123c']
const DEFAULT_TOOLBAR_STATE = {
  paragraph: true,
  heading1: false,
  heading2: false,
  bold: false,
  italic: false,
  underline: false,
  strikeThrough: false,
  alignLeft: true,
  alignCenter: false,
  alignRight: false,
  bulletList: false,
  orderedList: false,
  blockquote: false,
  foreColor: '',
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function markdownishTextToHtml(value) {
  const normalized = String(value || '').replace(/\r\n/g, '\n').trim()
  if (!normalized) return '<p></p>'

  const lines = normalized.split('\n')
  const blocks = []
  let listType = null

  const closeList = () => {
    if (!listType) return
    blocks.push(listType === 'ol' ? '</ol>' : '</ul>')
    listType = null
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      closeList()
      continue
    }

    if (/^###\s+/.test(line)) {
      closeList()
      blocks.push(`<h3>${escapeHtml(line.replace(/^###\s+/, ''))}</h3>`)
      continue
    }

    if (/^##\s+/.test(line)) {
      closeList()
      blocks.push(`<h2>${escapeHtml(line.replace(/^##\s+/, ''))}</h2>`)
      continue
    }

    if (/^#\s+/.test(line)) {
      closeList()
      blocks.push(`<h1>${escapeHtml(line.replace(/^#\s+/, ''))}</h1>`)
      continue
    }

    if (/^>\s+/.test(line)) {
      closeList()
      blocks.push(`<blockquote><p>${escapeHtml(line.replace(/^>\s+/, ''))}</p></blockquote>`)
      continue
    }

    if (/^\d+\.\s+/.test(line)) {
      if (listType !== 'ol') {
        closeList()
        blocks.push('<ol>')
        listType = 'ol'
      }
      blocks.push(`<li>${escapeHtml(line.replace(/^\d+\.\s+/, ''))}</li>`)
      continue
    }

    if (/^[-*]\s+/.test(line)) {
      if (listType !== 'ul') {
        closeList()
        blocks.push('<ul>')
        listType = 'ul'
      }
      blocks.push(`<li>${escapeHtml(line.replace(/^[-*]\s+/, ''))}</li>`)
      continue
    }

    closeList()
    blocks.push(`<p>${escapeHtml(line)}</p>`)
  }

  closeList()
  return blocks.join('')
}

function sanitizeDocumentHtml(value) {
  return String(value || '')
    .replace(/<\s*script\b[^>]*>.*?<\s*\/script\s*>/gis, '')
    .replace(/\s+on[a-z-]+\s*=\s*(['"]).*?\1/gi, '')
    .replace(/\s+on[a-z-]+\s*=\s*[^\s>]+/gi, '')
    .replace(/\s+(contenteditable|spellcheck|draggable)\s*=\s*(['"]).*?\2/gi, '')
    .replace(/\s+(contenteditable|spellcheck|draggable)\s*=\s*[^\s>]+/gi, '')
    .trim()
}

function sanitizePastedHtml(value) {
  return sanitizeDocumentHtml(
    String(value || '')
      .replace(/<\s*(meta|link)\b[^>]*>/gi, '')
      .replace(/<\s*style\b[^>]*>.*?<\s*\/style\s*>/gis, '')
      .replace(/<\/?(html|head|body)[^>]*>/gi, ''),
  )
}

function ensureDoctype(value) {
  const html = String(value || '').trim()
  if (!html) return ''
  return /^<!doctype/i.test(html) ? html : `<!doctype html>\n${html}`
}

function buildBasicDocument(contentHtml, isEnglish) {
  return `<!doctype html>
<html lang="${isEnglish ? 'en' : 'zh-CN'}">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${isEnglish ? 'Editorial Draft' : '编辑稿'}</title>
    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 36px 20px;
        background:
          radial-gradient(circle at top, rgba(255, 214, 153, 0.24), transparent 34%),
          linear-gradient(180deg, #fbfaf7 0%, #f5f1ea 100%);
        color: #334155;
        font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      }
      .preview-shell {
        max-width: 760px;
        margin: 0 auto;
        padding: 36px 34px 48px;
        border-radius: 30px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 26px 60px rgba(15, 23, 42, 0.08);
      }
      h1, h2, h3, h4, h5, h6 {
        margin: 0 0 18px;
        color: #0d0783;
        font-family: "Noto Serif SC", "Songti SC", serif;
        line-height: 1.35;
      }
      h1 { font-size: 2.05rem; }
      h2 { margin-top: 34px; font-size: 1.56rem; }
      h3 { margin-top: 28px; font-size: 1.22rem; }
      p, li, blockquote, td, th {
        font-size: 1rem;
        line-height: 1.95;
      }
      p { margin: 0 0 18px; }
      ul, ol {
        margin: 0 0 22px;
        padding-left: 1.5rem;
      }
      blockquote {
        margin: 28px 0;
        padding: 18px 20px;
        border-left: 4px solid #ea6b00;
        border-radius: 0 20px 20px 0;
        background: rgba(234, 107, 0, 0.08);
        color: #475569;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 24px 0;
      }
      th, td {
        border: 1px solid rgba(148, 163, 184, 0.35);
        padding: 12px 14px;
        vertical-align: top;
      }
      hr {
        margin: 28px 0;
        border: none;
        border-top: 1px solid rgba(148, 163, 184, 0.35);
      }
      strong { color: #0f172a; }
    </style>
  </head>
  <body>
    <div class="preview-shell">${contentHtml || '<p></p>'}</div>
  </body>
</html>`
}

function ensureHtmlDocument(value, fallbackText, isEnglish) {
  const explicitHtml = sanitizeDocumentHtml(value)
  if (explicitHtml) {
    if (/<html[\s>]/i.test(explicitHtml)) return ensureDoctype(explicitHtml)
    return buildBasicDocument(explicitHtml, isEnglish)
  }
  if (fallbackText && String(fallbackText).trim()) {
    return buildBasicDocument(markdownishTextToHtml(fallbackText), isEnglish)
  }
  return buildBasicDocument('<p></p>', isEnglish)
}

function extractPlainTextFromHtml(value) {
  const html = String(value || '').trim()
  if (!html || typeof DOMParser === 'undefined') return ''
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  return String(doc.body?.innerText || '').replace(/\s+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
}

function buildDocumentPayload(html) {
  return {
    schema: 'editable-html-v1',
    html,
  }
}

function measureFrameHeight(doc, minFrameHeight) {
  if (!doc) return minFrameHeight
  const body = doc.body
  const root = doc.documentElement
  const measured = Math.max(
    body?.scrollHeight || 0,
    body?.offsetHeight || 0,
    body?.clientHeight || 0,
    root?.scrollHeight || 0,
    root?.offsetHeight || 0,
    root?.clientHeight || 0,
  )
  return Math.max(minFrameHeight, measured + 8)
}

function resolveSeed({ initialHtml, initialDocument, fallbackText, isEnglish }) {
  const documentHtml =
    initialDocument && typeof initialDocument === 'object' && typeof initialDocument.html === 'string'
      ? initialDocument.html
      : ''

  if (initialHtml && String(initialHtml).trim()) {
    return {
      html: ensureHtmlDocument(initialHtml, fallbackText, isEnglish),
      seedType: 'html',
    }
  }

  if (documentHtml && String(documentHtml).trim()) {
    return {
      html: ensureHtmlDocument(documentHtml, fallbackText, isEnglish),
      seedType: 'editor_document',
    }
  }

  if (fallbackText && String(fallbackText).trim()) {
    return {
      html: ensureHtmlDocument('', fallbackText, isEnglish),
      seedType: 'raw_text',
    }
  }

  return {
    html: ensureHtmlDocument('', '', isEnglish),
    seedType: 'empty',
  }
}

function serializeEditableDocument(doc) {
  if (!doc?.documentElement) return ''
  const clone = doc.documentElement.cloneNode(true)
  if (clone && typeof clone.querySelectorAll === 'function') {
    clone.querySelectorAll('[contenteditable],[spellcheck],[draggable]').forEach((node) => {
      node.removeAttribute('contenteditable')
      node.removeAttribute('spellcheck')
      node.removeAttribute('draggable')
    })
  }
  return `<!doctype html>\n${clone.outerHTML}`
}

function safeQueryCommandState(doc, command) {
  try {
    return Boolean(doc.queryCommandState(command))
  } catch {
    return false
  }
}

function safeQueryCommandValue(doc, command) {
  try {
    return String(doc.queryCommandValue(command) || '')
  } catch {
    return ''
  }
}

function collectToolbarState(doc) {
  if (!doc) return DEFAULT_TOOLBAR_STATE
  const formatBlock = safeQueryCommandValue(doc, 'formatBlock').toLowerCase()
  return {
    paragraph: !formatBlock || formatBlock.includes('p') || formatBlock.includes('normal'),
    heading1: formatBlock.includes('h1'),
    heading2: formatBlock.includes('h2'),
    bold: safeQueryCommandState(doc, 'bold'),
    italic: safeQueryCommandState(doc, 'italic'),
    underline: safeQueryCommandState(doc, 'underline'),
    strikeThrough: safeQueryCommandState(doc, 'strikeThrough'),
    alignLeft: safeQueryCommandState(doc, 'justifyLeft') || (!safeQueryCommandState(doc, 'justifyCenter') && !safeQueryCommandState(doc, 'justifyRight')),
    alignCenter: safeQueryCommandState(doc, 'justifyCenter'),
    alignRight: safeQueryCommandState(doc, 'justifyRight'),
    bulletList: safeQueryCommandState(doc, 'insertUnorderedList'),
    orderedList: safeQueryCommandState(doc, 'insertOrderedList'),
    blockquote: formatBlock.includes('blockquote'),
    foreColor: safeQueryCommandValue(doc, 'foreColor').toLowerCase(),
  }
}

function focusEditableSurface(doc, win) {
  if (!doc || !win) return
  try {
    win.focus()
  } catch {}
  if (doc.body) {
    try {
      doc.body.focus({ preventScroll: true })
    } catch {
      try {
        doc.body.focus()
      } catch {}
    }
  }
}

function ToolbarButton({ active = false, disabled = false, label, onClick, children }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={label}
      className={[
        'inline-flex h-10 min-w-10 items-center justify-center rounded-2xl border px-3 text-sm font-semibold transition',
        active
          ? 'border-fudan-blue bg-fudan-blue text-white'
          : 'border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30 hover:text-fudan-blue',
        disabled ? 'cursor-not-allowed opacity-40' : '',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function ModeButton({ active, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded-full px-4 py-2 text-sm font-semibold transition',
        active ? 'bg-fudan-blue text-white' : 'bg-white text-slate-500 hover:text-fudan-blue',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function RichPreviewEditor({
  isEnglish,
  contentVersion,
  initialDocument,
  initialHtml,
  fallbackText,
  statusText,
  formatterModel,
  editorSource,
  isDirty,
  hasUnpublishedChanges,
  sectionKicker,
  helperLineOverride,
  helpText,
  editablePanelTitle,
  previewPanelTitle,
  editableFrameTitle = 'Editable editorial document frame',
  previewFrameTitle = 'Editorial preview frame',
  minFrameHeight = 960,
  onChange,
}) {
  const [mode, setMode] = useState('edit')
  const [seedSnapshot, setSeedSnapshot] = useState(() =>
    resolveSeed({ initialHtml, initialDocument, fallbackText, isEnglish }),
  )
  const [previewHtml, setPreviewHtml] = useState(seedSnapshot.html)
  const [toolbarState, setToolbarState] = useState(DEFAULT_TOOLBAR_STATE)
  const [editableReady, setEditableReady] = useState(false)
  const [editableFrameHeight, setEditableFrameHeight] = useState(minFrameHeight)
  const [previewFrameHeight, setPreviewFrameHeight] = useState(minFrameHeight)
  const editableFrameRef = useRef(null)
  const previewFrameRef = useRef(null)
  const editableCleanupRef = useRef(() => {})
  const latestHtmlRef = useRef(seedSnapshot.html)
  const onChangeRef = useRef(onChange)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    if (!MODE_OPTIONS.includes(mode)) {
      setMode('edit')
    }
  }, [mode])

  useEffect(() => {
    const nextSeed = resolveSeed({ initialHtml, initialDocument, fallbackText, isEnglish })
    editableCleanupRef.current?.()
    latestHtmlRef.current = nextSeed.html
    setSeedSnapshot(nextSeed)
    setPreviewHtml(nextSeed.html)
    setToolbarState(DEFAULT_TOOLBAR_STATE)
    setEditableReady(false)
    setEditableFrameHeight(minFrameHeight)
    setPreviewFrameHeight(minFrameHeight)
    onChangeRef.current?.({
      html: nextSeed.html,
      document: buildDocumentPayload(nextSeed.html),
      text: extractPlainTextFromHtml(nextSeed.html),
      dirty: false,
    })
  }, [contentVersion, fallbackText, initialDocument, initialHtml, isEnglish, minFrameHeight])

  useEffect(() => () => editableCleanupRef.current?.(), [])

  useEffect(() => {
    setEditableFrameHeight((current) => Math.max(current, minFrameHeight))
    setPreviewFrameHeight((current) => Math.max(current, minFrameHeight))
  }, [minFrameHeight])

  const updateEditableFrameHeight = (doc) => {
    setEditableFrameHeight(measureFrameHeight(doc, minFrameHeight))
  }

  const updatePreviewFrameHeight = (doc) => {
    setPreviewFrameHeight(measureFrameHeight(doc, minFrameHeight))
  }

  const syncFromDocument = (doc, dirty) => {
    const nextHtml = serializeEditableDocument(doc)
    if (!nextHtml) return
    latestHtmlRef.current = nextHtml
    setPreviewHtml((current) => (current === nextHtml ? current : nextHtml))
    setToolbarState(collectToolbarState(doc))
    updateEditableFrameHeight(doc)
    onChangeRef.current?.({
      html: nextHtml,
      document: buildDocumentPayload(nextHtml),
      text: extractPlainTextFromHtml(nextHtml),
      dirty,
    })
  }

  const handleEditableLoad = () => {
    const iframe = editableFrameRef.current
    const doc = iframe?.contentDocument
    const win = iframe?.contentWindow
    if (!doc || !win) return

    editableCleanupRef.current?.()
    setEditableReady(false)

    const armDocument = () => {
      try {
        doc.designMode = 'on'
        doc.execCommand('styleWithCSS', false, true)
      } catch {}

      if (doc.body) {
        doc.body.contentEditable = 'true'
        doc.body.setAttribute('contenteditable', 'true')
        doc.body.spellcheck = false
        doc.body.setAttribute('spellcheck', 'false')
        doc.body.tabIndex = -1
      }

      const handleSelection = () => setToolbarState(collectToolbarState(doc))
      const handleInput = () => syncFromDocument(doc, true)
      const handleFocus = () => {
        focusEditableSurface(doc, win)
        handleSelection()
      }
      const handlePaste = (event) => {
        const pastedHtml = event.clipboardData?.getData('text/html')
        const pastedText = event.clipboardData?.getData('text/plain')
        if (!pastedHtml && !pastedText) return
        event.preventDefault()
        try {
          doc.execCommand('styleWithCSS', false, true)
        } catch {}
        if (pastedHtml) {
          doc.execCommand('insertHTML', false, sanitizePastedHtml(pastedHtml))
        } else {
          doc.execCommand('insertText', false, pastedText || '')
        }
        syncFromDocument(doc, true)
      }
      const handleClick = (event) => {
        focusEditableSurface(doc, win)
        const target = event.target
        if (target && typeof target.closest === 'function') {
          const link = target.closest('a')
          if (link) event.preventDefault()
        }
      }

      doc.addEventListener('focusin', handleFocus)
      doc.addEventListener('input', handleInput)
      doc.addEventListener('keyup', handleSelection)
      doc.addEventListener('mouseup', handleSelection)
      doc.addEventListener('mousedown', handleFocus)
      doc.addEventListener('selectionchange', handleSelection)
      doc.addEventListener('paste', handlePaste)
      doc.addEventListener('click', handleClick)

      editableCleanupRef.current = () => {
        doc.removeEventListener('focusin', handleFocus)
        doc.removeEventListener('input', handleInput)
        doc.removeEventListener('keyup', handleSelection)
        doc.removeEventListener('mouseup', handleSelection)
        doc.removeEventListener('mousedown', handleFocus)
        doc.removeEventListener('selectionchange', handleSelection)
        doc.removeEventListener('paste', handlePaste)
        doc.removeEventListener('click', handleClick)
      }

      setEditableReady(true)
      focusEditableSurface(doc, win)
      syncFromDocument(doc, false)
    }

    win.requestAnimationFrame(armDocument)
  }

  const handlePreviewLoad = () => {
    const doc = previewFrameRef.current?.contentDocument
    if (!doc) return
    const win = previewFrameRef.current?.contentWindow
    if (win?.requestAnimationFrame) {
      win.requestAnimationFrame(() => updatePreviewFrameHeight(doc))
      return
    }
    updatePreviewFrameHeight(doc)
  }

  const withEditableDocument = (callback) => {
    const iframe = editableFrameRef.current
    const doc = iframe?.contentDocument
    const win = iframe?.contentWindow
    if (!doc || !win) return
    focusEditableSurface(doc, win)
    callback(doc, win)
    syncFromDocument(doc, true)
  }

  const runCommand = (command, value = null) => {
    withEditableDocument((doc) => {
      try {
        doc.execCommand('styleWithCSS', false, true)
      } catch {}
      doc.execCommand(command, false, value)
    })
  }

  const insertTable = () => {
    const tableHtml = `
      <table style="width:100%; border-collapse:collapse; margin:24px 0;">
        <thead>
          <tr>
            <th style="border:1px solid rgba(148,163,184,0.35); padding:12px 14px; text-align:left;">${isEnglish ? 'Header A' : '表头一'}</th>
            <th style="border:1px solid rgba(148,163,184,0.35); padding:12px 14px; text-align:left;">${isEnglish ? 'Header B' : '表头二'}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="border:1px solid rgba(148,163,184,0.35); padding:12px 14px;">${isEnglish ? 'Cell A1' : '内容一'}</td>
            <td style="border:1px solid rgba(148,163,184,0.35); padding:12px 14px;">${isEnglish ? 'Cell B1' : '内容二'}</td>
          </tr>
        </tbody>
      </table>
    `
    runCommand('insertHTML', tableHtml)
  }

  const modeLabels = {
    edit: isEnglish ? 'Edit' : '编辑',
    preview: isEnglish ? 'Preview' : '预览',
    split: isEnglish ? 'Split' : '分屏',
  }
  const seedLabels = {
    editor_document: isEnglish ? 'Loaded from saved editor document' : '已从保存的编辑文档恢复',
    html: isEnglish ? 'Loaded from saved HTML' : '已从最终 HTML 恢复',
    raw_text: isEnglish ? 'No final HTML yet, using raw draft as a temporary editable base' : '最终 HTML 尚未生成，先用原稿作为临时编辑底稿',
    empty: isEnglish ? 'Editor is ready for a new final draft' : '右侧成品区已准备好，可直接开始编辑',
  }
  const sourceLabels = {
    ai_formatted: isEnglish ? 'Current right draft comes from AI layout' : '当前右稿来自 AI 自动排版',
    manual_edited: isEnglish ? 'Current right draft contains manual edits' : '当前右稿包含人工编辑',
    imported_legacy_html: isEnglish ? 'Current right draft comes from legacy HTML import' : '当前右稿来自旧 HTML 导入',
  }
  const helperLine = helperLineOverride || sourceLabels[editorSource] || seedLabels[seedSnapshot.seedType]
  const resolvedSectionKicker = sectionKicker || (isEnglish ? 'Final Draft' : '最终成品区')
  const resolvedHelpText =
    helpText || (isEnglish ? 'Click directly inside the final draft canvas to edit titles, body paragraphs, emphasis, and tables.' : '直接点击右侧最终稿画布即可编辑标题、正文、强调和表格。')
  const resolvedEditablePanelTitle =
    editablePanelTitle ||
    (mode === 'split'
      ? isEnglish
        ? 'Editable final draft'
        : '可编辑最终成品'
      : isEnglish
        ? 'Editable final draft canvas'
        : '可编辑最终成品画布')
  const resolvedPreviewPanelTitle = previewPanelTitle || (isEnglish ? 'Rendered preview' : '最终呈现预览')
  const toolbarDisabled = !editableReady

  return (
    <div className="editorial-rich-workbench">
      <div className="editorial-rich-topbar">
        <div>
          <div className="section-kicker">{resolvedSectionKicker}</div>
          <div className="mt-2 text-sm text-slate-500">{statusText}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {formatterModel ? <span className="rounded-full bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-500">{formatterModel}</span> : null}
          {hasUnpublishedChanges ? (
            <span className="rounded-full bg-amber-100 px-3 py-2 text-xs font-semibold text-amber-800">
              {isEnglish ? 'Live and working draft differ' : '线上稿与当前工作稿不同'}
            </span>
          ) : null}
          {isDirty ? (
            <span className="rounded-full bg-fudan-orange/10 px-3 py-2 text-xs font-semibold text-fudan-orange">
              {isEnglish ? 'Unsaved manual edits' : '人工修改未保存'}
            </span>
          ) : null}
        </div>
      </div>

      <div className="editorial-rich-toolbar-shell">
        <div className="editorial-rich-mode-switch">
          <ModeButton active={mode === 'edit'} label={modeLabels.edit} onClick={() => setMode('edit')} />
          <ModeButton active={mode === 'preview'} label={modeLabels.preview} onClick={() => setMode('preview')} />
          <ModeButton active={mode === 'split'} label={modeLabels.split} onClick={() => setMode('split')} />
        </div>

        <div className="editorial-rich-toolbar">
          <ToolbarButton
            label={isEnglish ? 'Paragraph' : '正文'}
            active={toolbarState.paragraph}
            disabled={toolbarDisabled}
            onClick={() => runCommand('formatBlock', 'p')}
          >
            P
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Heading 1' : '大标题'}
            active={toolbarState.heading1}
            disabled={toolbarDisabled}
            onClick={() => runCommand('formatBlock', 'h1')}
          >
            H1
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Heading 2' : '小标题'}
            active={toolbarState.heading2}
            disabled={toolbarDisabled}
            onClick={() => runCommand('formatBlock', 'h2')}
          >
            H2
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Bold' : '加粗'} active={toolbarState.bold} disabled={toolbarDisabled} onClick={() => runCommand('bold')}>
            <Bold size={16} />
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Italic' : '斜体'} active={toolbarState.italic} disabled={toolbarDisabled} onClick={() => runCommand('italic')}>
            <Italic size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Underline' : '下划线'}
            active={toolbarState.underline}
            disabled={toolbarDisabled}
            onClick={() => runCommand('underline')}
          >
            <Underline size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Strike' : '删除线'}
            active={toolbarState.strikeThrough}
            disabled={toolbarDisabled}
            onClick={() => runCommand('strikeThrough')}
          >
            <Strikethrough size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Align left' : '左对齐'}
            active={toolbarState.alignLeft}
            disabled={toolbarDisabled}
            onClick={() => runCommand('justifyLeft')}
          >
            <AlignLeft size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Align center' : '居中'}
            active={toolbarState.alignCenter}
            disabled={toolbarDisabled}
            onClick={() => runCommand('justifyCenter')}
          >
            <AlignCenter size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Align right' : '右对齐'}
            active={toolbarState.alignRight}
            disabled={toolbarDisabled}
            onClick={() => runCommand('justifyRight')}
          >
            <AlignRight size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Bullet list' : '无序列表'}
            active={toolbarState.bulletList}
            disabled={toolbarDisabled}
            onClick={() => runCommand('insertUnorderedList')}
          >
            <List size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Ordered list' : '有序列表'}
            active={toolbarState.orderedList}
            disabled={toolbarDisabled}
            onClick={() => runCommand('insertOrderedList')}
          >
            <ListOrdered size={16} />
          </ToolbarButton>
          <ToolbarButton
            label={isEnglish ? 'Quote' : '引用'}
            active={toolbarState.blockquote}
            disabled={toolbarDisabled}
            onClick={() => runCommand('formatBlock', 'blockquote')}
          >
            <Quote size={16} />
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Divider' : '分隔线'} disabled={toolbarDisabled} onClick={() => runCommand('insertHorizontalRule')}>
            <Minus size={16} />
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Table' : '表格'} disabled={toolbarDisabled} onClick={insertTable}>
            Tbl
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Clear format' : '清除格式'} disabled={toolbarDisabled} onClick={() => runCommand('removeFormat')}>
            <Eraser size={16} />
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Undo' : '撤销'} disabled={toolbarDisabled} onClick={() => runCommand('undo')}>
            <Undo2 size={16} />
          </ToolbarButton>
          <ToolbarButton label={isEnglish ? 'Redo' : '重做'} disabled={toolbarDisabled} onClick={() => runCommand('redo')}>
            <Redo2 size={16} />
          </ToolbarButton>
          <div className="editorial-rich-color-row">
            {COLOR_OPTIONS.map((color) => (
              <button
                key={color}
                type="button"
                title={isEnglish ? `Set color ${color}` : `设置颜色 ${color}`}
                onClick={() => runCommand('foreColor', color)}
                disabled={toolbarDisabled}
                className={[
                  'h-8 w-8 rounded-full border-2 transition',
                  toolbarState.foreColor.includes(color.replace('#', '').toLowerCase()) ? 'border-slate-900 scale-105' : 'border-white',
                  toolbarDisabled ? 'cursor-not-allowed opacity-40' : '',
                ].join(' ')}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>

        <div className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 px-4 py-3 text-sm leading-7 text-slate-600">
          {helperLine}
        </div>
        <div className="text-sm leading-7 text-slate-500">{resolvedHelpText}</div>
      </div>

      <div className={mode === 'split' ? 'mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]' : 'mt-5'}>
        <div className={mode === 'preview' ? 'hidden' : ''}>
          <div className="overflow-hidden rounded-[1.8rem] border border-slate-200/70 bg-slate-50">
            <div className="border-b border-slate-200/70 bg-white px-5 py-4 text-sm font-semibold text-slate-600">{resolvedEditablePanelTitle}</div>
            <div className="editorial-rich-canvas" style={{ minHeight: `${minFrameHeight}px` }}>
              <iframe
                key={contentVersion}
                ref={editableFrameRef}
                title={editableFrameTitle}
                className="editorial-rich-frame"
                srcDoc={seedSnapshot.html}
                onLoad={handleEditableLoad}
                style={{ height: `${editableFrameHeight}px` }}
              />
            </div>
          </div>
        </div>

        {mode !== 'edit' ? (
          <div className={mode === 'preview' ? '' : ''}>
            <div className="overflow-hidden rounded-[1.8rem] border border-slate-200/70 bg-slate-50">
              <div className="border-b border-slate-200/70 bg-white px-5 py-4 text-sm font-semibold text-slate-600">{resolvedPreviewPanelTitle}</div>
              <div className="editorial-rich-canvas" style={{ minHeight: `${minFrameHeight}px` }}>
                <iframe
                  ref={previewFrameRef}
                  title={previewFrameTitle}
                  className="editorial-rich-frame"
                  srcDoc={previewHtml || latestHtmlRef.current || seedSnapshot.html}
                  onLoad={handlePreviewLoad}
                  style={{ height: `${previewFrameHeight}px` }}
                />
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default RichPreviewEditor
