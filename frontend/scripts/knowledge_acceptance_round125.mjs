import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round125_knowledge')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round125-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8015
const FRONTEND_PORT = 4180
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
    throw new Error(`Fetch failed for ${pathname}: ${response.status}`)
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

    const browser = await chromium.launch()

  const latestArticles = await fetchJson('/api/articles/latest?limit=6&offset=0&language=zh')
  const article = Array.isArray(latestArticles) ? latestArticles.find((item) => item?.id) : null
  const secondArticle = Array.isArray(latestArticles) ? latestArticles.find((item) => item?.id && item.id !== article?.id) : null
  if (!article?.id) {
    throw new Error('No latest article available for knowledge acceptance')
  }

    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const paidPage = await paidContext.newPage()
    const uniqueThemeTitle = `知识库验收${String(Date.now()).slice(-6)}`

    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })

    await openRoute(paidPage, `/article/${article.id}`)
    await paidPage.locator('[data-testid="article-page-shell"]').waitFor({ timeout: 20000 })
    await paidPage.locator('[data-knowledge-open-modal]').click()
    await paidPage.locator('[data-knowledge-article-modal]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-create-title]').fill(uniqueThemeTitle)
    await paidPage.getByRole('button', { name: /创建主题并加入本文|Create and add this article/i }).click()
    await paidPage.locator(`[data-knowledge-select-theme]`).first().waitFor({ timeout: 20000 })
    await paidPage.evaluate(() => window.scrollTo(0, 0))
    await paidPage.waitForTimeout(300)
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_article_modal.png') })

    let paidThemes = null
    const startedAt = Date.now()
    while (Date.now() - startedAt < 20000) {
      paidThemes = await fetchPaidJson('/api/me/knowledge/themes')
      if ((paidThemes.items || []).some((item) => item.title === uniqueThemeTitle && item.article_count >= 1)) {
        break
      }
      await paidPage.waitForTimeout(800)
    }
    const createdTheme = (paidThemes?.items || []).find((item) => item.title === uniqueThemeTitle)
    if (!createdTheme?.slug) {
      throw new Error(`Theme was not created through article modal: ${uniqueThemeTitle}`)
    }
    if (!createdTheme.contains_article && createdTheme.article_count < 1) {
      throw new Error(`Created theme does not contain the current article: ${uniqueThemeTitle}`)
    }

    if (createdTheme?.id && secondArticle?.id) {
      await fetchPaidJson(`/api/me/knowledge/themes/${createdTheme.id}/articles`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ article_id: secondArticle.id }),
      })
    }

    await openRoute(paidPage, '/me/knowledge')
    await paidPage.locator('[data-knowledge-hub-page]').waitFor({ timeout: 15000 })
    await paidPage.locator(`[data-knowledge-theme-card="${createdTheme.slug}"]`).waitFor({ timeout: 15000 })
    await paidPage.evaluate(() => window.scrollTo(0, 0))
    await paidPage.waitForTimeout(300)
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_knowledge_hub.png') })

    await openRoute(paidPage, `/me/knowledge/${createdTheme.slug}`)
    await paidPage.locator(`[data-knowledge-theme-page="${createdTheme.slug}"]`).waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-chat-panel]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-clear-selection]').click()
    await paidPage.locator('[data-knowledge-article-toggle]').first().click()
    await paidPage.locator('[data-knowledge-chat-panel] textarea').fill('请总结这个主题')
    await paidPage.locator('[data-knowledge-chat-panel] button[aria-label="发送"]').click()
    await paidPage.waitForFunction(() => document.querySelectorAll('[data-knowledge-chat-message="assistant"]').length >= 2, null, {
      timeout: 30000,
    })
    const latestAssistantText = await paidPage.locator('[data-knowledge-chat-message="assistant"]').last().innerText()
    if (latestAssistantText.includes('**')) {
      throw new Error('Knowledge theme chat rendered raw markdown markers')
    }
    if (/\[(?:\d{1,3})\]/.test(latestAssistantText)) {
      throw new Error('Knowledge theme chat still rendered raw citation markers')
    }
    if ((await paidPage.locator('[data-knowledge-chat-panel] a[href^="/article/"]').count()) !== 0) {
      throw new Error('Knowledge theme chat still rendered visible source links')
    }
    await paidPage.evaluate(() => window.scrollTo(0, 0))
    await paidPage.waitForTimeout(300)
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_theme_page.png') })

    await openRoute(paidPage, '/me')
    await paidPage.getByRole('link', { name: /打开我的知识库|Open my knowledge base/i }).waitFor({ timeout: 15000 })
    await paidPage.evaluate(() => window.scrollTo(0, 0))
    await paidPage.waitForTimeout(300)
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_my_library.png') })

    const freeContext = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
    const freePage = await freeContext.newPage()
    await login(freePage, {
      email: 'reader@example.com',
      password: 'Reader2026!',
      expectedPath: '/me',
    })
    await openRoute(freePage, '/me/knowledge')
    await freePage.waitForURL(`${FRONTEND_URL}/membership`, { timeout: 20000 })
    await freePage.evaluate(() => window.scrollTo(0, 0))
    await freePage.waitForTimeout(300)
    await freePage.screenshot({ path: path.join(OUTPUT_DIR, 'free_membership_gate.png') })

    await freeContext.close()
    await paidContext.close()
    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true }).catch(() => {})
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
