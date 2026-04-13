import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round34_visual')
const BACKEND_PORT = 8011
const FRONTEND_PORT = 4176
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ACCOUNTS = {
  free_member: { email: 'reader@example.com', password: 'Reader2026!', homePath: '/me' },
  paid_member: { email: 'paid@example.com', password: 'Paid2026!', homePath: '/membership' },
  admin: { email: 'admin@example.com', password: 'Admin2026!', homePath: '/admin' },
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

async function configureLanguage(page, language) {
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
  await page.waitForTimeout(500)
}

function screenshotName(targetPath, variant) {
  const normalized = targetPath === '/' ? 'home' : targetPath.replace(/[/?=&]/g, '_').replace(/^_+/, '')
  return `${variant}-${normalized}.png`
}

async function saveCapture(page, targetPath, variant) {
  await openRoute(page, targetPath)
  await page.screenshot({ path: path.join(OUTPUT_DIR, screenshotName(targetPath, variant)), fullPage: true })
}

async function loginWithPassword(page, accountKey) {
  const account = ACCOUNTS[accountKey]
  await openRoute(page, '/login')
  await page.locator('input[type="email"]').first().fill(account.email)
  await page.locator('input[type="password"]').first().fill(account.password)
  await Promise.all([
    page.waitForURL(new RegExp(`${FRONTEND_URL}${account.homePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`), { timeout: 30000 }),
    page.locator('form button[type="submit"]').first().click(),
  ])
  await page.waitForTimeout(800)
}

async function resolveArticleIds() {
  const response = await fetch(`${BACKEND_URL}/api/articles/latest?limit=200`)
  const items = await response.json()
  const publicArticle = items.find((item) => item.access_level === 'public') || items[0]
  return {
    publicArticleId: publicArticle?.id || 1,
  }
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true })

  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  await runCommand(npmCommand, ['run', 'build'], FRONTEND_DIR, {
    VITE_API_BASE_URL: `${BACKEND_URL}/api`,
  })
  const backendProcess = spawnServer(
    'python',
    ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    PROJECT_ROOT,
    {
      DEV_AUTH_ENABLED: '1',
      ADMIN_EMAILS: 'admin@example.com',
      PAYMENTS_ENABLED: '0',
      PAYMENT_PROVIDER: 'mock',
    },
  )
  const previewProcess = spawnServer(npmCommand, ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)], FRONTEND_DIR)

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const articleIds = await resolveArticleIds()
    const browser = await chromium.launch()

    const guestPage = await browser.newPage({ viewport: { width: 1440, height: 1200 } })
    await configureLanguage(guestPage, 'zh')
    await saveCapture(guestPage, '/', 'desktop-guest')
    await saveCapture(guestPage, '/login', 'desktop-guest')

    const freePage = await browser.newPage({ viewport: { width: 1440, height: 1200 } })
    await configureLanguage(freePage, 'zh')
    await loginWithPassword(freePage, 'free_member')
    await saveCapture(freePage, '/me', 'desktop-free')

    const paidPage = await browser.newPage({ viewport: { width: 1440, height: 1200 } })
    await configureLanguage(paidPage, 'zh')
    await loginWithPassword(paidPage, 'paid_member')
    await saveCapture(paidPage, '/membership', 'desktop-paid')

    const adminPage = await browser.newPage({ viewport: { width: 1440, height: 1200 } })
    await configureLanguage(adminPage, 'zh')
    await loginWithPassword(adminPage, 'admin')
    await saveCapture(adminPage, '/admin', 'desktop-admin')
    await saveCapture(adminPage, '/admin/memberships', 'desktop-admin')
    await saveCapture(adminPage, '/editorial', 'desktop-admin')

    const englishPage = await browser.newPage({ viewport: { width: 1440, height: 1200 } })
    await configureLanguage(englishPage, 'en')
    await saveCapture(englishPage, '/?lang=en', 'desktop-en')
    await saveCapture(englishPage, `/article/${articleIds.publicArticleId}?lang=en`, 'desktop-en')

    const mobileGuest = await browser.newPage({ viewport: { width: 430, height: 932 }, isMobile: true })
    await configureLanguage(mobileGuest, 'zh')
    await saveCapture(mobileGuest, '/login', 'mobile-guest')
    await saveCapture(mobileGuest, '/', 'mobile-guest')

    const mobileAdmin = await browser.newPage({ viewport: { width: 430, height: 932 }, isMobile: true })
    await configureLanguage(mobileAdmin, 'zh')
    await loginWithPassword(mobileAdmin, 'admin')
    await saveCapture(mobileAdmin, '/admin', 'mobile-admin')

    await browser.close()
    console.log({ output_dir: OUTPUT_DIR })
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
