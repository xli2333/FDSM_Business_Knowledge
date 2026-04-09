import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const BACKEND_PORT = 8010
const FRONTEND_PORT = 4175
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ACCOUNTS = {
  free_member: { email: 'reader@example.com', password: 'Reader2026!', homePath: '/me' },
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

async function resolveProtectedArticleId() {
  const response = await fetch(`${BACKEND_URL}/api/articles/latest?limit=40`)
  const items = await response.json()
  const protectedArticle = items.find((item) => item.access_level && item.access_level !== 'public')
  return protectedArticle?.id || items[0]?.id || 1
}

async function runGuestFlow(browser, protectedArticleId) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await configureLanguage(page, 'en')

  await openRoute(page, '/admin')
  await page.waitForURL(/\/login\?redirect=/, { timeout: 30000 })
  const redirectedToLogin = /\/login\?redirect=/.test(page.url())
  const loginHeadingVisible = await page.locator('input[type="password"]').first().isVisible().catch(() => false)

  await page.getByRole('link', { name: /Continue as guest/i }).click()
  await page.waitForURL(`${FRONTEND_URL}/`, { timeout: 30000 })

  await page.getByPlaceholder('Enter a question, topic, person, or concept').first().fill('AI')
  await page.keyboard.press('Enter')
  await page.waitForURL(/\/search\?/, { timeout: 30000 })
  const searchReached = /\/search\?/.test(page.url())

  await openRoute(page, `/article/${protectedArticleId}?lang=en`)
  const paywallVisible = await page.getByText(/Membership Wall|会员内容|付费内容/i).first().isVisible().catch(() => false)
  const englishTitle = ((await page.locator('article h1').first().textContent().catch(() => '')) || '').match(/[A-Za-z]/)

  await context.close()
  return {
    redirected_to_login: redirectedToLogin,
    password_field_visible: loginHeadingVisible,
    search_reached: searchReached,
    paywall_visible: paywallVisible,
    english_article_visible: Boolean(englishTitle),
  }
}

async function runFreeMemberFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await configureLanguage(page, 'zh')
  await loginWithPassword(page, 'free_member')

  const currentUrl = page.url()
  const titleVisible = await page.getByText(/我的资产|我的收藏|最近阅读/).first().isVisible().catch(() => false)

  await openRoute(page, '/chat')
  const redirectedToMembership = /\/membership$/.test(page.url())

  await context.close()
  return {
    redirected_to_library: /\/me$/.test(currentUrl),
    title_visible: titleVisible,
    chat_locked: redirectedToMembership,
  }
}

async function runAdminFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await configureLanguage(page, 'zh')
  await loginWithPassword(page, 'admin')

  const currentUrl = page.url()
  const adminTitleVisible = await page.locator('main h1').first().isVisible().catch(() => false)
  const recentUsersVisible = await page.getByText(/最近活跃的用户档案|Recent users/).first().isVisible().catch(() => false)

  await context.close()
  return {
    redirected_to_admin: /\/admin$/.test(currentUrl),
    admin_title_visible: adminTitleVisible,
    recent_users_visible: recentUsersVisible,
  }
}

async function runMobileFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 430, height: 932 }, isMobile: true })
  const page = await context.newPage()
  await configureLanguage(page, 'zh')

  await openRoute(page, '/login')
  const loginHeadingVisible = await page.locator('input[type="password"]').first().isVisible().catch(() => false)
  const guestLinkVisible = await page.getByRole('link', { name: /以访客身份继续/ }).isVisible().catch(() => false)
  const seedAccountVisible = await page.getByText(/Acceptance accounts|Mock accounts|验收账号|模拟账号/).first().isVisible().catch(() => false)

  await context.close()
  return {
    password_field_visible: loginHeadingVisible,
    guest_link_visible: guestLinkVisible,
    legacy_account_panel_visible: seedAccountVisible,
  }
}

async function main() {
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
  const previewProcess = spawnServer(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)], FRONTEND_DIR)

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const protectedArticleId = await resolveProtectedArticleId()
    const browser = await chromium.launch()

    const guest = await runGuestFlow(browser, protectedArticleId)
    const freeMember = await runFreeMemberFlow(browser)
    const admin = await runAdminFlow(browser)
    const mobile = await runMobileFlow(browser)

    await browser.close()

    console.log({
      protected_article_id: protectedArticleId,
      guest,
      free_member: freeMember,
      admin,
      mobile,
    })
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
