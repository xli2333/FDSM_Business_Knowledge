import {
  FileText,
  LoaderCircle,
  Plus,
  RefreshCw,
  Rocket,
  Save,
  Sparkles,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createMediaAdminItem,
  deleteMediaAdminItem,
  fetchMediaAdminItem,
  fetchMediaAdminItems,
  fetchMediaAdminSourceItems,
  generateMediaAdminCopy,
  publishMediaAdminItem,
  reopenMediaAdminSourceItem,
  resolveApiUrl,
  updateMediaAdminItem,
  uploadMediaAdminFile,
} from '../api/index.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const DEFAULT_FORM = {
  kind: 'audio',
  title: '',
  summary: '',
  speaker: '',
  series_name: '',
  episode_number: 1,
  publish_date: new Date().toISOString().slice(0, 10),
  duration_seconds: 0,
  visibility: 'public',
  cover_image_url: '',
  media_url: '',
  source_url: '',
  body_markdown: '',
  transcript_markdown: '',
  script_markdown: '',
  chapters: [],
}

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function formatDuration(seconds, isEnglish) {
  const safe = Number(seconds || 0)
  if (!safe) return isEnglish ? 'Pending' : '待补充'
  const minutes = Math.floor(safe / 60)
  const remain = safe % 60
  return isEnglish ? `${minutes}m ${remain}s` : `${minutes} 分 ${remain} 秒`
}

function toForm(item) {
  return {
    kind: item?.kind || 'audio',
    title: item?.title || '',
    summary: item?.summary || '',
    speaker: item?.speaker || '',
    series_name: item?.series_name || '',
    episode_number: item?.episode_number || 1,
    publish_date: item?.publish_date || new Date().toISOString().slice(0, 10),
    duration_seconds: item?.duration_seconds || 0,
    visibility: item?.visibility || 'public',
    cover_image_url: item?.cover_image_url || '',
    media_url: item?.media_url || '',
    source_url: item?.source_url || '',
    body_markdown: item?.body_markdown || '',
    transcript_markdown: item?.transcript_markdown || '',
    script_markdown: item?.script_markdown || '',
    chapters: Array.isArray(item?.chapters) ? item.chapters : [],
  }
}

function buildPersistPayload(form) {
  return {
    kind: form.kind || 'audio',
    title: String(form.title || '').trim() || null,
    summary: String(form.summary || '').trim() || null,
    speaker: String(form.speaker || '').trim() || null,
    series_name: String(form.series_name || '').trim() || null,
    episode_number: Math.max(1, Number(form.episode_number || 1)),
    publish_date: form.publish_date || DEFAULT_FORM.publish_date,
    duration_seconds: Math.max(0, Number(form.duration_seconds || 0)),
    visibility: form.visibility || 'public',
    cover_image_url: String(form.cover_image_url || '').trim() || null,
    media_url: String(form.media_url || '').trim() || null,
    source_url: String(form.source_url || '').trim() || null,
    body_markdown: String(form.body_markdown || '').trim() || null,
    transcript_markdown: String(form.transcript_markdown || '').trim() || null,
    script_markdown: String(form.script_markdown || '').trim() || null,
    chapters: Array.isArray(form.chapters) ? form.chapters : [],
  }
}

function hasLocalDraftSeed(form) {
  if (!form) return false
  return Boolean(
    String(form.title || '').trim() ||
      String(form.summary || '').trim() ||
      String(form.speaker || '').trim() ||
      String(form.series_name || '').trim() ||
      String(form.cover_image_url || '').trim() ||
      String(form.source_url || '').trim() ||
      String(form.body_markdown || '').trim() ||
      String(form.transcript_markdown || '').trim() ||
      String(form.script_markdown || '').trim() ||
      Number(form.duration_seconds || 0) > 0 ||
      Number(form.episode_number || 1) > 1 ||
      (form.visibility || 'public') !== 'public' ||
      (form.publish_date || DEFAULT_FORM.publish_date) !== DEFAULT_FORM.publish_date,
  )
}

