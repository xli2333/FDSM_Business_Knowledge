import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round178_cas_login')
const FRONTEND_PORT = 4197
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const MOCK_API_BASE_URL = 'http://127.0.0.1:65534/api'

function startFrontend() {
  return spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT), '--strictPort'], {
    cwd: FRONTEND_DIR,
    env: {
      ...process.env,
      VITE_API_BASE_URL: MOCK_API_BASE_URL,
      VITE_ENABLE_DEBUG_AUTH: '0',
    },
    shell: process.platform === 'win32',
    stdio: 'ignore',
  })
}

function terminateProcess(child) {
  return new Promise((resolve) => {
    if (!child?.pid) return resolve()
    if (process.platform !== 'win32') {
      child.kill()
      resolve()
      return
    }
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      shell: true,
    })
    killer.on('exit', () => resolve())
    killer.on('error', () => resolve())
  })
}

async function waitForServer(url, timeoutMs = 30000) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`Frontend server did not start: ${url}`)
}

async function fulfillJson(route, payload, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(payload),
  })
}

function guestCasStatus() {
  return {
    enabled: true,
    authenticated: false,
    user: null,
    auth_mode: 'cas',
    membership: {
      tier: 'guest',
      tier_label: '访客',
      status: 'anonymous',
      status_label: '未登录',
      is_authenticated: false,
      is_admin: false,
      can_access_member: false,
      can_access_paid: false,
      user_id: null,
      email: null,
      benefits: [],
    },
    business_profile: {
      user_id: null,
      email: null,
      display_name: '访客',
      role_home_path: '/',
      auth_source: 'guest',
      is_authenticated: false,
      is_admin: false,
    },
    role_home_path: '/',
  }
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true })
  const server = startFrontend()
  let browser = null
  try {
    await waitForServer(FRONTEND_URL)
    browser = await chromium.launch()
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
    await page.route(`${MOCK_API_BASE_URL}/**`, async (route) => {
      const url = new URL(route.request().url())
      const apiPath = url.pathname.replace(/^\/api/, '') || '/'
      if (apiPath === '/auth/status') {
        return fulfillJson(route, guestCasStatus())
      }
      return fulfillJson(route, { detail: `Unexpected mock route: ${apiPath}` }, 500)
    })

    await page.goto(`${FRONTEND_URL}/login?redirect=%2Fadmin`, { waitUntil: 'domcontentloaded' })
    const link = page.getByRole('link', { name: /Fudan CAS|统一身份认证/ })
    await link.waitFor({ timeout: 15000 })
    const href = await link.getAttribute('href')
    if (!href || !href.includes('/api/auth/cas/login?redirect=%2Fadmin')) {
      throw new Error(`Unexpected CAS login href: ${href}`)
    }
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'cas_login_entry.png'), fullPage: true })
    console.log(
      JSON.stringify(
        {
          ok: true,
          href,
          screenshot: path.relative(PROJECT_ROOT, path.join(OUTPUT_DIR, 'cas_login_entry.png')),
        },
        null,
        2,
      ),
    )
  } finally {
    if (browser) await browser.close()
    await terminateProcess(server)
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
