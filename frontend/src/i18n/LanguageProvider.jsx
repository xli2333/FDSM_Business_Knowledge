import { useEffect, useState } from 'react'
import { LanguageContext } from './LanguageContext.js'
import { messages } from './messages.js'

const STORAGE_KEY = 'fdsm-language'
const SUPPORTED_LANGUAGES = new Set(['zh', 'en'])

function normalizeLanguage(value) {
  const candidate = String(value || '').trim().toLowerCase()
  return SUPPORTED_LANGUAGES.has(candidate) ? candidate : 'zh'
}

function detectInitialLanguage() {
  if (typeof window === 'undefined') return 'zh'

  const searchParams = new URLSearchParams(window.location.search)
  const queryLang = normalizeLanguage(searchParams.get('lang'))
  if (SUPPORTED_LANGUAGES.has(searchParams.get('lang') || '')) return queryLang

  const storedLanguage = normalizeLanguage(window.localStorage.getItem(STORAGE_KEY))
  if (window.localStorage.getItem(STORAGE_KEY)) return storedLanguage

  const browserLanguage = String(window.navigator.language || '').toLowerCase()
  return browserLanguage.startsWith('en') ? 'en' : 'zh'
}

function resolveMessage(language, key) {
  const parts = String(key || '').split('.')
  let cursor = messages[language] || messages.zh

  for (const part of parts) {
    if (cursor && typeof cursor === 'object' && part in cursor) {
      cursor = cursor[part]
    } else {
      cursor = undefined
      break
    }
  }

  if (typeof cursor === 'string') return cursor

  cursor = messages.zh
  for (const part of parts) {
    if (cursor && typeof cursor === 'object' && part in cursor) {
      cursor = cursor[part]
    } else {
      return key
    }
  }
  return typeof cursor === 'string' ? cursor : key
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(detectInitialLanguage)

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(STORAGE_KEY, language)
    document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN'

    const url = new URL(window.location.href)
    if (language === 'en') {
      url.searchParams.set('lang', 'en')
    } else {
      url.searchParams.delete('lang')
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
  }, [language])

  const setLanguage = (nextLanguage) => {
    setLanguageState(normalizeLanguage(nextLanguage))
  }

  const toggleLanguage = () => {
    setLanguageState((current) => (current === 'en' ? 'zh' : 'en'))
  }

  const t = (key) => resolveMessage(language, key)

  return (
    <LanguageContext.Provider
      value={{
        language,
        isEnglish: language === 'en',
        setLanguage,
        toggleLanguage,
        t,
      }}
    >
      {children}
    </LanguageContext.Provider>
  )
}
