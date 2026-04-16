import { LoaderCircle, Send, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { chatWithMyKnowledgeTheme } from '../../api/index.js'
import { useLanguage } from '../../i18n/LanguageContext.js'
import { normalizeChatMarkdown } from '../../lib/chatMarkdown.js'
import AssistantResponseCard from '../shared/AssistantResponseCard.jsx'

function buildGreeting(themeTitle, isEnglish) {
  return {
    role: 'assistant',
    content: normalizeChatMarkdown(
      isEnglish
        ? `This analysis panel works only inside **${themeTitle}**. Responses stay within the articles you selected in this theme.`
        : `这个分析面板只在 **${themeTitle}** 内工作。回答只围绕你当前选中的文章展开。`,
    ),
    sources: [],
    followUps: [],
  }
}

function buildSelectionScopeKey(selectedArticleIds = []) {
  const normalizedIds = [...new Set((selectedArticleIds || []).map((item) => Number(item)).filter((item) => Number.isFinite(item) && item > 0))].sort(
    (left, right) => left - right,
  )
  return normalizedIds.length ? normalizedIds.join('-') : 'none'
}

function storageKey(themeSlug, selectionScopeKey) {
  return `fdsm-knowledge-theme-chat-${themeSlug}-${selectionScopeKey}`
}

function normalizeChatMessage(message, fallbackMessage) {
  if (!message || typeof message !== 'object') return fallbackMessage
  return {
    role: message.role === 'user' ? 'user' : 'assistant',
    content: normalizeChatMarkdown(message.content || fallbackMessage.content),
    sources: Array.isArray(message.sources) ? message.sources : [],
    followUps: Array.isArray(message.followUps) ? message.followUps : [],
  }
}

function loadStoredMessages(themeSlug, selectionScopeKey, fallbackMessage) {
  if (typeof window === 'undefined') return [fallbackMessage]
  try {
    const raw = window.localStorage.getItem(storageKey(themeSlug, selectionScopeKey))
    if (!raw) return [fallbackMessage]
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return [fallbackMessage]
    return parsed.map((message) => normalizeChatMessage(message, fallbackMessage))
  } catch {
    return [fallbackMessage]
  }
}

function saveStoredMessages(themeSlug, selectionScopeKey, messages) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey(themeSlug, selectionScopeKey), JSON.stringify(messages))
  } catch {
    // noop
  }
}

