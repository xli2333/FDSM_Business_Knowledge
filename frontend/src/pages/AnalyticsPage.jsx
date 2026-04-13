import { BarChart3, Bookmark, Eye, Heart, TrendingUp } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { fetchAnalyticsOverview } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import ArticleCard from '../components/shared/ArticleCard.jsx'

function AnalyticsPage() {
  const { accessToken } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchAnalyticsOverview(accessToken).then(setData).catch(() => setError('内容分析加载失败'))
  }, [accessToken])

  const trendMax = useMemo(() => Math.max(...(data?.views_trend || []).map((item) => item.value), 1), [data])

  return (
    <div className="page-shell py-12">
      <div className="mb-10">
        <div className="section-kicker">Analytics</div>
        <h1 className="section-title">内容表现与读者行为分析</h1>
        <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
          仅管理员可见。用于查看最近浏览趋势、点赞、收藏和高价值文章分布，辅助内容运营与发布决策。
        </p>
      </div>

      {error ? <div className="mb-6 text-sm text-red-500">{error}</div> : null}

      <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {(data?.metrics || []).map((metric) => (
          <div key={metric.label} className="fudan-panel p-6">
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{metric.label}</div>
            <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{metric.value}</div>
            <div className="mt-2 text-sm leading-7 text-slate-600">{metric.detail}</div>
          </div>
        ))}
      </section>

      <section className="mt-10 grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="fudan-panel p-8">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
              <TrendingUp size={20} />
            </div>
            <div>
              <div className="section-kicker">7 日趋势</div>
              <h2 className="font-serif text-3xl font-black text-fudan-blue">最近 7 天浏览走势</h2>
            </div>
          </div>
          <div className="mt-8 space-y-4">
            {(data?.views_trend || []).map((item) => (
              <div key={item.label}>
                <div className="mb-2 flex items-center justify-between text-sm text-slate-500">
                  <span>{item.label}</span>
                  <span>{item.value}</span>
                </div>
                <div className="h-3 rounded-full bg-slate-100">
                  <div
                    className="h-3 rounded-full bg-[linear-gradient(90deg,#0d0783,#ea6b00)]"
                    style={{ width: `${Math.max((item.value / trendMax) * 100, item.value > 0 ? 8 : 0)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="fudan-panel p-8">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
              <BarChart3 size={20} />
            </div>
            <div>
              <div className="section-kicker">分析结论</div>
              <h2 className="font-serif text-3xl font-black text-fudan-blue">当前读者行为的三个信号</h2>
            </div>
          </div>
          <div className="mt-6 space-y-4 text-sm leading-7 text-slate-600">
            <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
              浏览榜反映内容触达规模，适合评估首页推荐、专题策划和外部传播效果。
            </div>
            <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
              点赞榜更接近即时反馈，适合判断观点类和判断类内容是否打中读者情绪与价值认同。
            </div>
            <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
              收藏榜更接近长期价值，适合识别值得沉淀成专题、课程或会员产品的高价值文章。
            </div>
          </div>
        </div>
      </section>

      <section className="mt-12 space-y-12">
        {[
          ['浏览榜', <Eye key="views" size={18} />, data?.top_viewed || []],
          ['点赞榜', <Heart key="likes" size={18} />, data?.top_liked || []],
          ['收藏榜', <Bookmark key="bookmarks" size={18} />, data?.top_bookmarked || []],
        ].map(([title, icon, items]) => (
          <div key={title}>
            <div className="mb-6 flex items-center gap-3">
              <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">{icon}</div>
              <h2 className="font-serif text-3xl font-black text-fudan-blue">{title}</h2>
            </div>
            <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
              {items.map((article) => (
                <ArticleCard key={`${title}-${article.id}`} article={article} />
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}

export default AnalyticsPage
