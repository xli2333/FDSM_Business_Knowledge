import { ArrowRight, CalendarDays, CheckCircle2, CreditCard, FileText, Headphones, Shield, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { createBillingCheckoutIntent, fetchBillingPlans, fetchBillingProfile, fetchMyDashboard } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'
import { getRoleExperience, resolveRoleTier } from '../lib/roleExperience.js'

const ACTION_CLASSES = {
  primary: 'border border-fudan-blue/15 bg-fudan-blue text-white hover:bg-fudan-dark',
  secondary: 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15',
  plain: 'border border-slate-200 bg-white text-slate-600 hover:border-fudan-blue/30',
}

const PERIOD_COPY = {
  month: { zh: '月付', en: 'month' },
  quarter: { zh: '季付', en: 'quarter' },
  year: { zh: '年付', en: 'year' },
  oneoff: { zh: '一次性', en: 'one-off' },
}

const TIER_COPY = {
  guest: { zh: '访客', en: 'Guest' },
  free_member: { zh: '免费会员', en: 'Free Member' },
  paid_member: { zh: '付费会员', en: 'Paid Member' },
  admin: { zh: '管理员', en: 'Admin' },
}

const STATUS_COPY = {
  anonymous: { zh: '未登录', en: 'Not signed in' },
  active: { zh: '有效', en: 'Active' },
  trial: { zh: '试用中', en: 'Trial' },
  paused: { zh: '已暂停', en: 'Paused' },
  expired: { zh: '已过期', en: 'Expired' },
}

const ORDER_STATUS_COPY = {
  disabled: { zh: '待开通', en: 'Disabled' },
  pending: { zh: '待支付', en: 'Pending' },
  paid: { zh: '已支付', en: 'Paid' },
  failed: { zh: '失败', en: 'Failed' },
  cancelled: { zh: '已取消', en: 'Cancelled' },
}

const ENGLISH_BENEFITS = {
  free_member: [
    'Keep likes, bookmarks, and reading history in one member profile.',
    'Open the member audio shelf at the foundational level.',
    'Build a personal knowledge trail before deciding whether to upgrade.',
  ],
  paid_member: [
    'Open paid articles, premium audio, and in-depth member content.',
    'Use the membership layer for topic briefings, closed-door notes, and course-style reading.',
    'Support higher-value knowledge services and recurring subscription operations.',
  ],
  admin: [
    'Manage membership tiers, statuses, and renewal context from the admin side.',
    'Review the full member roster and recent billing signals in one workflow.',
    'Extend the system toward topic operations, publishing, and commercial management.',
  ],
}

function byLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

function formatPrice(plan, isEnglish) {
  if (!plan) return ''
  if (!plan.price_cents) return byLanguage(isEnglish, '免费', 'Free')
  const amount = (plan.price_cents / 100).toLocaleString('en-US')
  const periodLabel = PERIOD_COPY[plan.billing_period]?.[isEnglish ? 'en' : 'zh'] || plan.billing_period_label || plan.billing_period
  return `CNY ${amount} / ${periodLabel}`
}

function formatDateTime(value, isEnglish) {
  if (!value) return byLanguage(isEnglish, '长期有效', 'No expiry')
  return value.replace('T', ' ').slice(0, 16)
}

function translateTier(tier, isEnglish) {
  return TIER_COPY[tier]?.[isEnglish ? 'en' : 'zh'] || tier || byLanguage(isEnglish, '访客', 'Guest')
}

function translateStatus(status, isEnglish) {
  return STATUS_COPY[status]?.[isEnglish ? 'en' : 'zh'] || status || byLanguage(isEnglish, '未知', 'Unknown')
}

function translateOrderStatus(status, isEnglish) {
  return ORDER_STATUS_COPY[status]?.[isEnglish ? 'en' : 'zh'] || status || byLanguage(isEnglish, '未知', 'Unknown')
}

function MembershipPage() {
  const { authEnabled, backendAuthEnabled, isAuthenticated, membership, isAdmin, isPaidMember, canUseAiAssistant, openAuthDialog, accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [planPayload, setPlanPayload] = useState(null)
  const [billingPayload, setBillingPayload] = useState(null)
  const [assetDashboard, setAssetDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [checkoutBusy, setCheckoutBusy] = useState('')
  const [checkoutMessage, setCheckoutMessage] = useState('')
  const [error, setError] = useState('')

  const roleTier = resolveRoleTier({ membership, isAuthenticated })
  const roleExperience = useMemo(() => getRoleExperience(roleTier, isEnglish), [isEnglish, roleTier])

  useEffect(() => {
    let mounted = true
    async function load() {
      setLoading(true)
      setError('')
      try {
        const language = isEnglish ? 'en' : 'zh'
        const [plans, billing, dashboard] = await Promise.all([
          fetchBillingPlans(language),
          fetchBillingProfile(accessToken, language),
          isAuthenticated ? fetchMyDashboard(accessToken).catch(() => null) : Promise.resolve(null),
        ])
        if (!mounted) return
        setPlanPayload(plans)
        setBillingPayload(billing)
        setAssetDashboard(dashboard)
      } catch {
        if (!mounted) return
        setError(byLanguage(isEnglish, '会员与账单信息加载失败。', 'Failed to load membership and billing data.'))
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load().catch(() => {})
    return () => {
      mounted = false
    }
  }, [accessToken, isAuthenticated, isEnglish])

  const currentMembership = billingPayload?.membership || membership || {}
  const currentTier = currentMembership.tier || membership?.tier || 'guest'
  const currentTierDisplay = translateTier(currentTier, isEnglish)
  const currentStatusDisplay = translateStatus(currentMembership.status, isEnglish)
  const activeSubscription = billingPayload?.active_subscription || null
  const recentOrders = billingPayload?.recent_orders || []
  const paymentsEnabled = Boolean(planPayload?.payments_enabled)
  const paymentProvider = planPayload?.payment_provider || 'mock'
  const paymentProviderLabel = paymentProvider === 'mock' ? byLanguage(isEnglish, '方案确认', 'Plan review') : paymentProvider
  const canLogin = authEnabled || backendAuthEnabled
  const benefits = useMemo(() => {
    if (!isEnglish) return currentMembership.benefits || []
    return ENGLISH_BENEFITS[currentTier] || []
  }, [currentMembership.benefits, currentTier, isEnglish])
  const showMarketplace = currentTier === 'guest'
  const showMemberWorkspace = currentTier !== 'guest'

  const featuredPlans = useMemo(() => (planPayload?.items || []).filter((plan) => ['free_member', 'paid_member'].includes(plan.tier)).sort((a, b) => a.sort_order - b.sort_order), [planPayload])
  const paidPlans = useMemo(() => (planPayload?.items || []).filter((plan) => plan.tier === 'paid_member').sort((a, b) => a.sort_order - b.sort_order), [planPayload])

  const handleCheckout = async (planCode) => {
    setCheckoutMessage('')
    setError('')
    if (!isAuthenticated) {
      openAuthDialog()
      return
    }
    setCheckoutBusy(planCode)
    try {
      const result = await createBillingCheckoutIntent({ plan_code: planCode, success_url: `${window.location.origin}/membership`, cancel_url: `${window.location.origin}/membership` }, accessToken)
      setCheckoutMessage(
        result.payments_enabled
          ? byLanguage(isEnglish, '正在跳转到支付页面。', 'Opening the payment page.')
          : byLanguage(isEnglish, '已记录本次方案选择，当前环境尚未开启真实支付。', 'Your plan choice has been recorded. Online payment is not enabled in this environment yet.'),
      )
      if (result.checkout_url && result.payments_enabled) {
        window.location.href = result.checkout_url
        return
      }
      const latest = await fetchBillingProfile(accessToken, isEnglish ? 'en' : 'zh')
      setBillingPayload(latest)
    } catch (requestError) {
      if (requestError?.status === 401) {
        openAuthDialog()
        return
      }
      setError(byLanguage(isEnglish, '无法开始当前方案操作。', 'Failed to start the selected plan action.'))
    } finally {
      setCheckoutBusy('')
    }
  }

  const statusCards = [
    {
      label: byLanguage(isEnglish, '当前身份', 'Current role'),
      value: currentTierDisplay,
      detail: isAuthenticated
        ? byLanguage(isEnglish, '会员页会按当前身份切换内容。', 'This page adapts to your current role.')
        : byLanguage(isEnglish, '登录后会自动切换到对应视图。', 'Sign in to switch into the matching member view.'),
    },
    {
      label: byLanguage(isEnglish, '访问范围', 'Access scope'),
      value: isPaidMember
        ? byLanguage(isEnglish, '付费访问', 'Paid access')
        : currentMembership?.can_access_member
          ? byLanguage(isEnglish, '会员访问', 'Member access')
          : byLanguage(isEnglish, '公开访问', 'Public access'),
      detail: byLanguage(
        isEnglish,
        '文章、音频与 AI 能力会按当前身份解锁。',
        'Articles, audio, and AI features unlock according to your current role.',
      ),
    },
    {
      label: byLanguage(isEnglish, '订阅状态', 'Subscription state'),
      value: activeSubscription ? activeSubscription.plan_name || activeSubscription.plan_code : currentStatusDisplay,
      detail: activeSubscription
        ? byLanguage(isEnglish, `状态：${translateStatus(activeSubscription.status, isEnglish)}`, `Status: ${translateStatus(activeSubscription.status, isEnglish)}`)
        : paymentsEnabled
          ? byLanguage(isEnglish, '当前环境支持创建订阅与订单记录。', 'This environment can create subscription and order records.')
          : byLanguage(isEnglish, '当前环境仍以方案确认与账单记录为主。', 'This environment currently focuses on plan review and billing records.'),
    },
  ]

  const memberWorkspaceActions = useMemo(() => {
    if (currentTier === 'free_member') {
      return [
        {
          label: byLanguage(isEnglish, '我的资料库', 'My library'),
          path: '/me',
          tone: 'primary',
          icon: UserRound,
          description: byLanguage(isEnglish, '继续查看收藏、点赞与阅读历史。', 'Open bookmarks, likes, and reading history.'),
        },
        {
          label: byLanguage(isEnglish, '我的关注', 'Following'),
          path: '/following',
          tone: 'secondary',
          icon: Sparkles,
          description: byLanguage(isEnglish, '沿着已关注的标签和专题继续阅读。', 'Continue through followed tags and topics.'),
        },
        {
          label: byLanguage(isEnglish, '音频栏目', 'Audio hub'),
          path: '/audio',
          tone: 'plain',
          icon: Headphones,
          description: byLanguage(isEnglish, '进入会员可访问的音频内容。', 'Open the audio content available to your tier.'),
        },
      ]
    }

    if (currentTier === 'paid_member') {
      return [
        {
          label: byLanguage(isEnglish, '会员音频', 'Member audio'),
          path: '/audio',
          tone: 'primary',
          icon: Headphones,
          description: byLanguage(isEnglish, '直接进入完整音频流，不再停留在旧的四条音频入口。', 'Go straight into the full audio stream instead of the old four-track entry.'),
        },
        {
          label: byLanguage(isEnglish, '我的资料库', 'My library'),
          path: '/me',
          tone: 'secondary',
          icon: UserRound,
          description: byLanguage(isEnglish, '回到收藏、点赞和阅读历史。', 'Return to bookmarks, likes, and reading history.'),
        },
        {
          label: canUseAiAssistant ? byLanguage(isEnglish, 'AI 助理', 'AI assistant') : byLanguage(isEnglish, '我的关注', 'Following'),
          path: canUseAiAssistant ? '/chat' : '/following',
          tone: 'plain',
          icon: Sparkles,
          description: canUseAiAssistant
            ? byLanguage(isEnglish, '继续使用已解锁的 AI 助理能力。', 'Continue with the unlocked AI assistant.')
            : byLanguage(isEnglish, '沿着已关注的主题和标签继续阅读。', 'Continue through the topics and tags you follow.'),
        },
      ]
    }

    if (currentTier === 'admin') {
      return [
        {
          label: byLanguage(isEnglish, '管理总览', 'Admin overview'),
          path: '/admin',
          tone: 'primary',
          icon: Shield,
          description: byLanguage(isEnglish, '查看角色分布、最近用户和管理动作。', 'Open role distribution, recent users, and admin activity.'),
        },
        {
          label: byLanguage(isEnglish, '会员管理', 'Membership admin'),
          path: '/admin/memberships',
          tone: 'secondary',
          icon: UserRound,
          description: byLanguage(isEnglish, '调整用户等级、状态与到期时间。', 'Adjust tiers, statuses, and expiry dates.'),
        },
        {
          label: byLanguage(isEnglish, '编辑后台', 'Editorial'),
          path: '/editorial',
          tone: 'plain',
          icon: FileText,
          description: byLanguage(isEnglish, '继续处理内容审核与发布流程。', 'Continue editorial review and publishing workflows.'),
        },
      ]
    }

    return roleExperience.quickActions.map((item) => ({ ...item, icon: Sparkles }))
  }, [canUseAiAssistant, currentTier, isEnglish, roleExperience.quickActions])

  const memberAssetLinks = useMemo(() => {
    if (!['free_member', 'paid_member'].includes(currentTier)) return []
    const summary = assetDashboard?.asset_summary || {}
    return [
      {
        key: 'bookmarks',
        label: byLanguage(isEnglish, '我的收藏', 'My bookmarks'),
        path: '/me?tab=bookmarks',
        value: summary.bookmark_count ?? 0,
        description: byLanguage(isEnglish, '打开收藏文章流，并继续点回文章详情。', 'Open your bookmarked article flow and jump back into any article.'),
      },
      {
        key: 'likes',
        label: byLanguage(isEnglish, '我的点赞', 'My likes'),
        path: '/me?tab=likes',
        value: summary.like_count ?? 0,
        description: byLanguage(isEnglish, '查看你认可过的文章，并继续回到原文。', 'Review the articles you endorsed and return to the original story.'),
      },
      {
        key: 'history',
        label: byLanguage(isEnglish, '阅读历史', 'Reading history'),
        path: '/me?tab=history',
        value: summary.recent_view_count ?? 0,
        description: byLanguage(isEnglish, '回到最近看过的文章流，继续阅读。', 'Return to your recent reading flow and continue where you left off.'),
      },
    ]
  }, [assetDashboard, currentTier, isEnglish])

  const memberWorkspaceTitle =
    currentTier === 'free_member'
      ? byLanguage(isEnglish, '已开通的会员权益', 'Your unlocked member benefits')
      : currentTier === 'paid_member'
        ? byLanguage(isEnglish, '已解锁的付费权益', 'Your unlocked paid-member benefits')
        : byLanguage(isEnglish, '当前管理权限与入口', 'Your current admin access and tools')

  const memberWorkspaceBody =
    currentTier === 'free_member'
      ? byLanguage(
          isEnglish,
          '你已经是免费会员，会员页不再重复展示整屏售卖方案，而是直接给你可用权益、入口和升级动作。',
          'You are already a free member, so this page now skips the full sales layout and goes straight to your unlocked access, entry points, and upgrade actions.',
        )
      : currentTier === 'paid_member'
        ? byLanguage(
            isEnglish,
            '你已经拥有付费访问权限，这里优先展示已解锁内容、订阅状态和账单记录。',
            'You already have paid access, so this page now focuses on unlocked content, subscription state, and billing records.',
          )
        : byLanguage(
            isEnglish,
            '当前账号以管理员权限进入会员页，这里集中放置权限范围、账单背景和管理入口。',
            'This account enters the membership page with admin access, so the page now concentrates admin scope, billing context, and management tools.',
          )

  const managementTitle =
    currentTier === 'admin' ? byLanguage(isEnglish, '管理权限与账单背景', 'Admin access and billing context') : byLanguage(isEnglish, '管理订阅', 'Manage subscription')

  const managementBody =
    currentTier === 'free_member'
      ? byLanguage(
          isEnglish,
          '免费会员不再看到大块方案售卖区；如需升级，这里直接给你当前状态、账单记录和升级动作。',
          'Free members no longer see a large sales-first plan grid. This panel concentrates your current state, billing context, and upgrade actions.',
        )
      : currentTier === 'paid_member'
        ? byLanguage(
            isEnglish,
            '把当前方案、状态、账单记录和续费/切换动作收拢到一个区域，避免会员页再次退化成售卖页。',
            'This area consolidates the current plan, status, billing history, and renewal or switch actions, instead of turning the page back into a sales layout.',
          )
        : byLanguage(
            isEnglish,
            '管理员权限通常不是通过公开方案售卖获得，因此这里展示管理入口和账单背景，而不是普通订阅动作。',
            'Admin access is usually not managed through public plan sales, so this area surfaces management actions and billing context rather than standard subscription buttons.',
          )

  const subscriptionSummaryRows = [
    {
      label: byLanguage(isEnglish, '当前方案', 'Current plan'),
      value:
        activeSubscription?.plan_name ||
        (currentTier === 'paid_member'
          ? byLanguage(isEnglish, '付费会员权益', 'Paid member access')
          : currentTier === 'free_member'
            ? byLanguage(isEnglish, '免费会员', 'Free member')
            : byLanguage(isEnglish, '管理员权限', 'Admin access')),
    },
    { label: byLanguage(isEnglish, '状态', 'Status'), value: activeSubscription ? translateStatus(activeSubscription.status, isEnglish) : currentStatusDisplay },
    { label: byLanguage(isEnglish, '开始时间', 'Started at'), value: formatDateTime(activeSubscription?.started_at || currentMembership.started_at, isEnglish) },
    { label: byLanguage(isEnglish, '到期时间', 'Expires at'), value: formatDateTime(activeSubscription?.expires_at || currentMembership.expires_at, isEnglish) },
    { label: byLanguage(isEnglish, '支付环境', 'Payment path'), value: paymentProviderLabel },
    { label: byLanguage(isEnglish, '账单记录', 'Billing records'), value: byLanguage(isEnglish, `${recentOrders.length} 条`, `${recentOrders.length} records`) },
  ]

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.88)_58%,rgba(234,107,0,0.26))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{roleExperience.heroKicker}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{roleExperience.heroTitle}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{roleExperience.heroBody}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={openAuthDialog}
                className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
              >
                <Sparkles size={16} />
                {isAuthenticated
                  ? byLanguage(isEnglish, '切换账号', 'Switch account')
                  : canLogin
                    ? byLanguage(isEnglish, '立即登录', 'Sign in now')
                    : byLanguage(isEnglish, '登录暂不可用', 'Sign-in unavailable')}
              </button>
              <Link
                to="/audio"
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15"
              >
                <Headphones size={16} />
                {byLanguage(isEnglish, '音频栏目', 'Audio hub')}
              </Link>
              <Link
                to={isAdmin ? '/admin/memberships' : canUseAiAssistant ? '/chat' : '/me'}
                className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15"
              >
                {isAdmin ? <Shield size={16} /> : canUseAiAssistant ? <Sparkles size={16} /> : <UserRound size={16} />}
                {isAdmin ? byLanguage(isEnglish, '会员管理', 'Membership admin') : canUseAiAssistant ? byLanguage(isEnglish, 'AI 助理', 'AI assistant') : byLanguage(isEnglish, '我的资料库', 'My library')}
              </Link>
            </div>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            {statusCards.map((item) => (
              <div key={item.label} className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
                <div className="text-xs uppercase tracking-[0.24em] text-white/65">{item.label}</div>
                <div className="mt-3 font-serif text-3xl font-black text-white">{item.value}</div>
                <div className="mt-2 text-sm leading-7 text-white/76">{item.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {checkoutMessage ? <div className="mt-6 text-sm text-emerald-700">{checkoutMessage}</div> : null}

      <section className="mt-8 grid gap-4 md:grid-cols-3">
        {(showMemberWorkspace ? memberWorkspaceActions : roleExperience.quickActions).map((item) => (
          <Link
            key={`${currentTier}-${item.path}-${item.label}`}
            to={item.path}
            className={`rounded-[1.35rem] px-6 py-6 text-left text-sm transition ${ACTION_CLASSES[item.tone] || ACTION_CLASSES.plain}`}
          >
            <div className="font-serif text-2xl font-black">{item.label}</div>
            <div className="mt-4 leading-7 opacity-90">{item.description}</div>
          </Link>
        ))}
      </section>

      {memberAssetLinks.length ? (
        <section className="mt-8">
          <div className="mb-4 flex items-center gap-3">
            <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
              <UserRound size={20} />
            </div>
            <div>
              <div className="section-kicker">{byLanguage(isEnglish, '阅读资产', 'Reading assets')}</div>
              <h2 className="font-serif text-3xl font-black text-fudan-blue">
                {byLanguage(isEnglish, '收藏、点赞和历史都能直接点开', 'Bookmarks, likes, and history open directly')}
              </h2>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {memberAssetLinks.map((item) => (
              <Link
                key={item.key}
                to={item.path}
                className="rounded-[1.35rem] border border-slate-200 bg-white px-6 py-6 text-left transition hover:border-fudan-blue/25 hover:bg-fudan-blue/5"
                data-membership-asset-link={item.key}
              >
                <div className="text-xs uppercase tracking-[0.18em] text-fudan-orange">{item.label}</div>
                <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{item.value}</div>
                <div className="mt-3 text-sm leading-7 text-slate-600">{item.description}</div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {showMarketplace ? (
        <section className="mt-8 grid gap-6 lg:grid-cols-[0.72fr_1.28fr]">
          <div className="fudan-panel p-8">
            <div className="section-kicker">{byLanguage(isEnglish, '订阅说明', 'Subscription details')}</div>
            <h2 className="section-title">{byLanguage(isEnglish, '方案与支付状态', 'Plans and payment status')}</h2>
            <div className="mt-6 space-y-4 text-sm leading-7 text-slate-600">
              <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
                {byLanguage(isEnglish, '访客可以先比较方案，再决定是否登录和订阅。', 'Guests can compare plans first, then decide whether to sign in and subscribe.')}
              </div>
              <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
                {byLanguage(isEnglish, '当前环境会保留方案选择与账单记录，真实支付是否开启取决于支付配置。', 'This environment keeps plan choice and billing records, while real payment depends on the payment configuration.')}
              </div>
              <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-4">
                {byLanguage(isEnglish, '登录后，会员页会自动切换到你的当前权益和订阅管理视图。', 'After sign-in, this page automatically switches to your active benefits and subscription-management view.')}
              </div>
            </div>
            <div className="mt-6 rounded-[1.3rem] border border-dashed border-fudan-orange/40 bg-fudan-orange/5 p-5 text-sm leading-7 text-slate-600">
              {paymentsEnabled
                ? byLanguage(isEnglish, '当前环境已开启在线支付。', 'Online payment is currently enabled.')
                : byLanguage(isEnglish, '当前环境尚未开启真实支付，但可以先查看方案与支付路径。', 'Real payment is not enabled in this environment yet, but you can still review the plans and payment path.')}
            </div>
          </div>

          <div className="fudan-panel p-6 xl:p-8">
            <div className="section-kicker">{byLanguage(isEnglish, '公开方案', 'Public plans')}</div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {loading ? (
                <div className="rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-5 text-sm text-slate-500 md:col-span-2 lg:col-span-3">
                  {byLanguage(isEnglish, '正在读取方案信息...', 'Loading plan information...')}
                </div>
              ) : featuredPlans.length ? (
                featuredPlans.map((plan) => (
                  <div
                    key={plan.plan_code}
                    className={[
                      'flex h-full min-w-0 flex-col rounded-[1.5rem] border p-4 xl:p-5',
                      plan.tier === 'paid_member' ? 'border-fudan-orange/30 bg-fudan-orange/5' : 'border-fudan-blue/20 bg-fudan-blue/5',
                    ].join(' ')}
                  >
                    <div className="font-serif text-[1.55rem] font-black leading-tight text-fudan-blue xl:text-[1.7rem]">{plan.name}</div>
                    <div className="mt-2 text-[11px] uppercase tracking-[0.16em] text-slate-400">{plan.headline}</div>
                    <div
                      className={[
                        'mt-4 whitespace-nowrap font-black leading-none text-fudan-blue',
                        isEnglish
                          ? 'text-[clamp(1.08rem,1.45vw,1.36rem)] tracking-[-0.04em]'
                          : 'text-[clamp(1rem,1.35vw,1.26rem)] tracking-[-0.05em]',
                      ].join(' ')}
                    >
                      {formatPrice(plan, isEnglish)}
                    </div>
                    <div className="mt-3 text-sm leading-6 text-slate-600">{plan.description}</div>
                    <div className="mt-4 flex-1 space-y-3">
                      {plan.features.map((item) => (
                        <div key={item} className="rounded-[1rem] border border-white/70 bg-white/80 px-3 py-3 text-sm leading-6 text-slate-600">
                          {item}
                        </div>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleCheckout(plan.plan_code)}
                      disabled={checkoutBusy === plan.plan_code}
                      className="mt-5 inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <CreditCard size={16} />
                      {checkoutBusy === plan.plan_code
                        ? byLanguage(isEnglish, '处理中...', 'Processing...')
                        : paymentsEnabled
                          ? byLanguage(isEnglish, '继续支付', 'Continue to payment')
                          : byLanguage(isEnglish, '选择此方案', 'Choose this plan')}
                    </button>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-5 text-sm text-slate-500 md:col-span-2 lg:col-span-3">
                  {byLanguage(isEnglish, '当前还没有可展示的公开方案。', 'No public plans are available yet.')}
                </div>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {showMemberWorkspace ? (
        <>
          <section className="mt-8 grid gap-6 lg:grid-cols-[1.02fr_0.98fr]">
            <div className="fudan-panel p-8">
              <div className="section-kicker">{byLanguage(isEnglish, '会员权益', 'Member benefits')}</div>
              <h2 className="section-title">{memberWorkspaceTitle}</h2>
              <p className="mt-4 max-w-3xl text-base leading-8 text-slate-600">{memberWorkspaceBody}</p>

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {benefits.map((item) => (
                  <div key={item} className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-5 text-sm leading-7 text-slate-600">
                    <div className="flex items-start gap-3">
                      <div className="rounded-full bg-fudan-blue/10 p-2 text-fudan-blue">
                        <CheckCircle2 size={18} />
                      </div>
                      <div>{item}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-3">
                {memberWorkspaceActions.map((item) => {
                  const Icon = item.icon || Sparkles
                  return (
                    <Link
                      key={`workspace-${item.path}-${item.label}`}
                      to={item.path}
                      className={`rounded-[1.3rem] px-5 py-5 text-left text-sm transition ${ACTION_CLASSES[item.tone] || ACTION_CLASSES.plain}`}
                    >
                      <div className="flex items-center gap-3">
                        <Icon size={18} />
                        <div className="font-semibold">{item.label}</div>
                      </div>
                      <div className="mt-3 leading-7 opacity-90">{item.description}</div>
                    </Link>
                  )
                })}
              </div>
            </div>

            <div className="fudan-panel p-8">
              <div className="section-kicker">{byLanguage(isEnglish, '订阅操作', 'Subscription controls')}</div>
              <h2 className="section-title">{managementTitle}</h2>
              <p className="mt-4 text-base leading-8 text-slate-600">{managementBody}</p>

              <div className="mt-6 grid gap-3">
                {subscriptionSummaryRows.map((item) => (
                  <div key={item.label} className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-400">{item.label}</div>
                    <div className="mt-2 font-semibold text-fudan-blue">{item.value}</div>
                  </div>
                ))}
              </div>

              {currentTier === 'free_member' || currentTier === 'paid_member' ? (
                <div className="mt-6">
                  <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {currentTier === 'free_member' ? byLanguage(isEnglish, '升级方案', 'Upgrade options') : byLanguage(isEnglish, '续费与切换', 'Renew or switch')}
                  </div>
                  <div className="space-y-3">
                    {paidPlans.map((plan) => (
                      <button
                        key={plan.plan_code}
                        type="button"
                        onClick={() => handleCheckout(plan.plan_code)}
                        disabled={checkoutBusy === plan.plan_code}
                        className="flex w-full items-center justify-between gap-4 rounded-[1.3rem] border border-slate-200 bg-white px-4 py-4 text-left transition hover:border-fudan-blue/30 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <div>
                          <div className="font-semibold text-fudan-blue">{plan.name}</div>
                          <div className="mt-1 text-sm text-slate-500">{formatPrice(plan, isEnglish)}</div>
                        </div>
                        <div className="inline-flex items-center gap-2 text-sm font-semibold text-fudan-orange">
                          {checkoutBusy === plan.plan_code
                            ? byLanguage(isEnglish, '处理中...', 'Processing...')
                            : currentTier === 'free_member'
                              ? byLanguage(isEnglish, '升级到此方案', 'Upgrade to this plan')
                              : byLanguage(isEnglish, '打开此方案', 'Open this plan')}
                          <ArrowRight size={16} />
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              {currentTier === 'admin' ? (
                <div className="mt-6 flex flex-wrap gap-3">
                  <Link
                    to="/admin/memberships"
                    className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-5 py-3 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-100"
                  >
                    <UserRound size={16} />
                    {byLanguage(isEnglish, '会员管理', 'Membership admin')}
                  </Link>
                  <Link
                    to="/commercial/leads"
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/30"
                  >
                    <FileText size={16} />
                    {byLanguage(isEnglish, '账单与线索', 'Billing and leads')}
                  </Link>
                </div>
              ) : null}

              <div className="mt-6 rounded-[1.3rem] border border-slate-200/70 bg-white p-5">
                <div className="flex items-center gap-2 text-sm font-semibold text-fudan-blue">
                  <CalendarDays size={16} />
                  {byLanguage(isEnglish, '最近账单动向', 'Recent billing activity')}
                </div>
                {recentOrders.length ? (
                  <div className="mt-4 space-y-3">
                    {recentOrders.slice(0, 3).map((order) => (
                      <div key={order.id} className="rounded-[1rem] border border-slate-200/70 bg-slate-50 px-4 py-4 text-sm">
                        <div className="flex items-center justify-between gap-3">
                          <div className="font-semibold text-fudan-blue">{order.plan_name || order.plan_code}</div>
                          <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                            {translateOrderStatus(order.status, isEnglish)}
                          </span>
                        </div>
                        <div className="mt-2 text-slate-600">
                          {byLanguage(isEnglish, '金额', 'Amount')}: {(order.amount_cents / 100).toLocaleString('en-US')} / {order.currency}
                        </div>
                        <div className="text-slate-500">{formatDateTime(order.created_at, isEnglish)}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 text-sm leading-7 text-slate-500">
                    {byLanguage(
                      isEnglish,
                      '当前还没有账单记录。后续升级、续费或方案确认后，这里会显示最近动作。',
                      'There is no billing activity yet. Upgrades, renewals, and plan confirmations will appear here.',
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>

          <section id="billing-history" className="mt-12 grid gap-6 lg:grid-cols-[0.96fr_1.04fr]">
            <div className="fudan-panel p-8">
              <div className="section-kicker">{byLanguage(isEnglish, '账户状态', 'Account state')}</div>
              <h2 className="section-title">{byLanguage(isEnglish, '会员与订阅概览', 'Membership and subscription overview')}</h2>
              <div className="mt-6 rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-5 text-sm leading-7 text-slate-600">
                <div>{byLanguage(isEnglish, '会员等级', 'Membership tier')}: {currentTierDisplay}</div>
                <div>{byLanguage(isEnglish, '会员内容访问', 'Member content access')}: {currentMembership?.can_access_member ? byLanguage(isEnglish, '是', 'Yes') : byLanguage(isEnglish, '否', 'No')}</div>
                <div>{byLanguage(isEnglish, '付费内容访问', 'Paid content access')}: {currentMembership?.can_access_paid ? byLanguage(isEnglish, '是', 'Yes') : byLanguage(isEnglish, '否', 'No')}</div>
                <div>{byLanguage(isEnglish, '支付环境', 'Payment environment')}: {paymentsEnabled ? byLanguage(isEnglish, '已开启', 'Enabled') : byLanguage(isEnglish, '暂未开放', 'Not open yet')}</div>
              </div>
              <div className="mt-5 rounded-[1.3rem] border border-slate-200/70 bg-white p-5 text-sm leading-7 text-slate-600">
                {activeSubscription ? (
                  <>
                    <div className="font-semibold text-fudan-blue">{byLanguage(isEnglish, '当前订阅', 'Active subscription')}</div>
                    <div className="mt-2">{byLanguage(isEnglish, '方案', 'Plan')}: {activeSubscription.plan_name || activeSubscription.plan_code}</div>
                    <div>{byLanguage(isEnglish, '状态', 'Status')}: {translateStatus(activeSubscription.status, isEnglish)}</div>
                    <div>{byLanguage(isEnglish, '开始时间', 'Started at')}: {formatDateTime(activeSubscription.started_at, isEnglish)}</div>
                    <div>{byLanguage(isEnglish, '到期时间', 'Expires at')}: {formatDateTime(activeSubscription.expires_at, isEnglish)}</div>
                    <div>{byLanguage(isEnglish, '自动续费', 'Auto renew')}: {activeSubscription.auto_renew ? byLanguage(isEnglish, '已开启', 'On') : byLanguage(isEnglish, '未开启', 'Off')}</div>
                  </>
                ) : (
                  <div>
                    {byLanguage(
                      isEnglish,
                      '账单侧当前没有激活中的订阅记录，但会员访问权限仍以当前身份为准。',
                      'There is no active subscription record in billing right now, but your current role still controls access.',
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="fudan-panel p-8">
              <div className="section-kicker">{byLanguage(isEnglish, '账单记录', 'Billing history')}</div>
              <h2 className="section-title">{byLanguage(isEnglish, '最近订单与支付记录', 'Recent orders and payment records')}</h2>
              <div className="mt-6 space-y-3">
                {recentOrders.length ? (
                  recentOrders.map((order) => (
                    <div key={order.id} className="rounded-[1.3rem] border border-slate-200/70 bg-white p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-semibold text-fudan-blue">{order.plan_name || order.plan_code}</div>
                        <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                          {translateOrderStatus(order.status, isEnglish)}
                        </span>
                      </div>
                      <div className="mt-2 text-sm leading-7 text-slate-600">
                        {byLanguage(isEnglish, '金额', 'Amount')}: {(order.amount_cents / 100).toLocaleString('en-US')} / {order.currency}
                      </div>
                      <div className="text-sm leading-7 text-slate-500">{formatDateTime(order.created_at, isEnglish)}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-5 text-sm text-slate-500">
                    {byLanguage(
                      isEnglish,
                      '当前还没有账单订单记录。后续升级、续费或方案确认后，这里会沉淀完整记录。',
                      'There is no billing history yet. Upgrades, renewals, or plan confirmations will accumulate here.',
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}

export default MembershipPage
