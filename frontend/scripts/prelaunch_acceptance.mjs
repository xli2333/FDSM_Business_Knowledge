import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_ROOT = path.join(PROJECT_ROOT, 'qa', 'prelaunch', 'round34')
const SCREENSHOT_DIR = path.join(OUTPUT_ROOT, 'screenshots')
const REPORT_JSON_PATH = path.join(OUTPUT_ROOT, 'acceptance_results.json')
const REPORT_MD_PATH = path.join(OUTPUT_ROOT, 'acceptance_report.md')
const BACKEND_PORT = 8014
const FRONTEND_PORT = 4179
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ACCOUNTS = {
  free_member: {
    email: 'reader@example.com',
    password: 'Reader2026!',
    homePath: '/me',
  },
  paid_member: {
    email: 'paid@example.com',
    password: 'Paid2026!',
    homePath: '/membership',
  },
  admin: {
    email: 'admin@example.com',
    password: 'Admin2026!',
    homePath: '/admin',
  },
}

const CLEAN_COPY_PATTERNS = [/acceptance/i, /mock accounts/i, /seed accounts/i, /supabase/i, /验收账号/, /模拟账号/, /种子账号/]

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

function terminateProcess(child) {
  return new Promise((resolve) => {
    if (!child || !child.pid) {
      resolve()
      return
    }
    if (process.platform === 'win32') {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        shell: true,
      })
      killer.on('error', () => resolve())
      killer.on('exit', () => resolve())
      return
    }
    child.on('exit', () => resolve())
    child.kill('SIGTERM')
    setTimeout(() => {
      try {
        child.kill('SIGKILL')
      } catch {}
      resolve()
    }, 2000)
  })
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

async function fetchJson(pathname, headers = {}) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, { headers })
  if (!response.ok) {
    throw new Error(`Failed to fetch ${pathname}: ${response.status}`)
  }
  return response.json()
}

async function resolveArticleIds() {
  const latest = await fetchJson('/api/articles/latest?limit=200')
  const items = Array.isArray(latest) ? latest : []
  const publicArticle = items.find((item) => item.access_level === 'public') || items[0]
  const memberArticle = items.find((item) => item.access_level === 'member') || null
  const paidArticle = items.find((item) => item.access_level === 'paid') || null
  return {
    publicArticleId: publicArticle?.id || 1,
    memberArticleId: memberArticle?.id || publicArticle?.id || 1,
    paidArticleId: paidArticle?.id || memberArticle?.id || publicArticle?.id || 1,
  }
}

async function configurePage(page, { language = 'zh' } = {}) {
  await page.addInitScript(
    ({ nextLanguage }) => {
      window.localStorage.setItem('fdsm-language', nextLanguage)
    },
    { nextLanguage: language },
  )
}

async function waitForSettledPage(page, timeout = 12000) {
  try {
    await page.waitForLoadState('networkidle', { timeout })
  } catch {}
  await page.waitForTimeout(500)
}

async function openSpaRoute(page, targetPath) {
  const targetUrl = targetPath === '/' ? FRONTEND_URL : `${FRONTEND_URL}${targetPath}`
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await waitForSettledPage(page)
}

function attachDiagnostics(page) {
  const state = {
    consoleErrors: [],
    requestFailures: [],
    pageErrors: [],
  }

  page.on('console', (message) => {
    if (message.type() === 'error') {
      state.consoleErrors.push(message.text())
    }
  })
  page.on('requestfailed', (request) => {
    const errorText = request.failure()?.errorText || 'failed'
    if (/ERR_ABORTED/i.test(errorText)) return
    state.requestFailures.push(`${request.method()} ${request.url()} :: ${errorText}`)
  })
  page.on('pageerror', (error) => {
    state.pageErrors.push(error.message)
  })

  return state
}

function createCursor() {
  return {
    consoleErrors: 0,
    requestFailures: 0,
    pageErrors: 0,
  }
}

