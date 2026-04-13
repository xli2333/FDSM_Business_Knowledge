import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchOrganizations } from '../api/index.js'

function OrganizationsPage() {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchOrganizations(80).then(setItems).catch(() => setError('机构列表加载失败'))
  }, [])

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel p-8 md:p-10">
        <div className="section-kicker">Organizations</div>
        <h1 className="section-title">机构索引</h1>
        <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
          从文章中的机构字段聚合而来，用于把单篇内容继续串成机构维度的知识入口。
        </p>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      <section className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <Link key={item.slug} to={`/organization/${item.slug}`} className="fudan-card p-7">
            <div className="section-kicker">Organization</div>
            <div className="font-serif text-3xl font-black text-fudan-blue">{item.name}</div>
            <div className="mt-4 text-sm leading-7 text-slate-600">相关文章：{item.article_count} 篇</div>
            <div className="text-sm leading-7 text-slate-500">最近更新：{item.latest_publish_date || '未知'}</div>
          </Link>
        ))}
      </section>
    </div>
  )
}

export default OrganizationsPage
