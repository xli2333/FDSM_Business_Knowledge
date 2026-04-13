import { MessageSquare, Send, Sparkles, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import { deleteChatSession, fetchChatSession, fetchChatSessions, sendChatMessage } from '../../api/index.js'
import { useLanguage } from '../../i18n/LanguageContext.js'

const COPY = {
  zh: {
    quickCommands: [
      { label: '\u4eca\u65e5\u4e00\u8bfb', value: '/\u4eca\u65e5\u4e00\u8bfb' },
      { label: 'AI \u7b80\u62a5', value: '/\u7b80\u62a5 AI\u6218\u7565' },
      { label: 'ESG \u603b\u7ed3', value: '/\u603b\u7ed3 ESG\u8f6c\u578b' },
      { label: 'AI \u4e0e ESG', value: '/\u6bd4\u8f83 AI \u4e0e ESG' },
      { label: '\u751f\u6210\u5f0f AI \u65f6\u95f4\u7ebf', value: '/\u65f6\u95f4\u7ebf \u751f\u6210\u5f0fAI' },
      { label: '\u7ee7\u7eed\u9605\u8bfb', value: '/\u7ee7\u7eed\u9605\u8bfb' },
    ],
    greeting:
      '\u53ef\u4ee5\u76f4\u63a5\u63d0\u95ee\uff0c\u4e5f\u53ef\u4ee5\u7528 `/\u7b80\u62a5`\u3001`/\u603b\u7ed3`\u3001`/\u6bd4\u8f83`\u3001`/\u65f6\u95f4\u7ebf`\u3001`/\u4eca\u65e5\u4e00\u8bfb`\u3001`/\u7ee7\u7eed\u9605\u8bfb` \u8fd9\u4e9b\u5feb\u6377\u6307\u4ee4\u76f4\u63a5\u8fdb\u5165\u77e5\u8bc6\u5e93\u5de5\u4f5c\u6d41\u3002',
    errorFallback: '\u672c\u8f6e\u95ee\u7b54\u6682\u672a\u5b8c\u6210\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002',
    sessionManager: '\u4f1a\u8bdd\u7ba1\u7406',
    newSession: '\u65b0\u5efa\u4f1a\u8bdd',
    emptySessions: '\u8fd8\u6ca1\u6709\u5386\u53f2\u4f1a\u8bdd\u3002\u53d1\u9001\u7b2c\u4e00\u6761\u6d88\u606f\u540e\uff0c\u8fd9\u91cc\u4f1a\u81ea\u52a8\u751f\u6210\u8bb0\u5f55\u3002',
    loading: '\u52a0\u8f7d\u4e2d...',
    deleteSession: '\u5220\u9664\u4f1a\u8bdd',
    deleteFailed: '\u4f1a\u8bdd\u5220\u9664\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002',
    assistant: 'AI \u52a9\u7406',
    title: '\u56f4\u7ed5\u77e5\u8bc6\u5e93\u7ee7\u7eed\u63d0\u95ee\u3001\u6bd4\u8f83\u4e0e\u6574\u5408',
    placeholder:
      '\u8f93\u5165\u95ee\u9898\uff0c\u6216\u76f4\u63a5\u4f7f\u7528 /\u7b80\u62a5 /\u603b\u7ed3 /\u6bd4\u8f83 /\u65f6\u95f4\u7ebf /\u4eca\u65e5\u4e00\u8bfb /\u7ee7\u7eed\u9605\u8bfb',
    floatingButton: 'AI \u52a9\u7406',
    followUps: '\u53ef\u7ee7\u7eed\u64cd\u4f5c',
  },
  en: {
    quickCommands: [
      { label: 'Today Read', value: '/today' },
      { label: 'AI Brief', value: '/brief AI strategy' },
      { label: 'ESG Summary', value: '/summarize ESG transition' },
      { label: 'AI vs ESG', value: '/compare AI vs ESG' },
      { label: 'GenAI Timeline', value: '/timeline Generative AI' },
      { label: 'Continue Reading', value: '/recommend' },
    ],
    greeting:
      'Ask directly, or use `/brief`, `/summarize`, `/compare`, `/timeline`, `/today`, and `/recommend` to move faster through the knowledge base.',
    errorFallback: 'The assistant could not finish this round. Please try again later.',
    sessionManager: 'Sessions',
    newSession: 'New Session',
    emptySessions: 'No chat history yet. Your first message will automatically create a session.',
    loading: 'Loading...',
    deleteSession: 'Delete session',
    deleteFailed: 'Failed to delete the session. Please try again.',
    assistant: 'AI Assistant',
    title: 'Ask, compare, and synthesize across the knowledge base',
    placeholder: 'Ask a question, or use /brief /summarize /compare /timeline /today /recommend',
    floatingButton: 'AI Assistant',
    followUps: 'Continue with',
  },
}

function buildGreeting(content) {
  return {
    role: 'assistant',
    content,
    sources: [],
    followUps: [],
  }
}

function ChatPanel({ variant = 'floating' }) {
  const embedded = variant === 'page'
  const { isEnglish } = useLanguage()
  const copy = isEnglish ? COPY.en : COPY.zh

  const [open, setOpen] = useState(embedded)
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([buildGreeting(copy.greeting)])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessions, setSessions] = useState([])
  const [loadingSessionId, setLoadingSessionId] = useState(null)
  const [deletingSessionId, setDeletingSessionId] = useState(null)
  const [sessionError, setSessionError] = useState('')

  useEffect(() => {
    if (embedded) {
      setOpen(true)
    }
  }, [embedded])

  useEffect(() => {
    if (!embedded) return
    fetchChatSessions()
      .then((payload) => {
        setSessions(payload)
        setSessionError('')
      })
      .catch(() => {})
  }, [embedded, sessionId])

  useEffect(() => {
    setMessages((current) => {
      const isDefaultOnly = current.length === 1 && current[0]?.role === 'assistant' && !(current[0]?.sources || []).length
      if (!isDefaultOnly) return current
      if (current[0]?.content === copy.greeting) return current
      return [buildGreeting(copy.greeting)]
    })
  }, [copy.greeting])

  const loadSession = async (targetSessionId) => {
    if (!targetSessionId) return
    setSessionError('')
    setLoadingSessionId(targetSessionId)
    try {
      const payload = await fetchChatSession(targetSessionId)
      const nextMessages = (payload.messages || []).map((message) => ({
        role: message.role,
        content: message.content,
        sources: message.sources || [],
        followUps: message.follow_ups || [],
      }))
      setSessionId(targetSessionId)
      setMessages(nextMessages.length ? nextMessages : [buildGreeting(copy.greeting)])
    } catch {
      // Ignore session load failures in the panel and keep the current session.
    } finally {
      setLoadingSessionId(null)
    }
  }

  const startNewSession = () => {
    setSessionId(null)
    setMessages([buildGreeting(copy.greeting)])
    setInput('')
  }

  const handleDeleteSession = async (targetSessionId) => {
    if (!targetSessionId || deletingSessionId) return
    setDeletingSessionId(targetSessionId)
    setSessionError('')
    try {
      await deleteChatSession(targetSessionId)
      setSessions((current) => current.filter((session) => session.session_id !== targetSessionId))
      if (sessionId === targetSessionId) {
        startNewSession()
      }
    } catch {
      setSessionError(copy.deleteFailed)
    } finally {
      setDeletingSessionId(null)
    }
  }

  const submitMessage = async (rawValue) => {
    const value = rawValue.trim()
    if (!value || loading) return
    const nextMessages = [...messages, { role: 'user', content: value, sources: [], followUps: [] }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    try {
      const payload = await sendChatMessage({
        session_id: sessionId,
        mode: 'precise',
        language: isEnglish ? 'en' : 'zh',
        messages: nextMessages.map(({ role, content }) => ({ role, content })),
      })
      setSessionId(payload.session_id)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: payload.answer,
          sources: payload.sources || [],
          followUps: payload.follow_up_questions || [],
        },
      ])
      if (embedded) {
        fetchChatSessions()
          .then((payload) => {
            setSessions(payload)
            setSessionError('')
          })
          .catch(() => {})
      }
    } catch {
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: copy.errorFallback,
          sources: [],
          followUps: [],
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleSend = async () => {
    await submitMessage(input)
  }

  const handleShortcut = async (value) => {
    setInput(value)
    await submitMessage(value)
  }

  const panelBody = (
    <div className={`fudan-panel flex h-full overflow-hidden ${embedded ? 'min-h-[70vh]' : 'h-[70vh] w-[24rem]'}`}>
      {embedded ? (
        <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-slate-50/80 xl:flex xl:flex-col">
          <div className="border-b border-slate-200 px-5 py-4">
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-fudan-orange">
              <Sparkles size={15} />
              {copy.sessionManager}
            </div>
            <button
              type="button"
              onClick={startNewSession}
              className="mt-4 w-full rounded-full bg-fudan-blue px-4 py-3 text-sm font-semibold text-white transition hover:bg-fudan-dark"
            >
              {copy.newSession}
            </button>
            {sessionError ? <div className="mt-3 text-xs leading-6 text-red-500">{sessionError}</div> : null}
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3">
            {sessions.length === 0 ? (
              <div className="rounded-[1.1rem] border border-dashed border-slate-300 p-4 text-sm leading-7 text-slate-500">
                {copy.emptySessions}
              </div>
            ) : (
              <div className="space-y-2">
                {sessions.map((session) => (
                  <div key={session.session_id} className="relative">
                    <button
                      type="button"
                      onClick={() => loadSession(session.session_id)}
                      className={[
                        'block w-full rounded-[1.1rem] border px-4 py-3 pr-12 text-left transition',
                        sessionId === session.session_id
                          ? 'border-fudan-blue bg-white'
                          : 'border-transparent bg-white/70 hover:border-slate-200',
                      ].join(' ')}
                    >
                      <div className="font-serif text-base font-bold text-fudan-blue">{session.title}</div>
                      <div className="mt-1 line-clamp-2 text-xs leading-6 text-slate-500">{session.last_question}</div>
                      <div className="mt-2 text-[11px] uppercase tracking-[0.2em] text-slate-400">
                        {loadingSessionId === session.session_id ? copy.loading : session.updated_at.replace('T', ' ').slice(0, 16)}
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation()
                        handleDeleteSession(session.session_id)
                      }}
                      disabled={deletingSessionId === session.session_id}
                      className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-400 shadow-sm transition hover:border-red-200 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-50"
                      aria-label={`${copy.deleteSession}: ${session.title}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </aside>
      ) : null}

      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.22em] text-fudan-orange">
              <Sparkles size={16} />
              {copy.assistant}
            </div>
            <div className="mt-1 font-serif text-xl font-bold text-fudan-blue">{copy.title}</div>
          </div>
          {!embedded ? (
            <button type="button" onClick={() => setOpen(false)} className="rounded-full p-2 text-slate-400 hover:bg-slate-100">
              <X size={18} />
            </button>
          ) : null}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={[
                'rounded-[1.4rem] px-4 py-3 text-sm leading-7',
                message.role === 'assistant'
                  ? 'border border-slate-200 bg-slate-50 text-slate-700'
                  : 'ml-10 bg-fudan-blue text-white',
              ].join(' ')}
            >
              <ReactMarkdown>{message.content}</ReactMarkdown>
              {message.sources?.length ? (
                <div className="mt-3 space-y-2 border-t border-slate-200/80 pt-3 text-xs text-slate-500">
                  {message.sources.map((source) => (
                    <Link key={source.id} to={`/article/${source.id}`} className="block hover:text-fudan-blue">
                      [{source.publish_date}] {source.title}
                    </Link>
                  ))}
                </div>
              ) : null}
              {message.role === 'assistant' && message.followUps?.length ? (
                <div className="mt-4 border-t border-slate-200/80 pt-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{copy.followUps}</div>
                  <div className="flex flex-wrap gap-2">
                    {message.followUps.map((followUp) => (
                      <button
                        key={`${index}-${followUp}`}
                        type="button"
                        onClick={() => handleShortcut(followUp)}
                        className="rounded-full bg-white px-3 py-1.5 text-xs text-slate-600 transition hover:border-fudan-blue/20 hover:bg-slate-100 hover:text-fudan-blue"
                      >
                        {followUp}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ))}
        </div>

        <div className="border-t border-slate-200 px-4 py-4">
          <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500">
            {copy.quickCommands.map((command) => (
              <button
                key={`${command.label}-${command.value}`}
                type="button"
                onClick={() => handleShortcut(command.value)}
                className="rounded-full bg-slate-100 px-3 py-1 hover:bg-slate-200"
              >
                {command.label}
              </button>
            ))}
          </div>
          <div className="flex items-end gap-3">
            <textarea
              rows={embedded ? 4 : 3}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={copy.placeholder}
              className="min-h-[88px] flex-1 rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none placeholder:text-slate-400 focus:border-fudan-orange"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={loading}
              className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-fudan-orange text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  if (embedded) {
    return panelBody
  }

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {open ? (
        panelBody
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-3 rounded-full bg-fudan-blue px-5 py-4 text-sm font-semibold tracking-[0.18em] text-white shadow-[0_18px_60px_rgba(13,7,131,0.35)] transition hover:bg-fudan-dark"
        >
          <MessageSquare size={18} />
          {copy.floatingButton}
        </button>
      )}
    </div>
  )
}

export default ChatPanel