function takeDiagnosticDelta(state, cursor) {
  const delta = {
    consoleErrors: state.consoleErrors.slice(cursor.consoleErrors),
    requestFailures: state.requestFailures.slice(cursor.requestFailures),
    pageErrors: state.pageErrors.slice(cursor.pageErrors),
  }
  cursor.consoleErrors = state.consoleErrors.length
  cursor.requestFailures = state.requestFailures.length
  cursor.pageErrors = state.pageErrors.length
  return delta
}

function diagnosticsOk(delta) {
  return delta.consoleErrors.length === 0 && delta.requestFailures.length === 0 && delta.pageErrors.length === 0
}

function assertResult(condition, successDetail, failureDetail) {
  return {
    ok: Boolean(condition),
    detail: condition ? successDetail : failureDetail,
  }
}

async function saveScreenshot(page, role, stepKey) {
  const roleDir = path.join(SCREENSHOT_DIR, role)
  await fs.mkdir(roleDir, { recursive: true })
  const filePath = path.join(roleDir, `${stepKey}.png`)
  await page.screenshot({ path: filePath, fullPage: true })
  return filePath
}

async function ensureVisible(locator, timeout = 25000) {
  try {
    await locator.first().waitFor({ timeout })
    return true
  } catch {
    return false
  }
}

async function bodyText(page) {
  return ((await page.locator('body').textContent().catch(() => '')) || '').toLowerCase()
}

function copyLooksClean(text) {
  return CLEAN_COPY_PATTERNS.every((pattern) => !pattern.test(text))
}

async function runStep(page, diagnostics, cursor, role, stepKey, runAssertion) {
  const payload = await runAssertion()
  const delta = takeDiagnosticDelta(diagnostics, cursor)
  const screenshotPath = await saveScreenshot(page, role, stepKey)
  return {
    role,
    step: stepKey,
    url: page.url(),
    screenshot: path.relative(PROJECT_ROOT, screenshotPath).replace(/\\/g, '/'),
    ok: Boolean(payload.ok) && diagnosticsOk(delta),
    detail: payload.detail,
    diagnostics: delta,
  }
}

async function loginWithPassword(page, accountKey) {
  const account = ACCOUNTS[accountKey]
  await openSpaRoute(page, '/login')
  await page.locator('input[type="email"]').first().fill(account.email)
  await page.locator('input[type="password"]').first().fill(account.password)
  await Promise.all([
    page.waitForURL(new RegExp(`${FRONTEND_URL}${account.homePath.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`), { timeout: 30000 }),
    page.locator('form button[type="submit"]').first().click(),
  ])
  await waitForSettledPage(page)
}

