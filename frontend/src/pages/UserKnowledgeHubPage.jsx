import { BookOpen, LoaderCircle, Plus, RefreshCw, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createMyKnowledgeTheme, deleteMyKnowledgeTheme, fetchMyKnowledgeThemes } from '../api/index.js'
import KnowledgeThemeCard from '../components/knowledge/KnowledgeThemeCard.jsx'
import KnowledgeThemeConfirmModal from '../components/knowledge/KnowledgeThemeConfirmModal.jsx'
import KnowledgeThemeCreateModal from '../components/knowledge/KnowledgeThemeCreateModal.jsx'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function UserKnowledgeHubPage() {
  const { accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [payload, setPayload] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [creating, setCreating] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createError, setCreateError] = useState('')
  const [pendingDeleteTheme, setPendingDeleteTheme] = useState(null)
  const [deletingThemeSlug, setDeletingThemeSlug] = useState('')
  const [deleteError, setDeleteError] = useState('')

  const copy = useMemo(
    () =>
      isEnglish
        ? {
            kicker: 'Knowledge Console',
            title: 'My knowledge clusters',
            body: 'Turn saved articles into named themes, then continue AI work only inside those curated sets.',
            refresh: 'Refresh',
            createToggleOpen: 'New theme',
            createTitle: 'Create theme',
            createBody: 'Keep titles narrow and operational so the theme remains a usable working set.',
            titleLabel: 'Theme name',
            descriptionLabel: 'Theme note',
            titlePlaceholder: 'Example: AI governance watch',
            descriptionPlaceholder: 'Optional: what this theme should keep tracking',
            createButton: 'Create',
            cancel: 'Cancel',
            close: 'Close',
            empty: 'No theme yet. Create the first one here, then add articles from article pages.',
            loading: 'Loading your themes...',
            savedThemes: 'Theme clusters',
            savedThemesHint: 'Open a cluster to continue analysis only within that file set.',
            openCreate: 'Create your first theme',
            deleteThemeTitle: 'Delete this theme?',
            deleteThemeBody: 'The cluster card and its article mapping will be removed. This action cannot be undone.',
            deleteThemeConfirm: 'Delete theme',
          }
        : {
            kicker: '知识库工作台',
            title: '我的主题聚类',
            body: '把收藏文章整理成命名主题，再只围绕这组已筛过的材料继续做 AI 分析。',
            refresh: '刷新数据',
            createToggleOpen: '新建主题',
            createTitle: '创建主题',
            createBody: '主题名尽量短、准、可执行，这样后续文章越来越多时仍然容易管理。',
            titleLabel: '主题名称',
            descriptionLabel: '主题说明',
            titlePlaceholder: '例如：AI 主题知识库',
            descriptionPlaceholder: '可选：这个主题准备长期追踪什么',
            createButton: '创建',
            cancel: '取消',
            close: '关闭',
            empty: '你还没有创建任何主题，先建立第一个主题，再去文章详情页把内容加入进来。',
            loading: '正在加载你的主题...',
            savedThemes: '主题聚类卡片',
            savedThemesHint: '从某个主题进入后，AI 只会继续处理这一组文件。',
            openCreate: '创建第一个主题',
            deleteThemeTitle: '确认删除这个主题？',
            deleteThemeBody: '删除后，这张主题卡片和它关联的文章映射都会一起移除，且无法恢复。',
            deleteThemeConfirm: '删除主题',
          },
    [isEnglish],
  )

  useEffect(() => {
    let active = true

    const loadThemes = async () => {
      setLoading(true)
      try {
        const result = await fetchMyKnowledgeThemes(accessToken)
        if (!active) return
        setPayload(result)
        setPageError('')
      } catch (err) {
        if (!active) return
        setPageError(err?.message || (isEnglish ? 'Failed to load your knowledge base.' : '加载知识库失败。'))
      } finally {
        if (active) setLoading(false)
      }
    }

    loadThemes()
    return () => {
      active = false
    }
  }, [accessToken, isEnglish])

  const handleRefresh = async () => {
    if (loading) return
    setLoading(true)
    setPageError('')
    try {
      const result = await fetchMyKnowledgeThemes(accessToken)
      setPayload(result)
    } catch (err) {
      setPageError(err?.message || (isEnglish ? 'Failed to refresh your themes.' : '刷新主题失败。'))
    } finally {
      setLoading(false)
    }
  }

  const closeCreateModal = () => {
    setCreateModalOpen(false)
    setCreateTitle('')
    setCreateDescription('')
    setCreateError('')
  }

  const handleCreate = async () => {
    if (!createTitle.trim() || creating) return
    setCreating(true)
    setCreateError('')
    try {
      const created = await createMyKnowledgeTheme(
        {
          title: createTitle.trim(),
          description: createDescription.trim() || null,
        },
        accessToken,
      )
      setPayload((current) => ({
        total: Math.max(1, Number(current.total || 0) + 1),
        items: [created, ...(current.items || [])],
      }))
      closeCreateModal()
    } catch (err) {
      setCreateError(err?.message || (isEnglish ? 'Failed to create the theme.' : '创建主题失败。'))
    } finally {
      setCreating(false)
    }
  }

  const handleRequestDelete = (theme) => {
    setPendingDeleteTheme(theme)
    setDeleteError('')
  }

  const handleConfirmDelete = async () => {
    if (!pendingDeleteTheme?.slug || deletingThemeSlug) return
    setDeletingThemeSlug(pendingDeleteTheme.slug)
    setDeleteError('')
    try {
      await deleteMyKnowledgeTheme(pendingDeleteTheme.slug, accessToken)
      setPayload((current) => {
        const nextItems = (current.items || []).filter((item) => item.slug !== pendingDeleteTheme.slug)
        return {
          total: nextItems.length,
          items: nextItems,
        }
      })
      setPendingDeleteTheme(null)
    } catch (err) {
      setDeleteError(err?.message || (isEnglish ? 'Failed to delete the theme.' : '删除主题失败。'))
    } finally {
      setDeletingThemeSlug('')
    }
  }

  const items = payload.items || []

  return (
    <div className="page-shell py-10" data-knowledge-hub-page>
      <section className="knowledge-console-panel overflow-hidden">
        <div className="knowledge-console-header">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-4xl">
              <div className="knowledge-console-kicker">
                <BookOpen size={14} />
                {copy.kicker}
              </div>
              <h1 className="knowledge-console-title mt-3">{copy.title}</h1>
              <p className="knowledge-console-subtitle mt-2">{copy.body}</p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={handleRefresh} className="knowledge-console-tool-button">
                {loading ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />}
                {copy.refresh}
              </button>
              <button type="button" onClick={() => setCreateModalOpen(true)} className="knowledge-console-primary">
                <Plus size={15} />
                {copy.createToggleOpen}
              </button>
            </div>
          </div>
        </div>

        <div className="px-5 py-5 md:px-6 md:py-6">
          {pageError ? <div className="mb-5 rounded-[0.85rem] border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">{pageError}</div> : null}

          <div className="mb-5">
            <div className="knowledge-console-kicker">
              <Sparkles size={14} />
              {copy.savedThemes}
            </div>
            <div className="mt-2 text-sm text-slate-500">{copy.savedThemesHint}</div>
          </div>

          {loading ? (
            <div className="knowledge-console-panel border-dashed p-8 text-sm text-slate-500">
              <span className="inline-flex items-center gap-2">
                <LoaderCircle size={16} className="animate-spin" />
                {copy.loading}
              </span>
            </div>
          ) : items.length === 0 ? (
            <div className="knowledge-console-card border-dashed px-6 py-8 text-sm leading-7 text-slate-500">
              <div className="inline-flex items-center gap-2 text-fudan-orange">
                <Sparkles size={16} />
                {copy.empty}
              </div>
              <div className="mt-5">
                <button type="button" onClick={() => setCreateModalOpen(true)} className="knowledge-console-primary">
                  <Plus size={15} />
                  {copy.openCreate}
                </button>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {items.map((theme) => (
                <KnowledgeThemeCard
                  key={theme.slug}
                  theme={theme}
                  onRequestDelete={handleRequestDelete}
                  deleting={deletingThemeSlug === theme.slug}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      <KnowledgeThemeCreateModal
        open={createModalOpen}
        onClose={closeCreateModal}
        copy={copy}
        createTitle={createTitle}
        createDescription={createDescription}
        creating={creating}
        onTitleChange={(event) => setCreateTitle(event.target.value)}
        onDescriptionChange={(event) => setCreateDescription(event.target.value)}
        onCreate={handleCreate}
        error={createError}
      />

      <KnowledgeThemeConfirmModal
        open={Boolean(pendingDeleteTheme)}
        onClose={() => {
          if (deletingThemeSlug) return
          setPendingDeleteTheme(null)
          setDeleteError('')
        }}
        onConfirm={handleConfirmDelete}
        confirming={Boolean(deletingThemeSlug)}
        title={copy.deleteThemeTitle}
        body={copy.deleteThemeBody}
        confirmLabel={copy.deleteThemeConfirm}
        cancelLabel={copy.cancel}
        closeLabel={copy.close}
        dataScope="knowledge-hub-delete"
        error={deleteError}
      />
    </div>
  )
}

export default UserKnowledgeHubPage
