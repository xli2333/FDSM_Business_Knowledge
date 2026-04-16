import { Activity, Bot, Boxes, Clock3, Database, Link2, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchAdminRagOverview } from '../api/index.js'
import { useAuth } from '../auth/AuthContext.js'
import { useLanguage } from '../i18n/LanguageContext.js'

function MetricCard({ label, value, detail }) {
  return (
    <div className="fudan-panel p-6">
      <div className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</div>
      <div className="mt-3 font-serif text-4xl font-black text-fudan-blue">{value}</div>
      <div className="mt-2 text-sm leading-7 text-slate-500">{detail}</div>
    </div>
  )
}

function RagAdminPage() {
  const { accessToken } = useAuth()
  const { isEnglish } = useLanguage()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const copy = isEnglish
    ? {
        kicker: 'RAG Console',
        title: 'Track chunk assets, embedding jobs, and retrieval activity',
        body: 'Use one admin surface to verify which public articles have entered the chunk corpus, when they were processed, and whether recent retrieval traffic is healthy.',
        latestProcessed: 'Latest processed article',
        notProcessed: 'No processed article yet',
        latestAssets: 'Latest assets',
        latestAssetsTitle: 'Newest chunked articles',
        latestJobs: 'Latest jobs',
        latestJobsTitle: 'Ingestion queue and job outcomes',
        retrievals: 'Retrieval events',
        retrievalsTitle: 'Recent retrieval traffic',
        answers: 'Answer events',
        answersTitle: 'Recent answer generation',
        currentVersions: 'Current versions',
        openArticle: 'Open article',
        articleId: 'Article ID',
        versionStatus: 'Version status',
        jobStatus: 'Job',
        chunks: 'Chunks',
        embeddings: 'Embeddings',
        provider: 'Provider',
        processedAt: 'Processed at',
        updatedAt: 'Updated at',
        stage: 'Stage',
        trigger: 'Trigger',
        sources: 'Source articles',
        noAssets: 'No RAG assets yet.',
        noJobs: 'No ingestion jobs yet.',
        noRetrievals: 'No retrieval events yet.',
        noAnswers: 'No answer events yet.',
        failed: 'Failed jobs',
        pending: 'Pending jobs',
        healthy: 'Ready articles',
        processing: 'Processing articles',
        totalChunks: 'Total chunks',
        totalEmbeddings: 'Total embeddings',
        healthyDetail: 'Current public articles with a ready chunk version.',
        processingDetail: 'Current public articles still pending or rebuilding.',
        chunkDetail: 'All current chunks across the public corpus.',
        embeddingDetail: 'Stored chunk embeddings across current versions.',
        pendingDetail: 'Queued ingestion jobs waiting for processing.',
        failedDetail: 'Failed jobs that still need attention.',
        loading: 'Loading RAG console...',
        loadFailed: 'Failed to load the RAG console.',
      }
    : {
        kicker: 'RAG 后台',
        title: '跟踪切片资产、embedding 任务和检索流量',
        body: '这里专门给管理员查看公开文章是否已经进入 chunk 语料、什么时候处理完成，以及最近检索和回答链路是否正常。',
        latestProcessed: '最近一次处理',
        notProcessed: '暂时还没有处理完成的文章',
        latestAssets: '最新资产',
        latestAssetsTitle: '最新进入切片语料的文章',
        latestJobs: '最新任务',
        latestJobsTitle: '入库任务与处理结果',
        retrievals: '检索事件',
        retrievalsTitle: '最近检索流量',
        answers: '回答事件',
        answersTitle: '最近回答生成',
        currentVersions: '现行版本',
        openArticle: '打开文章',
        articleId: '文章 ID',
        versionStatus: '版本状态',
        jobStatus: '任务',
        chunks: '切片数',
        embeddings: '向量数',
        provider: '向量提供方',
        processedAt: '处理时间',
        updatedAt: '更新时间',
        stage: '阶段',
        trigger: '触发来源',
        sources: '命中文章',
        noAssets: '当前还没有 RAG 资产。',
        noJobs: '当前还没有入库任务。',
        noRetrievals: '当前还没有检索事件。',
        noAnswers: '当前还没有回答事件。',
        failed: '失败任务',
        pending: '排队任务',
        healthy: '就绪文章',
        processing: '处理中文章',
        totalChunks: '总切片数',
        totalEmbeddings: '总向量数',
        healthyDetail: '当前已经完成 chunk 版本并可用于检索的公开文章。',
        processingDetail: '当前仍在排队、处理中或重建中的公开文章。',
        chunkDetail: '当前公开语料里所有现行版本的切片总数。',
        embeddingDetail: '当前公开语料里所有现行版本的向量总数。',
        pendingDetail: '当前还在等待处理的入库任务数。',
        failedDetail: '当前失败且还需要人工关注的任务数。',
        loading: '正在加载 RAG 后台...',
        loadFailed: 'RAG 后台加载失败。',
      }

  useEffect(() => {
    setLoading(true)
    fetchAdminRagOverview(accessToken)
      .then((payload) => {
        setData(payload)
        setError('')
      })
      .catch((err) => {
        setError(err?.message || copy.loadFailed)
      })
      .finally(() => setLoading(false))
  }, [accessToken, copy.loadFailed])

  const latestProcessedAt = useMemo(() => data?.latest_processed_at || null, [data])
  const metrics = useMemo(
    () => [
      {
        label: copy.healthy,
        value: data?.ready_article_count ?? 0,
        detail: copy.healthyDetail,
      },
      {
        label: copy.processing,
        value: data?.processing_article_count ?? 0,
        detail: copy.processingDetail,
      },
      {
        label: copy.totalChunks,
        value: data?.total_chunk_count ?? 0,
        detail: copy.chunkDetail,
      },
      {
        label: copy.totalEmbeddings,
        value: data?.total_embedding_count ?? 0,
        detail: copy.embeddingDetail,
      },
      {
        label: copy.pending,
        value: data?.pending_job_count ?? 0,
        detail: copy.pendingDetail,
      },
      {
        label: copy.failed,
        value: data?.failed_job_count ?? 0,
        detail: copy.failedDetail,
      },
    ],
    [copy, data],
  )

  return (
    <div className="page-shell py-12">
      <section className="fudan-panel overflow-hidden">
        <div className="grid gap-8 bg-[linear-gradient(135deg,rgba(13,7,131,0.98),rgba(10,5,96,0.88)_58%,rgba(234,107,0,0.18))] px-8 py-10 text-white md:px-10 md:py-12 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="section-kicker !text-white/72">{copy.kicker}</div>
            <h1 className="font-serif text-4xl font-black leading-tight text-white md:text-6xl">{copy.title}</h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-white/84">{copy.body}</p>
          </div>

          <div className="grid gap-4 self-start md:grid-cols-2 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-white/65">
                <Clock3 size={14} />
                {copy.latestProcessed}
              </div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{latestProcessedAt || copy.notProcessed}</div>
            </div>
            <div className="rounded-[1.4rem] border border-white/12 bg-white/10 p-5 backdrop-blur">
              <div className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-white/65">
                <Database size={14} />
                {copy.currentVersions}
              </div>
              <div className="mt-3 font-serif text-3xl font-black text-white">{data?.current_version_count ?? 0}</div>
            </div>
          </div>
        </div>
      </section>

      {error ? <div className="mt-6 text-sm text-red-500">{error}</div> : null}
      {loading ? (
        <div className="mt-6 inline-flex items-center gap-2 text-sm text-slate-500">
          <RefreshCw size={16} className="animate-spin" />
          {copy.loading}
        </div>
      ) : null}

      <section className="mt-8 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} label={metric.label} value={metric.value} detail={metric.detail} />
        ))}
      </section>

      <section className="mt-8 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
                <Boxes size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.latestAssets}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.latestAssetsTitle}</h2>
              </div>
            </div>

            <div className="mt-5 space-y-4">
              {(data?.latest_assets || []).length ? (
                data.latest_assets.map((item) => (
                  <div key={`${item.article_id}-${item.version_id || 'none'}`} className="rounded-[1.3rem] border border-slate-200 bg-slate-50/70 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="font-serif text-2xl font-black text-fudan-blue">{item.title}</div>
                        <div className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                          {copy.articleId} #{item.article_id} · {item.publish_date}
                        </div>
                      </div>
                      <Link
                        to={`/article/${item.article_id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-fudan-blue transition hover:border-fudan-blue/30"
                      >
                        <Link2 size={15} />
                        {copy.openArticle}
                      </Link>
                    </div>

                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.versionStatus}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">{item.version_status || '-'}</div>
                      </div>
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.chunks}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">{item.chunk_count}</div>
                      </div>
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.embeddings}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">{item.embedding_count}</div>
                      </div>
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.provider}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">{item.embedding_provider || '-'}</div>
                      </div>
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.processedAt}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">{item.ingested_at || '-'}</div>
                      </div>
                      <div className="rounded-[1rem] border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
                        <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400">{copy.jobStatus}</div>
                        <div className="mt-2 font-semibold text-fudan-blue">
                          {[item.latest_job_status, item.latest_job_stage].filter(Boolean).join(' / ') || '-'}
                        </div>
                      </div>
                    </div>

                    {item.latest_job_error ? <div className="mt-3 text-sm leading-7 text-red-500">{item.latest_job_error}</div> : null}
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm text-slate-500">{copy.noAssets}</div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-fudan-orange/10 p-3 text-fudan-orange">
                <Activity size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.latestJobs}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.latestJobsTitle}</h2>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {(data?.latest_jobs || []).length ? (
                data.latest_jobs.map((job) => (
                  <div key={job.id} className="rounded-[1.2rem] border border-slate-200 bg-slate-50 p-4">
                    <div className="font-semibold text-fudan-blue">{job.title}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">
                      {copy.stage}: {job.stage} · {copy.trigger}: {job.trigger_source}
                    </div>
                    <div className="text-sm leading-7 text-slate-600">
                      {copy.chunks} {job.chunk_count} · {copy.embeddings} {job.embedding_count}
                    </div>
                    <div className="text-sm leading-7 text-slate-500">
                      {copy.updatedAt}: {job.completed_at || job.updated_at}
                    </div>
                    {job.error_message ? <div className="mt-2 text-sm leading-7 text-red-500">{job.error_message}</div> : null}
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm text-slate-500">{copy.noJobs}</div>
              )}
            </div>
          </div>

          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-fudan-blue/10 p-3 text-fudan-blue">
                <RefreshCw size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.retrievals}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.retrievalsTitle}</h2>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {(data?.recent_retrievals || []).length ? (
                data.recent_retrievals.map((event, index) => (
                  <div key={`${event.created_at}-${index}`} className="rounded-[1.2rem] border border-slate-200 bg-white p-4">
                    <div className="font-semibold text-fudan-blue">{event.query}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">
                      {event.scope_type} · {event.provider}
                    </div>
                    <div className="text-sm leading-7 text-slate-500">
                      {copy.chunks} {event.returned_chunk_count} · {copy.sources} {event.returned_article_count} · {event.latency_ms}ms
                    </div>
                    <div className="text-sm leading-7 text-slate-500">{event.created_at}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm text-slate-500">{copy.noRetrievals}</div>
              )}
            </div>
          </div>

          <div className="fudan-panel p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-emerald-50 p-3 text-emerald-700">
                <Bot size={18} />
              </div>
              <div>
                <div className="section-kicker">{copy.answers}</div>
                <h2 className="font-serif text-3xl font-black text-fudan-blue">{copy.answersTitle}</h2>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {(data?.recent_answers || []).length ? (
                data.recent_answers.map((event, index) => (
                  <div key={`${event.created_at}-${index}`} className="rounded-[1.2rem] border border-slate-200 bg-white p-4">
                    <div className="font-semibold text-fudan-blue">{event.question}</div>
                    <div className="mt-2 text-sm leading-7 text-slate-600">
                      {event.scope_type} · {event.answer_model || '-'}
                    </div>
                    <div className="text-sm leading-7 text-slate-500">
                      {copy.sources} {event.source_article_count} · {copy.chunks} {event.source_chunk_count}
                    </div>
                    <div className="text-sm leading-7 text-slate-500">{event.created_at}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.2rem] border border-dashed border-slate-300 p-5 text-sm text-slate-500">{copy.noAnswers}</div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

export default RagAdminPage