async function runGuestDesktopFlow(browser, articleIds) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  const diagnostics = attachDiagnostics(page)
  const cursor = createCursor()
  await configurePage(page, { language: 'zh' })

  const results = []

  await openSpaRoute(page, '/')
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'home', async () => {
      const heroVisible = await ensureVisible(page.locator('h1').first())
      const assistantVisible = await page.getByRole('button', { name: /AI Assistant|AI 助理/i }).first().isVisible().catch(() => false)
      return assertResult(heroVisible && !assistantVisible, 'Guest homepage is visible and AI assistant stays hidden.', 'Guest homepage is incomplete or AI assistant is exposed.')
    }),
  )

  const homeSearchInput = page.locator('main input').first()
  await homeSearchInput.fill('AI')
  await homeSearchInput.press('Enter')
  await page.waitForURL(/\/search\?/, { timeout: 30000 })
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'search', async () => {
      const resultsVisible = await ensureVisible(page.getByText(/Unified Search|统一搜索/))
      return assertResult(resultsVisible, 'Search results are visible.', 'Search results did not render correctly.')
    }),
  )

  await openSpaRoute(page, '/login')
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'login', async () => {
      const loginVisible = await ensureVisible(page.locator('main h1').first())
      const passwordVisible = await ensureVisible(page.locator('input[type="password"]'))
      const cleanText = copyLooksClean(await bodyText(page))
      return assertResult(
        loginVisible && passwordVisible && cleanText,
        'Login center renders as a clean password-based sign-in surface.',
        'Login center still exposes validation-only copy or is missing the password flow.',
      )
    }),
  )

  await page.getByRole('link', { name: /Continue as guest|以访客身份继续/ }).click()
  await page.waitForURL(`${FRONTEND_URL}/`, { timeout: 30000 })
  await waitForSettledPage(page)

  await openSpaRoute(page, `/article/${articleIds.publicArticleId}`)
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'public-article', async () => {
      const articleVisible = await ensureVisible(page.locator('article h1'))
      return assertResult(articleVisible, `Public article ${articleIds.publicArticleId} is readable.`, `Public article ${articleIds.publicArticleId} did not render correctly.`)
    }),
  )

  await openSpaRoute(page, `/article/${articleIds.publicArticleId}?lang=en`)
  await Promise.race([
    page.getByText(/English translation ready|Preview translation|Full translation/).first().waitFor({ timeout: 45000 }).catch(() => null),
    page.getByText(/temporarily unavailable/i).first().waitFor({ timeout: 45000 }).catch(() => null),
    page.waitForTimeout(12000),
  ])
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'public-article-translation', async () => {
      const titleText = (await page.locator('article h1').first().textContent().catch(() => '')) || ''
      const translationBadgeVisible = await ensureVisible(page.getByText(/English translation ready|Preview translation|Full translation/), 4000)
      const assistantButtonVisible = await page.getByRole('button', { name: /AI Assistant|AI 助理/i }).first().isVisible().catch(() => false)
      const relatedTitleText = (await page.locator('aside article h3').first().textContent().catch(() => '')) || ''
      return assertResult(
        /[A-Za-z]/.test(titleText) && translationBadgeVisible && !assistantButtonVisible && (!relatedTitleText || /[A-Za-z]/.test(relatedTitleText)),
        'English article mode renders translated body and translated recommendations.',
        'English article mode is incomplete or recommendation cards stayed untranslated.',
      )
    }),
  )

  await openSpaRoute(page, `/article/${articleIds.paidArticleId}`)
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'paid-article-gate', async () => {
      const articleVisible = await ensureVisible(page.locator('article h1'))
      const gateVisible = await ensureVisible(page.getByText(/Membership Wall|会员内容|付费内容/))
      return assertResult(articleVisible && gateVisible, `Paid article ${articleIds.paidArticleId} shows the paywall.`, `Paid article ${articleIds.paidArticleId} did not show the paywall correctly.`)
    }),
  )

  await openSpaRoute(page, '/membership')
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'membership', async () => {
      const membershipVisible = await ensureVisible(page.getByText(/Plans|会员|套餐/))
      const cleanText = copyLooksClean(await bodyText(page))
      return assertResult(membershipVisible && cleanText, 'Membership page renders with production-facing copy.', 'Membership page still contains validation-only wording.')
    }),
  )

  await openSpaRoute(page, '/audio')
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'audio', async () => {
      const audioVisible = await ensureVisible(page.getByText(/Premium Audio Stream|Audio Stream|Member audio|付费音频流|完整音频流|音频/))
      return assertResult(audioVisible, 'Audio page renders for guests.', 'Audio page did not render for guests.')
    }),
  )

  await openSpaRoute(page, '/video')
  results.push(
    await runStep(page, diagnostics, cursor, 'guest-desktop', 'video', async () => {
      const videoVisible = await ensureVisible(page.getByText(/Video Stream|Video Hub|视频流|视频/))
      return assertResult(videoVisible, 'Video page renders for guests.', 'Video page did not render for guests.')
    }),
  )

  await context.close()
  return results
}

