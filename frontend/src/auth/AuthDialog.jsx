import { LockKeyhole, Mail, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from './AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function AuthDialog({ open, onClose, onSubmit, loading, authEnabled }) {
  const { isEnglish, t } = useLanguage()
  const { authError } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  if (!open) return null

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!email.trim() || !password.trim()) return
    try {
      await onSubmit({ email: email.trim(), password })
    } catch {
      // The auth provider owns the error state rendered below.
    }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/40 px-4 backdrop-blur-sm">
      <div className="fudan-panel w-full max-w-lg p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="section-kicker">{t('navbar.signIn')}</div>
            <h2 className="font-serif text-3xl font-black text-fudan-blue">{isEnglish ? 'Sign in to continue' : '登录后继续'}</h2>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              {isEnglish
                ? 'Use your email and password to keep bookmarks, likes, reading history, and member access in one account.'
                : '使用邮箱和密码登录后，你的收藏、点赞、阅读历史和会员权限都会保留在同一个账号里。'}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate-200 p-2 text-slate-500 transition hover:bg-slate-50"
            aria-label={isEnglish ? 'Close sign-in dialog' : '关闭登录弹窗'}
          >
            <X size={16} />
          </button>
        </div>

        <div className="mt-5 rounded-[1.25rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">
          {isEnglish ? 'Stay on this page to sign in quickly, or open the full login page if you prefer.' : '你可以直接在当前页面完成登录，也可以进入完整登录页。'}
          <div className="mt-3">
            <Link to="/login" onClick={onClose} className="font-semibold text-fudan-blue transition hover:text-fudan-dark">
              {isEnglish ? 'Open full login page' : '进入完整登录页'}
            </Link>
          </div>
        </div>

        {authEnabled ? (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block">
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{isEnglish ? 'Email' : '邮箱'}</div>
              <div className="flex items-center gap-3 rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-3">
                <Mail size={16} className="text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-transparent text-sm outline-none"
                  autoFocus
                  required
                />
              </div>
            </label>

            <label className="block">
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{isEnglish ? 'Password' : '密码'}</div>
              <div className="flex items-center gap-3 rounded-[1.25rem] border border-slate-200 bg-slate-50 px-4 py-3">
                <LockKeyhole size={16} className="text-slate-400" />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={isEnglish ? 'Enter password' : '输入密码'}
                  className="w-full bg-transparent text-sm outline-none"
                  required
                />
              </div>
            </label>

            {authError ? <div className="text-sm text-rose-600">{authError}</div> : null}

            <button
              type="submit"
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-6 py-3 text-sm font-semibold tracking-[0.16em] text-white transition hover:bg-fudan-dark disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (isEnglish ? 'Signing in...' : '登录中...') : isEnglish ? 'Sign in' : '登录'}
            </button>
          </form>
        ) : (
          <div className="mt-6 rounded-[1.4rem] border border-dashed border-slate-300 bg-slate-50 p-5 text-sm leading-7 text-slate-500">
            {isEnglish ? 'Sign-in is unavailable at the moment. Please try again later.' : '登录暂不可用，请稍后再试。'}
          </div>
        )}
      </div>
    </div>
  )
}

export default AuthDialog
