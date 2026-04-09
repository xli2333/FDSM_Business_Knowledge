import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchSuggestions } from '../../api/index.js'
import { useAuth } from '../../auth/AuthContext.js'
import { useLanguage } from '../../i18n/LanguageContext.js'

function SearchBar({ initialQuery = '', initialMode = 'smart', onSearch, variant = 'hero' }) {
  const { isEnglish } = useLanguage()
  const { isAdmin, isAuthenticated, isPaidMember, openAuthDialog } = useAuth()
  const [query, setQuery] = useState(initialQuery)
  const [mode, setMode] = useState(initialMode)
  const [suggestions, setSuggestions] = useState([])
  const smartSearchLocked = !(isPaidMember || isAdmin)
  const modeTabs = smartSearchLocked
    ? [['exact', isEnglish ? 'Exact Search' : '精确搜索']]
    : [
        ['smart', isEnglish ? 'Smart Search' : '智能搜索'],
        ['exact', isEnglish ? 'Exact Search' : '精确搜索'],
      ]

  useEffect(() => {
    setQuery(initialQuery)
  }, [initialQuery])

  useEffect(() => {
    setMode(initialMode)
  }, [initialMode])

  useEffect(() => {
    if (smartSearchLocked && mode === 'smart') {
      setMode('exact')
    }
  }, [mode, smartSearchLocked])

  useEffect(() => {
    const value = query.trim()
    if (!value) {
      setSuggestions([])
      return undefined
    }

    const timer = window.setTimeout(async () => {
      try {
        const payload = await fetchSuggestions(value, isEnglish ? 'en' : 'zh')
        setSuggestions(payload.suggestions || [])
      } catch {
        setSuggestions([])
      }
    }, 220)

    return () => window.clearTimeout(timer)
  }, [isEnglish, query])

  const large = variant === 'hero'

  const handleModeChange = (nextMode) => {
    if (nextMode === 'smart' && smartSearchLocked) {
      if (!isAuthenticated) {
        openAuthDialog()
      }
      setMode('exact')
      return
    }
    setMode(nextMode)
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!query.trim()) return
    setSuggestions([])
    onSearch?.(query.trim(), mode)
  }

  return (
    <div className="relative w-full">
      <form onSubmit={handleSubmit} className="fudan-panel overflow-hidden">
        <div className="flex border-b border-slate-200/80">
          {modeTabs.map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => handleModeChange(value)}
              className={[
                'flex-1 px-5 py-4 text-sm font-semibold tracking-[0.2em] transition',
                mode === value ? 'bg-fudan-orange text-white' : 'bg-white text-slate-400 hover:bg-slate-50',
              ].join(' ')}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 px-5 py-4">
          <Search size={large ? 22 : 18} className="shrink-0 text-fudan-blue" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              mode === 'smart'
                ? isEnglish
                  ? 'Enter a question, topic, person, or concept'
                  : '输入问题、主题、人物或概念'
                : isEnglish
                  ? 'Enter title keywords or an exact phrase'
                  : '输入标题关键词或精确短语'
            }
            className={[
              'w-full bg-transparent outline-none placeholder:text-slate-400',
              large ? 'py-3 font-serif text-2xl md:text-3xl' : 'py-2 text-base',
            ].join(' ')}
          />
          <button
            type="submit"
            className={[
              'shrink-0 whitespace-nowrap rounded-[1rem] bg-fudan-blue text-sm font-semibold text-white transition hover:bg-fudan-dark',
              large ? 'min-w-[112px] px-6 py-3.5' : 'min-w-[92px] px-4 py-2.5',
            ].join(' ')}
          >
            {isEnglish ? 'Search' : '搜索'}
          </button>
        </div>
      </form>

      {smartSearchLocked ? (
        <div className="mt-3 px-2 text-xs leading-6 text-slate-500">
          {isEnglish
            ? 'Smart search is available to paid members. Exact keyword search remains open in the current tier.'
            : '智能搜索仅对付费会员开放，当前身份仍可使用精确关键词搜索。'}
        </div>
      ) : null}

      {suggestions.length > 0 ? (
        <div className="absolute inset-x-2 top-full z-20 mt-2 rounded-[1.4rem] border border-slate-200 bg-white p-3 shadow-xl">
          {suggestions.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => {
                setQuery(item)
                setSuggestions([])
                onSearch?.(item, mode)
              }}
              className="block w-full rounded-xl px-4 py-3 text-left text-sm text-slate-600 transition hover:bg-slate-50 hover:text-fudan-blue"
            >
              {item}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export default SearchBar