async function runFreeDesktopFlow(browser, articleIds) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  const diagnostics = attachDiagnostics(page)
  const cursor = createCursor()
  await configurePage(page, { language: 'zh' })

  await loginWithPassword(page, 'free_member')
  const results = []

  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'library-home', async () => {
      const titleVisible = await ensureVisible(page.getByText(/我的资产|我的收藏|最近阅读/))
      const assistantVisible = await page.getByRole('button', { name: /AI Assistant|AI 助理/i }).first().isVisible().catch(() => false)
      return assertResult(titleVisible && !assistantVisible, 'Free member lands on My Library and cannot see AI assistant.', 'Free member landing page is incorrect or AI assistant leaked.')
    }),
  )

  await openSpaRoute(page, '/chat')
  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'chat-locked', async () => {
      const redirectedToMembership = /\/membership$/.test(page.url())
      const membershipVisible = await ensureVisible(page.getByText(/Membership|会员|套餐/))
      return assertResult(
        redirectedToMembership && membershipVisible,
        'Free member is redirected away from the AI assistant.',
        'Free member can still reach the AI assistant or the redirect failed.',
      )
    }),
  )

  await openSpaRoute(page, '/following')
  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'following', async () => {
      const followingVisible = await ensureVisible(page.getByText(/我的关注|Personal Watchlist/))
      return assertResult(followingVisible, 'Following page renders for free member.', 'Following page did not render for free member.')
    }),
  )

  await openSpaRoute(page, `/article/${articleIds.memberArticleId}`)
  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'member-article', async () => {
      const articleVisible = await ensureVisible(page.locator('article h1'))
      const gateVisible = await ensureVisible(page.getByText(/Membership Wall|会员内容|付费内容/), 4000)
      return assertResult(articleVisible && !gateVisible, `Free member can read member article ${articleIds.memberArticleId}.`, `Free member is still blocked from member article ${articleIds.memberArticleId}.`)
    }),
  )

  await openSpaRoute(page, `/article/${articleIds.paidArticleId}`)
  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'paid-article-preview', async () => {
      const articleVisible = await ensureVisible(page.locator('article h1'))
      const gateVisible = await ensureVisible(page.getByText(/Membership Wall|付费内容|升级/))
      return assertResult(articleVisible && gateVisible, `Free member sees the paid upgrade boundary on article ${articleIds.paidArticleId}.`, `Free member does not see the paid upgrade boundary on article ${articleIds.paidArticleId}.`)
    }),
  )

  await openSpaRoute(page, '/membership')
  results.push(
    await runStep(page, diagnostics, cursor, 'free-desktop', 'membership', async () => {
      const upgradeVisible = await ensureVisible(page.getByText(/Upgrade|升级会员|套餐/))
      const cleanText = copyLooksClean(await bodyText(page))
      return assertResult(upgradeVisible && cleanText, 'Free member sees a clean upgrade path on membership page.', 'Membership page still contains validation-only copy for free member.')
    }),
  )

  await context.close()
  return results
}

