import {
  FileUp,
  Film,
  Headphones,
  LoaderCircle,
  Plus,
  Save,
  UploadCloud,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createMediaAdminItem,
  fetchMediaAdminItem,
  fetchMediaAdminItems,
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
  status: 'draft',
  cover_image_url: '',
  media_url: '',
  preview_url: '',
  source_url: '',
  body_markdown: '',
  transcript_markdown: '',
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
    status: item?.status || 'draft',
    cover_image_url: item?.cover_image_url || '',
    media_url: item?.media_url || '',
    preview_url: item?.preview_url || '',
    source_url: item?.source_url || '',
    body_markdown: item?.body_markdown || '',
    transcript_markdown: item?.transcript_markdown || '',
    chapters: item?.chapters || [],
  }
}

function getUploadAccept(kind) {
  return kind === 'video'
    ? '.mp4,.mov,.m4v,.webm,video/*'
    : '.mp3,.wav,.m4a,.aac,.ogg,audio/*'
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
  const previewInputRef = useRef(null)
  const [items, setItems] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [form, setForm] = useState(DEFAULT_FORM)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [filterKind, setFilterKind] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  const loadItems = useCallback(
    async (preferredId = null) => {
      const payload = await fetchMediaAdminItems(filterKind, filterStatus, 80)
      setItems(payload.items || [])
      const nextId = preferredId || payload.items?.[0]?.id || null
      if (!nextId) {
        setSelectedId(null)
        setForm(DEFAULT_FORM)
        return
      }
      const detail = await fetchMediaAdminItem(nextId)
      setSelectedId(detail.id)
      setForm(toForm(detail))
    },
    [filterKind, filterStatus],
  )

  useEffect(() => {
    loadItems().catch(() => setError(isEnglish ? 'Failed to load media studio.' : '媒体后台加载失败。'))
  }, [isEnglish, loadItems])

  const counts = useMemo(() => {
    const audioCount = items.filter((item) => item.kind === 'audio').length
    const videoCount = items.filter((item) => item.kind === 'video').length
    const publishedCount = items.filter((item) => item.status === 'published').length
    return { audioCount, videoCount, publishedCount }
  }, [items])

  const selectedItem = items.find((item) => item.id === selectedId) || null
  const previewUrl = resolveApiUrl(form.preview_url || form.media_url)
  const mediaUrl = resolveApiUrl(form.media_url)

  const resetMessages = () => {
    setError('')
    setMessage('')
  }

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
    setForm({
      ...DEFAULT_FORM,
      kind: filterKind || 'audio',
    })
  }

  const handleSelect = async (id) => {
    resetMessages()
    setBusy('select')
    try {
      const detail = await fetchMediaAdminItem(id)
      setSelectedId(detail.id)
      setForm(toForm(detail))
    } catch {
      setError(isEnglish ? 'Failed to load the selected media item.' : '媒体条目读取失败。')
    } finally {
      setBusy('')
    }
  }

  const handleSave = async () => {
    resetMessages()
    setBusy('save')
    try {
      const payload = {
        ...form,
        episode_number: Number(form.episode_number || 1),
        duration_seconds: Number(form.duration_seconds || 0),
      }
      const saved = selectedId ? await updateMediaAdminItem(selectedId, payload) : await createMediaAdminItem(payload)
      await loadItems(saved.id)
      setMessage(isEnglish ? 'Media entry saved.' : '媒体条目已保存。')
    } catch {
      setError(isEnglish ? 'Failed to save the media entry.' : '媒体条目保存失败。')
    } finally {
      setBusy('')
    }
  }

  const handleUpload = async (usage, file) => {
    if (!file) return
    resetMessages()
    setBusy(usage)
    try {
      const uploaded = await uploadMediaAdminFile(file, form.kind, usage)
      const duration = usage === 'media' ? await readMediaDuration(file, form.kind) : 0
      setForm((current) => ({
        ...current,
        media_url: usage === 'media' ? uploaded.url : current.media_url,
        preview_url: usage === 'preview' ? uploaded.url : current.preview_url,
        source_url: usage === 'media' && !current.source_url ? uploaded.url : current.source_url,
        duration_seconds: usage === 'media' && duration ? duration : current.duration_seconds,
      }))
      setMessage(
        usage === 'media'
          ? isEnglish
            ? 'Primary media file uploaded.'
            : '主媒体文件已上传。'
          : isEnglish
            ? 'Preview file uploaded.'
            : '试看文件已上传。',
      )
    } catch {
      setError(
        usage === 'media'
          ? isEnglish
            ? 'Failed to upload the primary media file.'
            : '主媒体文件上传失败。'
          : isEnglish
            ? 'Failed to upload the preview file.'
            : '试看文件上传失败。',
      )
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Admin Media Studio' : '管理员媒体后台'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
              {isEnglish ? 'Upload and publish audio or video from one desk' : '在一个后台完成音频与视频上传发布'}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'Audio and video upload capability is restored here. Admins can upload primary files, preview files, metadata, and publishing permissions without exposing those tools to other roles.'
                : '音频和视频上传能力已经恢复到这里。只有管理员可以上传主文件、试看文件、维护元数据和设置公开/会员/付费权限，其他身份没有这些能力。'}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleCreate}
                className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
              >
                <Plus size={16} />
                {isEnglish ? 'New media item' : '新建媒体条目'}
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={Boolean(busy)}
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'save' ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}
                {isEnglish ? 'Save entry' : '保存条目'}
              </button>
            </div>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Audio items' : '音频条目'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.audioCount}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Video items' : '视频条目'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.videoCount}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Published' : '已发布'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{counts.publishedCount}</div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {message ? <div className="mt-6 text-sm text-emerald-700">{message}</div> : null}

      <section className="mt-8 grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
        <aside className="space-y-6">
          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Filter' : '筛选'}</div>
            <div className="mt-4 grid gap-3">
              <select value={filterKind} onChange={(event) => setFilterKind(event.target.value)} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">
                <option value="">{isEnglish ? 'All kinds' : '全部类型'}</option>
                <option value="audio">{isEnglish ? 'Audio' : '音频'}</option>
                <option value="video">{isEnglish ? 'Video' : '视频'}</option>
              </select>
              <select value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">
                <option value="">{isEnglish ? 'All statuses' : '全部状态'}</option>
                <option value="draft">{isEnglish ? 'Draft' : '草稿'}</option>
                <option value="published">{isEnglish ? 'Published' : '已发布'}</option>
              </select>
              <button
                type="button"
                onClick={() => loadItems(selectedId).catch(() => setError(isEnglish ? 'Failed to refresh the media list.' : '媒体列表刷新失败。'))}
                className="rounded-full bg-fudan-blue px-4 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
              >
                {isEnglish ? 'Refresh list' : '刷新列表'}
              </button>
            </div>
          </div>

          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Items' : '媒体条目'}</div>
            <div className="mt-4 space-y-3">
              {items.length ? (
                items.map((item) => (
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
                      <div>
                        <div className="font-serif text-lg font-bold text-fudan-blue">{item.title}</div>
                        <div className="mt-2 text-sm leading-6 text-slate-500">
                          {item.kind === 'audio'
                            ? byLanguage(isEnglish, '音频', 'Audio')
                            : byLanguage(isEnglish, '视频', 'Video')}
                          {' / '}
                          {item.visibility_label}
                        </div>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                        {item.status}
                      </span>
                    </div>
                  </button>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
                  {isEnglish ? 'No media items found for the current filter.' : '当前筛选下还没有媒体条目。'}
                </div>
              )}
            </div>
          </div>
        </aside>

        <section className="space-y-6">
          <div className="fudan-panel p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="section-kicker">{isEnglish ? 'Editing' : '编辑区'}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">
                  {selectedId
                    ? isEnglish
                      ? `Editing #${selectedId}`
                      : `编辑条目 #${selectedId}`
                    : isEnglish
                      ? 'Create a new media item'
                      : '新建媒体条目'}
                </h2>
              </div>
              <div className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {isEnglish ? 'Duration' : '时长'}: {formatDuration(form.duration_seconds, isEnglish)}
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <select name="kind" value={form.kind} onChange={handleFieldChange} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">
                <option value="audio">{isEnglish ? 'Audio' : '音频'}</option>
                <option value="video">{isEnglish ? 'Video' : '视频'}</option>
              </select>
              <select name="visibility" value={form.visibility} onChange={handleFieldChange} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">
                <option value="public">{isEnglish ? 'Public' : '公开'}</option>
                <option value="member">{isEnglish ? 'Member' : '会员'}</option>
                <option value="paid">{isEnglish ? 'Paid' : '付费'}</option>
              </select>
              <input name="title" value={form.title} onChange={handleFieldChange} placeholder={isEnglish ? 'Title' : '标题'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2" />
              <textarea name="summary" rows={4} value={form.summary} onChange={handleFieldChange} placeholder={isEnglish ? 'Summary' : '摘要'} className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none md:col-span-2" />
              <input name="speaker" value={form.speaker} onChange={handleFieldChange} placeholder={isEnglish ? 'Speaker or host' : '主讲人 / 主播'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="series_name" value={form.series_name} onChange={handleFieldChange} placeholder={isEnglish ? 'Series name' : '栏目名'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="publish_date" type="date" value={form.publish_date} onChange={handleFieldChange} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="episode_number" type="number" min="1" value={form.episode_number} onChange={handleFieldChange} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="duration_seconds" type="number" min="0" value={form.duration_seconds} onChange={handleFieldChange} placeholder={isEnglish ? 'Duration seconds' : '时长秒数'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <select name="status" value={form.status} onChange={handleFieldChange} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">
                <option value="draft">{isEnglish ? 'Draft' : '草稿'}</option>
                <option value="published">{isEnglish ? 'Published' : '已发布'}</option>
              </select>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <button
                type="button"
                onClick={() => mediaInputRef.current?.click()}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-[1.2rem] border border-fudan-blue/20 bg-fudan-blue/5 px-4 py-4 text-sm font-semibold text-fudan-blue transition hover:bg-fudan-blue/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'media' ? <LoaderCircle size={16} className="animate-spin" /> : <UploadCloud size={16} />}
                {isEnglish ? 'Upload primary media file' : '上传主媒体文件'}
              </button>
              <button
                type="button"
                onClick={() => previewInputRef.current?.click()}
                disabled={Boolean(busy)}
                className="inline-flex items-center justify-center gap-2 rounded-[1.2rem] border border-fudan-orange/20 bg-fudan-orange/5 px-4 py-4 text-sm font-semibold text-fudan-orange transition hover:bg-fudan-orange/10 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy === 'preview' ? <LoaderCircle size={16} className="animate-spin" /> : <FileUp size={16} />}
                {isEnglish ? 'Upload preview file' : '上传试看文件'}
              </button>
            </div>

            <input
              ref={mediaInputRef}
              type="file"
              accept={getUploadAccept(form.kind)}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                handleUpload('media', file)
                event.target.value = ''
              }}
            />
            <input
              ref={previewInputRef}
              type="file"
              accept={getUploadAccept(form.kind)}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                handleUpload('preview', file)
                event.target.value = ''
              }}
            />

            <div className="mt-6 grid gap-4">
              <input name="media_url" value={form.media_url} onChange={handleFieldChange} placeholder={isEnglish ? 'Primary media URL' : '主媒体 URL'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="preview_url" value={form.preview_url} onChange={handleFieldChange} placeholder={isEnglish ? 'Preview URL' : '试看 URL'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="source_url" value={form.source_url} onChange={handleFieldChange} placeholder={isEnglish ? 'Source or external URL' : '来源 / 外链 URL'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <textarea name="body_markdown" rows={10} value={form.body_markdown} onChange={handleFieldChange} placeholder={isEnglish ? 'Program description Markdown' : '节目介绍 Markdown'} className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none" />
              <textarea name="transcript_markdown" rows={10} value={form.transcript_markdown} onChange={handleFieldChange} placeholder={isEnglish ? 'Transcript Markdown' : '逐字稿 Markdown'} className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none" />
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="fudan-panel overflow-hidden p-6">
              <div className="section-kicker">{isEnglish ? 'Preview' : '预览'}</div>
              <h3 className="font-serif text-2xl font-black text-fudan-blue">
                {form.kind === 'audio'
                  ? isEnglish
                    ? 'Audio playback'
                    : '音频播放'
                  : isEnglish
                    ? 'Video playback'
                    : '视频播放'}
              </h3>
              <div className="mt-5 rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-4">
                {form.kind === 'audio' ? (
                  <audio controls className="w-full" src={previewUrl || mediaUrl || undefined} />
                ) : (
                  <video controls className="aspect-video w-full rounded-[1rem] bg-slate-950" src={previewUrl || mediaUrl || undefined} />
                )}
              </div>
            </div>

            <div className="fudan-panel p-6">
              <div className="section-kicker">{isEnglish ? 'Current summary' : '当前概览'}</div>
              <div className="mt-4 space-y-3">
                <div className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                  <div>{isEnglish ? 'Selected item' : '当前条目'}: {selectedItem?.title || byLanguage(isEnglish, 'New draft', '新建草稿')}</div>
                  <div>{isEnglish ? 'Kind' : '类型'}: {form.kind}</div>
                  <div>{isEnglish ? 'Visibility' : '权限'}: {form.visibility}</div>
                  <div>{isEnglish ? 'Status' : '状态'}: {form.status}</div>
                  <div>{isEnglish ? 'Duration' : '时长'}: {formatDuration(form.duration_seconds, isEnglish)}</div>
                </div>
                <div className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
                  {isEnglish
                    ? 'Only admins can enter this page and call upload endpoints. Regular users can only consume the published media pages according to their tier.'
                    : '只有管理员能进入这个页面并调用上传接口。普通用户只能按自己的权限层级消费已经发布的媒体内容。'}
                </div>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={Boolean(busy)}
                  className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {busy === 'save' ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}
                  {isEnglish ? 'Save media entry' : '保存媒体条目'}
                </button>
              </div>
            </div>
          </div>
        </section>
      </section>
    </div>
  )
}

export default MediaStudioPage