function getUploadAccept(kind, usage) {
  if (usage === 'cover') {
    return '.png,.jpg,.jpeg,.webp,.gif,.bmp,.avif,image/png,image/jpeg,image/webp,image/gif,image/bmp,image/avif'
  }
  if (usage === 'transcript' || usage === 'script') {
    return '.md,.txt,.html,.htm,.docx,text/plain,text/markdown,text/html,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  }
  return kind === 'video'
    ? '.mp4,.mov,.m4v,.webm,video/*'
    : '.mp3,.wav,.m4a,.aac,.ogg,audio/*'
}

function getDraftStatusLabel(item, isEnglish) {
  if (!item) return ''
  if (item.is_reopened_from_published) {
    return isEnglish ? 'Back in draft box' : '已打回草稿箱'
  }
  return isEnglish ? 'Draft' : '草稿'
}

function getDraftStatusClass(item) {
  if (item?.is_reopened_from_published) {
    return 'border-fudan-blue/15 bg-fudan-blue/10 text-fudan-blue'
  }
  return 'border-amber-200 bg-amber-50 text-fudan-orange'
}

function canDeleteDraft(item) {
  return Boolean(item)
}

function readMediaDuration(file, kind) {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      resolve(0)
      return
    }
    const element = document.createElement(kind === 'video' ? 'video' : 'audio')
    const objectUrl = URL.createObjectURL(file)
    element.preload = 'metadata'
    element.src = objectUrl
    element.onloadedmetadata = () => {
      const duration = Number.isFinite(element.duration) ? Math.max(0, Math.round(element.duration)) : 0
      URL.revokeObjectURL(objectUrl)
      resolve(duration)
    }
    element.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      resolve(0)
    }
  })
}

