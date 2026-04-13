import { ArrowRight, Shield, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAdminOverview } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'
import { getRoleExperience } from '../lib/roleExperience.js'

const QUICK_ACTIONS = {
  zh: [
    { to: '/admin/memberships', label: '进入会员管理' },
    { to: '/editorial', label: '进入编辑工作台' },
    { to: '/admin/content-ops', label: '进入内容运营后台' },
    { to: '/analytics', label: '进入内容分析' },
    { to: '/media-studio', label: '进入媒体后台' },
    { to: '/commercial/leads', label: '查看商务线索' },
  ],
  en: [
    { to: '/admin/memberships', label: 'Open membership admin' },
    { to: '/editorial', label: 'Open editorial workbench' },
    { to: '/admin/content-ops', label: 'Open content operations' },
    { to: '/analytics', label: 'Open analytics' },
    { to: '/media-studio', label: 'Open media studio' },
    { to: '/commercial/leads', label: 'View commercial leads' },
  ],
}

function AdminConsolePage() {
  const { accessToken, businessProfile } = useAuth()
  const { isEnglish } = useLanguage()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const roleExperience = getRoleExperience('admin', isEnglish)
  const copy = isEnglish
    ? {
        page: 'Admin Console',
        current: 'Current account',
        primary: 'Primary entry',
        primaryBody: 'Admins land here first, then move into content, members, and review work.',
        tasks: 'Main tasks',
        taskValue: 'Members / Content / Review',
        taskBody: 'Use one dashboard to manage content operations, publishing, and member permissions.',
        quick: 'Quick actions',
        roles: 'Role distribution',
        rolesTitle: 'Current member structure',
        audits: 'Recent audits',
        auditsTitle: 'Recent role changes',
        noAudit: 'No audit entries yet.',
        noNote: 'No note',
        recentUsers: 'Recent users',
        recentUsersTitle: 'Recent active profiles',
        openMembership: 'Go to membership admin',
        profileFallback: 'Business profile',
        admin: 'Admin',
      }
    : {
        page: '管理控制台',
        current: '当前账号',
        primary: '主入口',
        primaryBody: '管理员先进入这里，再分流到内容、会员和审核工作。',
        tasks: '主要任务',
        taskValue: '会员 / 内容 / 审核',
        taskBody: '用一个控制台管理内容运营、发布状态和会员权限。',
        quick: '快捷入口',
        roles: '角色分布',
        rolesTitle: '当前会员结构',
        audits: '最近审计',
        auditsTitle: '最近角色变更',
        noAudit: '当前还没有角色变更记录。',
        noNote: '无备注',
        recentUsers: '最近用户',
        recentUsersTitle: '最近活跃的用户档案',
        openMembership: '前往会员管理',
        profileFallback: '业务档案',
        admin: '管理员',
      }

  useEffect(() => {
    fetchAdminOverview(accessToken)
      .then(setData)
      .catch(() => setError(isEnglish ? 'Failed to load the admin overview.' : '管理总览加载失败。'))
  }, [accessToken, isEnglish])

  const quickActions = isEnglish ? QUICK_ACTIONS.en : QUICK_ACTIONS.zh

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.86)_58%,rgba(16,185,129,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.02fr_0.98fr]">
          <div>
            <div className="section-kicker !text-white/72">{copy.page}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{roleExperience.heroTitle}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{roleExperience.heroBody}</p>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{copy.current}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">
                {businessProfile?.display_name || copy.admin}
              </div>
              <div className="mt-2 text-sm leading-7 text-white/76">{businessProfile?.email || businessProfile?.title}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{copy.primary}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{businessProfile?.role_home_path || '/admin'}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">{copy.primaryBody}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="text-xs uppercase tracking-[0.24em] text-white/65">{copy.tasks}</div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{copy.taskValue}</div>
              <div className="mt-2 text-sm leading-7 text-white/76">{copy.taskBody}</div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}

      <section className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {(data?.metrics || []).map((metric) => (
          <div key={metric.label} className="fudan-panel p-6">
            <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{metric.label}</div>
            <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{metric.value}</div>
            <div className="mt-2 text-sm leading-7 text-slate-600">{metric.detail}</div>
          </div>
        ))}
      </section>

      <section className="mt-8 grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-6">
          <div className="fudan-panel p-7">
            <div className="section-kicker">{copy.quick}</div>
            <div className="grid gap-3">
              {quickActions.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="rounded-[1.3rem] border border-slate-200 bg-white px-5 py-4 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/30"
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>

          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
                <UserRound size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.roles}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.rolesTitle}</h2>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {(data?.role_counts || []).map((item) => (
                <div key={item.tier} className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                  <div className="font-serif text-2xl font-black text-fudan-blue">{item.total}</div>
                  <div className="mt-2 text-sm leading-7 text-slate-600">{item.tier_label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-emerald-50 p-3 text-emerald-700">
                <Shield size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.audits}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.auditsTitle}</h2>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {(data?.recent_audits || []).length ? (
                data.recent_audits.map((item) => (
                  <div key={item.id} className="rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                    <div className="font-semibold text-fudan-blue">{item.target_user_id}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">
                      {(item.previous_tier || 'new') + ' / ' + (item.previous_status || 'new')} to {item.next_tier} / {item.next_status}
                    </div>
                    <div className="text-sm leading-7 text-slate-500">
                      {item.note || copy.noNote} / {item.created_at.replace('T', ' ').slice(0, 16)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm text-slate-500">
                  {copy.noAudit}
                </div>
              )}
            </div>
          </div>

          <div className="fudan-panel p-7">
            <div className="section-kicker">{copy.recentUsers}</div>
            <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.recentUsersTitle}</h2>
            <div className="mt-5 space-y-3">
              {(data?.recent_users || []).map((account) => (
                <div key={account.user_id} className="rounded-[1.2rem] border border-slate-200/70 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold text-fudan-blue">{account.display_name}</div>
                      <div className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{account.email || account.user_id}</div>
                    </div>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold text-slate-500">{account.tier_label}</span>
                  </div>
                  <div className="mt-2 text-sm leading-7 text-slate-600">
                    {account.organization || account.title || copy.profileFallback}
                  </div>
                  {account.title ? <div className="text-sm leading-7 text-slate-500">{account.title}</div> : null}
                </div>
              ))}
            </div>
            <Link to="/admin/memberships" className="mt-6 inline-flex items-center gap-2 text-sm font-semibold tracking-[0.16em] text-fudan-orange">
              {copy.openMembership}
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}

export default AdminConsolePage
