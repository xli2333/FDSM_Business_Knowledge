import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { fetchOrganization } from '../api/index.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'

const PAGE_SIZE = 18

function OrganizationPage() {
  const { slug } = useParams()
  const [data, setData] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)

  useEffect(() => {
    if (!slug) return
    fetchOrganization(slug, 1, PAGE_SIZE).then(setData)
  }, [slug])

  const handleLoadMore = async () => {
    if (!slug || !data) return
    setLoadingMore(true)
    try {
      const nextPage = data.page + 1
      const payload = await fetchOrganization(slug, nextPage, PAGE_SIZE)
      setData((current) => ({
        ...payload,
        articles: [...(current?.articles || []), ...payload.articles],
      }))
    } finally {
      setLoadingMore(false)
    }
  }

  if (!data) {
    return <div className="page-shell py-16 text-sm text-slate-500">机构页加载中...</div>
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel p-8 md:p-10">
        <div className="section-kicker">Organization Hub</div>
        <h1 className="section-title">{data.name}</h1>
        <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
          当前共聚合 {data.article_count} 篇相关文章，最近更新时间为 {data.latest_publish_date || '未知'}。
        </p>
      </section>

      <section className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {data.articles.map((item) => (
          <ArticleCard key={item.id} article={item} />
        ))}
      </section>

      {data.articles.length < data.article_count ? (
        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="rounded-full border border-slate-200 bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:border-fudan-blue/30 disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {loadingMore ? '加载中...' : '继续加载'}
          </button>
        </div>
      ) : null}
    </div>
  )
}

export default OrganizationPage
