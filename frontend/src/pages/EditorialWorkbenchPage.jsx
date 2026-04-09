import { Eye, FileUp, LoaderCircle, Rocket, Save, Send, Sparkles, Wand2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  autoFormatEditorialArticle,
  autotagEditorialArticle,
  createEditorialArticle,
  editorialHtmlExportUrl,
  fetchColumns,
  fetchEditorialArticle,
  fetchEditorialArticles,
  fetchEditorialDashboard,
  publishEditorialArticle,
  renderEditorialHtml,
  updateEditorialArticle,
  updateEditorialWorkflow,
  uploadEditorialFile,
} from '../api/index.js'
import { useLanguage } from '../i18n/LanguageContext.js'

const EMPTY_PREVIEW = '<!doctype html><html><head><meta charset="utf-8" /></head><body style="font-family:PingFang SC,Microsoft YaHei,sans-serif;padding:32px;background:#f8fafc;color:#334155"><div style="max-width:760px;margin:0 auto;background:#fff;border-radius:24px;padding:28px;box-shadow:0 20px 60px rgba(15,23,42,.08)"><h1 style="margin:0 0 12px;color:#0d0783">预览尚未生成</h1><p style="line-height:1.9">先保存稿件，再执行一键排版或 HTML 渲染。</p></div></body></html>'
const DEFAULT_COLUMNS = [{ slug: 'insights', name: '深度洞察' }, { slug: 'industry', name: '行业观察' }, { slug: 'research', name: '学术前沿' }, { slug: 'deans-view', name: '院长说' }]
const DEFAULT_FORM = { title: '', subtitle: '', author: 'Fudan Business Knowledge Editorial Desk', organization: 'Fudan Business Knowledge', publish_date: new Date().toISOString().slice(0, 10), source_url: '', cover_image_url: '', primary_column_slug: 'insights', article_type: '', main_topic: '', access_level: 'public', layout_mode: 'auto', formatting_notes: '', source_markdown: '', content_markdown: '' }
const DEFAULT_WORKFLOW = { review_note: '', scheduled_publish_at: '' }

