import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round140_markdown')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round140-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8017
const FRONTEND_PORT = 4182
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

async function waitForHttp(url, timeoutMs = 60000) {
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
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
  try {
    await page.waitForLoadState('networkidle', { timeout: 12000 })
  } catch {}
  await page.waitForTimeout(500)
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
  await page.waitForTimeout(800)
}

async function fetchJson(pathname, init = {}) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, init)
  if (!response.ok) {
    throw new Error(`Fetch failed for ${pathname}: ${response.status} ${await response.text()}`)
  }
  return response.json()
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

async function seedChatSession(sessionId, title, lastQuestion, assistantAnswer) {
  const script = `
import json
import os
import sqlite3

db = os.path.join(os.environ['FDSM_DATA_DIR'], 'fudan_knowledge_base.db')
conn = sqlite3.connect(db)
timestamp = '2026-04-16T10:00:00'
conn.execute(
    "INSERT OR REPLACE INTO chat_sessions (id, title, created_at, updated_at, last_question) VALUES (?, ?, ?, ?, ?)",
    (${JSON.stringify(sessionId)}, ${JSON.stringify(title)}, timestamp, timestamp, ${JSON.stringify(lastQuestion)}),
)
conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (${JSON.stringify(sessionId)},))
conn.execute(
    "INSERT INTO chat_messages (session_id, role, content, sources_json, follow_ups_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
    (${JSON.stringify(sessionId)}, 'user', ${JSON.stringify(lastQuestion)}, '[]', '[]', timestamp),
)
conn.execute(
    "INSERT INTO chat_messages (session_id, role, content, sources_json, follow_ups_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
    (${JSON.stringify(sessionId)}, 'assistant', ${JSON.stringify(assistantAnswer)}, '[]', json.dumps(['请继续压缩成三点判断'], ensure_ascii=False), timestamp),
)
conn.commit()
conn.close()
`.trim()

  await new Promise((resolve, reject) => {
    const child = spawn('python', ['-'], {
      cwd: PROJECT_ROOT,
      shell: process.platform === 'win32',
      env: {
        ...process.env,
        FDSM_DATA_DIR: TEMP_DATA_DIR,
      },
      stdio: ['pipe', 'ignore', 'pipe'],
    })
    let stderr = ''
    child.stdin.write(script)
    child.stdin.end()
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(stderr || `python exited with ${code}`))
    })
  })
}

