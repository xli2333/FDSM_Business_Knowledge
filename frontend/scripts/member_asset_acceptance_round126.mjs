import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round126_member_assets')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round126-'))
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

async function configureLanguage(page, language = 'zh') {
  await page.addInitScript((nextLanguage) => {
    window.localStorage.setItem('fdsm-language', nextLanguage)
  }, language)
}

async function openRoute(page, targetPath) {
  const targetUrl = targetPath === '/' ? FRONTEND_URL : `${FRONTEND_URL}${targetPath}`
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
  try {
    await page.waitForLoadState('networkidle', { timeout: 12000 })
  } catch {}
  await page.waitForTimeout(400)
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

async function verifyAssetFlow(page, key) {
  await openRoute(page, '/membership')
  await page.locator(`[data-membership-asset-link="${key}"]`).waitFor({ timeout: 15000 })
  await page.locator(`[data-membership-asset-link="${key}"]`).click()
  await page.waitForURL((url) => url.pathname === '/me' && url.searchParams.get('tab') === key, { timeout: 20000 })
  await page.locator(`[data-library-tab="${key}"]`).waitFor({ timeout: 15000 })
  await page.locator(`[data-library-section="${key}"]`).waitFor({ timeout: 15000 })
  await page.locator(`[data-library-summary-card="${key}"]`).waitFor({ timeout: 15000 })

  const articleLink = page.locator(`[data-library-section="${key}"] a[href^="/article/"]`).first()
  await articleLink.waitFor({ timeout: 15000 })
  const href = await articleLink.getAttribute('href')
  if (!href || !href.startsWith('/article/')) {
    throw new Error(`Asset flow ${key} did not expose an article detail link`)
  }
  await articleLink.click()
  await page.waitForURL(`${FRONTEND_URL}${href}`, { timeout: 20000 })
  await page.locator('[data-testid="article-page-shell"]').waitFor({ timeout: 15000 })
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

    const paidContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const paidPage = await paidContext.newPage()
    await login(paidPage, {
      email: 'paid@example.com',
      password: 'Paid2026!',
      expectedPath: '/membership',
    })
    for (const key of ['bookmarks', 'likes', 'history']) {
      await verifyAssetFlow(paidPage, key)
    }
    await openRoute(paidPage, '/membership')
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_membership_assets.png') })
    await openRoute(paidPage, '/me?tab=history')
    await paidPage.screenshot({ path: path.join(OUTPUT_DIR, 'paid_library_history.png') })
    await paidContext.close()

    const freeContext = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const freePage = await freeContext.newPage()
    await login(freePage, {
      email: 'reader@example.com',
      password: 'Reader2026!',
      expectedPath: '/me',
    })
    for (const key of ['bookmarks', 'likes', 'history']) {
      await verifyAssetFlow(freePage, key)
    }
    await openRoute(freePage, '/membership')
    await freePage.screenshot({ path: path.join(OUTPUT_DIR, 'free_membership_assets.png') })
    await freeContext.close()

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