function EditorialWorkbenchPage() {
  const { isEnglish } = useLanguage()
  const fileRef = useRef(null)
  const [articles, setArticles] = useState([])
  const [columns, setColumns] = useState(DEFAULT_COLUMNS)
  const [dashboard, setDashboard] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [form, setForm] = useState(DEFAULT_FORM)
  const [workflow, setWorkflow] = useState(DEFAULT_WORKFLOW)
  const [previewMode, setPreviewMode] = useState('web')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const previewDoc = useMemo(() => (previewMode === 'wechat' ? detail?.html_wechat : detail?.html_web) || EMPTY_PREVIEW, [detail, previewMode])
  const sourceCount = useMemo(() => String(form.source_markdown || '').replace(/\s+/g, '').length, [form.source_markdown])
  const contentCount = useMemo(() => String(form.content_markdown || '').replace(/\s+/g, '').length, [form.content_markdown])

  const syncDetail = useCallback(async (id) => {
    const article = await fetchEditorialArticle(id)
    setSelectedId(article.id)
    setDetail(article)
    setForm({
      title: article.title || '',
      subtitle: article.subtitle || '',
      author: article.author || DEFAULT_FORM.author,
      organization: article.organization || DEFAULT_FORM.organization,
      publish_date: article.publish_date || DEFAULT_FORM.publish_date,
      source_url: article.source_url || '',
      cover_image_url: article.cover_image_url || '',
      primary_column_slug: article.primary_column_slug || 'insights',
      article_type: article.article_type || '',
      main_topic: article.main_topic || '',
      access_level: article.access_level || 'public',
      layout_mode: article.layout_mode || 'auto',
      formatting_notes: article.formatting_notes || '',
      source_markdown: article.source_markdown || '',
      content_markdown: article.content_markdown || '',
    })
    setWorkflow({
      review_note: article.review_note || '',
      scheduled_publish_at: article.scheduled_publish_at ? article.scheduled_publish_at.slice(0, 16) : '',
    })
    return article
  }, [])

  const refreshAll = useCallback(async (preferredId = null) => {
    const [list, dash] = await Promise.all([fetchEditorialArticles(80), fetchEditorialDashboard(8)])
    setArticles(list)
    setDashboard(dash)
    const nextId = preferredId || list[0]?.id
    if (nextId) await syncDetail(nextId)
  }, [syncDetail])

  useEffect(() => {
    fetchColumns().then((items) => items?.length && setColumns(items)).catch(() => {})
    refreshAll().catch(() => setError(isEnglish ? 'Failed to load editorial workbench.' : '文章后台加载失败。'))
  }, [isEnglish, refreshAll])

  const persist = useCallback(async () => {
    const payload = { ...form, title: form.title.trim() || (isEnglish ? 'Untitled draft' : '未命名草稿'), source_markdown: form.source_markdown || form.content_markdown, content_markdown: form.content_markdown || form.source_markdown }
    return selectedId ? updateEditorialArticle(selectedId, payload) : createEditorialArticle(payload)
  }, [form, isEnglish, selectedId])

  const run = async (key, task) => {
    setBusy(key); setError(''); setMessage('')
    try { await task() } catch { setError(isEnglish ? 'Action failed.' : '操作失败。') } finally { setBusy('') }
  }

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,.98),rgba(10,5,96,.86)_58%,rgba(234,107,0,.2))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="section-kicker !text-white/72">{isEnglish ? 'Admin Editorial' : '管理员文章工作台'}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{isEnglish ? 'Upload, rewrite, auto-format, preview, publish' : '上传、改稿、自动排版、预览、发布'}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{isEnglish ? 'This page is rebuilt around the actual admin flow. The one-click formatter uses gemini-3-flash-preview with the backend Gemini key pool.' : '页面已改成真实管理员流程。一键自由排版固定使用 gemini-3-flash-preview，并走后台 Gemini key 池。'}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button type="button" onClick={() => { setSelectedId(null); setDetail(null); setForm(DEFAULT_FORM); setWorkflow(DEFAULT_WORKFLOW) }} className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-semibold text-fudan-blue"><Save size={16} />{isEnglish ? 'New draft' : '新建草稿'}</button>
              <button type="button" onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-6 py-3 text-sm font-semibold text-white"><FileUp size={16} />{isEnglish ? 'Upload file' : '上传文稿'}</button>
              <input ref={fileRef} type="file" accept=".md,.txt,.html,.htm,.docx,text/plain,text/markdown,text/html,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={(event) => run('upload', async () => { const file = event.target.files?.[0]; if (!file) return; const payload = await uploadEditorialFile(file); await refreshAll(payload.article.id); setMessage(isEnglish ? `Imported ${payload.filename}` : `已导入 ${payload.filename}`); event.target.value = '' })} />
            </div>
          </div>
          <div className="grid gap-4 self-start md:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur"><div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Drafts' : '草稿'}</div><div className="mt-3 font-serif text-3xl font-black text-white">{dashboard?.draft_count ?? 0}</div></div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur"><div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Pending review' : '待审核'}</div><div className="mt-3 font-serif text-3xl font-black text-white">{dashboard?.pending_review_count ?? 0}</div></div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur"><div className="text-xs uppercase tracking-[.24em] text-white/65">{isEnglish ? 'Published' : '已发布'}</div><div className="mt-3 font-serif text-3xl font-black text-white">{dashboard?.published_count ?? 0}</div></div>
          </div>
        </div>
      </section>
      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {message ? <div className="mt-6 text-sm text-emerald-700">{message}</div> : null}
      <section className="mt-8 grid gap-6 xl:grid-cols-[.72fr_1.28fr]">
        <aside className="space-y-6">
          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Draft list' : '稿件列表'}</div>
            <div className="mt-4 space-y-3">{articles.map((item) => <button key={item.id} type="button" onClick={() => run('select', async () => { await syncDetail(item.id) })} className={`block w-full rounded-[1.2rem] border p-4 text-left ${selectedId === item.id ? 'border-fudan-blue bg-fudan-blue/5' : 'border-slate-200/70 bg-white'}`}><div className="font-serif text-lg font-bold text-fudan-blue">{item.title}</div><div className="mt-2 text-sm text-slate-500">{item.workflow_label || item.workflow_status}</div></button>)}</div>
          </div>
          <div className="fudan-panel p-6">
            <div className="section-kicker">{isEnglish ? 'Workflow' : '流程控制'}</div>
            <textarea name="review_note" rows={4} value={workflow.review_note} onChange={(e) => setWorkflow((c) => ({ ...c, review_note: e.target.value }))} placeholder={isEnglish ? 'Review note' : '审核备注'} className="mt-4 w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none" />
            <input name="scheduled_publish_at" type="datetime-local" value={workflow.scheduled_publish_at} onChange={(e) => setWorkflow((c) => ({ ...c, scheduled_publish_at: e.target.value }))} className="mt-4 w-full rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
            <div className="mt-4 grid gap-3">
              <button type="button" onClick={() => run('submit', async () => { const saved = await persist(); const article = await updateEditorialWorkflow(saved.id, { action: 'submit_review', review_note: workflow.review_note, scheduled_publish_at: null }); await refreshAll(article.id); setMessage(isEnglish ? 'Submitted for review.' : '已提交审核。') })} className="inline-flex items-center justify-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue">{busy === 'submit' ? <LoaderCircle size={16} className="animate-spin" /> : <Send size={16} />}{isEnglish ? 'Submit review' : '提交审核'}</button>
              <button type="button" onClick={() => run('publish', async () => { const saved = await persist(); await publishEditorialArticle(saved.id); await refreshAll(saved.id); setMessage(isEnglish ? 'Published.' : '已发布。') })} className="inline-flex items-center justify-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">{busy === 'publish' ? <LoaderCircle size={16} className="animate-spin" /> : <Rocket size={16} />}{isEnglish ? 'Publish' : '发布'}</button>
            </div>
          </div>
        </aside>
        <div className="space-y-6">
          <section className="fudan-panel p-6">
            <div className="flex flex-wrap gap-3">
              <button type="button" onClick={() => run('save', async () => { const saved = await persist(); await refreshAll(saved.id); setMessage(isEnglish ? 'Draft saved.' : '草稿已保存。') })} className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue">{busy === 'save' ? <LoaderCircle size={16} className="animate-spin" /> : <Save size={16} />}{isEnglish ? 'Save' : '保存'}</button>
              <button type="button" onClick={() => run('format', async () => { const saved = await persist(); const article = await autoFormatEditorialArticle(saved.id, { source_markdown: form.source_markdown || form.content_markdown, layout_mode: form.layout_mode, formatting_notes: form.formatting_notes }); await refreshAll(article.id); setMessage(isEnglish ? `Formatted with ${article.formatter_model || 'gemini-3-flash-preview'}` : `已完成一键排版，模型：${article.formatter_model || 'gemini-3-flash-preview'}`) })} className="inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white">{busy === 'format' ? <LoaderCircle size={16} className="animate-spin" /> : <Wand2 size={16} />}{isEnglish ? 'One-click format' : '一键自由排版'}</button>
              <button type="button" onClick={() => run('autotag', async () => { const saved = await persist(); const article = await autotagEditorialArticle(saved.id); await refreshAll(article.id); setMessage(isEnglish ? 'Tags refreshed.' : '标签已更新。') })} className="inline-flex items-center gap-2 rounded-full border border-fudan-orange/20 bg-fudan-orange/10 px-4 py-3 text-sm font-semibold text-fudan-orange">{busy === 'autotag' ? <LoaderCircle size={16} className="animate-spin" /> : <Sparkles size={16} />}{isEnglish ? 'Auto tag' : '自动标签'}</button>
              <button type="button" onClick={() => run('render', async () => { const saved = await persist(); await renderEditorialHtml(saved.id); await refreshAll(saved.id); setMessage(isEnglish ? 'Preview generated.' : '预览已生成。') })} className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-600">{busy === 'render' ? <LoaderCircle size={16} className="animate-spin" /> : <Eye size={16} />}{isEnglish ? 'Render preview' : '生成预览'}</button>
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <input name="title" value={form.title} onChange={(e) => setForm((c) => ({ ...c, title: e.target.value }))} placeholder={isEnglish ? 'Title' : '标题'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none xl:col-span-2" />
              <input name="subtitle" value={form.subtitle} onChange={(e) => setForm((c) => ({ ...c, subtitle: e.target.value }))} placeholder={isEnglish ? 'Subtitle' : '副标题'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none xl:col-span-2" />
              <input name="author" value={form.author} onChange={(e) => setForm((c) => ({ ...c, author: e.target.value }))} placeholder={isEnglish ? 'Author' : '作者'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="organization" value={form.organization} onChange={(e) => setForm((c) => ({ ...c, organization: e.target.value }))} placeholder={isEnglish ? 'Organization' : '机构'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="publish_date" type="date" value={form.publish_date} onChange={(e) => setForm((c) => ({ ...c, publish_date: e.target.value }))} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <select name="primary_column_slug" value={form.primary_column_slug} onChange={(e) => setForm((c) => ({ ...c, primary_column_slug: e.target.value }))} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none">{columns.map((item) => <option key={item.slug} value={item.slug}>{item.name || item.slug}</option>)}</select>
              <input name="article_type" value={form.article_type} onChange={(e) => setForm((c) => ({ ...c, article_type: e.target.value }))} placeholder={isEnglish ? 'Article type' : '文章类型'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <input name="main_topic" value={form.main_topic} onChange={(e) => setForm((c) => ({ ...c, main_topic: e.target.value }))} placeholder={isEnglish ? 'Main topic' : '主话题'} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none" />
              <select name="access_level" value={form.access_level} onChange={(e) => setForm((c) => ({ ...c, access_level: e.target.value }))} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"><option value="public">公开</option><option value="member">会员</option><option value="paid">付费</option></select>
              <select name="layout_mode" value={form.layout_mode} onChange={(e) => setForm((c) => ({ ...c, layout_mode: e.target.value }))} className="rounded-[1.1rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none"><option value="auto">自动排版</option><option value="insight">深度长文</option><option value="briefing">快报简报</option><option value="interview">访谈实录</option></select>
              <textarea name="formatting_notes" rows={3} value={form.formatting_notes} onChange={(e) => setForm((c) => ({ ...c, formatting_notes: e.target.value }))} placeholder={isEnglish ? 'Formatting notes for gemini-3-flash-preview' : '给 gemini-3-flash-preview 的排版说明'} className="rounded-[1.2rem] border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-7 outline-none xl:col-span-4" />
            </div>
            <div className="mt-6 grid gap-5 xl:grid-cols-2">
              <div><div className="mb-3 flex items-center justify-between"><div className="section-kicker">{isEnglish ? 'Source draft' : '原稿'}</div><div className="text-sm text-slate-500">{sourceCount} 字</div></div><textarea name="source_markdown" rows={20} value={form.source_markdown} onChange={(e) => setForm((c) => ({ ...c, source_markdown: e.target.value }))} className="w-full rounded-[1.3rem] border border-slate-200 bg-slate-50 px-5 py-4 text-sm leading-7 outline-none" /></div>
              <div><div className="mb-3 flex items-center justify-between"><div className="section-kicker">{isEnglish ? 'Formatted draft' : '排版稿'}</div><div className="text-sm text-slate-500">{contentCount} 字</div></div><textarea name="content_markdown" rows={20} value={form.content_markdown} onChange={(e) => setForm((c) => ({ ...c, content_markdown: e.target.value }))} className="w-full rounded-[1.3rem] border border-slate-200 bg-slate-50 px-5 py-4 text-sm leading-7 outline-none" /></div>
            </div>
          </section>
          <section className="grid gap-6 lg:grid-cols-[1.04fr_.96fr]">
            <div className="fudan-panel overflow-hidden p-6">
              <div className="flex gap-2"><button type="button" onClick={() => setPreviewMode('web')} className={`rounded-full px-4 py-2 text-sm font-semibold ${previewMode === 'web' ? 'bg-fudan-blue text-white' : 'border border-slate-200 bg-white text-slate-500'}`}>Web</button><button type="button" onClick={() => setPreviewMode('wechat')} className={`rounded-full px-4 py-2 text-sm font-semibold ${previewMode === 'wechat' ? 'bg-fudan-blue text-white' : 'border border-slate-200 bg-white text-slate-500'}`}>WeChat</button></div>
              <div className="mt-5 overflow-hidden rounded-[1.6rem] border border-slate-200/70 bg-slate-50"><iframe title="Editorial preview" className="h-[860px] w-full bg-white" srcDoc={previewDoc} /></div>
            </div>
            <div className="space-y-6">
              <div className="fudan-panel p-6"><div className="section-kicker">{isEnglish ? 'Publishing' : '发布信息'}</div><div className="mt-4 rounded-[1.3rem] border border-slate-200/70 bg-slate-50 p-5 text-sm leading-7 text-slate-600"><div>{isEnglish ? 'Status' : '状态'}: {detail?.workflow_label || detail?.workflow_status || 'draft'}</div><div>{isEnglish ? 'Formatter' : '排版模型'}: {detail?.formatter_model || 'gemini-3-flash-preview'}</div><div>{isEnglish ? 'Last formatted' : '最近排版'}: {(detail?.last_formatted_at || '').replace('T', ' ').slice(0, 16) || '未设置'}</div><div>{isEnglish ? 'Live article' : '正式文章'}: {detail?.article_id || '未发布'}</div></div>{detail?.article_id ? <Link to={`/article/${detail.article_id}`} className="mt-4 inline-flex items-center gap-2 rounded-full bg-fudan-blue px-5 py-3 text-sm font-semibold text-white">打开正式文章</Link> : null}{detail?.id && detail?.html_web ? <div className="mt-4 flex flex-wrap gap-3"><a href={editorialHtmlExportUrl(detail.id, 'web')} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue">导出网页 HTML</a><a href={editorialHtmlExportUrl(detail.id, 'wechat')} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-fudan-blue">导出公众号 HTML</a></div> : null}</div>
              <div className="fudan-panel p-6"><div className="section-kicker">{isEnglish ? 'Logic' : '排版逻辑'}</div><div className="mt-4 rounded-[1.2rem] border border-slate-200/70 bg-slate-50 p-4 text-sm leading-7 text-slate-600">{isEnglish ? 'Admin only. Raw draft on the left, formatted draft on the right, gemini-3-flash-preview in the middle, then preview and publish.' : '仅管理员可用。左边原稿，右边排版稿，中间用 gemini-3-flash-preview 自动排版，最后预览并发布。'}</div></div>
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}

export default EditorialWorkbenchPage