async function runPaidDesktopFlow(browser, articleIds) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  const diagnostics = attachDiagnostics(page)
  const cursor = createCursor()
  await configurePage(page, { language: 'zh' })

  await loginWithPassword(page, 'paid_member')
  const results = []

  results.push(
    await runStep(page, diagnostics, cursor, 'paid-desktop', 'membership-home', async () => {
      const membershipVisible = await ensureVisible(page.getByText(/会员空间|订阅状态|套餐|Membership/))
      const assistantVisible = await ensureVisible(page.getByRole('button', { name: /AI Assistant|AI 助理/i }), 4000)
      return assertResult(membershipVisible && assistantVisible, 'Paid member lands on membership space with AI assistant entry.', 'Paid member membership space is incomplete or AI assistant entry is missing.')
    }),
  )

  await openSpaRoute(page, '/audio')
  results.push(
    await runStep(page, diagnostics, cursor, 'paid-desktop', 'audio', async () => {
      const audioVisible = await ensureVisible(page.getByText(/Premium Audio Stream|Audio Stream|Member audio|付费音频流|完整音频流|音频/))
      return assertResult(audioVisible, 'Paid member audio hub renders.', 'Paid member audio hub did not render.')
    }),
  )

  await openSpaRoute(page, '/video')
  results.push(
    await runStep(page, diagnostics, cursor, 'paid-desktop', 'video', async () => {
      const videoVisible = await ensureVisible(page.getByText(/Video Stream|Video Hub|视频流|视频/))
      return assertResult(videoVisible, 'Paid member video hub renders.', 'Paid member video hub did not render.')
    }),
  )

  await openSpaRoute(page, `/article/${articleIds.paidArticleId}`)
  results.push(
    await runStep(page, diagnostics, cursor, 'paid-desktop', 'paid-article', async () => {
      const articleVisible = await ensureVisible(page.locator('article h1'))
      const gateVisible = await ensureVisible(page.getByText(/Membership Wall|会员内容|付费内容/), 4000)
      return assertResult(articleVisible && !gateVisible, `Paid member can read paid article ${articleIds.paidArticleId}.`, `Paid member is still blocked from paid article ${articleIds.paidArticleId}.`)
    }),
  )

  await openSpaRoute(page, '/chat?lang=en')
  results.push(
    await runStep(page, diagnostics, cursor, 'paid-desktop', 'chat-english', async () => {
      const chatVisible = await ensureVisible(page.getByText(/AI Assistant|Sessions|New Session/), 5000)
      const chineseLabelVisible = await page.getByText(/AI 助理/).first().isVisible().catch(() => false)
      return assertResult(chatVisible && !chineseLabelVisible, 'Paid member can enter the English AI assistant surface.', 'Paid member English AI assistant surface is incorrect.')
    }),
  )

  await context.close()
  return results
}

async function runAdminDesktopFlow(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  const diagnostics = attachDiagnostics(page)
  const cursor = createCursor()
  await configurePage(page, { language: 'zh' })

  await loginWithPassword(page, 'admin')
  const results = []

  results.push(
    await runStep(page, diagnostics, cursor, 'admin-desktop', 'admin-home', async () => {
      const text = await bodyText(page)
      const adminVisible =
        (await ensureVisible(page.locator('main h1'))) &&
        /最近活跃的用户档案|recent users|最近调权记录|recent role changes/.test(text)
      const cleanText = copyLooksClean(text)
      return assertResult(adminVisible && cleanText, 'Admin console renders with production-facing operations copy.', 'Admin console still contains validation-only copy or is incomplete.')
    }),
  )

  await openSpaRoute(page, '/admin/memberships')
  results.push(
    await runStep(page, diagnostics, cursor, 'admin-desktop', 'memberships', async () => {
      const membershipsVisible = await ensureVisible(page.getByText(/Membership administration|Memberships|会员管理|新建记录|Create record/))
      return assertResult(membershipsVisible, 'Admin membership management renders.', 'Admin membership management did not render.')
    }),
  )

  await openSpaRoute(page, '/editorial')
  results.push(
    await runStep(page, diagnostics, cursor, 'admin-desktop', 'editorial', async () => {
      const editorialVisible = await ensureVisible(page.getByText(/Editorial Workbench|AI source articles|Draft editor/))
      return assertResult(editorialVisible, 'Editorial workbench renders for admin.', 'Editorial workbench did not render for admin.')
    }),
  )

  await openSpaRoute(page, '/media-studio')
  results.push(
    await runStep(page, diagnostics, cursor, 'admin-desktop', 'media-studio', async () => {
      const mediaVisible = await ensureVisible(page.getByText(/Media Studio|音视频后台|节目列表/))
      return assertResult(mediaVisible, 'Media Studio renders for admin.', 'Media Studio did not render for admin.')
    }),
  )

  await openSpaRoute(page, '/commercial/leads')
  results.push(
    await runStep(page, diagnostics, cursor, 'admin-desktop', 'commercial-leads', async () => {
      const leadsVisible = await ensureVisible(page.getByText(/Lead Console|商业咨询|Billing Orders/))
      return assertResult(leadsVisible, 'Commercial lead console renders for admin.', 'Commercial lead console did not render for admin.')
    }),
  )

  await context.close()
  return results
}

