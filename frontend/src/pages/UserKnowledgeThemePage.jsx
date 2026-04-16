import { ArrowLeft, CheckSquare, LoaderCircle, PencilLine, Square, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  deleteMyKnowledgeTheme,
  fetchMyKnowledgeThemeDetail,
  removeArticleFromMyKnowledgeTheme,
  updateMyKnowledgeTheme,
} from '../api/index.js'
import KnowledgeThemeArticleRow from '../components/knowledge/KnowledgeThemeArticleRow.jsx'
import KnowledgeThemeChatPanel from '../components/knowledge/KnowledgeThemeChatPanel.jsx'
import KnowledgeThemeConfirmModal from '../components/knowledge/KnowledgeThemeConfirmModal.jsx'
import KnowledgeThemeEditModal from '../components/knowledge/KnowledgeThemeEditModal.jsx'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function UserKnowledgeThemePage() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const { accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [theme, setTheme] = useState(null)
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [renameOpen, setRenameOpen] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [descriptionDraft, setDescriptionDraft] = useState('')
  const [renameError, setRenameError] = useState('')
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [removingArticleId, setRemovingArticleId] = useState(null)
  const [selectedArticleIds, setSelectedArticleIds] = useState([])

  const copy = useMemo(
    () =>
      isEnglish
        ? {
            back: 'Back to my knowledge base',
            title: 'Theme workbench',
            body: 'Select the filed articles first, then run AI analysis only inside that chosen set.',
            empty: 'This theme has no article yet. Go back to an article page and file one into this theme first.',
            edit: 'Rename',
            save: 'Save',
            cancel: 'Cancel',
            close: 'Close',
            delete: 'Delete',
            deleteConfirm: 'Delete this theme now? The saved article mapping will also be removed.',
            articleFlow: 'File list',
            removeArticle: 'Remove from theme',
            removeConfirm: 'Remove this article from the current theme now?',
            removeFailed: 'Failed to remove this article from the theme.',
            renameTitle: 'Theme name',
            renameNote: 'Theme note',
            titleRequired: 'Theme name is required.',
            openArticle: 'Open article',
            defaultSource: 'Article',
            columnLabel: 'Section',
            selectedCount: 'Selected articles',
            selectAll: 'Select all',
            clearSelection: 'Clear',
            selectArticle: 'Select this article',
            unselectArticle: 'Unselect this article',
            inThemeCount: 'Total filed',
            filePanelHint: 'Select all or choose a few articles before talking to AI.',
            deleteThemeTitle: 'Delete this theme?',
            deleteThemeBody: 'The theme, its article mapping, and its private working context will all be removed.',
            deleteThemeConfirm: 'Delete theme',
          }
        : {
            back: '返回我的知识库',
            title: '主题工作台',
            body: '先选择要纳入分析的文章，再只围绕这组已选内容继续和 AI 沟通。',
            empty: '这个主题里还没有文章，先回到文章详情页，把内容收录进来再继续使用。',
            edit: '重命名',
            save: '保存',
            cancel: '取消',
            close: '关闭',
            delete: '删除',
            deleteConfirm: '现在删除这个主题吗？这个主题里的文章关联也会一起清空。',
            articleFlow: '文件列表',
            removeArticle: '移出主题',
            removeConfirm: '现在把这篇文章从当前主题里移出吗？',
            removeFailed: '从主题中移出文章失败。',
            renameTitle: '主题名称',
            renameNote: '主题说明',
            titleRequired: '主题名称不能为空。',
            defaultDescription: '把相关文章整理成一条长期学习主线，再从下面勾选当前要交给 AI 处理的那几篇。',
            openArticle: '打开文章',
            defaultSource: '文章',
            columnLabel: '栏目',
            selectedCount: '已选文章',
            selectAll: '一键全选',
            clearSelection: '清空',
            selectArticle: '选中这篇文章',
            unselectArticle: '取消选中这篇文章',
            inThemeCount: '主题内总数',
            filePanelHint: '你可以一键全选，也可以只勾选几篇后再和 AI 沟通。',
            deleteThemeTitle: '确认删除这个主题？',
            deleteThemeBody: '删除后，这个主题、它关联的文章映射以及主题工作上下文都会一起移除。',
            deleteThemeConfirm: '删除主题',
          },
    [isEnglish],
  )

  useEffect(() => {
    if (!slug) return
    let active = true
    setLoading(true)
    fetchMyKnowledgeThemeDetail(slug, accessToken)
      .then((payload) => {
        if (!active) return
        const articleIds = (payload.articles || []).map((item) => item.id)
        setTheme(payload)
        setTitleDraft(payload.title || '')
        setDescriptionDraft(payload.description || '')
        setSelectedArticleIds(articleIds)
        setPageError('')
      })
      .catch((err) => {
        if (!active) return
        setPageError(err?.message || (isEnglish ? 'Failed to load this theme.' : '加载主题失败。'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [accessToken, isEnglish, slug])

  const openRenameModal = () => {
    setTitleDraft(theme?.title || '')
    setDescriptionDraft(theme?.description || '')
    setRenameError('')
    setRenameOpen(true)
  }

  const handleSave = async () => {
    if (!theme?.slug || saving) return
    const trimmedTitle = titleDraft.trim()
    const trimmedDescription = descriptionDraft.trim()
    if (!trimmedTitle) {
      setRenameError(copy.titleRequired)
      return
    }
    setSaving(true)
    setRenameError('')
    try {
      const updated = await updateMyKnowledgeTheme(
        theme.slug,
        {
          title: trimmedTitle,
          description: trimmedDescription || null,
        },
        accessToken,
      )
      setTheme((current) => (current ? { ...current, ...updated } : current))
      setRenameOpen(false)
      if (updated.slug && updated.slug !== theme.slug) {
        navigate(`/me/knowledge/${updated.slug}`, { replace: true })
      }
    } catch (err) {
      setRenameError(err?.message || (isEnglish ? 'Failed to save the theme.' : '保存主题失败。'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!theme?.slug || deleting) return
    setDeleting(true)
    setDeleteError('')
    try {
      await deleteMyKnowledgeTheme(theme.slug, accessToken)
      navigate('/me/knowledge')
    } catch (err) {
      setDeleteError(err?.message || (isEnglish ? 'Failed to delete the theme.' : '删除主题失败。'))
    } finally {
      setDeleting(false)
    }
  }

  const handleRemoveArticle = async (articleId) => {
    if (!theme?.id || !articleId || removingArticleId) return
    if (!window.confirm(copy.removeConfirm)) return
    setRemovingArticleId(articleId)
    setPageError('')
    try {
      await removeArticleFromMyKnowledgeTheme(theme.id, articleId, accessToken)
      setTheme((current) => {
        if (!current) return current
        const nextArticles = (current.articles || []).filter((item) => item.id !== articleId)
        return {
          ...current,
          article_count: Math.max(0, (current.article_count || 0) - 1),
          preview_articles: (current.preview_articles || []).filter((item) => item.id !== articleId),
          articles: nextArticles,
          total: Math.max(0, (current.total || current.article_count || 0) - 1),
        }
      })
      setSelectedArticleIds((current) => current.filter((id) => id !== articleId))
    } catch (err) {
      setPageError(err?.message || copy.removeFailed)
    } finally {
      setRemovingArticleId(null)
    }
  }

  if (loading) {
    return <div className="page-shell py-16 text-sm text-slate-500">{isEnglish ? 'Loading theme...' : '正在加载主题...'}</div>
  }

  if (!theme) {
    return <div className="page-shell py-16 text-sm text-slate-500">{pageError || (isEnglish ? 'Theme unavailable.' : '当前主题不可用。')}</div>
  }

  const articles = theme.articles || []
  const allArticleIds = articles.map((item) => item.id)
  const themeDescription = String(theme.description || '').trim()

  const toggleArticleSelection = (articleId) => {
    setSelectedArticleIds((current) => (current.includes(articleId) ? current.filter((id) => id !== articleId) : [...current, articleId]))
  }

  return (
    <div className="page-shell py-10" data-knowledge-theme-page={theme.slug}>
      <div className="mb-7 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-4xl">
          <Link to="/me/knowledge" className="inline-flex items-center gap-2 text-sm font-semibold text-slate-500 transition hover:text-fudan-blue">
            <ArrowLeft size={15} />
            {copy.back}
          </Link>

          <div className="mt-5">
            <div className="knowledge-console-kicker">{copy.title}</div>
            <h1 className="knowledge-console-title mt-3">{theme.title}</h1>
            {themeDescription ? <p className="knowledge-console-subtitle mt-3 text-base leading-8">{themeDescription}</p> : null}
          </div>
        </div>

        <div className="flex min-h-[7rem] min-w-[13rem] flex-col justify-center rounded-[1rem] border border-slate-200 bg-white px-4 py-4" data-knowledge-page-top-controls>
          <div className="knowledge-console-label">{copy.articleFlow}</div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSelectedArticleIds(allArticleIds)}
              className="knowledge-console-tool-button"
              data-knowledge-select-all
            >
              <CheckSquare size={15} />
              {copy.selectAll}
            </button>
            <button
              type="button"
              onClick={() => setSelectedArticleIds([])}
              className="knowledge-console-tool-button"
              data-knowledge-clear-selection
            >
              <Square size={15} />
              {copy.clearSelection}
            </button>
          </div>
        </div>
      </div>

      {pageError ? <div className="mb-6 rounded-[0.85rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{pageError}</div> : null}

      <section className="knowledge-console-panel overflow-hidden xl:h-[calc(100vh-15.5rem)] xl:min-h-[42rem]">
        <div className="grid xl:h-full xl:min-h-0 xl:grid-cols-[26rem_minmax(0,1fr)] 2xl:grid-cols-[28rem_minmax(0,1fr)]">
          <aside className="border-b border-slate-200 xl:flex xl:h-full xl:min-h-0 xl:flex-col xl:border-r xl:border-b-0">
            <div className="border-b border-slate-200 bg-slate-50 px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="knowledge-console-kicker">{copy.articleFlow}</div>
                  <div className="mt-2 font-serif text-4xl font-black text-fudan-blue">{theme.article_count || 0}</div>
                  <div className="mt-2 text-sm leading-7 text-slate-500">{copy.filePanelHint}</div>
                </div>

                <div className="flex flex-wrap justify-end gap-2">
                  <button type="button" onClick={openRenameModal} className="knowledge-console-tool-button" data-knowledge-theme-open-rename>
                    <PencilLine size={14} />
                    {copy.edit}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteOpen(true)
                      setDeleteError('')
                    }}
                    disabled={deleting}
                    className="knowledge-console-tool-button disabled:cursor-not-allowed disabled:opacity-55"
                    data-knowledge-theme-open-delete
                  >
                    {deleting ? <LoaderCircle size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    {copy.delete}
                  </button>
                </div>
              </div>
            </div>

            {articles.length === 0 ? (
              <div className="px-5 py-6 text-sm leading-7 text-slate-500 xl:flex-1 xl:overflow-y-auto">{copy.empty}</div>
            ) : (
              <div className="xl:min-h-0 xl:flex-1 xl:overflow-y-auto">
                {articles.map((article) => (
                  <KnowledgeThemeArticleRow
                    key={article.id}
                    article={article}
                    checked={selectedArticleIds.includes(article.id)}
                    removing={removingArticleId === article.id}
                    onToggleChecked={() => toggleArticleSelection(article.id)}
                    onRemove={() => handleRemoveArticle(article.id)}
                    copy={copy}
                  />
                ))}
              </div>
            )}
          </aside>

          <div className="bg-white xl:h-full xl:min-h-0">
            <KnowledgeThemeChatPanel
              themeSlug={theme.slug}
              themeTitle={theme.title}
              accessToken={accessToken}
              selectedArticleIds={selectedArticleIds}
              totalArticleCount={theme.article_count || 0}
            />
          </div>
        </div>
      </section>

      <KnowledgeThemeEditModal
        open={renameOpen}
        onClose={() => {
          if (saving) return
          setRenameOpen(false)
          setRenameError('')
          setTitleDraft(theme.title || '')
          setDescriptionDraft(theme.description || '')
        }}
        onSave={handleSave}
        saving={saving}
        titleValue={titleDraft}
        descriptionValue={descriptionDraft}
        onTitleChange={(event) => setTitleDraft(event.target.value)}
        onDescriptionChange={(event) => setDescriptionDraft(event.target.value)}
        copy={copy}
        error={renameError}
      />

      <KnowledgeThemeConfirmModal
        open={deleteOpen}
        onClose={() => {
          if (deleting) return
          setDeleteOpen(false)
          setDeleteError('')
        }}
        onConfirm={handleDelete}
        confirming={deleting}
        title={copy.deleteThemeTitle}
        body={copy.deleteThemeBody}
        confirmLabel={copy.deleteThemeConfirm}
        cancelLabel={copy.cancel}
        closeLabel={copy.close}
        dataScope="knowledge-theme-delete"
        error={deleteError}
      />
    </div>
  )
}

export default UserKnowledgeThemePage