function buildSelectionScopeKey(articleIds = []) {
  return [...new Set((articleIds || []).map((item) => Number(item)).filter((item) => Number.isFinite(item) && item > 0))]
    .sort((left, right) => left - right)
    .join('-')
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

    const latestArticles = await fetchJson('/api/articles/latest?limit=6&offset=0&language=zh')
    const [firstArticle, secondArticle] = Array.isArray(latestArticles) ? latestArticles.filter((item) => item?.id).slice(0, 2) : []
    if (!firstArticle?.id) {
      throw new Error('No article available for markdown acceptance')
    }

    const createdTheme = await fetchPaidJson('/api/me/knowledge/themes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: `markdown-acceptance-${String(Date.now()).slice(-6)}`,
        description: '用于主题聊天 Markdown 表格验收',
        initial_article_id: firstArticle.id,
      }),
    })

    if (secondArticle?.id) {
      await fetchPaidJson(`/api/me/knowledge/themes/${createdTheme.id}/articles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ article_id: secondArticle.id }),
      })
    }

    const themeDetail = await fetchPaidJson(`/api/me/knowledge/themes/${createdTheme.slug}`)
    const selectedArticleIds = (themeDetail.articles || []).map((item) => item.id)
    const selectionScopeKey = buildSelectionScopeKey(selectedArticleIds)
    const knowledgeMessages = [
      {
        role: 'user',
        content: '请给我一个表格版总结',
        sources: [],
        followUps: [],
      },
      {
        role: 'assistant',
        content: [
          '### 总结对比',
          '',
          '| 维度 | 判断 |',
          '| --- | --- |',
          '| 当前动作 | 管理层先把周报改成经营驾驶舱 [1][2] |',
          '| 后续节奏 | 周复盘改成固定复盘节奏 [3] |',
        ].join('\n'),
        sources: [],
        followUps: ['请继续压缩成三点判断'],
      },
    ]

    const assistantSessionId = `round140-${Date.now()}`
    const assistantTitle = 'Markdown 表格验收会话'
    await seedChatSession(
      assistantSessionId,
      assistantTitle,
      '请把这段结论整理成表格',
      [
        '### 对照表',
        '',
        '| 维度 | 结论 |',
        '| --- | --- |',
        '| 结论一 | 经营驾驶舱取代周报 [1] |',
        '| 结论二 | 周复盘改成固定节奏 [2][3] |',
      ].join('\n'),
    )

    const browser = await chromium.launch()
    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const paidPage = await paidContext.newPage()

    await paidContext.addInitScript(
      ({ themeSlug, scopeKey, messages }) => {
        window.localStorage.setItem(`fdsm-knowledge-theme-chat-${themeSlug}-${scopeKey}`, JSON.stringify(messages))
      },
      {
        themeSlug: createdTheme.slug,
        scopeKey: selectionScopeKey,
        messages: knowledgeMessages,
      },
    )

    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })

    await openRoute(paidPage, `/me/knowledge/${createdTheme.slug}`)
    await paidPage.locator(`[data-knowledge-theme-page="${createdTheme.slug}"]`).waitFor({ timeout: 20000 })
    await paidPage.locator('[data-knowledge-chat-message="assistant"] table').last().waitFor({ timeout: 15000 })
    const knowledgeRender = await paidPage.evaluate(() => {
      const assistantBlocks = Array.from(document.querySelectorAll('[data-knowledge-chat-message="assistant"] [data-assistant-markdown]'))
      const latest = assistantBlocks.at(-1)
      return {
        tableCount: latest?.querySelectorAll('table').length || 0,
        rawPipeSyntax: /\|\s*维度\s*\|/.test(latest?.innerText || '') || /\|\s*---\s*\|/.test(latest?.innerText || ''),
        citationMarkers: /\[(?:\d{1,3})\]/.test(latest?.innerText || ''),
        sourceLinks: document.querySelectorAll('[data-knowledge-chat-panel] a[href^="/article/"]').length,
      }
    })
    if (knowledgeRender.tableCount < 1 || knowledgeRender.rawPipeSyntax || knowledgeRender.citationMarkers || knowledgeRender.sourceLinks > 0) {
      throw new Error(`Knowledge theme markdown rendering failed: ${JSON.stringify(knowledgeRender)}`)
    }
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'knowledge_theme_markdown.png') })

    await openRoute(paidPage, '/chat')
    await paidPage.locator('[data-chat-panel="page"]').waitFor({ timeout: 15000 })
    await paidPage.locator('aside button').filter({ hasText: assistantTitle }).first().click()
    await paidPage.locator('[data-chat-message="assistant"] table').last().waitFor({ timeout: 15000 })
    const assistantRender = await paidPage.evaluate(() => {
      const assistantBlocks = Array.from(document.querySelectorAll('[data-chat-message="assistant"] [data-assistant-markdown]'))
      const latest = assistantBlocks.at(-1)
      return {
        tableCount: latest?.querySelectorAll('table').length || 0,
        rawPipeSyntax: /\|\s*维度\s*\|/.test(latest?.innerText || '') || /\|\s*---\s*\|/.test(latest?.innerText || ''),
        citationMarkers: /\[(?:\d{1,3})\]/.test(latest?.innerText || ''),
        sourceLinks: document.querySelectorAll('[data-chat-panel="page"] a[href^="/article/"]').length,
      }
    })
    if (assistantRender.tableCount < 1 || assistantRender.rawPipeSyntax || assistantRender.citationMarkers || assistantRender.sourceLinks > 0) {
      throw new Error(`Assistant markdown rendering failed: ${JSON.stringify(assistantRender)}`)
    }
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'assistant_chat_markdown.png') })

    await paidContext.close()
    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true }).catch(() => {})
  }
}

await main()
