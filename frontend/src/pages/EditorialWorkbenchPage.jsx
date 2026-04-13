import { FileUp, LoaderCircle, RefreshCw, Rocket, Save, Sparkles, Trash2, Wand2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  autoFormatEditorialArticle,
  autoSummarizeEditorialArticle,
  autotagEditorialArticle,
  createEditorialArticle,
  deleteEditorialArticle,
  fetchColumns,
  fetchEditorialArticle,
  fetchEditorialArticles,
  fetchEditorialDashboard,
  fetchEditorialTopics,
  publishEditorialArticle,
  resolveApiUrl,
  updateEditorialArticle,
  uploadEditorialFile,
} from '../api/index.js'
import RichPreviewEditor from '../components/editorial/RichPreviewEditor.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

const EMPTY_PREVIEW = `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 40px 22px;
        background:
          radial-gradient(circle at top, rgba(255, 214, 153, 0.28), transparent 34%),
          linear-gradient(180deg, #fbfaf7 0%, #f5f1ea 100%);
        color: #475569;
        font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      }
      .shell {
        max-width: 760px;
        margin: 0 auto;
        padding: 30px;
        border-radius: 30px;
        background: rgba(255, 255, 255, 0.94);
        box-shadow: 0 26px 60px rgba(15, 23, 42, 0.08);
      }
      h1 {
        margin: 0 0 14px;
        color: #ea6b00;
        font-size: 24px;
      }
      p {
        margin: 0;
        line-height: 1.9;
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <h1>等待自动排版</h1>
      <p>左侧原稿保存后，点击“自动排版”，右侧会显示最终 HTML 成品。原稿或标题等关键字段变更后，旧预览会自动失效。</p>
    </div>
  </body>
</html>`

const DEFAULT_COLUMNS = [
  { slug: 'insights', name: '深度洞察' },
  { slug: 'industry', name: '行业观察' },
  { slug: 'research', name: '学术前沿' },
  { slug: 'deans-view', name: '院长说' },
]

const DEFAULT_FORM = {
  title: '',
  subtitle: '',
  author: 'Fudan Business Knowledge Editorial Desk',
  organization: '',
  publish_date: new Date().toISOString().slice(0, 10),
  source_url: '',
  cover_image_url: '',
  primary_column_slug: '',
  primary_column_manual: false,
  access_level: 'public',
  layout_mode: 'auto',
  formatting_notes: '',
  source_markdown: '',
  content_markdown: '',
  tags: [],
  selected_topics: [],
}

const EMPTY_EDITOR_STATE = {
  html: '',
  document: null,
  text: '',
  dirty: false,
  version: 'empty',
}

function tagKey(tag) {
  return `${tag?.category || 'topic'}:${tag?.name || ''}`
}

function topicKey(topic) {
  return `topic:${topic?.id ?? ''}:${topic?.slug ?? ''}`
}

function canDeleteDraftEntry(article) {
  return Boolean(article && !article.article_id && article.status !== 'published')
}

function getDraftStatusLabel(article, isEnglish) {
  if (!article) return ''
  if (article.status === 'published' && article.has_unpublished_changes) {
    return isEnglish ? 'Published / Waiting republish' : '已发布 / 待重新发布'
  }
  if (article.status === 'published' && article.is_reopened_from_published) {
    return isEnglish ? 'Published / Back in draft box' : '已发布 / 回编中'
  }
  return article.workflow_label || article.workflow_status || (isEnglish ? 'Draft' : '草稿')
}

function getDraftStatusClass(article) {
  if (article?.status === 'published' && article?.has_unpublished_changes) {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  }
  if (article?.status === 'published') {
    return 'border-fudan-blue/15 bg-fudan-blue/10 text-fudan-blue'
  }
  return 'border-amber-200 bg-amber-50 text-fudan-orange'
}

function buildPersistPayload(form, detail, isEnglish, editorState = null, summaryEditorState = null) {
  const sourceMarkdown = String(form.source_markdown || '').trim()
  const retainedTags = Array.isArray(form.tags) ? form.tags : []
  const payload = {
    title: String(form.title || '').trim() || (isEnglish ? 'Untitled draft' : '未命名草稿'),
    subtitle: String(form.subtitle || '').trim() || null,
    author: String(form.author || '').trim() || DEFAULT_FORM.author,
    organization: String(form.organization || '').trim() || DEFAULT_FORM.organization,
    publish_date: form.publish_date || DEFAULT_FORM.publish_date,
    source_url: String(form.source_url || '').trim() || null,
    cover_image_url: String(form.cover_image_url || '').trim() || null,
    primary_column_slug: form.primary_column_slug || null,
    primary_column_manual: Boolean(form.primary_column_manual && form.primary_column_slug),
    access_level: form.access_level || 'public',
    layout_mode: form.layout_mode || 'auto',
    formatting_notes: String(form.formatting_notes || '').trim() || null,
    source_markdown: sourceMarkdown,
    content_markdown: detail?.content_markdown || sourceMarkdown,
    tags: retainedTags,
    selected_topic_ids: Array.isArray(form.selected_topics) ? form.selected_topics.map((item) => item.id).filter(Boolean) : [],
  }

  if (summaryEditorState?.dirty && summaryEditorState?.html) {
    payload.summary_html = summaryEditorState.html
    payload.summary_editor_document = summaryEditorState.document || null
    payload.summary_markdown = String(summaryEditorState.text || detail?.summary_markdown || '').trim() || null
  }

  if (editorState?.dirty && editorState?.html) {
    payload.final_html = editorState.html
    payload.editor_document = editorState.document || null
  }

  return payload
}

function normalizeForm(article) {
  return {
    title: article?.title || '',
    subtitle: article?.subtitle || '',
    author: article?.author || DEFAULT_FORM.author,
    organization: article?.organization || DEFAULT_FORM.organization,
    publish_date: article?.publish_date || DEFAULT_FORM.publish_date,
    source_url: article?.source_url || '',
    cover_image_url: article?.cover_image_url || '',
    primary_column_slug: article?.primary_column_slug || '',
    primary_column_manual: Boolean(article?.primary_column_manual),
    access_level: article?.access_level || 'public',
    layout_mode: article?.layout_mode || 'auto',
    formatting_notes: article?.formatting_notes || '',
    source_markdown: article?.source_markdown || '',
    content_markdown: article?.content_markdown || '',
    tags: Array.isArray(article?.tags) ? article.tags : [],
    selected_topics: Array.isArray(article?.selected_topics) ? article.selected_topics : [],
  }
}