async function runMobileFlow(browser, roleKey, route) {
  const context = await browser.newContext({ viewport: { width: 430, height: 932 }, isMobile: true })
  const page = await context.newPage()
  const diagnostics = attachDiagnostics(page)
  const cursor = createCursor()
  await configurePage(page, { language: 'zh' })

  if (roleKey !== 'guest') {
    await loginWithPassword(page, roleKey)
  } else {
    await openSpaRoute(page, '/login')
  }

  await openSpaRoute(page, route)
  const result = await runStep(page, diagnostics, cursor, `mobile-${roleKey}`, route.replace(/[/?=&]/g, '_').replace(/^_+/, ''), async () => {
    const bodyVisible = await ensureVisible(page.locator('main'))
    return assertResult(bodyVisible, `${roleKey} mobile route ${route} renders.`, `${roleKey} mobile route ${route} did not render.`)
  })

  await context.close()
  return [result]
}

function buildMarkdownReport(results, meta) {
  const passed = results.filter((item) => item.ok).length
  const failed = results.length - passed
  const lines = [
    '# Round34 Prelaunch Acceptance Report',
    '',
    `- Generated at: ${new Date().toISOString()}`,
    `- Frontend URL: ${FRONTEND_URL}`,
    `- Backend URL: ${BACKEND_URL}`,
    `- Public article ID: ${meta.publicArticleId}`,
    `- Member article ID: ${meta.memberArticleId}`,
    `- Paid article ID: ${meta.paidArticleId}`,
    `- Total steps: ${results.length}`,
    `- Passed: ${passed}`,
    `- Failed: ${failed}`,
    '',
    '## Results',
    '',
  ]

  for (const item of results) {
    lines.push(`- [${item.ok ? 'x' : ' '}] ${item.role} / ${item.step}: ${item.detail}`)
    lines.push(`  Screenshot: ${item.screenshot}`)
    lines.push(`  URL: ${item.url}`)
    if (!diagnosticsOk(item.diagnostics)) {
      if (item.diagnostics.consoleErrors.length) {
        lines.push(`  console errors: ${item.diagnostics.consoleErrors.join(' | ')}`)
      }
      if (item.diagnostics.requestFailures.length) {
        lines.push(`  request failures: ${item.diagnostics.requestFailures.join(' | ')}`)
      }
      if (item.diagnostics.pageErrors.length) {
        lines.push(`  page errors: ${item.diagnostics.pageErrors.join(' | ')}`)
      }
    }
  }

  return `${lines.join('\n')}\n`
}

async function main() {
  await fs.mkdir(SCREENSHOT_DIR, { recursive: true })

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
  const previewProcess = spawnServer(
    npmCommand,
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    FRONTEND_DIR,
  )

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const articleIds = await resolveArticleIds()
    const browser = await chromium.launch()

    const results = [
      ...(await runGuestDesktopFlow(browser, articleIds)),
      ...(await runFreeDesktopFlow(browser, articleIds)),
      ...(await runPaidDesktopFlow(browser, articleIds)),
      ...(await runAdminDesktopFlow(browser)),
      ...(await runMobileFlow(browser, 'guest', '/login')),
      ...(await runMobileFlow(browser, 'free_member', '/me')),
      ...(await runMobileFlow(browser, 'paid_member', '/membership')),
      ...(await runMobileFlow(browser, 'admin', '/admin')),
    ]

    await browser.close()

    const payload = {
      generated_at: new Date().toISOString(),
      frontend_url: FRONTEND_URL,
      backend_url: BACKEND_URL,
      article_ids: articleIds,
      summary: {
        total: results.length,
        passed: results.filter((item) => item.ok).length,
        failed: results.filter((item) => !item.ok).length,
      },
      results,
    }

    await fs.writeFile(REPORT_JSON_PATH, JSON.stringify(payload, null, 2), 'utf8')
    await fs.writeFile(REPORT_MD_PATH, buildMarkdownReport(results, articleIds), 'utf8')
    console.log(JSON.stringify(payload.summary))
    if (payload.summary.failed > 0) {
      process.exitCode = 1
    }
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
