import { ArrowRight, LockKeyhole, Mail } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'
import { getRoleExperience, resolveRoleTier } from '../lib/roleExperience.js'

const ROLE_PANEL_CLASSES = {
  guest: 'border border-slate-200/70 bg-slate-50 text-slate-600',
  free_member: 'border border-fudan-blue/20 bg-fudan-blue/5 text-fudan-blue',
  paid_member: 'border border-fudan-orange/25 bg-fudan-orange/10 text-fudan-orange',
  admin: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
}

function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { isEnglish } = useLanguage()
  const {
    authEnabled,
    isAuthenticated,
    loading,
    roleHomePath,
    membership,
    businessProfile,
    signInWithPassword,
    signOut,
    authError,
  } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const redirect = searchParams.get('redirect') || ''

  const currentTier = resolveRoleTier({ membership, isAuthenticated })
  const currentExperience = getRoleExperience(currentTier, isEnglish)

  const surfaceCards = useMemo(
    () =>
      isEnglish
        ? [
            {
              eyebrow: 'Access',
              title: 'One sign-in for reading, membership, and admin access',
              body: 'The same account can take you into personal reading, member access, or admin tools when your role allows it.',
            },
            {
              eyebrow: 'Continuity',
              title: 'Return to the page you wanted',
              body: 'If a protected page sends you here, the platform remembers that destination and takes you back after sign-in.',
            },
            {
              eyebrow: 'Guest access',
              title: 'Public reading stays open',
              body: 'Public articles, topics, and organization pages remain available even before you sign in.',
            },
          ]
        : [
            {
              eyebrow: '访问',
              title: '一个登录入口，覆盖阅读、会员与管理权限',
              body: '同一个账号可以进入个人阅读、会员访问，或在具备权限时进入后台管理工具。',
            },
            {
              eyebrow: '延续',
              title: '回到你原本要去的页面',
              body: '如果你是从受保护页面跳转到这里，登录后系统会自动带你回去。',
            },
            {
              eyebrow: '访客浏览',
              title: '公开阅读继续开放',
              body: '公开文章、专题和机构页在登录前也可以继续浏览。',
            },
          ],
    [isEnglish],
  )

  useEffect(() => {
    if (!loading && isAuthenticated) {
      const targetPath =
        redirect || (roleHomePath && roleHomePath !== '/' ? roleHomePath : currentExperience.entryPath) || '/'
      navigate(targetPath, { replace: true })
    }
  }, [currentExperience.entryPath, isAuthenticated, loading, navigate, redirect, roleHomePath])

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password.trim()) return
    setSubmitting(true)
    try {
      await signInWithPassword({ email: email.trim(), password })
    } catch {
      // Error state is already stored in the auth provider.
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-shell py-10 md:py-12">
      <section className="grid gap-6 xl:grid-cols-[1.04fr_0.96fr]">
        <div className="fudan-panel overflow-hidden">
          <div className="bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.84)_56%,rgba(234,107,0,0.24))] px-7 py-10 text-white md:px-10 md:py-12">
            <div className="section-kicker !text-white/70">{isEnglish ? 'Login' : '登录'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">
              {isEnglish ? 'Sign in to Fudan Business Knowledge Base' : '登录复旦商业知识库'}
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">
              {isEnglish
                ? 'Continue reading, keep your bookmarks, and enter the page that matches your account after sign-in.'
                : '登录后继续阅读、保留你的收藏，并进入与你账号权限匹配的页面。'}
            </p>
          </div>

          <div className="grid gap-4 p-7 md:grid-cols-3 md:p-10">
            {surfaceCards.map((item) => (
              <div key={item.title} className="rounded-[1.35rem] border border-slate-200/70 bg-slate-50 p-5">
                <div className="text-xs uppercase tracking-[0.18em] text-fudan-orange">{item.eyebrow}</div>
                <div className="mt-3 font-serif text-2xl font-black text-fudan-blue">{item.title}</div>
                <div className="mt-3 text-sm leading-7 text-slate-600">{item.body}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <div className="fudan-panel p-7 md:p-8">
            <div className="section-kicker">{isEnglish ? 'Sign in' : '登录'}</div>
            <h2 className="font-serif text-3xl font-black text-fudan-blue">
              {isAuthenticated ? businessProfile?.display_name || currentExperience.label : isEnglish ? 'Account login' : '账号登录'}
            </h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">
              {isAuthenticated
                ? businessProfile?.bio ||
                  (isEnglish
                    ? 'You are already signed in. Continue to your home page or switch to another account.'
                    : '你已经登录。可以继续进入你的首页，或切换到其他账号。')
                : isEnglish
                  ? 'Enter your email and password. After sign-in, the platform sends you to the right page for your account.'
                  : '请输入邮箱和密码。登录后，平台会带你进入与你账号匹配的页面。'}
            </p>

            {isAuthenticated ? (
              <div className="mt-6 space-y-4">
                <div className={`rounded-[1.35rem] px-5 py-4 ${ROLE_PANEL_CLASSES[currentTier] || ROLE_PANEL_CLASSES.guest}`}>
                  <div className="text-xs uppercase tracking-[0.18em] text-current/75">{isEnglish ? 'Home page' : '默认首页'}</div>
                  <div className="mt-3 font-serif text-3xl font-black">{currentExperience.label}</div>
                  <div className="mt-2 text-sm leading-7 text-current/80">{redirect || roleHomePath || currentExperience.entryPath || '/'}</div>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link
                    to={redirect || roleHomePath || currentExperience.entryPath || '/'}
                    className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
                  >
                    {isEnglish ? 'Continue' : '继续进入'}
                    <ArrowRight size={16} />
                  </Link>
                  <button
                    type="button"
                    onClick={signOut}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
                  >
                    {isEnglish ? 'Switch account' : '切换账号'}
                  </button>
                </div>
              </div>
            ) : authEnabled ? (
              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <label className="block">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {isEnglish ? 'Email' : '邮箱'}
                  </div>
                  <div className="flex items-center gap-3 rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-4">
                    <Mail size={16} className="text-slate-400" />
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      placeholder="you@example.com"
                      className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
                      required
                    />
                  </div>
                </label>

                <label className="block">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {isEnglish ? 'Password' : '密码'}
                  </div>
                  <div className="flex items-center gap-3 rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-4">
                    <LockKeyhole size={16} className="text-slate-400" />
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      placeholder={isEnglish ? 'Enter password' : '输入密码'}
                      className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"
                      required
                    />
                  </div>
                </label>

                {authError ? <div className="text-sm text-rose-600">{authError}</div> : null}

                <button
                  type="submit"
                  disabled={submitting}
                  className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submitting ? (isEnglish ? 'Signing in...' : '登录中...') : isEnglish ? 'Sign in' : '登录'}
                  <ArrowRight size={16} />
                </button>
              </form>
            ) : (
              <div className="mt-6 rounded-[1.3rem] border border-dashed border-slate-300 bg-slate-50 p-5 text-sm leading-7 text-slate-600">
                {isEnglish ? 'Sign-in is unavailable at the moment. Please try again later.' : '登录暂不可用，请稍后再试。'}
              </div>
            )}
          </div>

          <div className="fudan-panel p-7 md:p-8">
            <div className="section-kicker">{isEnglish ? 'Guest access' : '访客入口'}</div>
            <h2 className="font-serif text-3xl font-black text-fudan-blue">{isEnglish ? 'Browse as guest' : '先以访客身份浏览'}</h2>
            <p className="mt-4 text-sm leading-7 text-slate-600">
              {isEnglish
                ? 'Public articles, topics, and organization pages remain open. Sign in only when you need personal assets, member access, or admin tools.'
                : '公开文章、专题和机构页继续开放。只有在需要个人资产、会员访问或后台工具时才需要登录。'}
            </p>
            <Link
              to="/"
              className="mt-6 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-600 transition hover:border-fudan-blue/30"
            >
              <LockKeyhole size={16} />
              {isEnglish ? 'Continue as guest' : '以访客身份继续'}
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}

export default LoginPage
