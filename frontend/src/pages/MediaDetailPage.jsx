import {
  ArrowLeft,
  CalendarDays,
  Clock3,
  ExternalLink,
  FilePenLine,
  Headphones,
  LoaderCircle,
  LockKeyhole,
  PlayCircle,
  Video,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { editPublishedMediaItem, fetchMediaItemDetail, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import MediaMarkdownBlock from '../components/media/MediaMarkdownBlock.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { formatDate } from '../utils/formatters.js'

function formatDuration(seconds, isEnglish) {
  const safe = Number(seconds || 0)
  if (!safe) return isEnglish ? 'Duration pending' : '时长待补全'
  const minutes = Math.floor(safe / 60)
  const remain = safe % 60
  return isEnglish ? `${minutes}m ${remain}s` : `${minutes} 分 ${remain} 秒`
}

function buildPlayableUrl(item) {
  const url = item?.accessible ? item?.media_url || item?.preview_url : item?.preview_url || item?.media_url
  return resolveApiUrl(url)
}

function buildPreviewLabel(previewSeconds, isEnglish) {
  const safe = Number(previewSeconds || 0)
  if (!safe) return isEnglish ? 'Preview' : '预览'
  const minutes = safe >= 60 ? Math.floor(safe / 60) : 0
  if (minutes >= 1) {
    return isEnglish ? `${minutes} min preview` : `${minutes} 分钟预览`
  }
  return isEnglish ? `${safe}s preview` : `${safe} 秒预览`
}

function MediaDetailPage({ kind = 'audio' }) {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  const playerRef = useRef(null)
  const { isEnglish } = useLanguage()
  const { accessToken, isAdmin } = useAuth()
  const [item, setItem] = useState(null)
  const [error, setError] = useState('')
  const [editError, setEditError] = useState('')
  const [editingMediaId, setEditingMediaId] = useState(null)
  const [selectedChapterSeconds, setSelectedChapterSeconds] = useState(null)
  const [previewEnded, setPreviewEnded] = useState(false)

  useEffect(() => {
    let mounted = true
    setError('')
    setEditError('')
    setItem(null)
    setSelectedChapterSeconds(null)
    setPreviewEnded(false)

    fetchMediaItemDetail(kind, slug, accessToken)
      .then((response) => {
        if (!mounted) return
        setItem(response)
        const firstChapter = Array.isArray(response?.chapters) ? response.chapters[0] : null
        setSelectedChapterSeconds(Number.isFinite(firstChapter?.timestamp_seconds) ? firstChapter.timestamp_seconds : null)
      })
      .catch((nextError) => {
        if (!mounted) return
        setError(nextError?.message || (isEnglish ? 'Failed to load this media item.' : '媒体详情加载失败。'))
      })

    return () => {
      mounted = false
    }
  }, [accessToken, isEnglish, kind, slug])

  useEffect(() => {
    setPreviewEnded(false)
    const node = playerRef.current
    if (!node) return
    try {
      node.pause?.()
      node.currentTime = 0
    } catch {}
  }, [item?.slug])

  const playableUrl = buildPlayableUrl(item)
  const previewLimit = item?.accessible ? 0 : Number(item?.preview_duration_seconds || 0)
  const coverUrl = resolveApiUrl(item?.cover_image_url)
  const chapters = Array.isArray(item?.chapters) ? item.chapters : []
  const isAudio = kind === 'audio'
  const backToHubPath = isAudio ? '/audio' : '/video'

  const applySeek = (seconds) => {
    const safeSeconds = Math.max(0, Number(seconds || 0))
    setSelectedChapterSeconds(safeSeconds)
    const node = playerRef.current
    if (!node) return
    try {
      node.currentTime = safeSeconds
    } catch {}
  }

  const handleLoadedMetadata = () => {
    if (!Number.isFinite(selectedChapterSeconds)) return
    const node = playerRef.current
    if (!node) return
    try {
      node.currentTime = Math.max(0, Number(selectedChapterSeconds || 0))
    } catch {}
  }

  const handleTimeUpdate = (event) => {
    const node = event.currentTarget
    const currentSeconds = Number(node.currentTime || 0)
    if (previewLimit && currentSeconds >= previewLimit) {
      node.currentTime = previewLimit
      node.pause()
      setPreviewEnded(true)
    }

    if (!chapters.length) return
    let activeSeconds = chapters[0]?.timestamp_seconds || 0
    for (const chapter of chapters) {
      if (Number(chapter?.timestamp_seconds || 0) <= currentSeconds) {
        activeSeconds = Number(chapter.timestamp_seconds || 0)
      }
    }
    setSelectedChapterSeconds(activeSeconds)
  }

  const handlePlay = (event) => {
    if (!previewLimit) return
    const node = event.currentTarget
    if (previewEnded && node.currentTime >= previewLimit - 0.25) {
      node.currentTime = 0
      setPreviewEnded(false)
    }
  }

  const handleEditAgain = async () => {
    const mediaItemId = item?.media_item_id || item?.id
    if (!mediaItemId || editingMediaId) return
    setEditError('')
    setEditingMediaId(mediaItemId)
    try {
      const draft = await editPublishedMediaItem(mediaItemId, accessToken)
      navigate(`/media-studio?draft_id=${draft.id}&reopened=1`)
    } catch (nextError) {
      setEditError(nextError?.message || (isEnglish ? 'Failed to open this media item for editing.' : '打开该媒体的重编草稿失败。'))
    } finally {
      setEditingMediaId(null)
    }
  }

  if (!item && !error) {
    return <div className="page-shell py-16 text-sm text-slate-500">{isEnglish ? 'Loading media item...' : '正在加载媒体详情...'}</div>
  }

  if (!item) {
    return (
      <div className="page-shell py-16">
        <div className="rounded-[1.6rem] border border-dashed border-slate-300 bg-white p-8 text-sm leading-7 text-slate-500">
          {error || (isEnglish ? 'This media item is temporarily unavailable.' : '当前媒体内容暂时不可用。')}
        </div>
      </div>
    )
  }

  const playbackBadgeClass = item.accessible
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-amber-200 bg-amber-50 text-amber-700'
  const playbackLabel = item.accessible
    ? isEnglish
      ? 'Full playback'
      : '完整可播'
    : buildPreviewLabel(previewLimit, isEnglish)

  return (
    <div
      className="page-shell py-8 md:py-10"
      data-media-detail-page={kind}
      data-selected-chapter={Number.isFinite(selectedChapterSeconds) ? String(selectedChapterSeconds) : ''}
    >
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <article className="min-w-0 space-y-8">
          <section className="space-y-5">
            <Link
              to={backToHubPath}
              className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 transition hover:text-fudan-blue"
            >
              <ArrowLeft size={16} />
              {isEnglish ? (isAudio ? 'Back to audio' : 'Back to video') : isAudio ? '返回音频流' : '返回视频流'}
            </Link>

            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${playbackBadgeClass}`}>
                {playbackLabel}
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                {item.visibility_label}
              </span>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                {item.series_name || (isAudio ? 'Audio' : 'Video')}
              </span>
            </div>

            <h1 className="font-serif text-4xl font-black leading-tight text-fudan-blue md:text-6xl" data-media-detail-title="">
              {item.title}
            </h1>

            <div className="flex flex-wrap gap-3 text-sm text-slate-500">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2">
                <CalendarDays size={14} />
                {formatDate(item.publish_date)}
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2">
                <Clock3 size={14} />
                {formatDuration(item.duration_seconds, isEnglish)}
              </div>
            </div>
          </section>

          <section className="fudan-panel overflow-hidden" data-media-player-shell="">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="section-kicker">{isEnglish ? 'Playback' : '播放区'}</div>
            </div>
            <div className="px-6 py-6">
              {isAudio ? (
                playableUrl ? (
                  <div className="rounded-[1.4rem] border border-slate-200 bg-slate-50 p-5">
                    <audio
                      ref={playerRef}
                      controls
                      preload="metadata"
                      src={playableUrl}
                      className="w-full"
                      data-media-player={kind}
                      controlsList={item.accessible ? undefined : 'nodownload noplaybackrate'}
                      onLoadedMetadata={handleLoadedMetadata}
                      onPlay={handlePlay}
                      onTimeUpdate={handleTimeUpdate}
                      onContextMenu={item.accessible ? undefined : (event) => event.preventDefault()}
                    >
                      {isEnglish ? 'Your browser does not support the audio player.' : '当前浏览器不支持音频播放。'}
                    </audio>
                  </div>
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
                    {isEnglish ? 'Playback will appear after the media file is attached.' : '媒体文件上传后会在这里出现播放器。'}
                  </div>
                )
              ) : playableUrl ? (
                <video
                  ref={playerRef}
                  controls
                  preload="metadata"
                  src={playableUrl}
                  className="aspect-video w-full rounded-[1.4rem] bg-slate-950"
                  data-media-player={kind}
                  controlsList={item.accessible ? undefined : 'nodownload noplaybackrate'}
                  onLoadedMetadata={handleLoadedMetadata}
                  onPlay={handlePlay}
                  onTimeUpdate={handleTimeUpdate}
                  onContextMenu={item.accessible ? undefined : (event) => event.preventDefault()}
                />
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-[1.4rem] bg-[linear-gradient(135deg,rgba(2,132,199,0.14),rgba(15,23,42,0.08)_65%,rgba(234,107,0,0.12))]">
                  <div className="rounded-full border border-slate-200 bg-white/85 p-5 text-slate-500 shadow-sm">
                    <Video size={22} />
                  </div>
                </div>
              )}

              {!item.accessible && item.gate_copy ? (
                <div className="mt-5 rounded-[1.2rem] border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-800">
                  {item.gate_copy}
                </div>
              ) : null}

              {previewEnded ? (
                <div className="mt-4 rounded-[1.2rem] border border-fudan-orange/20 bg-fudan-orange/10 p-4 text-sm leading-7 text-fudan-orange">
                  {isEnglish
                    ? 'The preview ended here. Upgrade to continue with the full item.'
                    : '预览已在这里结束，升级后可继续收听或观看完整内容。'}
                </div>
              ) : null}
            </div>
          </section>

          {item.body_markdown ? (
            <section className="fudan-panel overflow-hidden" data-media-detail-body="">
              <div className="px-6 py-6">
                <MediaMarkdownBlock content={item.body_markdown} variant="panel" dataScope="detail-body" />
              </div>
            </section>
          ) : null}

          <section className="fudan-panel overflow-hidden" data-media-detail-chapters="">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="section-kicker">{isEnglish ? 'Chapters' : '章节目录'}</div>
            </div>
            <div className="grid gap-3 px-6 py-6">
              {chapters.length ? (
                chapters.map((chapter) => {
                  const isActive = Number(selectedChapterSeconds) === Number(chapter.timestamp_seconds || 0)
                  return (
                    <button
                      key={chapter.timestamp_label}
                      type="button"
                      aria-pressed={isActive}
                      data-media-chapter-button={chapter.timestamp_label}
                      onClick={() => applySeek(chapter.timestamp_seconds)}
                      className={[
                        'rounded-[1.2rem] border px-4 py-4 text-left transition',
                        isActive
                          ? 'border-fudan-blue bg-fudan-blue/5 shadow-[0_14px_36px_rgba(13,7,131,0.08)]'
                          : 'border-slate-200 bg-slate-50 hover:border-fudan-blue/30',
                      ].join(' ')}
                    >
                      <div className="text-sm font-semibold text-fudan-blue">{chapter.timestamp_label}</div>
                      <div className="mt-2 text-sm leading-7 text-slate-600">{chapter.title}</div>
                    </button>
                  )
                })
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 bg-slate-50 p-5 text-sm leading-7 text-slate-500">
                  {isEnglish ? 'No chapter outline is available yet.' : '当前还没有章节目录。'}
                </div>
              )}
            </div>
          </section>
        </article>

        <aside className="space-y-6 xl:sticky xl:top-24 xl:self-start">
          <section className="fudan-panel overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="section-kicker">{isEnglish ? 'Info' : '节目资料'}</div>
            </div>
            <div className="space-y-4 px-6 py-6 text-sm leading-7 text-slate-600">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                  {isEnglish ? 'Type' : '类型'}
                </div>
                <div className="mt-1 flex items-center gap-2 text-fudan-blue">
                  {isAudio ? <Headphones size={16} /> : <Video size={16} />}
                  {isEnglish ? (isAudio ? 'Audio' : 'Video') : isAudio ? '音频' : '视频'}
                </div>
              </div>
              {item.speaker ? (
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {isEnglish ? 'Speaker' : '主讲人'}
                  </div>
                  <div className="mt-1">{item.speaker}</div>
                </div>
              ) : null}
              {item.series_name ? (
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {isEnglish ? 'Series' : '系列'}
                  </div>
                  <div className="mt-1">{item.series_name}</div>
                </div>
              ) : null}
              {coverUrl ? (
                <img src={coverUrl} alt={item.title} className="w-full rounded-[1.25rem] object-cover" />
              ) : null}
            </div>
          </section>

          <section className="fudan-panel overflow-hidden">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="section-kicker">{isEnglish ? 'Actions' : '操作入口'}</div>
            </div>
            <div className="flex flex-wrap gap-3 px-6 py-6">
              {isAdmin ? (
                <button
                  type="button"
                  onClick={handleEditAgain}
                  disabled={editingMediaId === (item.media_item_id || item.id)}
                  className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/15 bg-white px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/35 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {editingMediaId === (item.media_item_id || item.id) ? <LoaderCircle size={16} className="animate-spin" /> : <FilePenLine size={16} />}
                  {isEnglish ? 'Edit again' : '重新编辑'}
                </button>
              ) : null}
              {!item.accessible ? (
                <Link
                  to="/membership"
                  className="inline-flex items-center gap-2 rounded-full bg-fudan-orange px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#d45f00]"
                >
                  <LockKeyhole size={16} />
                  {isEnglish ? 'Upgrade access' : '升级查看完整内容'}
                </Link>
              ) : null}
              {item.accessible && playableUrl ? (
                <a
                  href={playableUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
                >
                  <PlayCircle size={16} />
                  {isEnglish ? 'Open media file' : '打开媒体文件'}
                </a>
              ) : null}
              {item.source_url ? (
                <a
                  href={resolveApiUrl(item.source_url)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
                >
                  <ExternalLink size={16} />
                  {isEnglish ? 'Source' : '原始链接'}
                </a>
              ) : null}
            </div>
            {editError ? <div className="px-6 pb-6 text-sm text-red-500">{editError}</div> : null}
          </section>
        </aside>
      </div>
    </div>
  )
}

export default MediaDetailPage
