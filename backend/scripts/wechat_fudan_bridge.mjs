import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const PROJECT_ROOT = path.resolve(__dirname, '..', '..')
const WECHAT_SERVICE_PATH = path.join(PROJECT_ROOT, '公众号排版', 'server', 'wechatOfficialPublisherService.mjs')

const { generateWechatDraftPreview } = await import(pathToFileURL(WECHAT_SERVICE_PATH).href)

function normalizeText(value) {
  return String(value ?? '').trim()
}

function normalizeLines(value) {
  if (!Array.isArray(value)) return []
  return value.map((item) => normalizeText(item)).filter(Boolean)
}

function stripLeadingCreditsBlock(html, omitCredits) {
  if (!omitCredits) return String(html || '')
  return String(html || '').replace(
    /(<article[^>]*>\s*)<section style="margin: 0 0 28px; padding: 0;">[\s\S]*?<\/section>/,
    '$1',
  )
}

function buildLayout(item) {
  return {
    templateId: 'fudan_business_knowledge',
    author: normalizeText(item.author),
    editor: normalizeText(item.editor),
    digest: normalizeText(item.summary),
    contentSourceUrl: normalizeText(item.source_url),
    creditLines: normalizeLines(item.credit_lines),
    openingHighlightMode: normalizeText(item.opening_highlight_mode) || 'smart_lead',
    needOpenComment: false,
    onlyFansCanComment: false,
  }
}

async function renderItem(item) {
  const title = normalizeText(item.title) || 'Untitled'
  const articleContent = normalizeText(item.content_markdown || item.article_content)
  const omitCredits = item.omit_credits !== false

  const preview = await generateWechatDraftPreview({
    topic: title,
    articleContent,
    illustrationBundle: {
      slots: [],
      assets: [],
      assetVersions: {},
    },
    layout: buildLayout(item),
    apiKey: normalizeText(item.api_key),
    renderPlan: item.render_plan && typeof item.render_plan === 'object' ? item.render_plan : undefined,
  })

  const contentHtml = stripLeadingCreditsBlock(preview.contentHtml || '', omitCredits)
  const previewHtml = stripLeadingCreditsBlock(preview.previewHtml || '', omitCredits)

  return {
    title,
    contentHtml,
    previewHtml,
    renderPlan: preview.renderPlan || {},
    metadata: preview.metadata || {},
    warnings: Array.isArray(preview.warnings) ? preview.warnings : [],
  }
}

async function readStdin() {
  const chunks = []
  for await (const chunk of process.stdin) {
    chunks.push(chunk)
  }
  return Buffer.concat(chunks).toString('utf8').trim()
}

async function main() {
  const raw = await readStdin()
  const payload = raw ? JSON.parse(raw) : {}
  const items = Array.isArray(payload.items) ? payload.items : [payload]
  const results = []

  for (const item of items) {
    results.push(await renderItem(item || {}))
  }

  process.stdout.write(JSON.stringify({ results }, null, 2))
}

main().catch((error) => {
  const message = error instanceof Error ? `${error.message}\n${error.stack || ''}` : String(error)
  process.stderr.write(message)
  process.exitCode = 1
})
