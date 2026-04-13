function textByLanguage(isEnglish, zh, en) {
  return isEnglish ? en : zh
}

const ROLE_DATA = {
  guest: {
    label: { zh: '访客', en: 'Guest' },
    heroKicker: { zh: '访客', en: 'Guest' },
    heroTitle: { zh: '先读公开内容，再决定是否登录', en: 'Start with public reading, then sign in when needed' },
    heroBody: {
      zh: '公开文章、专题、音频和视频都可先浏览。需要收藏、会员访问或后台能力时再登录。',
      en: 'Public articles, topics, audio, and video are available right away. Sign in when you need saved assets, member access, or admin tools.',
    },
    entryLabel: { zh: '进入登录中心', en: 'Open login center' },
    entryPath: '/login',
    statCards: [
      {
        label: { zh: '公开内容', en: 'Public content' },
        value: { zh: '文章 / 专题 / 媒体', en: 'Articles / Topics / Media' },
        detail: { zh: '先从公开阅读与公开媒体入口开始。', en: 'Start with public reading and public media.' },
      },
      {
        label: { zh: '升级路径', en: 'Upgrade path' },
        value: { zh: '免费 -> 付费', en: 'Free -> Paid' },
        detail: { zh: '登录后可沉淀资产，并按需升级。', en: 'Sign in to build your library, then upgrade when needed.' },
      },
      {
        label: { zh: '媒体入口', en: 'Media entry' },
        value: { zh: '音频 / 视频', en: 'Audio / Video' },
        detail: { zh: '音频与视频页面都继续保留。', en: 'Both audio and video pages stay online.' },
      },
    ],
    quickActions: [
      {
        label: { zh: '公开首页', en: 'Public home' },
        path: '/',
        tone: 'primary',
        description: { zh: '继续浏览公开文章、专题和精选内容。', en: 'Continue through public articles, topics, and featured content.' },
      },
      {
        label: { zh: '会员方案', en: 'Membership plans' },
        path: '/membership',
        tone: 'secondary',
        description: { zh: '查看免费、付费与管理员权限差异。', en: 'Compare free, paid, and admin access.' },
      },
      {
        label: { zh: '统一搜索', en: 'Unified search' },
        path: '/search?q=AI&mode=exact',
        tone: 'plain',
        description: { zh: '从主题、人物和概念进入知识库。', en: 'Enter the knowledge base through topics, people, and concepts.' },
      },
    ],
    navLinks: [
      { label: { zh: '首页', en: 'Home' }, to: '/' },
      { label: { zh: '会员', en: 'Membership' }, to: '/membership' },
      { label: { zh: '音频', en: 'Audio' }, to: '/audio' },
      { label: { zh: '视频', en: 'Video' }, to: '/video' },
      { label: { zh: '专题', en: 'Topics' }, to: '/topics' },
      { label: { zh: '机构', en: 'Organizations' }, to: '/organizations' },
      { label: { zh: '时光机', en: 'Time Machine' }, to: '/time-machine' },
    ],
  },
  free_member: {
    label: { zh: '免费会员', en: 'Free Member' },
    heroKicker: { zh: '免费会员', en: 'Free Member' },
    heroTitle: { zh: '把收藏、关注和升级路径放在一起', en: 'Keep your library, follows, and upgrade path together' },
    heroBody: {
      zh: '免费会员可保留收藏、点赞、历史和关注，并继续使用音频视频预览入口。',
      en: 'Free members keep bookmarks, likes, history, and follows while continuing into audio and video previews.',
    },
    entryLabel: { zh: '进入我的资产', en: 'Open my library' },
    entryPath: '/me',
    statCards: [
      {
        label: { zh: '收藏', en: 'Bookmarks' },
        value: { zh: '长期清单', en: 'Reading list' },
        detail: { zh: '把值得反复阅读的内容留在清单里。', en: 'Keep important content in a durable list.' },
      },
      {
        label: { zh: '关注信号', en: 'Signals' },
        value: { zh: '点赞 / 关注', en: 'Likes / Follows' },
        detail: { zh: '系统会按你的偏好继续组织阅读。', en: 'The product keeps shaping your reading around your interests.' },
      },
      {
        label: { zh: '媒体', en: 'Media' },
        value: { zh: '音频 / 视频', en: 'Audio / Video' },
        detail: { zh: '继续访问公开媒体与预览入口。', en: 'Continue into public media and preview entry points.' },
      },
    ],
    quickActions: [
      {
        label: { zh: '我的资产', en: 'My library' },
        path: '/me',
        tone: 'primary',
        description: { zh: '查看收藏、点赞、历史和个人概览。', en: 'Open bookmarks, likes, history, and your account overview.' },
      },
      {
        label: { zh: '我的关注', en: 'Following' },
        path: '/following',
        tone: 'secondary',
        description: { zh: '沿着已关注的主题和标签继续阅读。', en: 'Continue through followed topics and tags.' },
      },
      {
        label: { zh: '升级会员', en: 'Upgrade to paid' },
        path: '/membership',
        tone: 'plain',
        description: { zh: '解锁更深层的付费文章与媒体。', en: 'Unlock deeper paid articles and media.' },
      },
    ],
    navLinks: [
      { label: { zh: '首页', en: 'Home' }, to: '/' },
      { label: { zh: '我的资产', en: 'My Library' }, to: '/me' },
      { label: { zh: '我的关注', en: 'Following' }, to: '/following' },
      { label: { zh: '会员', en: 'Membership' }, to: '/membership' },
      { label: { zh: '音频', en: 'Audio' }, to: '/audio' },
      { label: { zh: '视频', en: 'Video' }, to: '/video' },
      { label: { zh: '专题', en: 'Topics' }, to: '/topics' },
    ],
  },
  paid_member: {
    label: { zh: '付费会员', en: 'Paid Member' },
    heroKicker: { zh: '付费会员', en: 'Paid Member' },
    heroTitle: { zh: '从完整文章、音频和视频权益开始', en: 'Start with full articles, audio, and video access' },
    heroBody: {
      zh: '付费会员可直接访问完整文章、付费音频、付费视频和更深层的会员内容。',
      en: 'Paid members can go straight into full articles, paid audio, paid video, and deeper member content.',
    },
    entryLabel: { zh: '进入会员空间', en: 'Open membership' },
    entryPath: '/membership',
    statCards: [
      {
        label: { zh: '完整文章', en: 'Full articles' },
        value: { zh: '完整访问', en: 'Full access' },
        detail: { zh: '不再受试看边界影响。', en: 'Read without preview limits.' },
      },
      {
        label: { zh: '会员媒体', en: 'Member media' },
        value: { zh: '音频 / 视频', en: 'Audio / Video' },
        detail: { zh: '公开、会员、付费媒体在同一系统内持续更新。', en: 'Public, member, and paid media stay in one live system.' },
      },
      {
        label: { zh: '个人资产', en: 'My library' },
        value: { zh: '持续沉淀', en: 'Keep building' },
        detail: { zh: '听完或看完后继续回到收藏与历史。', en: 'Return to bookmarks and history after listening or watching.' },
      },
    ],
    quickActions: [
      {
        label: { zh: '会员权益', en: 'Member benefits' },
        path: '/membership',
        tone: 'primary',
        description: { zh: '查看当前等级、订阅状态和已解锁权益。', en: 'Review your tier, subscription state, and unlocked benefits.' },
      },
      {
        label: { zh: '音频页面', en: 'Audio hub' },
        path: '/audio',
        tone: 'secondary',
        description: { zh: '进入完整音频流与预览入口。', en: 'Open the full audio stream and preview entry.' },
      },
      {
        label: { zh: '视频页面', en: 'Video hub' },
        path: '/video',
        tone: 'plain',
        description: { zh: '进入公开、试看与会员视频页面。', en: 'Open public, preview, and member video.' },
      },
    ],
    navLinks: [
      { label: { zh: '首页', en: 'Home' }, to: '/' },
      { label: { zh: '会员', en: 'Membership' }, to: '/membership' },
      { label: { zh: '音频', en: 'Audio' }, to: '/audio' },
      { label: { zh: '视频', en: 'Video' }, to: '/video' },
      { label: { zh: '我的资产', en: 'My Library' }, to: '/me' },
      { label: { zh: '我的关注', en: 'Following' }, to: '/following' },
    ],
  },
  admin: {
    label: { zh: '管理员', en: 'Admin' },
    heroKicker: { zh: '管理员', en: 'Admin' },
    heroTitle: { zh: '在一个控制台里管理会员、文章与媒体', en: 'Run memberships, editorial, and media from one console' },
    heroBody: {
      zh: '管理员登录后直接进入内容与权限运营：会员管理、文章工作台、媒体后台和商务线索都在这里收口。',
      en: 'Admins land directly on membership management, the editorial workbench, the media studio, and lead operations.',
    },
    entryLabel: { zh: '进入管理控制台', en: 'Open admin console' },
    entryPath: '/admin',
    statCards: [
      {
        label: { zh: '成员', en: 'Members' },
        value: { zh: '角色 / 等级', en: 'Roles / Tiers' },
        detail: { zh: '确认不同身份落在正确页面与权限层。', en: 'Make sure each role lands on the right page and access layer.' },
      },
      {
        label: { zh: '内容', en: 'Content' },
        value: { zh: '文章 / 媒体', en: 'Editorial / Media' },
        detail: { zh: '继续处理上传、排版、预览、发布和媒体上传。', en: 'Continue through upload, formatting, preview, publishing, and media upload.' },
      },
      {
        label: { zh: '审计', en: 'Audit' },
        value: { zh: '操作记录', en: 'Activity logs' },
        detail: { zh: '最近的角色调整和后台操作都应可追踪。', en: 'Keep recent role changes and admin actions traceable.' },
      },
    ],
    quickActions: [
      {
        label: { zh: '管理总览', en: 'Admin overview' },
        path: '/admin',
        tone: 'primary',
        description: { zh: '查看角色分布、最近用户和管理动态。', en: 'Open role distribution, recent users, and admin activity.' },
      },
      {
        label: { zh: '会员管理', en: 'Membership admin' },
        path: '/admin/memberships',
        tone: 'secondary',
        description: { zh: '调整用户等级、状态和到期时间。', en: 'Adjust tiers, statuses, and expiry dates.' },
      },
      {
        label: { zh: '内容分析', en: 'Analytics' },
        path: '/analytics',
        tone: 'plain',
        description: { zh: '查看浏览、点赞、收藏与趋势分析。', en: 'Review views, likes, bookmarks, and trend analytics.' },
      },
      {
        label: { zh: '文章后台', en: 'Editorial' },
        path: '/editorial',
        tone: 'plain',
        description: { zh: '进入上传、改稿、一键排版、预览和发布流程。', en: 'Enter upload, rewrite, auto-format, preview, and publishing workflows.' },
      },
      {
        label: { zh: '媒体后台', en: 'Media Studio' },
        path: '/media-studio',
        tone: 'plain',
        description: { zh: '进入音频/视频上传、试看上传与媒体权限管理。', en: 'Enter audio/video upload, preview upload, and media permission control.' },
      },
      {
        label: { zh: '销售线索', en: 'Leads' },
        path: '/commercial/leads',
        tone: 'plain',
        description: { zh: '查看商务线索与跟进状态。', en: 'Review commercial leads and follow-up progress.' },
      },
    ],
    navLinks: [
      { label: { zh: '管理总览', en: 'Admin' }, to: '/admin' },
      { label: { zh: '会员管理', en: 'Memberships' }, to: '/admin/memberships' },
      { label: { zh: '内容分析', en: 'Analytics' }, to: '/analytics' },
      { label: { zh: '文章后台', en: 'Editorial' }, to: '/editorial' },
      { label: { zh: '媒体后台', en: 'Media Studio' }, to: '/media-studio' },
      { label: { zh: '销售线索', en: 'Leads' }, to: '/commercial/leads' },
      { label: { zh: '前台首页', en: 'Front site' }, to: '/' },
    ],
  },
}

