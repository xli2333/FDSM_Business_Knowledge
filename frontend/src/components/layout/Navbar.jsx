import {
  Crown,
  Film,
  Headphones,
  LogIn,
  LogOut,
  MessageSquare,
  PenTool,
  Search,
  Shield,
  Sparkles,
  UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext.js'
import { useLanguage } from '../../i18n/LanguageContext.js'
import { getRoleExperience, resolveRoleTier } from '../../lib/roleExperience.js'

const TIER_LABELS = {
  zh: {
    guest: '访客',
    free_member: '免费会员',
    paid_member: '付费会员',
    admin: '管理员',
  },
  en: {
    guest: 'Guest',
    free_member: 'Free Member',
    paid_member: 'Paid Member',
    admin: 'Admin',
  },
}

const MEMBERSHIP_STYLES = {
  guest: 'border border-slate-200 bg-white text-slate-500',
  free_member: 'border border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue',
  paid_member: 'border border-fudan-orange/25 bg-fudan-orange/10 text-fudan-orange',
  admin: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
}

function LanguageSwitch() {
  const { language, setLanguage, t } = useLanguage()

  return (
    <div className="inline-flex items-center rounded-full border border-slate-200 bg-white p-1 shadow-sm">
      <button
        type="button"
        onClick={() => setLanguage('zh')}
        className={[
          'rounded-full px-3 py-1.5 text-xs font-bold tracking-[0.16em] transition',
          language === 'zh' ? 'bg-fudan-blue text-white' : 'text-slate-500',
        ].join(' ')}
      >
        {t('navbar.languageZh')}
      </button>
      <button
        type="button"
        onClick={() => setLanguage('en')}
        className={[
          'rounded-full px-3 py-1.5 text-xs font-bold tracking-[0.16em] transition',
          language === 'en' ? 'bg-fudan-blue text-white' : 'text-slate-500',
        ].join(' ')}
      >
        {t('navbar.languageEn')}
      </button>
    </div>
  )
}

function Navbar() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const { t, language } = useLanguage()
  const {
    authEnabled,
    isAuthenticated,
    membership,
    businessProfile,
    roleHomePath,
    isAdmin,
    signOut,
    user,
    canUseAiAssistant,
  } = useAuth()

  const isEnglish = language === 'en'
  const roleTier = resolveRoleTier({ membership, isAuthenticated })
  const roleExperience = getRoleExperience(roleTier, isEnglish)
  const defaultSearchMode = membership?.can_access_paid || isAdmin ? 'smart' : 'exact'
  const discoveryNavItems = [
    { label: isEnglish ? 'Topic Square' : '专题广场', to: '/topics' },
    { label: isEnglish ? 'Deep Insights' : '深度洞察', to: '/column/insights' },
    { label: isEnglish ? 'Industry Watch' : '行业观察', to: '/column/industry' },
    { label: isEnglish ? 'Research Frontiers' : '学术前沿', to: '/column/research' },
    { label: isEnglish ? "Dean's View" : '院长说', to: '/column/deans-view' },
  ]
  const navItems = [...roleExperience.navLinks.map((item) => (item.to === '/topics' ? { ...item, label: isEnglish ? 'Topic Square' : '专题广场' } : item)), ...discoveryNavItems].filter(
    (item, index, items) => items.findIndex((candidate) => candidate.to === item.to) === index,
  )
  const roleHomeTarget = isAuthenticated ? (roleHomePath && roleHomePath !== '/' ? roleHomePath : roleExperience.entryPath) : '/login'

  const desktopActionItems = isAdmin
    ? [
        { label: isEnglish ? 'Admin' : '管理总览', to: '/admin', icon: Shield, className: 'border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100' },
        ...(canUseAiAssistant
          ? [{ label: isEnglish ? 'AI Assistant' : 'AI 助理', to: '/chat', icon: MessageSquare, className: 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15' }]
          : []),
        { label: isEnglish ? 'Editorial' : '文章后台', to: '/editorial', icon: PenTool, className: 'border border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue hover:bg-fudan-blue/15' },
        { label: isEnglish ? 'Media Studio' : '媒体后台', to: '/media-studio', icon: Film, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
        { label: isEnglish ? 'Leads' : '销售线索', to: '/commercial/leads', icon: Sparkles, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
      ]
    : roleTier === 'paid_member'
      ? [
          { label: isEnglish ? 'Membership' : '会员空间', to: '/membership', icon: Crown, className: 'border border-fudan-orange/25 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15' },
          ...(canUseAiAssistant
            ? [{ label: isEnglish ? 'AI Assistant' : 'AI 助理', to: '/chat', icon: MessageSquare, className: 'border border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue hover:bg-fudan-blue/15' }]
            : []),
          { label: isEnglish ? 'Audio' : '音频', to: '/audio', icon: Headphones, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
          { label: isEnglish ? 'Video' : '视频', to: '/video', icon: Film, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
          { label: isEnglish ? 'My Library' : '我的资产', to: '/me', icon: UserRound, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
        ]
      : roleTier === 'free_member'
        ? [
            { label: isEnglish ? 'My Library' : '我的资产', to: '/me', icon: UserRound, className: 'border border-fudan-blue/20 bg-fudan-blue/10 text-fudan-blue hover:bg-fudan-blue/15' },
            { label: isEnglish ? 'Following' : '我的关注', to: '/following', icon: Sparkles, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
            { label: isEnglish ? 'Video' : '视频', to: '/video', icon: Film, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
            { label: isEnglish ? 'Upgrade' : '升级会员', to: '/membership', icon: Crown, className: 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15' },
            { label: isEnglish ? 'Commercial' : '商业方案', to: '/commercial', icon: Sparkles, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
          ]
        : [
            { label: isEnglish ? 'Login' : '登录中心', to: '/login', icon: LogIn, className: 'border border-fudan-blue/15 bg-fudan-blue text-white hover:bg-fudan-dark' },
            { label: isEnglish ? 'Membership' : '会员方案', to: '/membership', icon: UserRound, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
            { label: isEnglish ? 'Audio' : '音频', to: '/audio', icon: Headphones, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
            { label: isEnglish ? 'Video' : '视频', to: '/video', icon: Film, className: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30' },
          ]

  const mobileActionItems = desktopActionItems.map((item) => ({ label: item.label, to: item.to }))
  const mobileNavItems = [...navItems, ...mobileActionItems].filter((item, index, items) => items.findIndex((candidate) => candidate.to === item.to) === index)
  const membershipClass = MEMBERSHIP_STYLES[membership?.tier] || MEMBERSHIP_STYLES.guest
  const membershipLabel = TIER_LABELS[language]?.[membership?.tier] || TIER_LABELS[language]?.guest || membership?.tier_label
  const roleHomeLabel = isAuthenticated ? roleExperience.entryLabel : isEnglish ? 'Login' : '登录中心'

  const handleSubmit = (event) => {
    event.preventDefault()
    if (!query.trim()) return
    navigate(`/search?q=${encodeURIComponent(query.trim())}&mode=${defaultSearchMode}`)
  }

  const authLabel = isAuthenticated ? t('navbar.signOut') : authEnabled ? t('navbar.signIn') : t('navbar.signIn')

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/88 backdrop-blur-xl">
      <div className="page-shell py-4">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <Link to="/" className="flex min-w-0 items-center gap-4">
              <img src="/mainpage_logo.png" alt={t('appName')} className="h-12 w-auto shrink-0" />
              <div className="min-w-0">
                <div className="truncate font-serif text-lg font-black text-fudan-blue sm:text-xl">{t('appName')}</div>
                <div className="truncate text-[11px] uppercase tracking-[0.28em] text-slate-400">
                  {isAuthenticated ? `${businessProfile?.display_name || ''} / ${membershipLabel}` : t('appSubtitle')}
                </div>
              </div>
            </Link>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <LanguageSwitch />

              <Link to={isAuthenticated ? roleHomeTarget : '/membership'} className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold ${membershipClass}`}>
                <UserRound size={16} />
                {membershipLabel}
              </Link>

              <button
                type="button"
                onClick={() => {
                  if (isAuthenticated) {
                    signOut()
                    return
                  }
                  navigate('/login')
                }}
                className={[
                  'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition',
                  isAuthenticated
                    ? 'border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                    : 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
                ].join(' ')}
              >
                {isAuthenticated ? <LogOut size={16} /> : <LogIn size={16} />}
                <span className="hidden sm:inline">{isAuthenticated ? user?.email || t('navbar.signOut') : authLabel}</span>
                <span className="sm:hidden">{isAuthenticated ? t('navbar.signOut') : t('navbar.signIn')}</span>
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <form
              onSubmit={handleSubmit}
              className="flex w-full items-center gap-3 rounded-[1.25rem] border border-slate-200 bg-white px-4 py-3 shadow-[0_12px_40px_rgba(15,23,42,0.05)] xl:max-w-xl"
            >
              <Search size={18} className="shrink-0 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t('navbar.searchPlaceholder')}
                className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
              />
            </form>

            <div className="hidden flex-wrap items-center justify-end gap-2 xl:flex">
              {desktopActionItems.map((item) => {
                const Icon = item.icon
                return (
                  <Link
                    key={`desktop-${item.to}`}
                    to={item.to}
                    className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${item.className}`}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                )
              })}

              <Link
                to={roleHomeTarget}
                className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
              >
                {roleHomeLabel}
              </Link>
            </div>
          </div>

          <nav className="hidden flex-wrap items-center gap-x-5 gap-y-2 xl:flex">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  ['text-sm font-semibold tracking-[0.08em] transition', isActive ? 'text-fudan-blue' : 'text-slate-500 hover:text-fudan-blue'].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="xl:hidden">
            <nav className="flex gap-3 overflow-x-auto pb-1">
              {mobileNavItems.map((item) => (
                <NavLink
                  key={`mobile-${item.to}`}
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      'whitespace-nowrap rounded-full border px-4 py-2 text-sm font-semibold transition',
                      isActive ? 'border-fudan-blue bg-fudan-blue text-white' : 'border-slate-200 bg-white text-slate-500',
                    ].join(' ')
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>
      </div>
    </header>
  )
}

export default Navbar
