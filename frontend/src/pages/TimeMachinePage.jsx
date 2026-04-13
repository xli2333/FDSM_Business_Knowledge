import { Clock, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchTimeMachine, resolveApiUrl } from '../api/index.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function TimeMachinePage() {
  const { isEnglish } = useLanguage()
  const [targetDate, setTargetDate] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const runTimeMachine = async (dateValue = '') => {
    setLoading(true)
    try {
      const payload = await fetchTimeMachine(dateValue, isEnglish ? 'en' : 'zh')
      setData(payload)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let mounted = true
    async function loadInitialCard() {
      setLoading(true)
      try {
        const payload = await fetchTimeMachine('', isEnglish ? 'en' : 'zh')
        if (mounted) {
          setData(payload)
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }
    loadInitialCard().catch(() => {})
    return () => {
      mounted = false
    }
  }, [isEnglish])

  return (
    <div className="page-shell py-12">
      <div className="mb-8">
        <div className="section-kicker">{isEnglish ? 'Time Machine' : '时光机'}</div>
        <h1 className="section-title">{isEnglish ? 'Return to a date and reopen the reading context of that day' : '从某一天切回当时的阅读现场'}</h1>
      </div>

      <div className="fudan-panel p-6">
        <div className="flex flex-col gap-4 md:flex-row">
          <div className="flex flex-1 items-center gap-3 rounded-full border border-slate-200 bg-slate-50 px-4 py-3">
            <Clock size={18} className="text-fudan-blue" />
            <input
              value={targetDate}
              onChange={(event) => setTargetDate(event.target.value)}
              placeholder={isEnglish ? 'Enter a date, for example 2023-06-21' : '输入日期，例如 2023-06-21'}
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
            />
          </div>
          <button
            type="button"
            onClick={() => runTimeMachine(targetDate)}
            className="rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold tracking-[0.18em] text-white transition hover:bg-fudan-dark"
          >
            {isEnglish ? 'Start time machine' : '启动时光机'}
          </button>
        </div>
      </div>

      {loading ? <div className="mt-10 text-sm text-slate-500">{isEnglish ? 'Searching through the archive...' : '正在检索历史内容...'}</div> : null}

      {data ? (
        <div className="mt-10 flex justify-center">
          <div className="w-full max-w-2xl rounded-[2rem] border border-slate-200 bg-white p-5 shadow-[0_24px_80px_rgba(15,23,42,0.12)]">
            <div className="aspect-square overflow-hidden rounded-[1.4rem] bg-slate-100">
              {data.cover_url ? (
                <img src={resolveApiUrl(data.cover_url)} alt={data.title} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full items-end bg-[linear-gradient(135deg,rgba(13,7,131,0.96),rgba(10,5,96,0.8)_60%,rgba(234,107,0,0.55))] p-8 text-white">
                  <div>
                    <div className="text-xs uppercase tracking-[0.24em] text-white/65">Time Machine</div>
                    <div className="mt-3 font-serif text-3xl font-black">{data.publish_date}</div>
                  </div>
                </div>
              )}
            </div>
            <div className="px-4 py-6 text-center">
              <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{data.publish_date}</div>
              <h2 className="mt-3 font-serif text-3xl font-black text-fudan-blue">{data.title}</h2>
              <p className="mt-5 text-lg font-semibold leading-8 text-fudan-orange">“{data.quote}”</p>
              <p className="mt-5 text-sm leading-7 text-slate-600">{data.excerpt}</p>
              <div className="mt-6 flex items-center justify-center gap-3">
                <Link to={`/article/${data.id}`} className="rounded-full bg-fudan-orange px-5 py-3 text-sm font-semibold text-white">
                  {isEnglish ? 'Read article' : '阅读文章'}
                </Link>
                <button
                  type="button"
                  onClick={() => runTimeMachine(targetDate)}
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-600"
                >
                  <RefreshCw size={15} />
                  {isEnglish ? 'Try another one' : '换一篇'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default TimeMachinePage
