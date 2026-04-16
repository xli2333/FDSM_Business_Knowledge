import { LoaderCircle, Plus, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addArticleToMyKnowledgeTheme,
  createMyKnowledgeTheme,
  fetchMyKnowledgeThemes,
  removeArticleFromMyKnowledgeTheme,
} from '../../api/index.js'
import { useLanguage } from '../../i18n/LanguageContext.js'

function KnowledgeThemeComposerModal({ open, onClose, article, accessToken = '' }) {
  const { isEnglish } = useLanguage()
  const [payload, setPayload] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(false)
  const [savingThemeId, setSavingThemeId] = useState(null)
  const [createTitle, setCreateTitle] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const copy = useMemo(
    () =>
      isEnglish
        ? {
            title: 'Add To Knowledge Base',
            body: 'Put this article into one of your private themes, or create a new theme first.',
            createHint: 'No theme yet. Create the first one now so this article enters a clear working set immediately.',
            createBody: 'Create another private theme here when this article belongs to a new long-term topic.',
            createTitleLabel: 'Theme name',
            createDescriptionLabel: 'Theme note',
            createPlaceholder: 'Example: AI strategy library',
            createDescriptionPlaceholder: 'Optional: what this theme should keep tracking',
            createButton: 'Create and add this article',
            createOnlyButton: 'Create the first theme and add this article',
            empty: 'No saved theme yet. Create your first knowledge theme here.',
            added: 'Already in this theme',
            add: 'Add to this theme',
            remove: 'Remove',
            openHub: 'Open my knowledge base',
            loading: 'Loading your themes...',
            emptyTheme: 'No article in this theme yet.',
            themeList: 'Existing themes',
          }
        : {
            title: '加入知识库',
            body: '把这篇文章放进你的私有主题里，或者先创建一个新的收藏主题。',
            createHint: '你还没有任何主题，先创建第一个主题，让这篇文章直接进入明确的工作集合。',
            createBody: '如果这篇文章应该进入一个新的长期主题，也可以直接在这里继续新建主题。',
            createTitleLabel: '主题名称',
            createDescriptionLabel: '主题说明',
            createPlaceholder: '例如：AI 主题知识库',
            createDescriptionPlaceholder: '可选：这个主题准备长期追踪什么',
            createButton: '创建主题并加入本文',
            createOnlyButton: '创建第一个主题并加入本文',
            empty: '你还没有保存任何主题，先在这里创建第一个知识库主题。',
            added: '已收录到这个主题',
            add: '加入这个主题',
            remove: '移出主题',
            openHub: '打开我的知识库',
            loading: '正在加载你的主题…',
            emptyTheme: '这个主题里还没有文章。',
            themeList: '已有主题',
          },
    [isEnglish],
  )

  useEffect(() => {
    if (!open || !article?.id) return
    let active = true
    setLoading(true)
    setError('')
    fetchMyKnowledgeThemes(accessToken, article.id)
      .then((result) => {
        if (!active) return
        setPayload(result)
      })
      .catch((err) => {
        if (!active) return
        setError(err?.message || (isEnglish ? 'Failed to load themes.' : '加载主题失败。'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [accessToken, article?.id, isEnglish, open])

  useEffect(() => {
    if (!open) {
      setCreateTitle('')
      setCreateDescription('')
      setCreating(false)
      setSavingThemeId(null)
      setError('')
    }
  }, [open])

  if (!open || !article) return null

  const items = payload.items || []
  const showCreateOnly = !loading && items.length === 0

  const refreshThemes = async () => {
    const result = await fetchMyKnowledgeThemes(accessToken, article.id)
    setPayload(result)
  }

  const handleCreate = async () => {
    if (!createTitle.trim() || creating) return
    setCreating(true)
    setError('')
    try {
      await createMyKnowledgeTheme(
        {
          title: createTitle.trim(),
          description: createDescription.trim() || null,
          initial_article_id: article.id,
        },
        accessToken,
      )
      setCreateTitle('')
      setCreateDescription('')
      await refreshThemes()
    } catch (err) {
      setError(err?.message || (isEnglish ? 'Failed to create the theme.' : '创建主题失败。'))
    } finally {
      setCreating(false)
    }
  }

  const handleToggleArticle = async (theme) => {
    if (!theme?.id || savingThemeId) return
    setSavingThemeId(theme.id)
    setError('')
    try {
      if (theme.contains_article) {
        await removeArticleFromMyKnowledgeTheme(theme.id, article.id, accessToken)
      } else {
        await addArticleToMyKnowledgeTheme(theme.id, article.id, accessToken)
      }
      await refreshThemes()
    } catch (err) {
      setError(err?.message || (isEnglish ? 'Failed to update this theme.' : '更新主题失败。'))
    } finally {
      setSavingThemeId(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6" data-knowledge-article-modal>
      <div className="max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-[1.4rem] border border-slate-200 bg-white shadow-[0_28px_90px_rgba(15,23,42,0.28)]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 bg-slate-50 px-6 py-6 md:px-8">
          <div className="min-w-0">
            <div className="knowledge-console-kicker">{copy.title}</div>
            <div className="mt-2 font-serif text-3xl font-black leading-tight text-fudan-blue">{article.title}</div>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">{copy.body}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="knowledge-console-tool-button h-11 w-11 p-0"
            aria-label={isEnglish ? 'Close' : '关闭'}
          >
            <X size={18} />
          </button>
        </div>

        <div className={showCreateOnly ? 'max-h-[72vh] overflow-y-auto px-6 py-6 md:px-8' : 'grid gap-0 lg:grid-cols-[20rem_minmax(0,1fr)]'}>
          {showCreateOnly ? (
            <div className="mx-auto w-full max-w-2xl">
              {error ? <div className="mb-4 rounded-[0.95rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}
              <div className="knowledge-console-panel p-6">
                <div className="knowledge-console-kicker">{copy.title}</div>
                <div className="mt-3 font-serif text-3xl font-black text-fudan-blue">{copy.createOnlyButton}</div>
                <p className="mt-4 text-sm leading-7 text-slate-600">{copy.createHint}</p>

                <label className="mt-5 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{copy.createTitleLabel}</label>
                <input
                  value={createTitle}
                  onChange={(event) => setCreateTitle(event.target.value)}
                  placeholder={copy.createPlaceholder}
                  className="knowledge-console-input mt-2"
                  data-knowledge-create-title
                  autoFocus
                />

                <label className="mt-5 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{copy.createDescriptionLabel}</label>
                <textarea
                  value={createDescription}
                  onChange={(event) => setCreateDescription(event.target.value)}
                  placeholder={copy.createDescriptionPlaceholder}
                  rows={5}
                  className="knowledge-console-textarea mt-2 min-h-[10rem] resize-none"
                />

                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={creating || !createTitle.trim()}
                  className="knowledge-console-primary mt-5 w-full justify-center disabled:cursor-not-allowed disabled:opacity-55"
                >
                  {creating ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
                  {copy.createOnlyButton}
                </button>

                <Link
                  to="/me/knowledge"
                  className="mt-4 inline-flex text-sm font-semibold text-fudan-blue transition hover:text-fudan-dark"
                  onClick={onClose}
                >
                  {copy.openHub}
                </Link>
              </div>
            </div>
          ) : (
            <>
              <aside className="border-b border-slate-200 bg-slate-50/80 p-6 lg:border-b-0 lg:border-r">
                <div className="knowledge-console-panel p-5">
                  <div className="knowledge-console-kicker">{copy.createTitleLabel}</div>
                  <p className="mt-3 text-sm leading-7 text-slate-600">{copy.createBody}</p>

                  <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{copy.createTitleLabel}</label>
                  <input
                    value={createTitle}
                    onChange={(event) => setCreateTitle(event.target.value)}
                    placeholder={copy.createPlaceholder}
                    className="knowledge-console-input mt-2"
                    data-knowledge-create-title
                  />

                  <label className="mt-4 block text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{copy.createDescriptionLabel}</label>
                  <textarea
                    value={createDescription}
                    onChange={(event) => setCreateDescription(event.target.value)}
                    placeholder={copy.createDescriptionPlaceholder}
                    rows={4}
                    className="knowledge-console-textarea mt-2 min-h-[8rem] resize-none"
                  />

                  <button
                    type="button"
                    onClick={handleCreate}
                    disabled={creating || !createTitle.trim()}
                    className="knowledge-console-primary mt-5 w-full justify-center disabled:cursor-not-allowed disabled:opacity-55"
                  >
                    {creating ? <LoaderCircle size={15} className="animate-spin" /> : <Plus size={15} />}
                    {copy.createButton}
                  </button>

                  <Link
                    to="/me/knowledge"
                    className="mt-3 inline-flex text-sm font-semibold text-fudan-blue transition hover:text-fudan-dark"
                    onClick={onClose}
                  >
                    {copy.openHub}
                  </Link>
                </div>
              </aside>

              <div className="max-h-[70vh] overflow-y-auto p-6 md:p-8">
                {error ? <div className="mb-4 rounded-[0.95rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{error}</div> : null}
                {loading ? (
                  <div className="rounded-[1.1rem] border border-dashed border-slate-300 bg-slate-50 px-5 py-12 text-center text-sm text-slate-500">
                    <span className="inline-flex items-center gap-2">
                      <LoaderCircle size={16} className="animate-spin" />
                      {copy.loading}
                    </span>
                  </div>
                ) : (
                  <>
                    <div className="knowledge-console-kicker">{copy.themeList}</div>
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      {items.map((theme) => (
                        <article
                          key={theme.id}
                          className="rounded-[1rem] border border-slate-200 bg-white p-5 shadow-[0_16px_44px_rgba(15,23,42,0.05)]"
                          data-knowledge-select-theme={theme.slug}
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="font-serif text-2xl font-black text-fudan-blue">{theme.title}</div>
                              <div className="mt-2 text-sm text-slate-500">
                                {theme.article_count} {isEnglish ? 'articles' : '篇文章'}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleToggleArticle(theme)}
                              disabled={savingThemeId === theme.id}
                              className={[
                                'inline-flex shrink-0 items-center gap-2 rounded-[0.8rem] px-4 py-2 text-sm font-semibold transition',
                                theme.contains_article
                                  ? 'border border-fudan-blue/15 bg-fudan-blue text-white'
                                  : 'border border-fudan-orange/20 bg-fudan-orange/10 text-fudan-orange hover:bg-fudan-orange/15',
                              ].join(' ')}
                            >
                              {savingThemeId === theme.id ? <LoaderCircle size={14} className="animate-spin" /> : null}
                              {theme.contains_article ? copy.remove : copy.add}
                            </button>
                          </div>

                          {theme.description ? <p className="mt-3 text-sm leading-7 text-slate-600">{theme.description}</p> : null}

                          <div className="mt-4 rounded-[0.95rem] border border-slate-200 bg-slate-50 p-4">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                              {theme.contains_article ? copy.added : isEnglish ? 'Articles' : '文章'}
                            </div>
                            <div className="mt-3 space-y-2">
                              {(theme.preview_articles || []).slice(0, 2).map((item) => (
                                <div key={`${theme.id}-${item.id}`} className="rounded-[0.8rem] border border-white bg-white px-3 py-3 text-sm text-slate-600">
                                  <div className="font-semibold text-fudan-blue">{item.title}</div>
                                  <div className="mt-1 text-xs leading-6 text-slate-400">{item.publish_date}</div>
                                </div>
                              ))}
                              {!theme.preview_articles?.length ? (
                                <div className="rounded-[0.8rem] border border-dashed border-slate-300 bg-white px-3 py-4 text-sm text-slate-400">{copy.emptyTheme}</div>
                              ) : null}
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default KnowledgeThemeComposerModal
