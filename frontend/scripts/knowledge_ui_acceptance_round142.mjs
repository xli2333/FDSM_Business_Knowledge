import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round142_knowledge_ui')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round142-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8019
const FRONTEND_PORT = 4184
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

async function seedChatSession(sessionId, title, lastQuestion, assistantAnswer, followUps = []) {
  const script = `
import json
import os
import sqlite3

db = os.path.join(os.environ['FDSM_DATA_DIR'], 'fudan_knowledge_base.db')
conn = sqlite3.connect(db)
timestamp = '2026-04-16T11:10:00'
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
    (${JSON.stringify(sessionId)}, 'assistant', ${JSON.stringify(assistantAnswer)}, '[]', json.dumps(${JSON.stringify(followUps)}, ensure_ascii=False), timestamp),
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

function buildBrokenMarkdownSample() {
  return [
    '1. 核心主题与关注对象',
    '',
    '- *提出一个体创造力： 研究表明，生成式AI能显著提升个体作者的创作水准。',
    '- 《重新定义护城河：AI变革中的于英涛与新华三》：聚焦于**新华三集团（H3C）**及其掌舵人于英涛。',
    '- *人机共创：* 未来的文学创作可能演变为“人机共创”。',
  ].join('\n')
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
      GEMINI_API_KEY: '',
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
    const article = Array.isArray(latestArticles) ? latestArticles.find((item) => item?.id) : null
    if (!article?.id) {
      throw new Error('No article available for round142 acceptance')
    }

    const uniqueSuffix = String(Date.now()).slice(-6)
    const initialTitle = `round142-theme-${uniqueSuffix}`
    const renamedTitle = `round142-empty-desc-${uniqueSuffix}`
    const theme = await fetchPaidJson('/api/me/knowledge/themes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: initialTitle,
        description: '用于 round142 UI 验收的主题简介',
        initial_article_id: article.id,
      }),
    })
    const themeDetail = await fetchPaidJson(`/api/me/knowledge/themes/${theme.slug}`)
    const selectedArticleIds = (themeDetail.articles || []).map((item) => item.id)
    const scopeKey = buildSelectionScopeKey(selectedArticleIds)
    const brokenMarkdown = buildBrokenMarkdownSample()

    const assistantSessionId = `round142-${Date.now()}`
    const assistantSessionTitle = 'round142 助理验收会话'
    await seedChatSession(
      assistantSessionId,
      assistantSessionTitle,
      '请总结这一组知识点',
      brokenMarkdown,
      ['请继续压缩成三点判断'],
    )

    const browser = await chromium.launch()
    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const paidPage = await paidContext.newPage()

    await paidContext.addInitScript(
      ({ themeSlug, selectionScopeKey, assistantContent }) => {
        window.localStorage.setItem('fdsm-language', 'zh')
        window.localStorage.setItem(
          `fdsm-knowledge-theme-chat-${themeSlug}-${selectionScopeKey}`,
          JSON.stringify([
            { role: 'user', content: '请先总结这组材料', sources: [], followUps: [] },
            { role: 'assistant', content: assistantContent, sources: [], followUps: ['请继续追问这组材料'] },
          ]),
        )
      },
      {
        themeSlug: theme.slug,
        selectionScopeKey: scopeKey,
        assistantContent: brokenMarkdown,
      },
    )

    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })

    await openRoute(paidPage, '/')
    const homeState = await paidPage.evaluate(() => {
      const section = Array.from(document.querySelectorAll('.fudan-panel')).find((panel) => panel.innerText.includes('立即体验'))
      const titles = section ? Array.from(section.querySelectorAll('a')).map((item) => item.innerText) : []
      const knowledgeLink = section ? Array.from(section.querySelectorAll('a')).find((item) => item.innerText.includes('知识库系统')) : null
      return {
        hasKnowledgeSystem: titles.some((item) => item.includes('知识库系统')),
        hasTimeMachine: titles.some((item) => item.includes('时光机')),
        knowledgeHref: knowledgeLink?.getAttribute('href') || '',
      }
    })
    if (!homeState.hasKnowledgeSystem || homeState.hasTimeMachine || homeState.knowledgeHref !== '/me/knowledge') {
      throw new Error(`Home knowledge system card validation failed: ${JSON.stringify(homeState)}`)
    }
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'home_knowledge_system_card.png') })

    await openRoute(paidPage, `/me/knowledge/${theme.slug}`)
    await paidPage.locator(`[data-knowledge-theme-page="${theme.slug}"]`).waitFor({ timeout: 15000 })

    const themeRenderState = await paidPage.evaluate(() => {
      const panel = document.querySelector('[data-knowledge-chat-panel]')
      const latest = Array.from(document.querySelectorAll('[data-knowledge-chat-message="assistant"] [data-assistant-markdown]')).at(-1)
      return {
        hasContinueLabel: Boolean(panel?.innerText.includes('继续追问')),
        hasFollowUpButton: Array.from(panel?.querySelectorAll('button') || []).some((button) => button.innerText.includes('请继续追问这组材料')),
        rawDoubleStars: Boolean(latest?.innerText.includes('**新华三集团（H3C）**') || latest?.innerText.includes('*提出一个体创造力') || latest?.innerText.includes('*人机共创')),
        strongCount: latest?.querySelectorAll('strong').length || 0,
        text: latest?.innerText || '',
        html: latest?.innerHTML || '',
      }
    })
    if (themeRenderState.hasContinueLabel || themeRenderState.hasFollowUpButton || themeRenderState.rawDoubleStars || themeRenderState.strongCount < 3) {
      throw new Error(`Knowledge theme render validation failed: ${JSON.stringify(themeRenderState)}`)
    }

    await paidPage.locator('[data-knowledge-theme-open-rename]').click()
    await paidPage.locator('[data-knowledge-theme-rename-modal]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-theme-rename-title]').fill('')
    await paidPage.locator('[data-knowledge-theme-rename-description]').fill('')
    const saveDisabledWhenTitleEmpty = await paidPage.locator('[data-knowledge-theme-rename-save]').isDisabled()
    if (!saveDisabledWhenTitleEmpty) {
      throw new Error('Theme rename save button stayed enabled when title was empty')
    }
    await paidPage.locator('[data-knowledge-theme-rename-title]').fill(renamedTitle)
    await Promise.all([
      paidPage.waitForURL(new RegExp(`${FRONTEND_URL}/me/knowledge/${renamedTitle}$`), { timeout: 20000 }),
      paidPage.locator('[data-knowledge-theme-rename-save]').click(),
    ])
    await paidPage.locator('[data-knowledge-theme-rename-modal]').waitFor({ state: 'hidden', timeout: 15000 })
    await paidPage.waitForFunction(
      (expectedTitle) => document.querySelector('[data-knowledge-theme-page] h1')?.textContent?.trim() === expectedTitle,
      renamedTitle,
      { timeout: 15000 },
    )

    const themeRenameState = await paidPage.evaluate(() => ({
      title: document.querySelector('[data-knowledge-theme-page] h1')?.textContent?.trim() || '',
      subtitleCount: document.querySelectorAll('[data-knowledge-theme-page] .knowledge-console-subtitle').length,
      subtitleText: document.querySelector('[data-knowledge-theme-page] .knowledge-console-subtitle')?.textContent?.trim() || '',
    }))
    if (themeRenameState.title !== renamedTitle || themeRenameState.subtitleCount !== 0 || themeRenameState.subtitleText) {
      throw new Error(`Theme rename blank-description validation failed: ${JSON.stringify(themeRenameState)}`)
    }
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'knowledge_theme_round142.png') })

    await openRoute(paidPage, '/chat')
    await paidPage.locator('[data-chat-panel="page"]').waitFor({ timeout: 15000 })
    await paidPage.locator('aside button').filter({ hasText: assistantSessionTitle }).first().click()
    await paidPage.waitForTimeout(800)

    const assistantRenderState = await paidPage.evaluate(() => {
      const panel = document.querySelector('[data-chat-panel="page"]')
      const latest = Array.from(document.querySelectorAll('[data-chat-message="assistant"] [data-assistant-markdown]')).at(-1)
      const quickLabels = ['/简报', '/总结', '/比较', '/时间线', '/今日一读', '/继续阅读']
      return {
        hasQuickCommandButtons: Array.from(panel?.querySelectorAll('button') || []).some((button) => quickLabels.includes(button.innerText.trim())),
        hasRawCommandText: Boolean(panel?.innerText.includes('/简报') || panel?.innerText.includes('/总结')),
        hasAssistantFollowUpButton: Array.from(document.querySelectorAll('[data-chat-message="assistant"] button')).length > 0,
        rawDoubleStars: Boolean(latest?.innerText.includes('**新华三集团（H3C）**') || latest?.innerText.includes('*提出一个体创造力') || latest?.innerText.includes('*人机共创')),
        strongCount: latest?.querySelectorAll('strong').length || 0,
        text: latest?.innerText || '',
        html: latest?.innerHTML || '',
      }
    })
    if (
      assistantRenderState.hasQuickCommandButtons ||
      assistantRenderState.hasRawCommandText ||
      assistantRenderState.hasAssistantFollowUpButton ||
      assistantRenderState.rawDoubleStars ||
      assistantRenderState.strongCount < 3
    ) {
      throw new Error(`Assistant render validation failed: ${JSON.stringify(assistantRenderState)}`)
    }

    await paidPage.locator('[data-chat-panel="page"] textarea').fill('这段输入会在新建会话后被清空')
    await paidPage.getByRole('button', { name: '新建会话' }).click()
    await paidPage.waitForFunction(
      () => {
        const textarea = document.querySelector('[data-chat-panel="page"] textarea')
        const messages = document.querySelectorAll('[data-chat-message]')
        const latestAssistant = document.querySelector('[data-chat-message="assistant"] [data-assistant-markdown]')
        return Boolean(
          textarea &&
            textarea.value === '' &&
            messages.length === 1 &&
            latestAssistant &&
            !latestAssistant.textContent.includes('/简报') &&
            document.activeElement === textarea,
        )
      },
      null,
      { timeout: 15000 },
    )
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'assistant_round142.png') })

    await paidContext.close()
    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true }).catch(() => {})
  }
}

await main()
