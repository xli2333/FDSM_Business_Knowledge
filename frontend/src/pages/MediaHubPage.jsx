import {
  CalendarDays,
  Clock3,
  ExternalLink,
  Headphones,
  LockKeyhole,
  PlayCircle,
  Video,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchMediaHub, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const HUB_COPY = {
  audio: {
    zh: {
      kicker: '付费音频流',
      title: '音频改成连续卡片流，按会员权限直接分发',
      body: '音频页不再使用上方大说明卡和左长右短结构。所有音频统一按卡片流展示，付费会员可收听完整版，访客与免费会员只保留 1 分钟试听。',
      empty: '当前还没有可展示的音频内容。',
      open: '打开完整音频',
      upgrade: '升级查看完整音频',
      switchLabel: '去视频页',
      membershipEntry: '查看会员权限',
    },
    en: {
      kicker: 'Premium Audio Stream',
      title: 'Audio now runs as a continuous card stream',
      body: 'The audio page no longer uses a large top explainer or a long-left-short-right layout. Every item now lives in a continuous media card stream. Paid members get full playback, while guests and free members keep a one-minute preview.',
      empty: 'No audio items are available yet.',
      open: 'Open full audio',
      upgrade: 'Upgrade for full audio',
      switchLabel: 'Open video',
      membershipEntry: 'View membership access',
    },
  },
  video: {
    zh: {
      kicker: '视频流',
      title: '视频页也回到和文章一致的流式分布',
      body: '视频页与音频页保持同一套流式卡片结构，避免再出现大面积说明区和不必要的详情主卡。可播放条目直接播放，受限条目按试看规则收口。',
      empty: '当前还没有可展示的视频内容。',
      open: '打开完整视频',
      upgrade: '升级查看完整视频',
      switchLabel: '去音频页',
      membershipEntry: '查看会员权限',
    },
    en: {
      kicker: 'Video Stream',
      title: 'Video now follows the same flowing layout as articles',
      body: 'The video page now shares the same continuous card structure as audio. The oversized explainer and main detail card are gone. Playable items open directly, while gated items stay inside a preview flow.',
      empty: 'No video items are available yet.',
      open: 'Open full video',
      upgrade: 'Upgrade for full video',
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

function MediaCard({ item, kind, isEnglish, openLabel, upgradeLabel }) {
  const mediaRef = useRef(null)
  const [previewEnded, setPreviewEnded] = useState(false)
  const playableUrl = buildPlayableUrl(item)
  const previewLimit = item.accessible ? 0 : Number(item.preview_duration_seconds || 0)
  const coverUrl = resolveApiUrl(item.cover_image_url)
  const excerpt = item.transcript_excerpt || item.summary
  const isAudio = kind === 'audio'

  useEffect(() => {
    setPreviewEnded(false)
    const node = mediaRef.current
    if (!node) return
    try {
      node.pause?.()
      node.currentTime = 0
    } catch {}
  }, [item.slug])

  const handleTimeUpdate = (event) => {
    if (!previewLimit) return
    const node = event.currentTarget
    if (node.currentTime >= previewLimit) {
      node.currentTime = previewLimit
      node.pause()
      setPreviewEnded(true)
    }
  }

  const handlePlay = (event) => {
    if (!previewLimit) return
    const node = event.currentTarget
    if (previewEnded && node.currentTime >= previewLimit - 0.25) {
      node.currentTime = 0
      setPreviewEnded(false)
    }
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
    <article className="fudan-card flex h-full flex-col overflow-hidden">
      <div className="relative overflow-hidden">
        {coverUrl ? (
          <img src={coverUrl} alt={item.title} className="h-52 w-full object-cover" loading="lazy" />
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
        <h2 className="mt-3 font-serif text-[2rem] font-black leading-tight text-fudan-blue">{item.title}</h2>

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

        <p className="mt-5 text-sm leading-7 text-slate-600">{item.summary}</p>
        {excerpt && excerpt !== item.summary ? <p className="mt-4 text-sm leading-7 text-slate-500">{excerpt}</p> : null}

        {!item.accessible && item.gate_copy ? (
          <div className="mt-5 rounded-[1.25rem] border border-amber-200 bg-amber-50 p-4 text-sm leading-7 text-amber-800">
            {item.gate_copy}
          </div>
        ) : null}

        <div className="mt-6">
          {isAudio ? (
            playableUrl ? (
              <audio
                ref={mediaRef}
                controls
                preload="metadata"
                src={playableUrl}
                className="w-full"
                controlsList={item.accessible ? undefined : 'nodownload noplaybackrate'}
                onPlay={handlePlay}
                onTimeUpdate={handleTimeUpdate}
                onContextMenu={item.accessible ? undefined : (event) => event.preventDefault()}
              >
                {isEnglish ? 'Your browser does not support the audio player.' : '当前浏览器不支持音频播放。'}
              </audio>
            ) : (
              <div className="rounded-[1.2rem] border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                {isEnglish ? 'Playback will appear after the media file is attached.' : '媒体文件上传后会在这里出现播放器。'}
              </div>
            )
          ) : playableUrl ? (
            <video
              ref={mediaRef}
              controls
              preload="metadata"
              src={playableUrl}
              className="aspect-video w-full rounded-[1.25rem] bg-slate-950"
              controlsList={item.accessible ? undefined : 'nodownload noplaybackrate'}
              onPlay={handlePlay}
              onTimeUpdate={handleTimeUpdate}
              onContextMenu={item.accessible ? undefined : (event) => event.preventDefault()}
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-[1.25rem] bg-[linear-gradient(135deg,rgba(2,132,199,0.14),rgba(15,23,42,0.08)_65%,rgba(234,107,0,0.12))]">
              <div className="rounded-full border border-slate-200 bg-white/85 p-5 text-slate-500 shadow-sm">
                <Video size={22} />
              </div>
            </div>
          )}
        </div>

        {previewEnded ? (
          <div className="mt-4 rounded-[1.2rem] border border-fudan-orange/20 bg-fudan-orange/10 p-4 text-sm leading-7 text-fudan-orange">
            {isEnglish
              ? 'The preview ended here. Upgrade to continue with the full item.'
              : '预览已在这里结束，升级后可继续收听或观看完整内容。'}
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap gap-3">
          {item.accessible && playableUrl ? (
            <a
              href={playableUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
            >
              <PlayCircle size={16} />
              {openLabel}
            </a>
          ) : (
            <Link
              to="/membership"
              className="inline-flex items-center gap-2 rounded-full bg-fudan-orange px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#d45f00]"
            >
              <LockKeyhole size={16} />
              {upgradeLabel}
            </Link>
          )}
          {item.accessible && item.source_url ? (
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
      </div>
    </article>
  )
}

function MediaHubPage({ kind = 'audio' }) {
  const { isEnglish } = useLanguage()
  const { accessToken, isAdmin } = useAuth()
  const [payload, setPayload] = useState(null)
  const [error, setError] = useState('')

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
              openLabel={copy.open}
              upgradeLabel={copy.upgrade}
            />
          ))}
        </section>
      )}

    </div>
  )
}

export default MediaHubPage
