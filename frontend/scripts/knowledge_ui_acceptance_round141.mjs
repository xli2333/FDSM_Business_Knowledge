import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round141_knowledge_ui')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round141-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8018
const FRONTEND_PORT = 4183
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
      throw new Error('No article available for knowledge UI acceptance')
    }

    const uniqueSuffix = String(Date.now()).slice(-6)
    const deleteTheme = await fetchPaidJson('/api/me/knowledge/themes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: `round141-delete-${uniqueSuffix}`,
        description: '用于 Hub 删除验收',
        initial_article_id: article.id,
      }),
    })

    const editTheme = await fetchPaidJson('/api/me/knowledge/themes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: `round141-edit-${uniqueSuffix}`,
        description: '用于重命名弹窗验收',
        initial_article_id: article.id,
      }),
    })

    const renamedTitle = `round141-renamed-${uniqueSuffix}`
    const renamedDescription = '重命名弹窗验收说明已更新'

    const browser = await chromium.launch()
    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
    const paidPage = await paidContext.newPage()

    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })

    const navbarState = await paidPage.evaluate(() => {
      const aiAction = document.querySelector('[data-navbar-desktop-action="/chat"]')
      return {
        exists: Boolean(aiAction),
        className: aiAction?.className || '',
      }
    })
    if (!navbarState.exists || !navbarState.className.includes('border-transparent') || !navbarState.className.includes('bg-transparent')) {
      throw new Error(`Desktop navbar action did not switch to text-first style: ${JSON.stringify(navbarState)}`)
    }
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_navbar_actions.png') })

    await openRoute(paidPage, '/me/knowledge')
    await paidPage.locator(`[data-knowledge-theme-card="${deleteTheme.slug}"]`).waitFor({ timeout: 15000 })
    const deleteCard = paidPage.locator(`[data-knowledge-theme-card="${deleteTheme.slug}"]`)
    await deleteCard.hover()
    await deleteCard.locator(`[data-knowledge-theme-delete-button="${deleteTheme.slug}"]`).click()
    await paidPage.locator('[data-knowledge-confirm-modal="knowledge-hub-delete"]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-confirm-submit="knowledge-hub-delete"]').click()
    await paidPage.waitForSelector(`[data-knowledge-theme-card="${deleteTheme.slug}"]`, { state: 'detached', timeout: 15000 })
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'knowledge_hub_delete.png') })

    await openRoute(paidPage, `/me/knowledge/${editTheme.slug}`)
    await paidPage.locator(`[data-knowledge-theme-page="${editTheme.slug}"]`).waitFor({ timeout: 15000 })
    const selectedMetricCount = await paidPage.locator('[data-knowledge-selected-count-metric]').count()
    if (selectedMetricCount !== 1) {
      throw new Error(`Selected article metric duplicated on theme page: ${selectedMetricCount}`)
    }

    await paidPage.locator('[data-knowledge-theme-open-rename]').click()
    await paidPage.locator('[data-knowledge-theme-rename-modal]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-theme-rename-title]').fill(renamedTitle)
    await paidPage.locator('[data-knowledge-theme-rename-description]').fill(renamedDescription)
    await Promise.all([
      paidPage.waitForURL(new RegExp(`${FRONTEND_URL}/me/knowledge/${renamedTitle}$`), { timeout: 20000 }),
      paidPage.locator('[data-knowledge-theme-rename-save]').click(),
    ])
    await paidPage.locator('[data-knowledge-theme-rename-modal]').waitFor({ state: 'hidden', timeout: 15000 })

    const themeHeading = (await paidPage.locator('h1').first().innerText()).trim()
    if (themeHeading !== renamedTitle) {
      throw new Error(`Theme title did not update after rename: ${themeHeading}`)
    }
    const themeBody = await paidPage.locator('[data-knowledge-theme-page] .knowledge-console-subtitle').first().innerText()
    if (!themeBody.includes(renamedDescription)) {
      throw new Error(`Theme description did not update after rename: ${themeBody}`)
    }

    await paidPage.locator('[data-knowledge-theme-open-delete]').click()
    await paidPage.locator('[data-knowledge-confirm-modal="knowledge-theme-delete"]').waitFor({ timeout: 15000 })
    await paidPage.locator('[data-knowledge-confirm-modal="knowledge-theme-delete"]').getByRole('button', { name: '取消' }).click()
    await paidPage.locator('[data-knowledge-confirm-modal="knowledge-theme-delete"]').waitFor({ state: 'hidden', timeout: 15000 })
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'knowledge_theme_rename_modal.png') })

    await paidContext.close()
    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true }).catch(() => {})
  }
}

await main()