export function resolveRoleTier({ membership, isAuthenticated = false } = {}) {
  if (!isAuthenticated) return 'guest'
  const tier = (membership?.tier || '').trim()
  if (tier === 'admin' || tier === 'paid_member' || tier === 'free_member') return tier
  return 'free_member'
}

export function getRoleExperience(tier, isEnglish = false) {
  const safeTier = ROLE_DATA[tier] ? tier : 'guest'
  const source = ROLE_DATA[safeTier]
  return {
    tier: safeTier,
    label: textByLanguage(isEnglish, source.label.zh, source.label.en),
    heroKicker: textByLanguage(isEnglish, source.heroKicker.zh, source.heroKicker.en),
    heroTitle: textByLanguage(isEnglish, source.heroTitle.zh, source.heroTitle.en),
    heroBody: textByLanguage(isEnglish, source.heroBody.zh, source.heroBody.en),
    entryLabel: textByLanguage(isEnglish, source.entryLabel.zh, source.entryLabel.en),
    entryPath: source.entryPath,
    statCards: source.statCards.map((item) => ({
      label: textByLanguage(isEnglish, item.label.zh, item.label.en),
      value: textByLanguage(isEnglish, item.value.zh, item.value.en),
      detail: textByLanguage(isEnglish, item.detail.zh, item.detail.en),
    })),
    quickActions: source.quickActions.map((item) => ({
      label: textByLanguage(isEnglish, item.label.zh, item.label.en),
      path: item.path,
      tone: item.tone,
      description: textByLanguage(isEnglish, item.description.zh, item.description.en),
    })),
    navLinks: source.navLinks.map((item) => ({
      label: textByLanguage(isEnglish, item.label.zh, item.label.en),
      to: item.to,
    })),
  }
}
