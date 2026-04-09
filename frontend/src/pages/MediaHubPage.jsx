import {
  CalendarDays,
  Clock3,
  ExternalLink,
  Headphones,
  LockKeyhole,
  PlayCircle,
  Video,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { fetchMediaHub, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const HUB_COPY = {
  audio: {
    zh: {
      kicker: '音频媒体',
      title: '真实音频与会员音频统一在这里',
      body: '音频页现在直接走后台媒体接口。真实的 4 个本地 mp3 会保留，同时管理员可继续新增公开、会员和付费音频。',
      empty: '当前还没有可展示的音频内容。',
      open: '打开音频文件',
      download: '下载音频',
    },
    en: {
      kicker: 'Audio Media',
      title: 'Real and member audio in one place',
      body: 'The audio page now uses the live media API. The four local mp3 tracks stay online, and admins can continue publishing public, member, and paid audio.',
      empty: 'No audio items are available yet.',
      open: 'Open audio file',
      download: 'Download audio',
    },
  },
  video: {
    zh: {
      kicker: '视频媒体',
      title: '公开视频与会员视频继续保留',
      body: '视频页已经恢复，不再被跳转到音频。这里展示后台维护的视频内容，并继续支持按公开、会员、付费权限分发。',
      empty: '当前还没有可展示的视频内容。',
      open: '打开视频文件',
      download: '下载视频',
    },
    en: {
      kicker: 'Video Media',
      title: 'Public and member video stay online',
      body: 'The video page has been restored and no longer redirects to audio. It shows live media items from the backend with public, member, and paid access tiers.',
      empty: 'No video items are available yet.',
      open: 'Open video file',
      download: 'Download video',
    },
  },
}

const TIER_LABELS = {
  guest: { zh: '游客', en: 'Guest' },
  free_member: { zh: '免费会员', en: 'Free Member' },
  paid_member: { zh: '付费会员', en: 'Paid Member' },
  admin: { zh: '管理员', en: 'Admin' },
}

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function formatDuration(seconds, isEnglish) {
  const safe = Number(seconds || 0)
  if (!safe) return isEnglish ? 'Duration pending' : '时长待补充'
  const minutes = Math.floor(safe / 60)
  const remain = safe % 60
  return isEnglish ? `${minutes}m ${remain}s` : `${minutes} 分 ${remain} 秒`
}

function buildPlayableUrl(item) {
  const url = item?.accessible ? item?.media_url || item?.preview_url : item?.preview_url || item?.media_url
  return resolveApiUrl(url)
}

function MediaHubPage({ kind = 'audio' }) {
  const { isEnglish } = useLanguage()
  const { accessToken, isAdmin } = useAuth()
  const [payload, setPayload] = useState(null)
  const [selectedSlug, setSelectedSlug] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    fetchMediaHub(kind, accessToken, 24)
      .then((response) => {
        if (!mounted) return
        setPayload(response)
        setSelectedSlug((current) => current || response.items?.[0]?.slug || '')
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
  const selectedItem = items.find((item) => item.slug === selectedSlug) || items[0] || null
  const viewerTier = payload?.viewer_tier || 'guest'
  const totalDuration = useMemo(
    () => items.reduce((sum, item) => sum + Number(item.duration_seconds || 0), 0),
    [items],
  )
  const playableUrl = buildPlayableUrl(selectedItem)
  const richMarkdown = selectedItem?.body_markdown || selectedItem?.transcript_markdown || ''

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(234,107,0,0.22))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{copy.kicker}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{copy.title}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{copy.body}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              {isAdmin ? (
                <Link
                  to="/media-studio"
                  className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
                >
                  {kind === 'audio' ? <Headphones size={16} /> : <Video size={16} />}
                  {isEnglish ? 'Open media studio' : '进入媒体后台'}
                </Link>
              ) : null}
              <Link
                to="/membership"
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15"
              >
                <LockKeyhole size={16} />
                {isEnglish ? 'View access tiers' : '查看权限层级'}
              </Link>
            </div>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Viewer tier' : '当前身份'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">
                {TIER_LABELS[viewerTier]?.[isEnglish ? 'en' : 'zh'] || viewerTier}
              </div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish ? 'Playback and preview depend on your current membership tier.' : '播放和试看会按当前身份权限自动收口。'}
              </div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Visible items' : '可见内容'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{items.length}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish
                  ? `Public ${payload?.public_count || 0} / Member ${payload?.member_count || 0} / Paid ${payload?.paid_count || 0}`
                  : `公开 ${payload?.public_count || 0} / 会员 ${payload?.member_count || 0} / 付费 ${payload?.paid_count || 0}`}
              </div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Total runtime' : '总时长'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{formatDuration(totalDuration, isEnglish)}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish ? 'Audio and video items now come from the same media system.' : '音频和视频已经重新接回同一套媒体系统。'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      {!items.length ? (
        <section className="mt-8 rounded-[1.6rem] border border-dashed border-slate-300 bg-white p-8 text-sm leading-7 text-slate-500">
          {copy.empty}
        </section>
      ) : (
        <section className="mt-8 grid gap-6 xl:grid-cols-[1.02fr_0.98fr]">
          <article className="fudan-panel overflow-hidden p-8">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="section-kicker">{selectedItem?.series_name || (kind === 'audio' ? 'Audio' : 'Video')}</div>
                <h2 className="mt-2 font-serif text-4xl font-black text-fudan-blue">{selectedItem?.title}</h2>
              </div>
              <div className="rounded-full bg-fudan-blue/10 p-4 text-fudan-blue">
                {kind === 'audio' ? <Headphones size={20} /> : <Video size={20} />}
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-3 text-sm text-slate-500">
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2">
                <CalendarDays size={15} />
                {selectedItem?.publish_date || (isEnglish ? 'Unknown date' : '日期待补充')}
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2">
                <Clock3 size={15} />
                {formatDuration(selectedItem?.duration_seconds, isEnglish)}
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2">
                {selectedItem?.visibility_label}
              </div>
            </div>

            <p className="mt-6 text-base leading-8 text-slate-600">{selectedItem?.summary}</p>

            {!selectedItem?.accessible && selectedItem?.gate_copy ? (
              <div className="mt-6 rounded-[1.3rem] border border-amber-200 bg-amber-50 p-5 text-sm leading-7 text-amber-800">
                {selectedItem.gate_copy}
              </div>
            ) : null}

            {kind === 'audio' ? (
              <audio key={selectedItem?.slug} controls preload="metadata" src={playableUrl || undefined} className="mt-6 w-full">
                {isEnglish ? 'Your browser does not support the audio player.' : '当前浏览器不支持音频播放。'}
              </audio>
            ) : (
              <video
                key={selectedItem?.slug}
                controls
                preload="metadata"
                src={playableUrl || undefined}
                className="mt-6 aspect-video w-full rounded-[1.25rem] bg-slate-950"
              />
            )}

            <div className="mt-6 flex flex-wrap gap-3">
              {playableUrl ? (
                <>
                  <a
                    href={playableUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
                  >
                    <PlayCircle size={16} />
                    {copy.open}
                  </a>
                  <a
                    href={playableUrl}
                    download
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
                  >
                    <ExternalLink size={16} />
                    {copy.download}
                  </a>
                </>
              ) : null}
            </div>

            {richMarkdown ? (
              <div className="prose prose-slate mt-8 max-w-none rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-6">
                <ReactMarkdown>{richMarkdown}</ReactMarkdown>
              </div>
            ) : null}
          </article>

          <section className="grid gap-4">
            {items.map((item) => {
              const active = item.slug === selectedItem?.slug
              const tone = item.accessible
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-amber-200 bg-amber-50 text-amber-700'

              return (
                <button
                  key={item.slug}
                  type="button"
                  onClick={() => setSelectedSlug(item.slug)}
                  className={[
                    'fudan-card p-6 text-left transition',
                    active ? 'border-fudan-orange/35 bg-fudan-orange/5 shadow-[0_18px_40px_rgba(234,107,0,0.12)]' : '',
                  ].join(' ')}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs uppercase tracking-[0.22em] text-slate-400">{item.series_name || item.kind}</div>
                      <h3 className="mt-2 font-serif text-2xl font-black leading-tight text-fudan-blue">{item.title}</h3>
                    </div>
                    <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
                      {item.kind === 'audio' ? <Headphones size={18} /> : <Video size={18} />}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-3 text-sm text-slate-500">
                    <span>{item.publish_date}</span>
                    <span>/</span>
                    <span>{formatDuration(item.duration_seconds, isEnglish)}</span>
                  </div>

                  <p className="mt-4 text-sm leading-7 text-slate-600">{item.summary}</p>

                  <div className="mt-5 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${tone}`}>
                      {item.accessible
                        ? isEnglish
                          ? 'Unlocked'
                          : '当前可播放'
                        : isEnglish
                          ? 'Preview or gated'
                          : '试看或受限'}
                    </span>
                    {item.visibility_label ? (
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500">
                        {item.visibility_label}
                      </span>
                    ) : null}
                  </div>
                </button>
              )
            })}
          </section>
        </section>
      )}
    </div>
  )
}

export default MediaHubPage
