import { ArrowRight, BadgeCheck, Building2, CreditCard, Layers3, ShieldCheck, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchBillingPlans, fetchCommerceOverview, submitDemoRequest } from '../api/index.js'
import TagBadge from '../components/shared/TagBadge.jsx'
import { useLanguage } from '../i18n/LanguageContext.js'
import { formatTopicType } from '../utils/formatters.js'

const INITIAL_FORM = {
  name: '',
  organization: '',
  role: '',
  email: '',
  phone: '',
  use_case: '',
  message: '',
}

function CommercialPage() {
  const { isEnglish } = useLanguage()
  const [overview, setOverview] = useState(null)
  const [planPayload, setPlanPayload] = useState(null)
  const [form, setForm] = useState(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([fetchCommerceOverview(), fetchBillingPlans(isEnglish ? 'en' : 'zh')])
      .then(([overviewData, planData]) => {
        setOverview(overviewData)
        setPlanPayload(planData)
      })
      .catch(() => setError(isEnglish ? 'Failed to load the commercial overview.' : '商业页信息加载失败'))
  }, [isEnglish])

  const plans = planPayload?.items || []
  const paidPlan = plans.find((item) => item.tier === 'paid_member')
  const freePlan = plans.find((item) => item.tier === 'free_member')
  const planSummary = {
    paymentsEnabled: Boolean(planPayload?.payments_enabled),
    paidPrice: paidPlan ? `CNY ${(paidPlan.price_cents / 100).toLocaleString('en-US')}` : isEnglish ? 'Not configured' : '未配置',
    freeTier: isEnglish ? 'Free Member' : freePlan?.name || '免费会员',
    planCount: plans.length,
  }

  const handleChange = (event) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setResult(null)
    setError('')
    try {
      const payload = await submitDemoRequest(form)
      setResult(payload)
      setForm(INITIAL_FORM)
    } catch {
      setError(isEnglish ? 'Submission failed. Please review the form and try again.' : '提交失败，请检查信息后重试')
    } finally {
      setSubmitting(false)
    }
  }

  const capabilityCards = isEnglish
    ? [
        ['Institutional Knowledge Hub', 'A unified base for faculty insight, topic planning, knowledge search, and AI support.', <Building2 key="a" size={20} />],
        ['Research & Teaching Support', 'Turn scattered articles into columns, tags, topics, and structured reading paths.', <Layers3 key="b" size={20} />],
        ['Membership Media Service', 'Run search, AI, audio, video, subscriptions, and lead capture in one system.', <Sparkles key="c" size={20} />],
      ]
    : [
        ['机构知识中枢', '统一承接教师观点、专题策划、知识检索和 AI 支持能力。', <Building2 key="a" size={20} />],
        ['研究与教学支持', '把分散文章组织成栏目、标签、专题和结构化阅读路径。', <Layers3 key="b" size={20} />],
        ['会员媒体服务', '在一个系统里管理搜索、AI、音视频、订阅和销售线索。', <Sparkles key="c" size={20} />],
      ]

  const capabilityBullets = isEnglish
    ? [
        'Unified search with filtering, sorting, suggestions, BM25, and vector retrieval.',
        'AI assistant for Q&A, summaries, comparisons, timelines, and recommendations.',
        'Four access levels for guests, free members, paid members, and admins.',
        'Subscription foundation with plans, orders, and payment integration readiness.',
        'Editorial backend for upload, review, HTML rendering, scheduling, and publishing.',
      ]
    : [
        '统一搜索支持筛选、排序、建议词、BM25 和向量检索。',
        'AI 助理支持问答、摘要、比较、时间线整理和相关推荐。',
        '访客、免费会员、付费会员和管理员四层访问体系已经落地。',
        '订阅基础能力已经具备方案、订单和支付接入准备。',
        '编辑后台支持上传、审核、HTML 渲染、定时和发布。',
      ]

  const packageCards = isEnglish
    ? [
        ['Knowledge Base Edition', 'For institution-level content archiving, topic search, and structured browsing.'],
        ['Membership Edition', 'Adds layered access, AI assistant, paywall, audio, video, and subscription readiness.'],
        ['Operations Edition', 'Adds lead management, editorial workflow, experience QA, and analytics.'],
      ]
    : [
        ['知识库版本', '适合机构级内容归档、专题检索和结构化浏览。'],
        ['会员版本', '增加会员分层、AI 助理、付费墙、音视频和订阅能力。'],
        ['运营版本', '增加线索管理、编辑流程、体验质检和运营分析。'],
      ]

  const cooperationBullets = isEnglish
    ? [
        'Suitable for school knowledge platforms, research libraries, brand content hubs, and executive education programs.',
        'Can expand toward premium columns, course products, institution seats, and private deployment.',
        'Submitted information goes directly into the backend so follow-up discussions can begin immediately.',
      ]
    : [
        '适用于院校知识平台、研究资料库、品牌内容中枢和高管教育项目。',
        '可以继续扩展到会员专栏、课程产品、机构席位和私有化部署。',
        '提交的信息会直接写入后台，便于后续商务沟通和跟进。',
      ]

  return (
    <div className="pb-16">
      <section className="page-shell pt-12 md:pt-16">
        <div className="fudan-panel overflow-hidden">
          <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.82)_58%,rgba(234,107,0,0.42))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <div className="section-kicker !text-white/72">Commercial Readiness</div>
              <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
                {isEnglish ? (
                  <>
                    Bring the Fudan business knowledge base
                    <br />
                    into member services and institutional programs
                  </>
                ) : (
                  <>
                    让复旦商业知识库
                    <br />
                    进入会员服务与机构项目
                  </>
                )}
              </h1>
              <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
                {isEnglish
                  ? 'The platform already includes search, AI assistance, layered access, publishing workflows, and a subscription foundation that can support institutional programs.'
                  : '平台已经具备搜索、AI 助理、分层访问、发布工作流和订阅基础能力，可用于承接机构级内容项目。'}
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  to="/search?q=AI&mode=exact"
                  className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold tracking-[0.16em] text-fudan-blue transition hover:bg-slate-100"
                >
                  {isEnglish ? 'See the search experience' : '查看搜索体验'}
                  <ArrowRight size={16} />
                </Link>
                <Link
                  to="/membership"
                  className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15"
                >
                  {isEnglish ? 'View membership & billing' : '查看会员与订阅'}
                </Link>
                <a
                  href="#demo-request"
                  className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-white/15"
                >
                  {isEnglish ? 'Book a demo' : '预约演示'}
                </a>
              </div>
            </div>

            <div className="grid gap-4 self-start md:grid-cols-2 lg:grid-cols-1">
              {(overview?.metrics || []).map((metric) => (
                <div key={metric.label} className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
                  <div className="text-xs uppercase tracking-[0.24em] text-white/65">{metric.label}</div>
                  <div className="mt-3 font-serif text-4xl font-black text-white">{metric.value}</div>
                  <div className="mt-2 text-sm leading-7 text-white/76">{metric.detail}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="page-shell mt-8 text-sm text-red-500">{error}</div> : null}

      <section className="page-shell mt-12">
        <div className="grid gap-6 xl:grid-cols-3">
          {capabilityCards.map(([title, desc, icon]) => (
            <div key={title} className="fudan-card p-6">
              <div className="inline-flex rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">{icon}</div>
              <h2 className="mt-4 font-serif text-2xl font-black text-fudan-blue">{title}</h2>
              <p className="mt-3 text-sm leading-7 text-slate-600">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="page-shell mt-12">
        <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="fudan-panel p-8">
            <div className="section-kicker">Capabilities</div>
            <h2 className="section-title">{isEnglish ? 'A complete platform for structured knowledge publishing' : '面向结构化知识发布的完整平台'}</h2>
            <div className="mt-6 space-y-4">
              {capabilityBullets.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                  <BadgeCheck size={18} className="mt-1 shrink-0 text-fudan-orange" />
                  <div className="text-sm leading-7 text-slate-600">{item}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="fudan-panel p-8">
            <div className="section-kicker">Subscription Foundation</div>
            <div className="space-y-4">
              <div className="rounded-[1.4rem] border border-slate-200/70 bg-white p-5">
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-fudan-orange/10 p-3 text-fudan-orange">
                    <CreditCard size={18} />
                  </div>
                  <div className="font-serif text-2xl font-black text-fudan-blue">
                    {isEnglish ? 'Plans and payment readiness' : '方案与支付准备'}
                  </div>
                </div>
                <div className="mt-4 text-sm leading-7 text-slate-600">
                  {isEnglish
                    ? `Plan count: ${planSummary.planCount}, free tier: ${planSummary.freeTier}, flagship paid plan: ${planSummary.paidPrice}.`
                    : `当前方案数：${planSummary.planCount}，免费层：${planSummary.freeTier}，付费主方案：${planSummary.paidPrice}。`}
                </div>
                <div className="mt-3 text-sm leading-7 text-slate-600">
                  {planSummary.paymentsEnabled
                    ? isEnglish
                      ? 'Online payment can be opened in the current environment.'
                      : '当前环境已经可以开启在线支付。'
                    : isEnglish
                      ? 'The current environment keeps the subscription flow in preview mode before live payment capture is enabled.'
                      : '当前环境会先以预发布方式保留订阅流程，待需要时再开启真实支付。'}
                </div>
              </div>

              {packageCards.map(([title, desc]) => (
                <div key={title} className="rounded-[1.4rem] border border-slate-200/70 bg-white p-5">
                  <div className="font-serif text-2xl font-black text-fudan-blue">{title}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">{desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="page-shell mt-12">
        <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="fudan-panel p-8">
            <div className="section-kicker">Trust Signals</div>
            <h2 className="section-title">{isEnglish ? 'Real data, real content, real operating entry points' : '真实数据、真实内容、真实入口'}</h2>
            <div className="mt-5 flex flex-wrap gap-3">
              {(overview?.hot_tags || []).map((tag) => (
                <TagBadge key={tag.slug} tag={tag} />
              ))}
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-5">
                <div className="text-xs uppercase tracking-[0.24em] text-slate-400">FAISS Index</div>
                <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{overview?.faiss_ready ? 'READY' : 'PENDING'}</div>
                <div className="mt-2 text-sm leading-7 text-slate-600">
                  {isEnglish ? 'The vector index is already connected to the retrieval chain.' : '向量索引已经接入检索链路。'}
                </div>
              </div>
              <div className="rounded-[1.4rem] border border-slate-200/70 bg-slate-50 p-5">
                <div className="text-xs uppercase tracking-[0.24em] text-slate-400">AI Engine</div>
                <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{overview?.ai_ready ? 'ONLINE' : 'OFFLINE'}</div>
                <div className="mt-2 text-sm leading-7 text-slate-600">
                  {isEnglish ? 'Gemini is connected to summaries, chat, query expansion, and reranking.' : 'Gemini 已接入摘要、对话、查询扩展和重排能力。'}
                </div>
              </div>
            </div>
            <div className="mt-6 rounded-[1.4rem] border border-dashed border-slate-300 p-5 text-sm leading-7 text-slate-500">
              {isEnglish ? `Latest data refresh: ${overview?.updated_at || 'Unavailable'}` : `最近一次数据更新时间：${overview?.updated_at || '未读取到'}`}
            </div>
          </div>

          <div className="fudan-panel p-8">
            <div className="section-kicker">Top Topics</div>
            <div className="space-y-4">
              {(overview?.top_topics || []).map((topic) => (
                <Link key={topic.slug} to={`/topic/${topic.slug}`} className="block rounded-[1.4rem] border border-slate-200/70 bg-white p-5 transition hover:bg-slate-50">
                  <div className="text-xs uppercase tracking-[0.24em] text-fudan-orange">{formatTopicType(topic.type)}</div>
                  <div className="mt-3 font-serif text-2xl font-black text-fudan-blue">{topic.title}</div>
                  <div className="mt-3 text-sm leading-7 text-slate-600">{topic.description}</div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="demo-request" className="page-shell mt-12">
        <div className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="fudan-panel p-8">
            <div className="section-kicker">Cooperation</div>
            <h2 className="section-title">{isEnglish ? 'Plan a product demo or partnership conversation' : '预约产品演示或合作沟通'}</h2>
            <div className="mt-5 space-y-4 text-sm leading-7 text-slate-600">
              {cooperationBullets.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4">
                  <ShieldCheck size={18} className="mt-1 shrink-0 text-fudan-orange" />
                  <div>{item}</div>
                </div>
              ))}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="fudan-panel p-8">
            <div className="section-kicker">Demo Request</div>
            <div className="grid gap-4 md:grid-cols-2">
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                placeholder={isEnglish ? 'Name' : '姓名'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                required
              />
              <input
                name="organization"
                value={form.organization}
                onChange={handleChange}
                placeholder={isEnglish ? 'Institution / Company' : '机构 / 公司'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                required
              />
              <input
                name="role"
                value={form.role}
                onChange={handleChange}
                placeholder={isEnglish ? 'Role / Title' : '职位 / 角色'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                required
              />
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                placeholder={isEnglish ? 'Email' : '邮箱'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"
                required
              />
              <input
                name="phone"
                value={form.phone}
                onChange={handleChange}
                placeholder={isEnglish ? 'Phone / WeChat' : '手机 / 微信'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2"
              />
              <input
                name="use_case"
                value={form.use_case}
                onChange={handleChange}
                placeholder={isEnglish ? 'What scenario do you want to use it for?' : '希望用于什么场景？'}
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2"
                required
              />
              <textarea
                name="message"
                rows={5}
                value={form.message}
                onChange={handleChange}
                placeholder={
                  isEnglish
                    ? 'Extra notes, such as target audience, deployment model, and whether private deployment is needed'
                    : '补充说明，例如目标用户、部署方式，以及是否需要私有化部署'
                }
                className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none md:col-span-2"
              />
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-4">
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? (isEnglish ? 'Submitting...' : '提交中...') : isEnglish ? 'Submit demo request' : '提交演示申请'}
              </button>
              {result ? <div className="text-sm text-emerald-700">{isEnglish ? `Submitted. Lead ID #${result.id}` : `已提交，线索编号 #${result.id}`}</div> : null}
              {error ? <div className="text-sm text-red-500">{error}</div> : null}
            </div>
          </form>
        </div>
      </section>
    </div>
  )
}

export default CommercialPage