function TagChip({ tag, removable = false, onRemove }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-semibold"
      style={{
        borderColor: tag?.color || '#cbd5e1',
        color: tag?.color || '#334155',
        background: `${tag?.color || '#e2e8f0'}14`,
      }}
    >
      <span>{tag?.name}</span>
      {removable ? (
        <button type="button" onClick={() => onRemove?.(tag)} className="text-current/80 transition hover:text-current">
          <X size={13} />
        </button>
      ) : null}
    </span>
  )
}

function EditorialWorkbenchPage() {
  const { isEnglish } = useLanguage()
  const fileRef = useRef(null)
  const coverFileRef = useRef(null)
  const hasInitializedRef = useRef(false)
  const [searchParams, setSearchParams] = useSearchParams()
  const [articles, setArticles] = useState([])
  const [columns, setColumns] = useState(DEFAULT_COLUMNS)
  const [dashboard, setDashboard] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState(DEFAULT_FORM)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [summaryEditorState, setSummaryEditorState] = useState(EMPTY_EDITOR_STATE)
  const [editorState, setEditorState] = useState(EMPTY_EDITOR_STATE)
  const [topicQuery, setTopicQuery] = useState('')
  const [topicResults, setTopicResults] = useState([])
  const sourceCount = useMemo(() => String(form.source_markdown || '').replace(/\s+/g, '').length, [form.source_markdown])
  const currentColumn = useMemo(
    () => columns.find((item) => item.slug === form.primary_column_slug) || null,
    [columns, form.primary_column_slug],
  )
  const aiColumn = useMemo(
    () => columns.find((item) => item.slug === detail?.primary_column_ai_slug) || null,
    [columns, detail?.primary_column_ai_slug],
  )
  const requestedEditorialId = useMemo(() => {
    const value = Number(searchParams.get('editorial_id') || '')
    return Number.isFinite(value) && value > 0 ? value : null
  }, [searchParams])
  const reopenedFromArticle = searchParams.get('reopened') === '1'
  const hasUnsavedSummaryEdits = Boolean(summaryEditorState?.dirty && String(summaryEditorState?.html || '').trim())
  const hasUnsavedManualEdits = Boolean(editorState?.dirty && String(editorState?.html || '').trim())
  const canDeleteSelectedDraft = canDeleteDraftEntry(detail)
  const coverUrl = resolveApiUrl(form.cover_image_url)

  const syncDetail = useCallback(async (id) => {
    const article = await fetchEditorialArticle(id)
    setSelectedId(article.id)
    setDetail(article)
    setForm(normalizeForm(article))
    return article
  }, [])

  const clearEditorialEntryQuery = useCallback(() => {
    const next = new URLSearchParams(searchParams)
    next.delete('editorial_id')
    next.delete('reopened')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const refreshAll = useCallback(
    async (preferredId = null) => {
      const [list, dash] = await Promise.all([fetchEditorialArticles(80), fetchEditorialDashboard(8)])
      setArticles(list)
      setDashboard(dash)
      const candidateIds = [preferredId, requestedEditorialId, list[0]?.id].filter(Boolean)
      const nextId = candidateIds.find((candidateId) => list.some((item) => item.id === candidateId)) || list[0]?.id || null
      if (nextId) {
        await syncDetail(nextId)
      } else {
        setSelectedId(null)
        setDetail(null)
        setForm(DEFAULT_FORM)
      }
    },
    [requestedEditorialId, syncDetail],
  )

  useEffect(() => {
    if (hasInitializedRef.current && !requestedEditorialId) return
    hasInitializedRef.current = true
    fetchColumns()
      .then((items) => {
        if (Array.isArray(items) && items.length) setColumns(items)
      })
      .catch(() => {})
    refreshAll(requestedEditorialId).catch((err) => {
      setError(err?.message || (isEnglish ? 'Failed to load editorial workbench.' : '编辑台加载失败。'))
    })
  }, [isEnglish, refreshAll, requestedEditorialId])

  useEffect(() => {
    if (!detail) {
      setSummaryEditorState(EMPTY_EDITOR_STATE)
      setEditorState(EMPTY_EDITOR_STATE)
      return
    }

    const seededSummaryHtml = detail.summary_html || detail.published_summary_html || ''
    setSummaryEditorState({
      html: seededSummaryHtml,
      document: detail.summary_editor_document || null,
      text: detail.summary_markdown || detail.excerpt || '',
      dirty: false,
      version: `summary:${detail.id}:${detail.updated_at || ''}:${detail.summary_updated_at || ''}:${seededSummaryHtml.length}`,
    })

    const seededHtml = detail.final_html || detail.html_web || detail.html_wechat || ''
    setEditorState({
      html: seededHtml,
      document: detail.editor_document || null,
      text: detail.plain_text_content || '',
      dirty: false,
      version: `${detail.id}:${detail.updated_at || ''}:${detail.editor_updated_at || ''}:${seededHtml.length}`,
    })
  }, [
    detail?.summary_editor_document,
    detail?.summary_html,
    detail?.published_summary_html,
    detail?.summary_markdown,
    detail?.summary_updated_at,
    detail?.editor_document,
    detail?.editor_updated_at,
    detail?.final_html,
    detail?.html_web,
    detail?.html_wechat,
    detail?.id,
    detail?.plain_text_content,
    detail?.updated_at,
  ])

  useEffect(() => {
    setTopicResults(Array.isArray(detail?.topic_candidates) ? detail.topic_candidates : [])
  }, [detail?.id, detail?.topic_candidates])

  const persist = useCallback(async (includeEditorState = false) => {
    const payload = buildPersistPayload(
      form,
      detail,
      isEnglish,
      includeEditorState ? editorState : null,
      includeEditorState ? summaryEditorState : null,
    )
    return selectedId ? updateEditorialArticle(selectedId, payload) : createEditorialArticle(payload)
  }, [detail, editorState, form, isEnglish, selectedId, summaryEditorState])

  const ensureDraftForCover = useCallback(async () => {
    const payload = buildPersistPayload(
      form,
      detail,
      isEnglish,
      hasUnsavedManualEdits ? editorState : null,
      hasUnsavedSummaryEdits ? summaryEditorState : null,
    )
    if (!String(payload.source_markdown || '').trim() && !String(payload.content_markdown || '').trim()) {
      const placeholder = isEnglish ? 'Cover image placeholder.' : '配图占位稿。'
      payload.source_markdown = placeholder
      payload.content_markdown = placeholder
    }
    return selectedId ? updateEditorialArticle(selectedId, payload) : createEditorialArticle(payload)
  }, [
    detail,
    editorState,
    form,
    hasUnsavedManualEdits,
    hasUnsavedSummaryEdits,
    isEnglish,
    selectedId,
    summaryEditorState,
  ])

  const run = useCallback(
    async (key, task) => {
      setBusy(key)
      setError('')
      setMessage('')
      try {
        await task()
      } catch (err) {
        setError(err?.message || (isEnglish ? 'Action failed.' : '操作失败。'))
      } finally {
        setBusy('')
      }
    },
    [isEnglish],
  )

  const handleCoverFile = useCallback(
    (file, sourceLabel) =>
      run('cover-upload', async () => {
        if (!file) return
        const saved = await ensureDraftForCover()
        const payload = await uploadEditorialFile(file, {
          usage: 'cover',
          editorialId: saved.id,
        })
        await refreshAll(payload.article.id)
        setMessage(
          sourceLabel === 'paste'
            ? isEnglish
              ? 'Cover image pasted into the draft.'
              : '配图已通过粘贴写入草稿。'
            : isEnglish
              ? `Cover image uploaded: ${payload.filename}`
              : `配图已上传：${payload.filename}`,
        )
      }),
    [ensureDraftForCover, isEnglish, refreshAll, run],
  )

  const handleCoverPaste = useCallback(
    (event) => {
      const items = Array.from(event.clipboardData?.items || [])
      const imageItem = items.find((item) => String(item.type || '').startsWith('image/'))
      if (!imageItem) return
      const file = imageItem.getAsFile()
      if (!file) return
      event.preventDefault()
      handleCoverFile(file, 'paste')
    },
    [handleCoverFile],
  )

  const handleSaveDraft = useCallback(
    () =>
      run('save', async () => {
        const saved = await persist(hasUnsavedManualEdits || hasUnsavedSummaryEdits)
        await refreshAll(saved.id)
        setMessage(isEnglish ? 'Draft saved.' : '草稿已保存。')
      }),
    [hasUnsavedManualEdits, hasUnsavedSummaryEdits, isEnglish, persist, refreshAll, run],
  )

  const previewStatus = useMemo(() => {
    if (!detail) return isEnglish ? 'Preview pending' : '等待生成预览'
    if (detail.status === 'published' && detail.has_unpublished_changes) {
      return isEnglish ? 'Live article is published, current edits are waiting to be republished' : '线上文章已发布，当前改动待重新发布'
    }
    if (detail.status === 'published' && detail.is_reopened_from_published) {
      return isEnglish ? 'Live article is published and has been reopened in the draft box' : '线上正文已发布，当前已重新进入草稿箱'
    }
    if (detail.status === 'published') return isEnglish ? 'Published' : '已发布'
    if (detail.final_html) return isEnglish ? 'Formatted HTML ready' : '最终 HTML 已生成'
    if (detail.last_formatted_at) return isEnglish ? 'Preview expired, re-run auto format' : '预览已过期，需要重新自动排版'
    return isEnglish ? 'Not formatted yet' : '尚未自动排版'
  }, [detail, isEnglish])

  const summaryStatus = useMemo(() => {
    if (!detail) return isEnglish ? 'Summary pending' : '等待生成摘要'
    if (detail.status === 'published' && detail.summary_has_unpublished_changes) {
      return isEnglish ? 'Live summary is published, current edits are waiting to be republished' : '线上摘要已发布，当前改动待重新发布'
    }
    if (detail.status === 'published' && detail.is_reopened_from_published) {
      return isEnglish ? 'Live summary is published and has been reopened in the draft box' : '线上摘要已发布，当前已重新进入草稿箱'
    }
    if (detail.status === 'published' && detail.published_summary_html) {
      return isEnglish ? 'Published summary ready' : '线上摘要已发布'
    }
    if (detail.summary_html) {
      return detail.summary_model ? (isEnglish ? 'AI summary ready' : 'AI 摘要已生成') : isEnglish ? 'Summary ready' : '摘要已生成'
    }
    return isEnglish ? 'Summary not generated yet' : '尚未生成摘要'
  }, [detail, isEnglish])

  const summaryHelperLine = useMemo(() => {
    if (summaryEditorState.dirty) {
      return isEnglish ? 'Current summary contains unsaved manual edits' : '当前摘要包含人工修改，尚未保存'
    }
    if (detail?.summary_model) {
      return isEnglish ? 'Current summary comes from AI generation' : '当前摘要来自 AI 自动生成'
    }
    if (detail?.summary_html) {
      return isEnglish ? 'Current summary comes from manual or historical editorial content' : '当前摘要来自人工修改或历史回填'
    }
    return isEnglish ? 'Generate an AI summary first, then refine it manually if needed' : '先生成 AI 摘要，再按需人工微调'
  }, [detail?.summary_html, detail?.summary_model, isEnglish, summaryEditorState.dirty])

  const resetDraft = () => {
    clearEditorialEntryQuery()
    setSelectedId(null)
    setDetail(null)
    setForm(DEFAULT_FORM)
    setSummaryEditorState(EMPTY_EDITOR_STATE)
    setEditorState(EMPTY_EDITOR_STATE)
    setTopicQuery('')
    setTopicResults([])
    setError('')
    setMessage('')
  }

  const handleDeleteDraft = useCallback(
    async (article) => {
      if (!article?.id) return
      if (!canDeleteDraftEntry(article)) {
        throw new Error(isEnglish ? 'Published articles cannot be deleted from the draft box.' : '已发布文章不能从草稿箱直接删除。')
      }
      const confirmed = window.confirm(
        isEnglish
          ? `Delete draft "${article.title || 'Untitled draft'}"? This cannot be undone.`
          : `确定删除草稿《${article.title || '未命名草稿'}》吗？此操作不可撤销。`,
      )
      if (!confirmed) return
      await deleteEditorialArticle(article.id)
      if (selectedId === article.id) clearEditorialEntryQuery()
      await refreshAll(selectedId === article.id ? null : selectedId)
      setMessage(isEnglish ? 'Draft deleted.' : '草稿已删除。')
      if (selectedId === article.id) {
        setEditorState(EMPTY_EDITOR_STATE)
      }
    },
    [clearEditorialEntryQuery, isEnglish, refreshAll, selectedId],
  )

  const handleSearchTopics = useCallback(
    () =>
      run('topic-search', async () => {
        const items = await fetchEditorialTopics(topicQuery, 12)
        setTopicResults(items)
      }),
    [run, topicQuery],
  )

  const appendTopic = useCallback((candidate) => {
    setForm((current) => {
      const currentTopics = Array.isArray(current.selected_topics) ? current.selected_topics : []
      if (currentTopics.some((item) => topicKey(item) === topicKey(candidate))) {
        return current
      }
      return {
        ...current,
        selected_topics: [...currentTopics, candidate],
      }
    })
  }, [])

  const moveSelectedTopic = useCallback((index, direction) => {
    setForm((current) => {
      const currentTopics = Array.isArray(current.selected_topics) ? [...current.selected_topics] : []
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= currentTopics.length) return current
      ;[currentTopics[index], currentTopics[targetIndex]] = [currentTopics[targetIndex], currentTopics[index]]
      return {
        ...current,
        selected_topics: currentTopics,
      }
    })
  }, [])


  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,.98),rgba(10,5,96,.88)_58%,rgba(234,107,0,.24))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.1fr_.9fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Editorial Admin' : '编辑台'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
              {isEnglish ? 'Final draft on top, raw draft below' : '上方最终成品，下方原稿'}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'This workbench keeps only the in-site workflow: raw draft, AI auto layout, tag confirmation, column confirmation, save, and publish.'
                : '这版编辑台只保留站内发布流程：原稿、AI 自动排版、标签确认、栏目确认、保存和发布。'}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={resetDraft}
                className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-fudan-blue"
              >
                <Save size={16} />
                {isEnglish ? 'New draft' : '新建草稿'}
              </button>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold text-white"
              >
                <FileUp size={16} />
                {isEnglish ? 'Upload file' : '上传原稿'}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".md,.txt,.html,.htm,.docx,text/plain,text/markdown,text/html,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="hidden"
                onChange={(event) =>
                  run('upload', async () => {
                    const file = event.target.files?.[0]
                    if (!file) return
                    const payload = await uploadEditorialFile(file)
                    await refreshAll(payload.article.id)
                    setMessage(isEnglish ? `Imported ${payload.filename}` : `已导入 ${payload.filename}`)
                    event.target.value = ''
                  })
                }
              />
              <input
                ref={coverFileRef}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.gif,.bmp,.avif,image/png,image/jpeg,image/webp,image/gif,image/bmp,image/avif"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  handleCoverFile(file, 'upload')
                }}
              />
            </div>
          </div>
          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Drafts' : '草稿数'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{dashboard?.draft_count ?? 0}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Ready to publish' : '发布前校验'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">
                {detail?.publish_validation?.length ? detail.publish_validation.length : 0}
              </div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Published' : '已发布'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{dashboard?.published_count ?? 0}</div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {message ? <div className="mt-6 text-sm text-emerald-700">{message}</div> : null}
      {reopenedFromArticle && requestedEditorialId && detail?.id === requestedEditorialId ? (
        <div className="mt-6 rounded-[1.1rem] border border-fudan-blue/15 bg-fudan-blue/10 px-5 py-4 text-sm leading-7 text-fudan-blue">
          {isEnglish
            ? 'This draft was reopened from a live article. The online version will not change until you publish again.'
            : '当前稿件来自线上正文回编。在你再次点击发布前，线上正式文章不会被覆盖。'}
        </div>
      ) : null}

      <section className="mt-8 grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="fudan-panel p-6">
          <div className="flex items-center justify-between gap-3">
            <div className="section-kicker">{isEnglish ? 'Draft list' : '草稿列表'}</div>
            <div className="text-xs text-slate-400">{isEnglish ? 'Current draft box' : '当前草稿箱'}</div>
          </div>
          <div className="mt-4 space-y-3">
            {articles.length ? (
              articles.map((item) => (
                <div
                  key={item.id}
                  className={`relative rounded-[1.2rem] border p-4 transition ${
                    selectedId === item.id ? 'border-fudan-blue bg-fudan-blue/5' : 'border-slate-200/70 bg-white hover:border-fudan-orange/30'
                  }`}
                >
                  {canDeleteDraftEntry(item) ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        run('delete', async () => {
                          await handleDeleteDraft(item)
                        })
                      }}
                      className="absolute right-3 top-3 inline-flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition hover:border-red-200 hover:text-red-500"
                      title={isEnglish ? 'Delete draft' : '删除草稿'}
                    >
                      <Trash2 size={15} />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => run('select', async () => {
                      if (requestedEditorialId && requestedEditorialId !== item.id) {
                        clearEditorialEntryQuery()
                      }
                      await syncDetail(item.id)
                    })}
                    className={`block w-full text-left ${canDeleteDraftEntry(item) ? 'pr-10' : ''}`}
                  >
                    <div className="font-serif text-lg font-bold text-fudan-blue">{item.title}</div>
                    <div className={`mt-2 inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold ${getDraftStatusClass(item)}`}>
                      {getDraftStatusLabel(item, isEnglish)}
                    </div>
                    <div className="mt-3 text-sm text-slate-500 line-clamp-2">{item.excerpt || (isEnglish ? 'No summary yet.' : '暂无摘要。')}</div>
                  </button>
                </div>
              ))
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-slate-200 px-4 py-5 text-sm leading-7 text-slate-400">
                {isEnglish ? 'No drafts in the draft box yet.' : '当前草稿箱里还没有稿件。'}
              </div>
            )}
          </div>
        </aside>

        <div className="space-y-6">
          <section className="fudan-panel p-6">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <input
                name="title"
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                placeholder={isEnglish ? 'Title' : '标题'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none xl:col-span-2"
              />
              <input
                name="subtitle"
                value={form.subtitle}
                onChange={(event) => setForm((current) => ({ ...current, subtitle: event.target.value }))}
                placeholder={isEnglish ? 'Subtitle' : '副标题'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none xl:col-span-2"
              />
              <input
                name="author"
                value={form.author}
                onChange={(event) => setForm((current) => ({ ...current, author: event.target.value }))}
                placeholder={isEnglish ? 'Author' : '作者'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="organization"
                value={form.organization}
                onChange={(event) => setForm((current) => ({ ...current, organization: event.target.value }))}
                placeholder={isEnglish ? 'Editor' : '编辑'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="publish_date"
                type="date"
                value={form.publish_date}
                onChange={(event) => setForm((current) => ({ ...current, publish_date: event.target.value }))}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <select
                name="access_level"
                value={form.access_level}
                onChange={(event) => setForm((current) => ({ ...current, access_level: event.target.value }))}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              >
                <option value="public">{isEnglish ? 'Public' : '公开'}</option>
                <option value="member">{isEnglish ? 'Member' : '会员'}</option>
                <option value="paid">{isEnglish ? 'Paid' : '付费'}</option>
              </select>
              <input
                name="source_url"
                value={form.source_url}
                onChange={(event) => setForm((current) => ({ ...current, source_url: event.target.value }))}
                placeholder={isEnglish ? 'Source URL' : '来源链接'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none xl:col-span-2"
              />
              <select
                name="layout_mode"
                value={form.layout_mode}
                onChange={(event) => setForm((current) => ({ ...current, layout_mode: event.target.value }))}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              >
                <option value="auto">{isEnglish ? 'Auto layout' : '自动排版'}</option>
                <option value="insight">{isEnglish ? 'Insight longform' : '深度长文'}</option>
                <option value="briefing">{isEnglish ? 'Briefing' : '快报短版'}</option>
                <option value="interview">{isEnglish ? 'Interview' : '访谈实录'}</option>
              </select>
              <textarea
                name="formatting_notes"
                rows={3}
                value={form.formatting_notes}
                onChange={(event) => setForm((current) => ({ ...current, formatting_notes: event.target.value }))}
                placeholder={isEnglish ? 'Optional formatting notes for AI layout' : '给 AI 自动排版的补充说明，可留空'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none xl:col-span-4"
              />
            </div>

            <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="rounded-[1.3rem] border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                  {isEnglish ? 'Cover preview' : '配图预览'}
                </div>
                {coverUrl ? (
                  <img
                    src={coverUrl}
                    alt={isEnglish ? 'Article cover preview' : '文章配图预览'}
                    className="max-h-[320px] w-full rounded-[1rem] object-cover"
                  />
                ) : (
                  <div className="rounded-[1rem] border border-dashed border-slate-300 px-5 py-8 text-sm leading-7 text-slate-500">
                    {isEnglish ? 'No article cover image yet.' : '当前还没有文章配图。'}
                  </div>
                )}
              </div>
              <div className="space-y-4">
                <button
                  type="button"
                  onClick={() => coverFileRef.current?.click()}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-[1.2rem] border border-fudan-blue/20 bg-fudan-blue/5 px-4 py-4 text-sm font-semibold text-fudan-blue transition hover:bg-fudan-blue/10"
                >
                  {busy === 'cover-upload' ? <LoaderCircle size={16} className="animate-spin" /> : <FileUp size={16} />}
                  {isEnglish ? 'Upload cover image' : '上传配图'}
                </button>
                <button
                  type="button"
                  onClick={() => setForm((current) => ({ ...current, cover_image_url: '' }))}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-[1.2rem] border border-slate-200 bg-white px-4 py-4 text-sm font-semibold text-slate-600 transition hover:border-red-200 hover:text-red-500"
                >
                  <X size={16} />
                  {isEnglish ? 'Clear cover image' : '清空配图'}
                </button>
                <div
                  data-testid="editorial-cover-paste-zone"
                  tabIndex={0}
                  onClick={(event) => event.currentTarget.focus()}
                  onPaste={handleCoverPaste}
                  className="rounded-[1.2rem] border border-dashed border-emerald-300 bg-emerald-50 px-4 py-5 text-sm leading-7 text-emerald-700 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200"
                >
                  {isEnglish
                    ? 'Click here and paste an image from your clipboard to replace the current article cover.'
                    : '点击这里后直接粘贴图片，即可把剪贴板里的图片设为当前文章配图。'}
                </div>
                <div className="rounded-[1.2rem] border border-slate-200 bg-white px-4 py-4 text-xs leading-6 text-slate-500">
                  {isEnglish
                    ? 'The uploaded cover will stay in the draft, and after publishing it will continue into the live article card and cover chain.'
                    : '上传后的配图会先保留在草稿里，发布后继续进入正式文章卡片与封面链路。'}
                </div>
              </div>
            </div>
          </section>

          <section className="fudan-panel p-6">
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() =>
                  run('format', async () => {
                    const saved = await persist(hasUnsavedManualEdits || hasUnsavedSummaryEdits)
                    const article = await autoFormatEditorialArticle(saved.id, {
                      source_markdown: form.source_markdown,
                      layout_mode: form.layout_mode,
                      formatting_notes: form.formatting_notes,
                    })
                    await refreshAll(article.id)
                    setMessage(isEnglish ? 'AI layout completed.' : 'AI 自动排版已完成。')
                  })
                }
                className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white"
              >
                {busy === 'format' ? <LoaderCircle size={16} className="animate-spin" /> : <Wand2 size={16} />}
                {isEnglish ? 'Auto format' : '自动排版'}
              </button>
              <button
                type="button"
                onClick={() =>
                  run('summary', async () => {
                    const saved = await persist(hasUnsavedManualEdits || hasUnsavedSummaryEdits)
                    const article = await autoSummarizeEditorialArticle(saved.id)
                    await refreshAll(article.id)
                    setMessage(isEnglish ? 'AI summary generated.' : 'AI 摘要已生成。')
                  })
                }
                className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-5 py-3 text-sm font-semibold text-fudan-blue"
              >
                {busy === 'summary' ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {isEnglish ? 'Auto summary' : '自动生成摘要'}
              </button>
              <button
                type="button"
                onClick={() =>
                  run('autotag', async () => {
                    const saved = await persist(hasUnsavedManualEdits || hasUnsavedSummaryEdits)
                    const article = await autotagEditorialArticle(saved.id)
                    await refreshAll(article.id)
                    setMessage(isEnglish ? 'Tags refreshed.' : 'AI 标签建议已更新。')
                  })
                }
                className="inline-flex items-center gap-2 rounded-full border border-fudan-orange/20 bg-fudan-orange/10 px-5 py-3 text-sm font-semibold text-fudan-orange"
              >
                {busy === 'autotag' ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {isEnglish ? 'Auto tag' : '自动打标签'}
              </button>
              <button
                type="button"
                onClick={() =>
                  run('publish', async () => {
                    if (hasUnsavedManualEdits || hasUnsavedSummaryEdits) {
                      throw new Error(
                        isEnglish
                          ? 'Save the manual edits in the summary or final draft before publishing.'
                          : '请先保存摘要区或最终稿区里的人工修改，再执行发布。',
                      )
                    }
                    const saved = await persist(false)
                    if (saved?.publish_validation?.length) {
                      setSelectedId(saved.id)
                      setDetail(saved)
                      setForm(normalizeForm(saved))
                      const issueText = saved.publish_validation.map((item) => item.message).filter(Boolean).join('；')
                      throw new Error(issueText || (isEnglish ? 'Publish validation failed after saving the latest draft.' : '保存最新草稿后，发布前校验未通过。'))
                    }
                    const result = await publishEditorialArticle(saved.id)
                    await refreshAll(null)
                    const topicTitles = Array.isArray(result?.selected_topics)
                      ? result.selected_topics.map((topic) => topic?.title).filter(Boolean)
                      : []
                    setMessage(
                      isEnglish
                        ? `Published to article #${result.article_id}. Topics: ${topicTitles.length ? topicTitles.join(', ') : 'none'}. The draft has left the draft box automatically.`
                        : `已发布到正式文章 #${result.article_id}。专题同步：${topicTitles.length ? topicTitles.join('、') : '未进入专题'}。该稿件已自动离开草稿箱。`,
                    )
                  })
                }
                className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-semibold text-emerald-700"
              >
                {busy === 'publish' ? <LoaderCircle size={16} className="animate-spin" /> : <Rocket size={16} />}
                {isEnglish ? 'Publish' : '发布'}
              </button>
              {canDeleteSelectedDraft ? (
                <button
                  type="button"
                  onClick={() =>
                    run('delete', async () => {
                      await handleDeleteDraft(detail)
                    })
                  }
                  className="inline-flex items-center gap-2 rounded-full border border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-600"
                >
                  {busy === 'delete' ? <LoaderCircle size={16} className="animate-spin" /> : <Trash2 size={16} />}
                  {isEnglish ? 'Delete draft' : '删除草稿'}
                </button>
              ) : null}
            </div>
          </section>

          <section className="grid gap-6 lg:grid-cols-[1.1fr_.9fr]">
            <div className="fudan-panel p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="section-kicker">{isEnglish ? 'Tags' : '标签确认'}</div>
                  <div className="mt-2 text-sm text-slate-500">
                    {isEnglish ? 'AI suggests tags first. Remove what should not stay.' : '先用 AI 建议标签，再把不应保留的标签去掉。'}
                  </div>
                </div>
                {detail?.ai_tags?.length ? (
                  <button
                    type="button"
                    onClick={() => setForm((current) => ({ ...current, tags: detail.ai_tags }))}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-fudan-blue"
                  >
                    <RefreshCw size={15} />
                    {isEnglish ? 'Reset to AI tags' : '恢复 AI 建议'}
                  </button>
                ) : null}
              </div>

              <div className="mt-5 flex flex-wrap gap-3">
                {form.tags.length ? (
                  form.tags.map((tag) => (
                    <TagChip
                      key={tagKey(tag)}
                      tag={tag}
                      removable
                      onRemove={(target) =>
                        setForm((current) => ({
                          ...current,
                          tags: current.tags.filter((item) => tagKey(item) !== tagKey(target)),
                        }))
                      }
                    />
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">
                    {isEnglish ? 'No retained tags yet.' : '当前还没有保留标签。'}
                  </div>
                )}
              </div>

              {detail?.removed_tags?.length ? (
                <div className="mt-5">
                  <div className="text-xs uppercase tracking-[.18em] text-slate-400">{isEnglish ? 'Removed tags' : '已移除标签'}</div>
                  <div className="mt-3 flex flex-wrap gap-3">
                    {detail.removed_tags.map((tag) => (
                      <span key={tagKey(tag)} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                        {tag.name}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="space-y-6">
              <div className="fudan-panel p-6">
                <div className="section-kicker">{isEnglish ? 'Column' : '栏目确认'}</div>
                <div className="mt-2 text-sm text-slate-500">
                  {detail?.primary_column_manual
                    ? isEnglish
                      ? 'Current column is manually confirmed.'
                      : '当前栏目为人工指定。'
                    : isEnglish
                      ? 'Current column follows the AI suggestion.'
                      : '当前栏目跟随 AI 建议。'}
                </div>
                <select
                  name="primary_column_slug"
                  value={form.primary_column_slug}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      primary_column_slug: event.target.value,
                      primary_column_manual: true,
                    }))
                  }
                  className="mt-4 w-full rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                >
                  <option value="">{isEnglish ? 'Select a column' : '选择栏目'}</option>
                  {columns.map((item) => (
                    <option key={item.slug} value={item.slug}>
                      {item.name || item.slug}
                    </option>
                  ))}
                </select>
                <div className="mt-4 rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                  <div>{isEnglish ? 'AI suggestion' : 'AI 建议'}: {aiColumn?.name || detail?.primary_column_ai_slug || (isEnglish ? 'Not available' : '暂无')}</div>
                  <div>{isEnglish ? 'Current selection' : '当前选择'}: {currentColumn?.name || (isEnglish ? 'Not selected' : '未选择')}</div>
                </div>
              </div>

              <div className="fudan-panel p-6">
                <div className="section-kicker">{isEnglish ? 'Topics' : '专题选择'}</div>
                <div className="mt-2 text-sm text-slate-500">
                  {isEnglish ? 'Choose which published topics this article should enter after publishing.' : '选择这篇文章发布后要进入哪些已发布专题。'}
                </div>

                <div className="mt-4 flex flex-wrap gap-3">
                  {(form.selected_topics || []).length ? (
                    form.selected_topics.map((topic, index) => (
                      <div
                        key={topicKey(topic)}
                        className="flex min-w-[220px] items-center justify-between gap-3 rounded-[1rem] border border-fudan-blue/20 bg-fudan-blue/10 px-4 py-3 text-sm font-semibold text-fudan-blue"
                      >
                        <div className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.2em] text-fudan-blue/60">
                            {isEnglish ? `Order ${index + 1}` : `顺序 ${index + 1}`}
                          </div>
                          <div className="truncate">{topic.title}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => moveSelectedTopic(index, -1)}
                            disabled={index === 0}
                            className="rounded-full border border-white/70 bg-white/85 px-3 py-1 text-xs font-semibold text-fudan-blue transition disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            {isEnglish ? 'Up' : '上移'}
                          </button>
                          <button
                            type="button"
                            onClick={() => moveSelectedTopic(index, 1)}
                            disabled={index === (form.selected_topics || []).length - 1}
                            className="rounded-full border border-white/70 bg-white/85 px-3 py-1 text-xs font-semibold text-fudan-blue transition disabled:cursor-not-allowed disabled:opacity-35"
                          >
                            {isEnglish ? 'Down' : '下移'}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setForm((current) => ({
                                ...current,
                                selected_topics: (current.selected_topics || []).filter((item) => topicKey(item) !== topicKey(topic)),
                              }))
                            }
                            className="rounded-full border border-white/70 bg-white/85 px-3 py-1 text-xs font-semibold text-fudan-blue transition hover:border-fudan-orange/30 hover:text-fudan-orange"
                          >
                            {isEnglish ? 'Remove' : '移除'}
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-[1.2rem] border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">
                      {isEnglish ? 'No topics selected yet.' : '当前还没有选择专题。'}
                    </div>
                  )}
                </div>

                {(form.selected_topics || []).length ? (
                  <div className="mt-3 text-xs leading-6 text-slate-500">
                    {isEnglish ? 'This order is used when the publish step writes topic relationships.' : '发布时写入专题关系时，会按这里的顺序同步。'}
                  </div>
                ) : null}

                <div className="mt-5 flex flex-wrap gap-3">
                  <input
                    value={topicQuery}
                    onChange={(event) => setTopicQuery(event.target.value)}
                    placeholder={isEnglish ? 'Search published topics' : '搜索已发布专题'}
                    className="min-w-[220px] flex-1 rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleSearchTopics}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue"
                  >
                    {busy === 'topic-search' ? <LoaderCircle size={15} className="animate-spin" /> : null}
                    {isEnglish ? 'Search topics' : '搜索专题'}
                  </button>
                </div>

                <div className="mt-4 space-y-3">
                  {topicResults.length ? (
                    topicResults.map((topic) => {
                      const exists = (form.selected_topics || []).some((item) => topicKey(item) === topicKey(topic))
                      return (
                        <div key={topicKey(topic)} className="flex items-start justify-between gap-4 rounded-[1rem] border border-slate-200 bg-slate-50 p-3">
                          <div>
                            <div className="font-semibold text-fudan-blue">{topic.title}</div>
                            {topic.subtitle ? <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{topic.subtitle}</div> : null}
                            {topic.description ? <div className="mt-2 text-sm leading-6 text-slate-600">{topic.description}</div> : null}
                          </div>
                          <button
                            type="button"
                            disabled={exists}
                            onClick={() => appendTopic(topic)}
                            className="rounded-full border border-fudan-orange/20 bg-fudan-orange/10 px-4 py-2 text-sm font-semibold text-fudan-orange disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {isEnglish ? 'Add' : '加入'}
                          </button>
                        </div>
                      )
                    })
                  ) : (
                    <div className="text-sm text-slate-400">{isEnglish ? 'Search to load topic candidates.' : '先搜索，再加载专题候选。'}</div>
                  )}
                </div>
              </div>

              <div className="fudan-panel p-6">
                <div className="section-kicker">{isEnglish ? 'Publish check' : '发布前校验'}</div>
                <div className="mt-4 rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                  {detail?.publish_validation?.length ? (
                    detail.publish_validation.map((issue) => <div key={issue.code}>• {issue.message}</div>)
                  ) : (
                    <div>{isEnglish ? 'Current draft passes publish validation.' : '当前稿件已通过发布前校验。'}</div>
                  )}
                </div>
              </div>
            </div>
          </section>

          <section className="space-y-6">
            <div className="fudan-panel overflow-hidden p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="section-kicker">{isEnglish ? 'AI Summary' : 'AI 摘要工作区'}</div>
                  <div className="mt-2 text-sm text-slate-500">{summaryStatus}</div>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                  <button
                    type="button"
                    onClick={handleSaveDraft}
                    className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/15 bg-fudan-blue/10 px-4 py-2 font-semibold text-fudan-blue"
                  >
                    {busy === 'save' ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
                    {isEnglish ? 'Save draft' : '保存'}
                  </button>
                  {detail?.summary_model ? <span>{detail.summary_model}</span> : null}
                  {detail?.has_summary_backup ? (
                    <button
                      type="button"
                      onClick={() =>
                        run('restore-summary', async () => {
                          if (hasUnsavedSummaryEdits) {
                            throw new Error(
                              isEnglish
                                ? 'Save or discard the current summary edits before restoring the backup.'
                                : '请先保存或放弃当前摘要区里的人工修改，再恢复上一版摘要。',
                            )
                          }
                          const restored = await updateEditorialArticle(detail.id, {
                            summary_html: detail.manual_summary_html_backup,
                          })
                          await refreshAll(restored.id)
                          setMessage(isEnglish ? 'The previous summary draft has been restored.' : '上一版摘要已恢复。')
                        })
                      }
                      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 font-semibold text-slate-600"
                    >
                      <RefreshCw size={15} />
                      {isEnglish ? 'Restore summary backup' : '恢复上一版摘要'}
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="mt-5">
                <RichPreviewEditor
                  isEnglish={isEnglish}
                  contentVersion={summaryEditorState.version}
                  initialDocument={detail?.summary_editor_document || null}
                  initialHtml={detail?.summary_html || detail?.published_summary_html || ''}
                  fallbackText={detail?.summary_markdown || detail?.excerpt || ''}
                  statusText={summaryStatus}
                  formatterModel={detail?.summary_model}
                  editorSource={summaryEditorState.dirty ? 'manual_edited' : detail?.summary_model ? 'ai_formatted' : detail?.summary_html ? 'imported_legacy_html' : null}
                  isDirty={summaryEditorState.dirty}
                  hasUnpublishedChanges={Boolean(detail?.summary_has_unpublished_changes)}
                  sectionKicker={isEnglish ? 'Summary Draft' : '摘要成品区'}
                  helperLineOverride={summaryHelperLine}
                  helpText={isEnglish ? 'Click directly inside the summary canvas to edit headings, bullets, emphasis, and paragraph rhythm.' : '直接点击摘要画布即可编辑摘要标题、要点、强调和段落节奏。'}
                  editablePanelTitle={isEnglish ? 'Editable summary canvas' : '可编辑摘要成品画布'}
                  previewPanelTitle={isEnglish ? 'Summary rendered preview' : '摘要最终呈现预览'}
                  editableFrameTitle="Editable editorial summary frame"
                  previewFrameTitle="Editorial summary preview frame"
                  onChange={(nextState) =>
                    setSummaryEditorState((current) => ({
                      ...current,
                      ...nextState,
                    }))
                  }
                />
              </div>
            </div>
            <div className="fudan-panel overflow-hidden p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="section-kicker">{isEnglish ? 'Final HTML preview' : '最终 HTML 预览'}</div>
                  <div className="mt-2 text-sm text-slate-500">{previewStatus}</div>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
                  <button
                    type="button"
                    onClick={handleSaveDraft}
                    className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/15 bg-fudan-blue/10 px-4 py-2 font-semibold text-fudan-blue"
                  >
                    {busy === 'save' ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
                    {isEnglish ? 'Save draft' : '保存'}
                  </button>
                  {detail?.formatter_model ? <span>{detail.formatter_model}</span> : null}
                  {detail?.has_manual_backup ? (
                    <button
                      type="button"
                      onClick={() =>
                        run('restore-manual', async () => {
                          if (hasUnsavedManualEdits) {
                            throw new Error(isEnglish ? 'Save or discard the current manual edits before restoring the backup.' : '请先保存或放弃当前右侧人工修改，再恢复上一版人工稿。')
                          }
                          const restored = await updateEditorialArticle(detail.id, {
                            final_html: detail.manual_final_html_backup,
                          })
                          await refreshAll(restored.id)
                          setMessage(isEnglish ? 'The previous manual draft has been restored.' : '上一版人工稿已恢复。')
                        })
                      }
                      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 font-semibold text-slate-600"
                    >
                      <RefreshCw size={15} />
                      {isEnglish ? 'Restore manual backup' : '恢复上一版人工稿'}
                    </button>
                  ) : null}
                  {detail?.article_id ? (
                    <Link to={`/article/${detail.article_id}`} className="rounded-full bg-fudan-blue px-4 py-2 font-semibold text-white">
                      {isEnglish ? 'Open article' : '打开正式文章'}
                    </Link>
                  ) : null}
                </div>
              </div>
              <div className="mt-5">
                <RichPreviewEditor
                  isEnglish={isEnglish}
                  contentVersion={editorState.version}
                  initialDocument={detail?.editor_document || null}
                  initialHtml={detail?.final_html || detail?.html_web || detail?.html_wechat || ''}
                  fallbackText={detail?.content_markdown || form.source_markdown}
                  statusText={previewStatus}
                  formatterModel={detail?.formatter_model}
                  editorSource={editorState.dirty ? 'manual_edited' : detail?.editor_source}
                  isDirty={editorState.dirty}
                  hasUnpublishedChanges={Boolean(detail?.has_unpublished_changes)}
                  onChange={(nextState) =>
                    setEditorState((current) => ({
                      ...current,
                      ...nextState,
                    }))
                  }
                />
              </div>
              {Array.isArray(detail?.render_metadata?.warnings) && detail.render_metadata.warnings.length ? (
                <div className="mt-4 rounded-[1.2rem] border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-900">
                  <div className="font-semibold">{isEnglish ? 'Render warnings' : '排版提醒'}</div>
                  <div className="mt-2 space-y-2">
                    {detail.render_metadata.warnings.map((warning) => (
                      <div key={warning}>{warning}</div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            <div className="fudan-panel p-6">
              <div className="mb-3 flex items-center justify-between">
                <div className="section-kicker">{isEnglish ? 'Raw draft' : '原稿'}</div>
                <div className="text-sm text-slate-500">
                  {sourceCount} {isEnglish ? 'chars' : '字'}
                </div>
              </div>
              <textarea
                name="source_markdown"
                rows={28}
                value={form.source_markdown}
                onChange={(event) => setForm((current) => ({ ...current, source_markdown: event.target.value }))}
                className="w-full rounded-[1.4rem] border border-slate-200 bg-slate-50 px-5 py-4 text-sm leading-7 outline-none"
                placeholder={isEnglish ? 'Paste the original draft here.' : '把原稿贴在这里。'}
              />
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}

export default EditorialWorkbenchPage
