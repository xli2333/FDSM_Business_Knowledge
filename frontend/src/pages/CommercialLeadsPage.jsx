import { Download, Inbox } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAdminBillingOrders, fetchDemoRequests, resolveApiUrl } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function CommercialLeadsPage() {
  const { accessToken, isAdmin } = useAuth()
  const { isEnglish } = useLanguage()
  const [items, setItems] = useState([])
  const [orders, setOrders] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchDemoRequests(80).then(setItems).catch(() => setError(isEnglish ? 'Failed to load inbound leads.' : '线索列表加载失败'))
  }, [isEnglish])

  useEffect(() => {
    if (!isAdmin) return
    fetchAdminBillingOrders(accessToken, 20)
      .then((payload) => setOrders(payload.items || []))
      .catch(() => {})
  }, [accessToken, isAdmin])

  return (
    <div className="page-shell py-12">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="section-kicker">Lead Console</div>
          <h1 className="section-title">{isEnglish ? 'Commercial inquiries and inbound leads' : '商业咨询与入站线索'}</h1>
          <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">
            {isEnglish
              ? 'This console reads the commercial inquiry table directly and pairs it with recent billing orders so operations can review demand and follow-up status in one place.'
              : '这里直接读取商业咨询线索，并结合最近的账单订单，方便运营团队在一个界面里查看需求来源与后续跟进状态。'}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <a
            href={resolveApiUrl('/api/commerce/demo-requests/export')}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
          >
            <Download size={16} />
            {isEnglish ? 'Export CSV' : '导出 CSV'}
          </a>
          <Link
            to="/commercial"
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/30"
          >
            {isEnglish ? 'Back to commercial page' : '返回商业方案页'}
          </Link>
        </div>
      </div>

      {error ? <div className="mt-8 text-sm text-red-500">{error}</div> : null}

      <div className="mt-8 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="fudan-panel overflow-hidden">
          {items.length === 0 ? (
            <div className="flex flex-col items-center gap-4 px-8 py-16 text-center text-slate-500">
              <Inbox size={32} className="text-slate-300" />
              <div>{isEnglish ? 'No commercial inquiries yet.' : '当前还没有商业咨询记录。'}</div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-left text-xs uppercase tracking-[0.18em] text-slate-400">
                    <th className="px-5 py-4">{isEnglish ? 'Created' : '时间'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Name' : '姓名'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Organization' : '机构'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Role' : '角色'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Email' : '邮箱'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Use case' : '场景'}</th>
                    <th className="px-5 py-4">{isEnglish ? 'Status' : '状态'}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id} className="border-t border-slate-200/70 align-top">
                      <td className="px-5 py-4 text-slate-500">{item.created_at.replace('T', ' ').slice(0, 16)}</td>
                      <td className="px-5 py-4 font-semibold text-fudan-blue">{item.name}</td>
                      <td className="px-5 py-4 text-slate-600">{item.organization}</td>
                      <td className="px-5 py-4 text-slate-600">{item.role}</td>
                      <td className="px-5 py-4 text-slate-600">{item.email}</td>
                      <td className="px-5 py-4 text-slate-600">
                        <div>{item.use_case}</div>
                        {item.message ? <div className="mt-2 text-xs leading-6 text-slate-400">{item.message}</div> : null}
                      </td>
                      <td className="px-5 py-4">
                        <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
                          {item.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="fudan-panel p-6">
          <div className="section-kicker">Billing Orders</div>
          <div className="space-y-3">
            {isAdmin ? (
              orders.length ? (
                orders.map((order) => (
                  <div key={order.id} className="rounded-[1.2rem] border border-slate-200/70 bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold text-fudan-blue">{order.plan_name || order.plan_code}</div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                        {order.status}
                      </span>
                    </div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">{order.email || (isEnglish ? 'No email' : '无邮箱')}</div>
                    <div className="text-sm leading-7 text-slate-500">{order.created_at.replace('T', ' ').slice(0, 16)}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm text-slate-500">
                  {isEnglish ? 'No billing orders have been created yet.' : '当前还没有账单订单记录。'}
                </div>
              )
            ) : (
              <div className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm text-slate-500">
                {isEnglish ? 'Billing orders are visible to admins after sign-in.' : '登录管理员账号后可查看最近账单订单。'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default CommercialLeadsPage
