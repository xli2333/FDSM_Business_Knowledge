import { Plus, RefreshCcw, Save, Shield, UserRound } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { fetchAdminMemberships, updateAdminMembership } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const DEFAULT_NEW_MEMBER = {
  user_id: '',
  email: '',
  tier: 'free_member',
  status: 'active',
  note: '',
  expires_at: '',
}

const TIER_OPTIONS = ['free_member', 'paid_member', 'admin']
const STATUS_OPTIONS = ['active', 'trial', 'paused', 'expired']

function tierLabel(tier, isEnglish) {
  return (
    {
      free_member: isEnglish ? 'Free Member' : '免费会员',
      paid_member: isEnglish ? 'Paid Member' : '付费会员',
      admin: isEnglish ? 'Admin' : '管理员',
    }[tier] || tier
  )
}

function statusLabel(status, isEnglish) {
  return (
    {
      active: isEnglish ? 'Active' : '有效',
      trial: isEnglish ? 'Trial' : '试用中',
      paused: isEnglish ? 'Paused' : '已暂停',
      expired: isEnglish ? 'Expired' : '已过期',
    }[status] || status
  )
}

function AdminMembershipsPage() {
  const { accessToken, authEnabled, isAdmin, isAuthenticated, membership, openAuthDialog } = useAuth()
  const { isEnglish } = useLanguage()
  const [data, setData] = useState({ items: [], counts: [], total: 0 })
  const [drafts, setDrafts] = useState({})
  const [newMember, setNewMember] = useState(DEFAULT_NEW_MEMBER)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [savingId, setSavingId] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [error, setError] = useState('')

  const loadData = useCallback(async () => {
    if (!isAdmin) return
    setLoading(true)
    setError('')
    try {
      const payload = await fetchAdminMemberships(accessToken, 120, query.trim())
      setData(payload)
      setDrafts(
        Object.fromEntries(
          (payload.items || []).map((item) => [
            item.user_id,
            {
              email: item.email || '',
              tier: item.tier,
              status: item.status,
              note: item.note || '',
              expires_at: item.expires_at || '',
            },
          ]),
        ),
      )
    } catch (loadError) {
      setError(loadError.status === 403 ? (isEnglish ? 'This account does not have admin access.' : '当前账号没有管理员权限。') : isEnglish ? 'Failed to load member records.' : '会员列表加载失败。')
    } finally {
      setLoading(false)
    }
  }, [accessToken, isAdmin, isEnglish, query])

  useEffect(() => {
    loadData().catch(() => {})
  }, [loadData])

  const handleDraftChange = (userId, field, value) => {
    setDrafts((current) => ({
      ...current,
      [userId]: {
        ...(current[userId] || {}),
        [field]: value,
      },
    }))
  }

  const handleSave = async (userId) => {
    setSavingId(userId)
    setStatusMessage('')
    setError('')
    try {
      await updateAdminMembership(userId, drafts[userId], accessToken)
      await loadData()
      setStatusMessage(isEnglish ? `Saved changes for ${userId}.` : `已保存 ${userId} 的会员设置。`)
    } catch {
      setError(isEnglish ? 'Failed to save member settings.' : '会员设置保存失败。')
    } finally {
      setSavingId('')
    }
  }

  const handleCreate = async () => {
    if (!newMember.user_id.trim()) {
      setError(isEnglish ? 'Please enter a user ID first.' : '请先填写用户 ID。')
      return
    }
    setSavingId('new-member')
    setStatusMessage('')
    setError('')
    try {
      await updateAdminMembership(
        newMember.user_id.trim(),
        {
          email: newMember.email.trim() || null,
          tier: newMember.tier,
          status: newMember.status,
          note: newMember.note.trim() || null,
          expires_at: newMember.expires_at || null,
        },
        accessToken,
      )
      setNewMember(DEFAULT_NEW_MEMBER)
      await loadData()
      setStatusMessage(isEnglish ? 'New member access record created.' : '已创建新的会员权限记录。')
    } catch {
      setError(isEnglish ? 'Failed to create the member record.' : '新会员记录创建失败。')
    } finally {
      setSavingId('')
    }
  }

  if (!isAuthenticated) {
    return (
      <div className="page-shell py-12">
        <div className="fudan-panel p-10 text-center">
          <div className="mx-auto inline-flex rounded-full bg-emerald-50 p-4 text-emerald-700">
            <Shield size={24} />
          </div>
          <div className="section-kicker mt-6">{isEnglish ? 'Admin Access' : '管理员入口'}</div>
          <h1 className="font-serif text-4xl font-black text-fudan-blue">{isEnglish ? 'Sign in to open membership administration' : '登录后进入会员管理'}</h1>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-8 text-slate-600">
            {isEnglish
              ? 'Membership administration is available only to admin accounts. Sign in first to review member status, roles, and expiry dates.'
              : '会员管理仅对管理员开放。请先登录，再查看会员状态、角色和到期时间。'}
          </p>
          <button
            type="button"
            onClick={openAuthDialog}
            className="mt-8 inline-flex items-center gap-2 rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-fudan-dark"
          >
            {authEnabled ? (isEnglish ? 'Sign in' : '立即登录') : isEnglish ? 'Sign-in unavailable' : '登录暂不可用'}
          </button>
        </div>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="page-shell py-12">
        <div className="fudan-panel p-10 text-center">
          <div className="mx-auto inline-flex rounded-full bg-amber-50 p-4 text-amber-700">
            <Shield size={24} />
          </div>
          <div className="section-kicker mt-6">{isEnglish ? 'Permission' : '权限提示'}</div>
          <h1 className="font-serif text-4xl font-black text-fudan-blue">{isEnglish ? 'This account is not an admin account' : '当前账号不是管理员'}</h1>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-8 text-slate-600">
            {isEnglish
              ? `Current role: ${membership?.tier_label || 'Member'}. Only admins can review and update membership access here.`
              : `当前身份：${membership?.tier_label || '普通用户'}。只有管理员可以在这里查看和更新会员权限。`}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(16,185,129,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Admin Console' : '管理台'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{isEnglish ? 'Membership administration' : '会员管理'}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'Review roles, update account status, add notes, and keep member access aligned with the product rules.'
                : '查看角色、更新账号状态、补充备注，并让会员访问权限与产品规则保持一致。'}
            </p>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Current role' : '当前身份'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{membership?.tier_label || (isEnglish ? 'Admin' : '管理员')}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">{membership?.email || (isEnglish ? 'Admin account' : '管理员账号')}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Total members' : '会员总数'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{data.total}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish ? 'Covers all member records returned by the current query.' : '按当前查询条件返回的会员记录总数。'}
              </div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{isEnglish ? 'Editable fields' : '可编辑字段'}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{isEnglish ? 'Tier / Status / Notes' : '等级 / 状态 / 备注'}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">
                {isEnglish ? 'Update tier, status, expiry date, and admin notes directly from this page.' : '可直接更新等级、状态、到期时间和后台备注。'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {statusMessage ? <div className="mt-6 text-sm text-emerald-700">{statusMessage}</div> : null}

      <section className="mt-8 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <aside className="space-y-6">
          <div className="fudan-panel p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="section-kicker">{isEnglish ? 'Role counts' : '分层统计'}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{isEnglish ? 'Membership structure' : '会员结构'}</h2>
              </div>
              <button
                type="button"
                onClick={() => loadData().catch(() => {})}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
              >
                <RefreshCcw size={16} />
                {isEnglish ? 'Refresh' : '刷新'}
              </button>
            </div>
            <div className="mt-5 space-y-3">
              {(data.counts || []).map((item) => (
                <div key={item.tier} className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                  <div className="font-serif text-2xl font-black text-fudan-blue">{item.total}</div>
                  <div className="mt-2 text-sm leading-7 text-slate-600">{item.tier_label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'New record' : '新建记录'}</div>
            <div className="space-y-3">
              <input
                value={newMember.user_id}
                onChange={(event) => setNewMember((current) => ({ ...current, user_id: event.target.value }))}
                placeholder={isEnglish ? 'User ID' : '用户 ID'}
                className="w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <input
                value={newMember.email}
                onChange={(event) => setNewMember((current) => ({ ...current, email: event.target.value }))}
                placeholder={isEnglish ? 'Email' : '邮箱'}
                className="w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <div className="grid gap-3 md:grid-cols-2">
                <select
                  value={newMember.tier}
                  onChange={(event) => setNewMember((current) => ({ ...current, tier: event.target.value }))}
                  className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                >
                  {TIER_OPTIONS.map((tier) => (
                    <option key={tier} value={tier}>
                      {tierLabel(tier, isEnglish)}
                    </option>
                  ))}
                </select>
                <select
                  value={newMember.status}
                  onChange={(event) => setNewMember((current) => ({ ...current, status: event.target.value }))}
                  className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {statusLabel(status, isEnglish)}
                    </option>
                  ))}
                </select>
              </div>
              <input
                type="date"
                value={newMember.expires_at}
                onChange={(event) => setNewMember((current) => ({ ...current, expires_at: event.target.value }))}
                className="w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <textarea
                rows={4}
                value={newMember.note}
                onChange={(event) => setNewMember((current) => ({ ...current, note: event.target.value }))}
                placeholder={isEnglish ? 'Admin note' : '备注'}
                className="w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
              />
              <button
                type="button"
                onClick={handleCreate}
                disabled={savingId === 'new-member'}
                className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Plus size={16} />
                {isEnglish ? 'Create record' : '创建记录'}
              </button>
            </div>
          </div>
        </aside>

        <section className="fudan-panel p-8">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="section-kicker">{isEnglish ? 'Member list' : '会员列表'}</div>
              <h2 className="section-title">{isEnglish ? 'Review and update access' : '查看并更新访问权限'}</h2>
            </div>
            <div className="flex gap-3">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={isEnglish ? 'Search user ID / email / note' : '搜索用户 ID / 邮箱 / 备注'}
                className="rounded-full border border-slate-200 bg-white px-4 py-3 text-sm outline-none"
              />
              <button
                type="button"
                onClick={() => loadData().catch(() => {})}
                className="rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
              >
                {isEnglish ? 'Search' : '搜索'}
              </button>
            </div>
          </div>

          <div className="mt-6 space-y-4">
            {loading ? (
              <div className="rounded-[1.4rem] border border-dashed border-slate-300 p-6 text-sm text-slate-500">
                {isEnglish ? 'Loading member records...' : '正在加载会员记录...'}
              </div>
            ) : (
              (data.items || []).map((item) => {
                const draft = drafts[item.user_id] || {}
                return (
                  <div key={item.user_id} className="rounded-[1.4rem] border border-slate-200/70 bg-white p-5">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div>
                        <div className="inline-flex items-center gap-2 text-sm font-semibold text-fudan-blue">
                          <UserRound size={16} />
                          {item.user_id}
                        </div>
                        <div className="mt-2 text-sm leading-7 text-slate-500">{item.email || (isEnglish ? 'No email' : '未填写邮箱')}</div>
                        <div className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                          {isEnglish ? 'Created at' : '创建于'} {item.created_at.replace('T', ' ').slice(0, 16)}
                        </div>
                      </div>

                      <div className="grid flex-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                        <select
                          value={draft.tier || item.tier}
                          onChange={(event) => handleDraftChange(item.user_id, 'tier', event.target.value)}
                          className="rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                        >
                          {TIER_OPTIONS.map((tier) => (
                            <option key={tier} value={tier}>
                              {tierLabel(tier, isEnglish)}
                            </option>
                          ))}
                        </select>
                        <select
                          value={draft.status || item.status}
                          onChange={(event) => handleDraftChange(item.user_id, 'status', event.target.value)}
                          className="rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                        >
                          {STATUS_OPTIONS.map((status) => (
                            <option key={status} value={status}>
                              {statusLabel(status, isEnglish)}
                            </option>
                          ))}
                        </select>
                        <input
                          type="date"
                          value={draft.expires_at || ''}
                          onChange={(event) => handleDraftChange(item.user_id, 'expires_at', event.target.value)}
                          className="rounded-[1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => handleSave(item.user_id)}
                          disabled={savingId === item.user_id}
                          className="inline-flex items-center justify-center gap-2 rounded-[1rem] bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <Save size={16} />
                          {isEnglish ? 'Save' : '保存'}
                        </button>
                      </div>
                    </div>

                    <textarea
                      rows={3}
                      value={draft.note || ''}
                      onChange={(event) => handleDraftChange(item.user_id, 'note', event.target.value)}
                      placeholder={isEnglish ? 'Admin note' : '备注'}
                      className="mt-4 w-full rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                    />
                  </div>
                )
              })
            )}
          </div>
        </section>
      </section>
    </div>
  )
}

export default AdminMembershipsPage