function KnowledgeThemeChatPanel({
  themeSlug,
  themeTitle,
  accessToken = '',
  selectedArticleIds = [],
  totalArticleCount = 0,
}) {
  const { isEnglish } = useLanguage()
  const greeting = useMemo(() => buildGreeting(themeTitle, isEnglish), [isEnglish, themeTitle])
  const selectionScopeKey = useMemo(() => buildSelectionScopeKey(selectedArticleIds), [selectedArticleIds])
  const scrollRef = useRef(null)
  const messageScopeKeyRef = useRef(selectionScopeKey)
  const [messages, setMessages] = useState([greeting])
  const [messageScopeKey, setMessageScopeKey] = useState(selectionScopeKey)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const selectedCount = selectedArticleIds.length
  const hasSelection = selectedCount > 0

  const copy = isEnglish
    ? {
        title: 'AI Analyst',
        body: 'Brief, compare, and synthesize only inside the articles selected from this theme.',
        placeholder: hasSelection ? 'Ask for a brief, contrast, timeline, or decision summary.' : 'Select at least one article on the left before asking AI.',
        quickActions: [
          'Give me a one-page executive brief for the selected articles',
          'Summarize the most important judgment shifts across the selected articles',
          'Build a timeline from the selected articles',
        ],
        send: 'Send',
        loading: 'The analyst is reviewing the selected articles...',
        selectedCount: 'Selected articles',
        analysisLabel: 'Analysis',
        questionLabel: 'Question',
      }
    : {
        title: 'AI 分析师',
        body: '只围绕当前选中的文章做简报、比较、时间线和判断提炼。',
        placeholder: hasSelection ? '请输入问题，或让系统生成简报、比较和时间线。' : '请先在左侧至少选择一篇文章，再继续和 AI 沟通。',
        quickActions: ['请基于当前选中文章生成一份核心简报', '请总结这些选中文章里最重要的判断变化', '请按时间线梳理这些选中文章的关键进展'],
        send: '发送',
        continueWith: '继续追问',
        loading: 'AI 正在审阅当前选中的文章...',
        selectedCount: '已选文章',
        analysisLabel: '分析',
        questionLabel: '问题',
      }

  useEffect(() => {
    const nextMessages = loadStoredMessages(themeSlug, selectionScopeKey, greeting)
    setMessages(nextMessages)
    setMessageScopeKey(selectionScopeKey)
    messageScopeKeyRef.current = selectionScopeKey
    setInput('')
  }, [greeting, selectionScopeKey, themeSlug])

  useEffect(() => {
    messageScopeKeyRef.current = messageScopeKey
  }, [messageScopeKey])

  useEffect(() => {
    saveStoredMessages(themeSlug, messageScopeKey, messages)
  }, [messageScopeKey, messages, themeSlug])

  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, loading])

  const submitMessage = async (rawValue) => {
    const value = String(rawValue || '').trim()
    if (!value || loading || !hasSelection) return
    const requestScopeKey = selectionScopeKey
    const baseMessages =
      messageScopeKeyRef.current === requestScopeKey ? messages : loadStoredMessages(themeSlug, requestScopeKey, greeting)
    const userMessage = { role: 'user', content: value, sources: [], followUps: [] }
    const nextMessages = [...baseMessages, userMessage]
    setMessages(nextMessages)
    setMessageScopeKey(requestScopeKey)
    messageScopeKeyRef.current = requestScopeKey
    setInput('')
    setLoading(true)
    try {
      const payload = await chatWithMyKnowledgeTheme(
        themeSlug,
        {
          language: isEnglish ? 'en' : 'zh',
          selected_article_ids: selectedArticleIds,
          messages: nextMessages.map((item) => ({
            role: item.role,
            content: item.content,
          })),
        },
        accessToken,
      )
      const assistantMessage = {
        role: 'assistant',
        content: normalizeChatMarkdown(payload.answer),
        sources: payload.sources || [],
        followUps: payload.follow_up_questions || [],
      }
      const scopedMessages = [...nextMessages, assistantMessage]
      saveStoredMessages(themeSlug, requestScopeKey, scopedMessages)
      if (messageScopeKeyRef.current === requestScopeKey) {
        setMessages(scopedMessages)
      }
    } catch (error) {
      const assistantMessage = {
        role: 'assistant',
        content: normalizeChatMarkdown(isEnglish ? error?.message || 'The knowledge assistant is temporarily unavailable.' : error?.message || '主题知识库 AI 暂时不可用，请稍后重试。'),
        sources: [],
        followUps: [],
      }
      const scopedMessages = [...nextMessages, assistantMessage]
      saveStoredMessages(themeSlug, requestScopeKey, scopedMessages)
      if (messageScopeKeyRef.current === requestScopeKey) {
        setMessages(scopedMessages)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="flex h-full min-h-[42rem] flex-col overflow-hidden xl:min-h-0" data-knowledge-chat-panel={themeSlug}>
      <div className="border-b border-slate-200 bg-slate-50 px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <div className="knowledge-console-kicker">
              <Sparkles size={14} />
              {copy.title}
            </div>
            <div className="mt-3 font-serif text-[2.3rem] font-black leading-tight text-fudan-blue">{themeTitle}</div>
            <p className="mt-3 text-base leading-8 text-slate-500">{copy.body}</p>
          </div>

          <div
            className="flex h-[7rem] w-[8rem] shrink-0 flex-col items-center justify-center rounded-[1rem] border border-slate-200 bg-white text-center"
            data-knowledge-selected-count-metric
          >
            <div className="knowledge-console-label">{copy.selectedCount}</div>
            <div className="mt-2 font-serif text-4xl font-black leading-none text-fudan-orange">{selectedCount}</div>
            <div className="mt-2 text-xs text-slate-400">{isEnglish ? `${totalArticleCount} in theme` : `主题内共 ${totalArticleCount} 篇`}</div>
          </div>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)] px-5 py-5 md:px-6">
        {messages.map((message, index) =>
          message.role === 'assistant' ? (
            <AssistantResponseCard
              key={`${message.role}-${index}`}
              label={copy.analysisLabel}
              content={message.content}
              dataScope="knowledge-theme-chat"
              sources={message.sources}
              showSources={false}
              wrapperProps={{ 'data-knowledge-chat-message': 'assistant' }}
            />
          ) : (
            <div
              key={`${message.role}-${index}`}
              className="ml-auto max-w-[88%] rounded-[1rem] border border-fudan-blue/12 bg-fudan-blue/[0.04] px-5 py-4"
              data-knowledge-chat-message="user"
            >
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-fudan-blue">{copy.questionLabel}</div>
              <div className="whitespace-pre-wrap text-base leading-8 text-slate-700">{message.content}</div>
            </div>
          ),
        )}

        {loading ? (
          <div className="rounded-[1rem] border border-dashed border-slate-300 bg-white px-4 py-3 text-sm text-slate-500">
            <span className="inline-flex items-center gap-2">
              <LoaderCircle size={15} className="animate-spin" />
              {copy.loading}
            </span>
          </div>
        ) : null}
      </div>

      <div className="border-t border-slate-200 bg-white px-5 py-5 md:px-6">
        <div className="mb-3 flex flex-wrap gap-2">
          {copy.quickActions.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => submitMessage(item)}
              disabled={!hasSelection}
              className="rounded-[0.8rem] border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-600 transition hover:border-fudan-blue/25 hover:bg-white hover:text-fudan-blue disabled:cursor-not-allowed disabled:opacity-55"
            >
              {item}
            </button>
          ))}
        </div>

        <div className="flex items-end gap-3">
          <textarea
            rows={3}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={copy.placeholder}
            className="knowledge-console-textarea min-h-[6.5rem] flex-1 resize-none text-base leading-8"
          />
          <button
            type="button"
            onClick={() => submitMessage(input)}
            disabled={loading || !hasSelection}
            className="knowledge-console-primary h-12 min-w-[3rem] px-4 disabled:cursor-not-allowed disabled:opacity-55"
            aria-label={copy.send}
          >
            <Send size={17} />
          </button>
        </div>
      </div>
    </section>
  )
}

export default KnowledgeThemeChatPanel