function MediaStudioPage() {
  const { isEnglish } = useLanguage()
  const mediaInputRef = useRef(null)
  const coverInputRef = useRef(null)
  const textUploadInputRef = useRef(null)
  const selectedIdRef = useRef(null)
  const [drafts, setDrafts] = useState([])
  const [sourceItems, setSourceItems] = useState([])
  const [sourceTotal, setSourceTotal] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState(DEFAULT_FORM)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [filterKind, setFilterKind] = useState('')
  const [sourceQuery, setSourceQuery] = useState('')

  useEffect(() => {
    selectedIdRef.current = selectedId
  }, [selectedId])

  const resetMessages = useCallback(() => {
    setError('')
    setMessage('')
  }, [])

  const syncDraftDetail = useCallback(async (id) => {
    const next = await fetchMediaAdminItem(id)
    setSelectedId(next.id)
    setDetail(next)
    setForm(toForm(next))
    return next
  }, [])

  const loadSourceItems = useCallback(async () => {
    const payload = await fetchMediaAdminSourceItems(filterKind, sourceQuery, 18)
    setSourceItems(payload.items || [])
    setSourceTotal(payload.total || 0)
    return payload
  }, [filterKind, sourceQuery])

  const loadDrafts = useCallback(
    async (preferredId = null) => {
      const payload = await fetchMediaAdminItems(filterKind, '', 80, '', 'active')
      const items = payload.items || []
      setDrafts(items)
      const candidateId =
        [preferredId, selectedIdRef.current, items[0]?.id].find((candidate) => items.some((item) => item.id === candidate)) || null
      if (candidateId) {
        await syncDraftDetail(candidateId)
      } else {
        setSelectedId(null)
        setDetail(null)
        setForm({
          ...DEFAULT_FORM,
          kind: filterKind || 'audio',
        })
      }
      return payload
    },
    [filterKind, syncDraftDetail],
  )

  const refreshAll = useCallback(async (preferredId = null) => {
    await Promise.all([loadDrafts(preferredId), loadSourceItems()])
  }, [loadDrafts, loadSourceItems])

  useEffect(() => {
    refreshAll().catch((err) => {
      setError(err?.message || (isEnglish ? 'Failed to load media studio.' : '媒体后台加载失败。'))
    })
  }, [isEnglish, refreshAll])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadSourceItems().catch(() => {})
    }, 280)
    return () => window.clearTimeout(timer)
  }, [loadSourceItems])

  const counts = useMemo(() => {
    const draftCount = drafts.length
    const audioDraftCount = drafts.filter((item) => item.kind === 'audio').length
    const videoDraftCount = drafts.filter((item) => item.kind === 'video').length
    return {
      draftCount,
      audioDraftCount,
      videoDraftCount,
      publishedCount: sourceTotal,
    }
  }, [drafts, sourceTotal])

  const textUploadUsage = form.kind === 'audio' ? 'transcript' : 'script'
  const textUploadLabel = form.kind === 'audio' ? (isEnglish ? 'Upload transcript' : '上传转录') : (isEnglish ? 'Upload script' : '上传脚本')

  const mediaUrl = resolveApiUrl(form.media_url)
  const coverUrl = resolveApiUrl(form.cover_image_url)

  const run = useCallback(
    async (key, task) => {
      setBusy(key)
      resetMessages()
      try {
        await task()
      } catch (err) {
        setError(err?.message || (isEnglish ? 'Action failed.' : '操作失败。'))
      } finally {
        setBusy('')
      }
    },
    [isEnglish, resetMessages],
  )

  const persistDraft = useCallback(async () => {
    const payload = buildPersistPayload(form)
    return selectedId ? updateMediaAdminItem(selectedId, payload) : createMediaAdminItem(payload)
  }, [form, selectedId])

  const handleFieldChange = (event) => {
    const { name, value } = event.target
    setForm((current) => ({
      ...current,
      [name]: ['episode_number', 'duration_seconds'].includes(name) ? Number(value || 0) : value,
    }))
  }

  const handleCreate = () => {
    resetMessages()
    setSelectedId(null)
    setDetail(null)
    setForm({
      ...DEFAULT_FORM,
      kind: filterKind || 'audio',
    })
  }

  const handleSelect = (id) =>
    run('select', async () => {
      await syncDraftDetail(id)
    })

  const handleSave = () =>
    run('save', async () => {
      const saved = await persistDraft()
      await refreshAll(saved.id)
      setMessage(isEnglish ? 'Draft saved.' : '草稿已保存。')
    })

  const handleDelete = () =>
    run('delete', async () => {
      if (!selectedId) return
      await deleteMediaAdminItem(selectedId)
      await refreshAll()
      setMessage(isEnglish ? 'Draft deleted.' : '草稿已删除。')
    })

  const handleGenerateCopy = () =>
    run('generate', async () => {
      const saved = await persistDraft()
      const generated = await generateMediaAdminCopy(saved.id)
      await refreshAll(generated.id)
      setMessage(isEnglish ? 'Program copy generated.' : '节目文字素材已生成。')
    })

  const handlePublish = () =>
    run('publish', async () => {
      const saved = await persistDraft()
      const published = await publishMediaAdminItem(saved.id)
      await refreshAll()
      setMessage(
        published?.media_item_id
          ? isEnglish
            ? `Published to media item #${published.media_item_id}. The draft was removed from the draft box automatically.`
            : `已发布到媒体内容 #${published.media_item_id}，当前草稿已自动从草稿箱删除。`
          : isEnglish
            ? 'Published successfully.'
            : '发布成功。',
      )
    })

  const handleReopen = (mediaItemId) =>
    run('reopen', async () => {
      const reopened = await reopenMediaAdminSourceItem(mediaItemId)
      await refreshAll(reopened.id)
      setMessage(isEnglish ? 'Published media was sent back to the draft box.' : '已发布媒体已打回草稿箱。')
    })

  const handleUpload = async (usage, file) => {
    if (!file) return
    resetMessages()
    setBusy(usage)
    try {
      let workingDraftId = selectedId || null
      if (selectedId || hasLocalDraftSeed(form)) {
        const savedDraft = await persistDraft()
        workingDraftId = savedDraft.id
      }
      const duration = usage === 'media' ? await readMediaDuration(file, form.kind) : 0
      const uploaded = await uploadMediaAdminFile(file, form.kind, usage, {
        draftId: workingDraftId || undefined,
        durationSeconds: duration || Number(form.duration_seconds || 0),
      })
      await refreshAll(uploaded?.item?.id || workingDraftId || null)
      if (usage === 'media') {
        setMessage(isEnglish ? 'Primary media uploaded and synced to the draft.' : '主媒体文件已上传并写入草稿。')
      } else if (usage === 'cover') {
        setMessage(isEnglish ? 'Cover image uploaded and synced to the draft.' : '首页图已上传并写入草稿。')
      } else {
        setMessage(
          form.kind === 'audio'
            ? isEnglish
              ? 'Transcript uploaded and parsed.'
              : '转录文件已上传并解析。'
            : isEnglish
              ? 'Script uploaded and parsed.'
              : '脚本文件已上传并解析。',
        )
      }
    } catch (err) {
      setError(err?.message || (isEnglish ? 'Upload failed.' : '上传失败。'))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Admin Media Workbench' : '管理端媒体工作台'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
              {isEnglish ? 'Manage audio and video with article-style draft flow' : '按文章草稿流管理音频与视频'}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'Upload the primary media file first, then upload transcript or script, generate program copy, save drafts, publish, and reopen live media back into the draft box when needed.'
                : '先上传主媒体文件，再上传转录或脚本，自动生成节目简介等文字素材，保存草稿、发布，并在需要时把线上内容重新打回草稿箱。'}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleCreate}
                className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
              >
                <Plus size={16} />
                {isEnglish ? 'New draft' : '新建草稿'}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={Boolean(busy)}
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'save' ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}
                {isEnglish ? 'Save draft' : '保存草稿'}
              </button>
              <button
                type="button"
                onClick={handleGenerateCopy}
                disabled={Boolean(busy)}
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'generate' ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {isEnglish ? 'Generate copy' : '生成文案'}
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={Boolean(busy)}
                className="inline-flex items-center gap-2 rounded-full bg-fudan-orange px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-[#d95f00] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'publish' ? <LoaderCircle size={16} className="animate-spin" /> : <Rocket size={16} />}
                {isEnglish ? 'Publish' : '发布'}
              </button>
            </div>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-2 lg:grid-cols-2">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Active drafts' : '活跃草稿'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.draftCount}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Published items' : '已发布内容'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.publishedCount}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Audio drafts' : '音频草稿'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.audioDraftCount}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Video drafts' : '视频草稿'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.videoDraftCount}</div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {message ? <div className="mt-6 text-sm text-emerald-700">{message}</div> : null}

      <section className="mt-8 grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
        <aside className="space-y-6">
          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Filter' : '筛选'}</div>
            <div className="mt-4 grid gap-3">
              <select
                value={filterKind}
                onChange={(event) => setFilterKind(event.target.value)}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              >
                <option value="">{isEnglish ? 'All kinds' : '全部类型'}</option>
                <option value="audio">{isEnglish ? 'Audio' : '音频'}</option>
                <option value="video">{isEnglish ? 'Video' : '视频'}</option>
              </select>
              <button
                type="button"
                onClick={() => refreshAll(selectedIdRef.current).catch(() => setError(isEnglish ? 'Failed to refresh.' : '刷新失败。'))}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-fudan-blue px-4 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
              >
                <RefreshCw size={15} />
                {isEnglish ? 'Refresh' : '刷新'}
              </button>
            </div>
          </div>

          <div className="fudan-panel p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="section-kicker">{isEnglish ? 'Draft box' : '草稿箱'}</div>
                <div className="mt-1 text-xs text-slate-400">{isEnglish ? 'Only active drafts stay here' : '这里只显示当前活跃草稿'}</div>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">{counts.draftCount}</span>
            </div>
            <div className="mt-4 space-y-3">
              {drafts.length ? (
                drafts.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleSelect(item.id)}
                    className={[
                      'block w-full rounded-[1.2rem] border p-4 text-left transition',
                      selectedId === item.id ? 'border-fudan-blue bg-fudan-blue/5' : 'border-slate-200/70 bg-white hover:bg-slate-50',
                    ].join(' ')}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-serif text-lg font-bold text-fudan-blue">{item.title || byLanguage(isEnglish, '未命名草稿', 'Untitled draft')}</div>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                          <span>{item.kind === 'audio' ? byLanguage(isEnglish, '音频', 'Audio') : byLanguage(isEnglish, '视频', 'Video')}</span>
                          <span>/</span>
                          <span>{formatDuration(item.duration_seconds, isEnglish)}</span>
                        </div>
                      </div>
                      <span className={['rounded-full border px-3 py-1 text-[11px] font-semibold', getDraftStatusClass(item)].join(' ')}>
                        {getDraftStatusLabel(item, isEnglish)}
                      </span>
                    </div>
                  </button>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {isEnglish ? 'No drafts in the draft box yet.' : '当前草稿箱里还没有稿件。'}
                </div>
              )}
            </div>
          </div>

          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Published library' : '已发布媒体'}</div>
            <div className="mt-4 grid gap-3">
              <input
                value={sourceQuery}
                onChange={(event) => setSourceQuery(event.target.value)}
                placeholder={isEnglish ? 'Search published media' : '搜索已发布媒体'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
            </div>
            <div className="mt-4 space-y-3">
              {sourceItems.length ? (
                sourceItems.map((item) => (
                  <div key={item.id} className="rounded-[1.2rem] border border-slate-200/70 bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-serif text-lg font-bold text-fudan-blue">{item.title}</div>
                        <div className="mt-2 text-xs text-slate-500">
                          {item.kind === 'audio' ? byLanguage(isEnglish, '音频', 'Audio') : byLanguage(isEnglish, '视频', 'Video')}
                          {' / '}
                          {item.visibility_label}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleReopen(item.media_item_id || item.id)}
                        disabled={Boolean(busy)}
                        className="rounded-full border border-fudan-blue/20 bg-fudan-blue/5 px-3 py-2 text-xs font-semibold text-fudan-blue transition hover:bg-fudan-blue/10 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {busy === 'reopen' ? (isEnglish ? 'Working...' : '处理中...') : isEnglish ? 'Send to draft box' : '打回草稿箱'}
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {isEnglish ? 'No published media matched the current search.' : '没有匹配当前搜索条件的已发布媒体。'}
                </div>
              )}
            </div>
          </div>
        </aside>

        <section className="space-y-6">
          {detail?.is_reopened_from_published ? (
            <div className="rounded-[1.4rem] border border-fudan-orange/20 bg-fudan-orange/5 px-5 py-4 text-sm leading-7 text-fudan-orange">
              {isEnglish
                ? 'This draft was sent back from a live media item. The online version will not change until you publish again.'
                : '这份草稿来自线上媒体打回草稿箱的版本，重新发布之前不会影响当前线上内容。'}
            </div>
          ) : null}

          <div className="fudan-panel p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="section-kicker">{isEnglish ? 'Editing' : '编辑区'}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">
                  {selectedId
                    ? isEnglish
                      ? `Editing draft #${selectedId}`
                      : `编辑草稿 #${selectedId}`
                    : isEnglish
                      ? 'Create a new draft'
                      : '新建媒体草稿'}
                </h2>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  {isEnglish ? 'Duration' : '时长'}: {formatDuration(form.duration_seconds, isEnglish)}
                </span>
                {detail ? (
                  <span className={['rounded-full border px-3 py-2 text-xs font-semibold', getDraftStatusClass(detail)].join(' ')}>
                    {getDraftStatusLabel(detail, isEnglish)}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <select
                name="kind"
                value={form.kind}
                onChange={handleFieldChange}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              >
                <option value="audio">{isEnglish ? 'Audio' : '音频'}</option>
                <option value="video">{isEnglish ? 'Video' : '视频'}</option>
              </select>
              <select
                name="visibility"
                value={form.visibility}
                onChange={handleFieldChange}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              >
                <option value="public">{isEnglish ? 'Public' : '公开'}</option>
                <option value="member">{isEnglish ? 'Member' : '会员'}</option>
                <option value="paid">{isEnglish ? 'Paid' : '付费'}</option>
              </select>
              <input
                name="title"
                value={form.title}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Program title' : '节目标题'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2"
              />
              <input
                name="speaker"
                value={form.speaker}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Speaker / host' : '主讲人 / 主播'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="series_name"
                value={form.series_name}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Series name' : '系列名称'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="publish_date"
                type="date"
                value={form.publish_date}
                onChange={handleFieldChange}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="episode_number"
                type="number"
                min="1"
                value={form.episode_number}
                onChange={handleFieldChange}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="duration_seconds"
                type="number"
                min="0"
                value={form.duration_seconds}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Duration seconds' : '时长秒数'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                name="cover_image_url"
                value={form.cover_image_url}
                readOnly
                placeholder={isEnglish ? 'Cover image is managed by upload' : '首页图通过上传维护'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-100 px-4 py-3 text-sm text-slate-400 outline-none"
              />
              <input
                name="source_url"
                value={form.source_url}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Source URL' : '来源 URL'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2"
              />
            </div>
          </div>

          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Uploads' : '上传区'}</div>
            <p className="mt-2 text-sm leading-7 text-slate-500">
              {isEnglish
                ? 'Upload the primary media first, then upload one text material entry. Audio uses transcript and video uses script. The studio only keeps AI-generated summary, program description, and chapters visible.'
                : '先上传主媒体文件，再上传一份文本素材。音频使用转录，视频使用脚本。后台只显示 AI 生成的摘要、节目简介和章节结果。'}
            </p>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <button
                type="button"
                onClick={() => mediaInputRef.current?.click()}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-[1.2rem] border border-fudan-blue/20 bg-fudan-blue/5 px-4 py-4 text-sm font-semibold text-fudan-blue transition hover:bg-fudan-blue/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'media' ? <LoaderCircle size={16} className="animate-spin" /> : <UploadCloud size={16} />}
                {isEnglish ? 'Upload media' : '上传主媒体'}
              </button>
              <button
                type="button"
                onClick={() => coverInputRef.current?.click()}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-[1.2rem] border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'cover' ? <LoaderCircle size={16} className="animate-spin" /> : <UploadCloud size={16} />}
                {isEnglish ? 'Upload cover image' : '上传首页图'}
              </button>
              <button
                type="button"
                onClick={() => textUploadInputRef.current?.click()}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-[1.2rem] border border-fudan-orange/20 bg-fudan-orange/5 px-4 py-4 text-sm font-semibold text-fudan-orange transition hover:bg-fudan-orange/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === textUploadUsage ? <LoaderCircle size={16} className="animate-spin" /> : <FileText size={16} />}
                {textUploadLabel}
              </button>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <input
                name="media_url"
                value={form.media_url}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Primary media URL' : '主媒体 URL'}
                className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <div className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500">
                {isEnglish ? 'No application-layer upload size cap is applied.' : '上传链路不再设置应用层文件大小上限。'}
              </div>
            </div>

            {coverUrl ? (
              <div className="mt-6 rounded-[1.3rem] border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                  {isEnglish ? 'Cover preview' : '首页图预览'}
                </div>
                <img
                  src={coverUrl}
                  alt={isEnglish ? 'Media cover preview' : '媒体首页图预览'}
                  className="max-h-[280px] w-full rounded-[1rem] object-cover"
                />
              </div>
            ) : null}

            {mediaUrl ? (
              <div className="mt-6 rounded-[1.3rem] border border-slate-200 bg-slate-50 p-4">
                <div className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">
                  {isEnglish ? 'Media preview' : '媒体预览'}
                </div>
                {form.kind === 'video' ? (
                  <video src={mediaUrl} controls className="max-h-[360px] w-full rounded-[1rem] bg-black" />
                ) : (
                  <audio src={mediaUrl} controls className="w-full" />
                )}
              </div>
            ) : null}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Summary' : '摘要'}</div>
              <textarea
                name="summary"
                rows={8}
                value={form.summary}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Program summary' : '节目摘要'}
                className="mt-4 w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none"
              />
            </div>
            <div className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Program description' : '节目简介'}</div>
              <textarea
                name="body_markdown"
                rows={8}
                value={form.body_markdown}
                onChange={handleFieldChange}
                placeholder={isEnglish ? 'Program intro in Markdown' : '节目简介 Markdown'}
                className="mt-4 w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none"
              />
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
            <div className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Generated chapters' : '识别章节'}</div>
              {Array.isArray(form.chapters) && form.chapters.length ? (
                <div className="mt-4 grid gap-3">
                  {form.chapters.map((chapter, index) => (
                    <div key={`${chapter.timestamp_label}-${index}`} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                      <span className="font-semibold text-fudan-blue">{chapter.timestamp_label}</span>
                      {' / '}
                      {chapter.title}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {isEnglish
                    ? 'No chapters detected yet. Upload the transcript or script material first if you want timestamp suggestions.'
                    : '暂未识别章节。如需时间戳建议，请先上传对应的转录或脚本文本。'}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={handleSave}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'save' ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}
                {isEnglish ? 'Save' : '保存'}
              </button>
              <button
                type="button"
                onClick={handleGenerateCopy}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-fudan-orange/20 bg-fudan-orange/5 px-5 py-3 text-sm font-semibold text-fudan-orange transition hover:bg-fudan-orange/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'generate' ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}
                {isEnglish ? 'Generate copy' : '生成文案'}
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-fudan-orange px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#d95f00] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'publish' ? <LoaderCircle size={16} className="animate-spin" /> : <Rocket size={16} />}
                {isEnglish ? 'Publish' : '发布'}
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={Boolean(busy) || !canDeleteDraft(detail)}
                className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-red-200 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'delete' ? <LoaderCircle size={16} className="animate-spin" /> : <Trash2 size={16} />}
                {isEnglish ? 'Delete draft' : '删除草稿'}
              </button>
            </div>
          </div>

          {detail?.published_summary || detail?.published_body_markdown ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="fudan-panel p-6">
                <div className="section-kicker">{isEnglish ? 'Published summary' : '线上摘要'}</div>
                <div className="mt-4 rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-4 text-sm leading-7 text-slate-600">
                  {detail.published_summary || (isEnglish ? 'No published summary yet.' : '线上摘要暂为空。')}
                </div>
              </div>
              <div className="fudan-panel p-6">
                <div className="section-kicker">{isEnglish ? 'Published program description' : '线上节目简介'}</div>
                <div className="mt-4 whitespace-pre-wrap rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-4 text-sm leading-7 text-slate-600">
                  {detail.published_body_markdown || (isEnglish ? 'No published program description yet.' : '线上节目简介暂为空。')}
                </div>
              </div>
            </div>
          ) : null}
        </section>
      </section>

      <input
        ref={mediaInputRef}
        type="file"
        accept={getUploadAccept(form.kind, 'media')}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          handleUpload('media', file)
        }}
      />
      <input
        ref={coverInputRef}
        type="file"
        accept={getUploadAccept(form.kind, 'cover')}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          handleUpload('cover', file)
        }}
      />
      <input
        ref={textUploadInputRef}
        type="file"
        accept={getUploadAccept(form.kind, textUploadUsage)}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          event.target.value = ''
          handleUpload(textUploadUsage, file)
        }}
      />
    </div>
  )
}

export default MediaStudioPage
