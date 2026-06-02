import { BellPlus, BellRing } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchColumnArticles, fetchFollows, toggleFollow } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'

const PAGE_SIZE = 18

function ColumnPage() {
  const { slug } = useParams()
  const { isAuthenticated, accessToken, openAuthDialog } = useAuth()
  const { isEnglish, language } = useLanguage()
  const [data, setData] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [isFollowing, setIsFollowing] = useState(false)

  useEffect(() => {
    if (!slug) return
    setData(null)
    fetchColumnArticles(slug, 1, PAGE_SIZE, language).then(setData)
  }, [language, slug])

  useEffect(() => {
    if (!slug || !isAuthenticated) {
      setIsFollowing(false)
      return
    }
    fetchFollows(accessToken).then((payload) => {
      setIsFollowing((payload.items || []).some((item) => item.entity_type === 'column' && item.entity_slug === slug))
    })
  }, [accessToken, isAuthenticated, slug])

  const handleLoadMore = async () => {
    if (!slug || !data) return
    setLoadingMore(true)
    try {
      const nextPage = data.page + 1
      const payload = await fetchColumnArticles(slug, nextPage, PAGE_SIZE, language)
      setData((current) => ({
        ...payload,
        items: [...(current?.items || []), ...payload.items],
      }))
    } finally {
      setLoadingMore(false)
    }
  }

  const handleFollow = async () => {
    if (!slug) return
    if (!isAuthenticated) {
      openAuthDialog()
      return
    }
    await toggleFollow(
      {
        entity_type: 'column',
        entity_slug: slug,
        active: !isFollowing,
      },
      accessToken,
    )
    setIsFollowing((current) => !current)
  }

  if (!data) {
    return <div className="page-shell py-16 text-sm text-slate-500">{isEnglish ? 'Loading section...' : '板块加载中...'}</div>
  }

  return (
    <div className="page-shell py-12">
      <div className="fudan-panel p-8 md:p-10">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="section-kicker">{isEnglish ? 'Section channel' : '板块频道'}</div>
            <h1 className="section-title">{data.column.name}</h1>
            <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">{data.column.description}</p>
          </div>
          <button
            type="button"
            onClick={handleFollow}
            className="inline-flex items-center gap-2 rounded-full border border-fudan-blue/20 bg-fudan-blue/10 px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:bg-fudan-blue/15"
          >
            {isFollowing ? <BellRing size={16} /> : <BellPlus size={16} />}
            {isFollowing ? (isEnglish ? 'Following section' : '已关注板块') : isEnglish ? 'Follow section' : '关注板块'}
          </button>
        </div>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {data.items.map((item) => (
          <ArticleCard key={item.id} article={item} />
        ))}
      </div>
      {data.items.length < data.total ? (
        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:border-fudan-blue/30 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {loadingMore ? (isEnglish ? 'Loading...' : '加载中...') : isEnglish ? 'Load more' : '继续加载'}
          </button>
        </div>
      ) : null}
    </div>
  )
}

export default ColumnPage
