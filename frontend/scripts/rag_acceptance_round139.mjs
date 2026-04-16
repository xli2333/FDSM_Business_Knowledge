import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round139_rag')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round139-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8016
const FRONTEND_PORT = 4181
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

if (await fs.stat(SOURCE_DB_PATH).catch(() => null)) {
  await fs.copyFile(SOURCE_DB_PATH, path.join(TEMP_DATA_DIR, 'fudan_knowledge_base.db'))
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true })
}

function spawnServer(command, args, cwd, extraEnv = {}) {
  const child = spawn(command, args, {
    cwd,
    stdio: 'ignore',
    shell: process.platform === 'win32',
    env: {
      ...process.env,
      ...extraEnv,
    },
  })
  child.on('error', () => {})
  return child
}

function runCommand(command, args, cwd, extraEnv = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: 'ignore',
      shell: process.platform === 'win32',
      env: {
        ...process.env,
        ...extraEnv,
      },
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`${command} ${args.join(' ')} exited with code ${code}`))
    })
  })
}

function terminateProcess(child) {
  return new Promise((resolve) => {
    if (!child?.pid) return resolve()
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      shell: true,
    })
    killer.on('exit', () => resolve())
    killer.on('error', () => resolve())
  })
}

async function waitForHttp(url, timeoutMs = 90000) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  throw new Error(`Timed out waiting for ${url}`)
}

async function openRoute(page, targetPath) {
  const targetUrl = targetPath === '/' ? FRONTEND_URL : `${FRONTEND_URL}${targetPath}`
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 90000 })
  try {
    await page.waitForLoadState('networkidle', { timeout: 15000 })
  } catch {}
  await page.waitForTimeout(600)
}

async function configureLanguage(page, language = 'zh') {
  await page.addInitScript((nextLanguage) => {
    window.localStorage.setItem('fdsm-language', nextLanguage)
  }, language)
}

async function login(page, { email, password, expectedPath }) {
  await configureLanguage(page, 'zh')
  await openRoute(page, '/login')
  await page.locator('input[type="email"]').first().fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  await Promise.all([
    page.waitForURL(`${FRONTEND_URL}${expectedPath}`, { timeout: 30000 }),
    page.locator('form button[type="submit"]').first().click(),
  ])
  await page.waitForTimeout(1000)
}

async function fetchJson(pathname, init = {}) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, init)
  if (!response.ok) {
    throw new Error(`Fetch failed for ${pathname}: ${response.status} ${await response.text()}`)
  }
  return response.json()
}

async function fetchAdminJson(pathname, init = {}) {
  return fetchJson(pathname, {
    ...init,
    headers: {
      'X-Debug-User-Id': 'mock-admin',
      'X-Debug-User-Email': 'admin@example.com',
      ...(init.headers || {}),
    },
  })
}

async function fetchPaidJson(pathname, init = {}) {
  return fetchJson(pathname, {
    ...init,
    headers: {
      'X-Debug-User-Id': 'mock-paid-member',
      'X-Debug-User-Email': 'paid@example.com',
      ...(init.headers || {}),
    },
  })
}

async function readIngestionSnapshot(articleId) {
  const script = `
import json
import os
import sqlite3

db = os.path.join(os.environ['FDSM_DATA_DIR'], 'fudan_knowledge_base.db')
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
article_id = ${articleId}
version = conn.execute(
    "SELECT status, chunk_count, metadata_json FROM article_versions WHERE article_id = ? AND is_current = 1 ORDER BY id DESC LIMIT 1",
    (article_id,),
).fetchone()
embedding_count = conn.execute(
    "SELECT COUNT(*) AS total FROM article_chunk_embeddings WHERE article_id = ?",
    (article_id,),
).fetchone()["total"]
print(json.dumps({
    "version_status": version["status"] if version else None,
    "chunk_count": version["chunk_count"] if version else 0,
    "embedding_count": embedding_count,
}, ensure_ascii=False))
`.trim()
  return new Promise((resolve, reject) => {
    const child = spawn('python', ['-'], {
      cwd: PROJECT_ROOT,
      shell: process.platform === 'win32',
      env: {
        ...process.env,
        FDSM_DATA_DIR: TEMP_DATA_DIR,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    let stdout = ''
    let stderr = ''
    child.stdin.write(script)
    child.stdin.end()
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `python exited with ${code}`))
        return
      }
      resolve(JSON.parse(stdout.trim()))
    })
  })
}

