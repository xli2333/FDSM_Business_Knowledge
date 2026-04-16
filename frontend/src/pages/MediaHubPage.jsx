import {
  ArrowRight,
  CalendarDays,
  Clock3,
  FilePenLine,
  Headphones,
  LoaderCircle,
  LockKeyhole,
  Video,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { editPublishedMediaItem, fetchMediaHub, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import MediaMarkdownBlock from '../components/media/MediaMarkdownBlock.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { encodeRoutePart } from '../utils/formatters.js'

const HUB_COPY = {
  audio: {
    zh: {
      kicker: '付费音频流',
      title: '音频流改成发现页，完整内容进入正式详情页',
      body: '音频流现在只负责浏览与进入详情。每条内容进入单独正式页后，再查看摘要、节目简介、章节目录与播放器。',
      empty: '当前还没有可展示的音频内容。',
      detail: '查看音频详情',
      switchLabel: '去视频页',
      membershipEntry: '查看会员权限',
    },
    en: {
      kicker: 'Premium Audio Stream',
      title: 'Audio now works as a discovery page with dedicated detail pages',
      body: 'The audio stream now focuses on discovery and entry. Open any item to view its summary, program description, chapters, and player on the dedicated detail page.',
      empty: 'No audio items are available yet.',
      detail: 'View audio details',
      switchLabel: 'Open video',
      membershipEntry: 'View membership access',
    },
  },
  video: {
    zh: {
      kicker: '视频流',
      title: '视频流回到列表职责，完整信息进入正式详情页',
      body: '视频流现在只负责内容发现和详情入口。每条视频都会进入单独正式页，再承载简介、目录和播放能力。',
      empty: '当前还没有可展示的视频内容。',
      detail: '查看视频详情',
      switchLabel: '去音频页',
      membershipEntry: '查看会员权限',
    },
    en: {
      kicker: 'Video Stream',
      title: 'Video now returns to list browsing, with a dedicated detail page',
      body: 'The video stream now focuses on discovery and entry. Each video opens into a dedicated page that carries the description, chapter outline, and playback experience.',
      empty: 'No video items are available yet.',
      detail: 'View video details',
      switchLabel: 'Open audio',
      membershipEntry: 'View membership access',
    },
  },
}

function formatDuration(seconds, isEnglish) {
  const safe = Number(seconds || 0)
  if (!safe) return isEnglish ? 'Duration pending' : '时长待补全'
  const minutes = Math.floor(safe / 60)
  const remain = safe % 60
  return isEnglish ? `${minutes}m ${remain}s` : `${minutes} 分 ${remain} 秒`
}

function buildDetailPath(kind, slug) {
  return `/${kind}/${encodeRoutePart(slug)}`
}

function MediaCard({ item, kind, isEnglish, detailLabel, canEdit, editBusy, onEditAgain }) {
  const detailPath = buildDetailPath(kind, item.slug)
  const coverUrl = resolveApiUrl(item.cover_image_url)
  const isAudio = kind === 'audio'
  const playbackBadgeClass = item.accessible
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
    : 'border-amber-200 bg-amber-50 text-amber-700'
  const playbackLabel = item.accessible
    ? isEnglish
      ? 'Full playback'
      : '完整可播'
    : isEnglish
      ? 'Preview in detail page'
      : '详情页内可预览'

  return (
    <article className="fudan-card flex h-full flex-col overflow-hidden">
      <Link to={detailPath} className="block">
        <div className="relative overflow-hidden">
          {coverUrl ? (
            <img src={coverUrl} alt={item.title} className="h-52 w-full object-cover transition duration-300 hover:scale-[1.02]" loading="lazy" />
          ) : (
            <div
              className={[
                'flex h-52 items-end p-6',
                isAudio
                  ? 'bg-[linear-gradient(135deg,rgba(13,7,131,0.95),rgba(10,5,96,0.76)_58%,rgba(234,107,0,0.46))]'
                  : 'bg-[linear-gradient(135deg,rgba(2,132,199,0.92),rgba(15,23,42,0.84)_58%,rgba(234,107,0,0.32))]',
              ].join(' ')}
            >
              <div className="flex items-center gap-3 rounded-full border border-white/18 bg-white/10 px-4 py-2 text-white/88 backdrop-blur">
                {isAudio ? <Headphones size={16} /> : <Video size={16} />}
                <span className="text-xs uppercase tracking-[0.24em]">{item.series_name || (isAudio ? 'Audio' : 'Video')}</span>
              </div>
            </div>
          )}
        </div>
      </Link>

      <div className="flex flex-1 flex-col p-6">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${playbackBadgeClass}`}>
            {playbackLabel}
          </span>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            {item.visibility_label}
          </span>
        </div>

        <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{item.series_name || (isAudio ? 'Audio' : 'Video')}</div>
        <Link to={detailPath} className="mt-3 block">
          <h2 className="font-serif text-[2rem] font-black leading-tight text-fudan-blue transition hover:text-fudan-dark">{item.title}</h2>
        </Link>

        <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2">
            <CalendarDays size={14} />
            {item.publish_date || (isEnglish ? 'Unknown date' : '日期待补全')}
          </div>
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2">
            <Clock3 size={14} />
            {formatDuration(item.duration_seconds, isEnglish)}
          </div>
        </div>

        <MediaMarkdownBlock content={item.summary || item.transcript_excerpt || ''} variant="card" dataScope="hub-summary" className="mt-5" />

        {item.gate_copy ? (
          <div className="mt-5 rounded-[1.25rem] border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-800">
            {item.gate_copy}
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to={detailPath}
            className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
          >
            <ArrowRight size={16} />
            {detailLabel}
          </Link>
          {canEdit ? (
            <button
              type="button"
              onClick={() => onEditAgain?.(item.media_item_id || item.id)}
              disabled={editBusy}
              className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/15 bg-white px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/35 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {editBusy ? <LoaderCircle size={16} className="animate-spin" /> : <FilePenLine size={16} />}
              {isEnglish ? 'Edit again' : '重新编辑'}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function MediaHubPage({ kind = 'audio' }) {
  const { isEnglish } = useLanguage()
  const { accessToken, isAdmin } = useAuth()
  const navigate = useNavigate()
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState('')
  const [editError, setEditError] = useState('')
  const [editingMediaId, setEditingMediaId] = useState(null)

  useEffect(() => {
    let mounted = true
    setError('')
    fetchMediaHub(kind, accessToken, 24)
      .then((response) => {
        if (!mounted) return
        setPayload(response)
      })
      .catch(() => {
        if (!mounted) return
        setError(isEnglish ? 'Failed to load media items.' : '媒体内容加载失败。')
      })
    return () => {
      mounted = false
    }
  }, [accessToken, isEnglish, kind])

  const copy = HUB_COPY[kind]?.[isEnglish ? 'en' : 'zh'] || HUB_COPY.audio[isEnglish ? 'en' : 'zh']
  const items = payload?.items || []
  const viewerTier = payload?.viewer_tier || 'guest'
  const switchTarget = kind === 'audio' ? '/video' : '/audio'
  const showMembershipEntry = viewerTier === 'guest' || viewerTier === 'free_member'

  const handleEditAgain = async (mediaItemId) => {
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

  return (
    <div className="page-shell py-12">
      <section className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="max-w-4xl">
          <div className="section-kicker">{copy.kicker}</div>
          <h1 className="font-serif text-4xl font-black leading-tight text-fudan-blue md:text-6xl">{copy.title}</h1>
          <p className="mt-5 text-base leading-8 text-slate-600 md:text-lg">{copy.body}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          {isAdmin ? (
            <Link
              to="/media-studio"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
            >
              {kind === 'audio' ? <Headphones size={16} /> : <Video size={16} />}
              {isEnglish ? 'Media studio' : '媒体后台'}
            </Link>
          ) : null}
          <Link
            to={switchTarget}
            className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
          >
            {kind === 'audio' ? <Video size={16} /> : <Headphones size={16} />}
            {copy.switchLabel}
          </Link>
          {showMembershipEntry ? (
            <Link
              to="/membership"
              className="inline-flex items-center gap-2 rounded-full bg-fudan-orange px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#d45f00]"
            >
              <LockKeyhole size={16} />
              {copy.membershipEntry}
            </Link>
          ) : null}
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {editError ? <div className="mt-3 text-sm text-red-500">{editError}</div> : null}

      {!items.length ? (
        <section className="mt-8 rounded-[1.6rem] border border-dashed border-slate-300 bg-white p-8 text-sm leading-7 text-slate-500">
          {copy.empty}
        </section>
      ) : (
        <section className="mt-8 grid gap-6 md:grid-cols-2 2xl:grid-cols-3">
          {items.map((item) => (
            <MediaCard
              key={item.slug}
              item={item}
              kind={kind}
              isEnglish={isEnglish}
              detailLabel={copy.detail}
              canEdit={isAdmin}
              editBusy={editingMediaId === (item.media_item_id || item.id)}
              onEditAgain={handleEditAgain}
            />
          ))}
        </section>
      )}
    </div>
  )
}

export default MediaHubPage