async function main() {
  await ensureDir(OUTPUT_DIR)
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'

  await runCommand(npmCommand, ['run', 'build'], FRONTEND_DIR, {
    VITE_API_BASE_URL: `${BACKEND_URL}/api`,
  })

  const backendProcess = spawnServer(
    'python',
    ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    PROJECT_ROOT,
    {
      FDSM_DATA_DIR: TEMP_DATA_DIR,
      DEV_AUTH_ENABLED: '1',
      ADMIN_EMAILS: 'admin@example.com',
      PAYMENTS_ENABLED: '0',
      PAYMENT_PROVIDER: 'mock',
      RAG_CHUNK_EMBEDDINGS_ENABLED: '1',
    },
  )

  const previewProcess = spawnServer(
    npmCommand,
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    FRONTEND_DIR,
  )

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const browser = await chromium.launch()
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
    const adminPage = await adminContext.newPage()
    await login(adminPage, {
      email: 'admin@example.com',
      password: 'Admin2026!',
      expectedPath: '/admin',
    })
    await openRoute(adminPage, '/editorial')
    await adminPage.getByRole('button', { name: /自动排版|Auto format/i }).first().waitFor({ timeout: 30000 })
    await adminPage.screenshot({ path: path.join(OUTPUT_DIR, 'admin_editorial_page.png') })

    const uniqueSuffix = String(Date.now()).slice(-6)
    const title = `AI 经营驾驶舱正在取代周报 ${uniqueSuffix}`
    const summaryMarkdown = [
      '### 核心摘要',
      '',
      '- **经营驾驶舱** 取代传统周报后，管理层开始按实时指标推进复盘。',
      '- **模型调用预算**、**周复盘机制** 和 **负责人追责链路** 被写进同一张经营表。',
    ].join('\n')
    const summaryHtml = `<div class="summary-preview-shell"><h3>核心摘要</h3><ul><li><strong>经营驾驶舱</strong> 取代传统周报后，管理层开始按实时指标推进复盘。</li><li><strong>模型调用预算</strong>、<strong>周复盘机制</strong> 和 <strong>负责人追责链路</strong> 被写进同一张经营表。</li></ul></div>`
    const finalHtml = `<div class="wechat-preview-shell"><section><h1>${title}</h1><p>这篇新文章讨论一家消费科技公司如何把经营驾驶舱放到管理中枢。</p><p>文章提出三个变化：第一，管理层不再依赖周报，而是每天查看经营驾驶舱；第二，模型调用预算和 ROI 被放进经营驾驶舱；第三，周复盘机制和负责人追责链路被绑定到同一套决策节奏里。</p></section></div>`
    const createPayload = {
      title,
      author: 'FDSM Rag Acceptance',
      organization: 'Fudan Business Knowledge',
      publish_date: '2026-04-16',
      source_markdown: [
        `${title}`,
        '',
        '这篇新文章讨论一家消费科技公司如何把经营驾驶舱放到管理中枢。',
        '文章提出三个变化：第一，管理层不再依赖周报，而是每天查看经营驾驶舱；第二，模型调用预算和 ROI 被放进经营驾驶舱；第三，周复盘机制和负责人追责链路被绑定到同一套决策节奏里。',
      ].join('\n'),
      content_markdown: [
        `${title}`,
        '',
        '这篇新文章讨论一家消费科技公司如何把经营驾驶舱放到管理中枢。',
        '文章提出三个变化：第一，管理层不再依赖周报，而是每天查看经营驾驶舱；第二，模型调用预算和 ROI 被放进经营驾驶舱；第三，周复盘机制和负责人追责链路被绑定到同一套决策节奏里。',
      ].join('\n'),
      excerpt: '经营驾驶舱、模型调用预算与周复盘机制正在重写消费科技公司的管理节奏。',
      primary_column_slug: 'insights',
      primary_column_manual: true,
      tags: [
        { name: 'AI/人工智能', slug: 'ai', category: 'topic', confidence: 0.98 },
        { name: '数字化转型', slug: 'digital', category: 'topic', confidence: 0.9 },
      ],
      summary_markdown: summaryMarkdown,
      summary_html: summaryHtml,
      summary_editor_document: { schema: 'editable-html-v1', html: summaryHtml },
      final_html: finalHtml,
      editor_document: { schema: 'editable-html-v1', html: finalHtml },
    }

    const created = await fetchAdminJson('/api/editorial/articles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createPayload),
    })
    const published = await fetchAdminJson(`/api/editorial/articles/${created.id}/publish`, {
      method: 'POST',
    })
    if (!published.article_id) {
      throw new Error('Admin publish did not return article_id')
    }

    const ingestionSnapshot = await readIngestionSnapshot(published.article_id)
    if (ingestionSnapshot.version_status !== 'ready') {
      throw new Error(`Published article ingestion is not ready: ${JSON.stringify(ingestionSnapshot)}`)
    }
    if (Number(ingestionSnapshot.chunk_count) < 1 || Number(ingestionSnapshot.embedding_count) < 1) {
      throw new Error(`Published article missing chunks or embeddings: ${JSON.stringify(ingestionSnapshot)}`)
    }

    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const paidPage = await paidContext.newPage()
    const themeTitle = `RAG 验收主题 ${uniqueSuffix}`

    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })
    await openRoute(paidPage, `/article/${published.article_id}`)
    await paidPage.locator('[data-testid="article-page-shell"]').waitFor({ timeout: 30000 })
    await paidPage.locator('[data-knowledge-open-modal]').click()
    await paidPage.locator('[data-knowledge-article-modal]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-create-title]').fill(themeTitle)
    await paidPage.getByRole('button', { name: /创建主题并加入本文|Create and add this article/i }).click()

    let paidThemes = null
    const startedAt = Date.now()
    while (Date.now() - startedAt < 30000) {
      paidThemes = await fetchPaidJson('/api/me/knowledge/themes')
      const match = (paidThemes.items || []).find((item) => item.title === themeTitle)
      if (match?.slug) break
      await paidPage.waitForTimeout(1000)
    }
    const createdTheme = (paidThemes?.items || []).find((item) => item.title === themeTitle)
    if (!createdTheme?.slug) {
      throw new Error('User theme was not created from the published article page')
    }

    await openRoute(paidPage, `/me/knowledge/${createdTheme.slug}`)
    await paidPage.locator(`[data-knowledge-theme-page="${createdTheme.slug}"]`).waitFor({ timeout: 30000 })
    await paidPage.locator('[data-knowledge-chat-panel]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-clear-selection]').click()
    await paidPage.locator('[data-knowledge-article-toggle]').first().click()
    await paidPage.locator('[data-knowledge-chat-panel] textarea').fill('这篇新文章里，经营驾驶舱取代周报之后，管理层最先改变的是哪三件事？')
    await paidPage.locator('[data-knowledge-chat-panel] button[aria-label="发送"]').click()
    await paidPage.waitForFunction(() => document.querySelectorAll('[data-knowledge-chat-message="assistant"]').length >= 2, null, {
      timeout: 120000,
    })

    const latestAssistantText = await paidPage.locator('[data-knowledge-chat-message="assistant"]').last().innerText()
    if (!latestAssistantText || latestAssistantText.length < 40) {
      throw new Error('Assistant answer is too short for the RAG acceptance flow')
    }
    if (latestAssistantText.includes('**')) {
      throw new Error('Assistant answer still rendered raw markdown markers')
    }
    if (/\[(?:\d{1,3})\]/.test(latestAssistantText)) {
      throw new Error('Assistant answer still rendered raw citation markers')
    }
    if ((await paidPage.locator('[data-knowledge-chat-panel] a[href^="/article/"]').count()) !== 0) {
      throw new Error('Assistant answer still rendered visible source links')
    }
    const requiredSignal = ['经营驾驶舱', '模型调用预算', '周复盘机制', '负责人追责链路']
    if (!requiredSignal.some((token) => latestAssistantText.includes(token))) {
      throw new Error(`Assistant answer did not mention any expected signal: ${latestAssistantText}`)
    }

    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_rag_theme_page.png') })
    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
  }
}

await main()
