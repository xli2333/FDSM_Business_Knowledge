import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round109_cover')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round109-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8015
const FRONTEND_PORT = 4180
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const PNG_BASE64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2ioAAAAASUVORK5CYII='

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

async function fetchAdminJson(pathname) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, {
    headers: {
      'X-Debug-User-Id': 'round109-admin',
      'X-Debug-User-Email': 'admin@example.com',
    },
  })
  if (!response.ok) {
    throw new Error(`Admin fetch failed for ${pathname}: ${response.status}`)
  }
  return response.json()
}

async function configureLanguage(page, language) {
  await page.addInitScript((nextLanguage) => {
    window.localStorage.setItem('fdsm-language', nextLanguage)
  }, language)
}

async function loginAdmin(page) {
  await configureLanguage(page, 'en')
  await openRoute(page, '/login')
  await page.locator('input[type="email"]').first().fill('admin@example.com')
  await page.locator('input[type="password"]').first().fill('Admin2026!')
  await Promise.all([
    page.waitForURL(`${FRONTEND_URL}/admin`, { timeout: 30000 }),
    page.locator('form button[type="submit"]').first().click(),
  ])
  await page.waitForTimeout(800)
}

async function pastePng(locator, filename) {
  await locator.evaluate(
    (node, payload) => {
      const binary = Uint8Array.from(atob(payload.base64), (char) => char.charCodeAt(0))
      const file = new File([binary], payload.filename, { type: 'image/png' })
      const dataTransfer = new DataTransfer()
      dataTransfer.items.add(file)
      const event = new ClipboardEvent('paste', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'clipboardData', { value: dataTransfer })
      node.dispatchEvent(event)
    },
    { base64: PNG_BASE64, filename },
  )
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
    const context = await browser.newContext({ viewport: { width: 1440, height: 1280 } })
    const page = await context.newPage()
    const editorialLabel = `Round109 Editorial ${Date.now()}`
    const mediaLabel = `Round109 Media ${Date.now()}`

    await loginAdmin(page)

    await openRoute(page, '/editorial')
    await page.locator('input[name="title"]').first().fill(editorialLabel)
    await page.locator('input[accept*="image/png"]').setInputFiles({
      name: 'round109-editorial-cover.png',
      mimeType: 'image/png',
      buffer: Buffer.from(PNG_BASE64, 'base64'),
    })
    await page.locator('img[alt="Article cover preview"]').waitFor({ state: 'visible', timeout: 20000 })
    const uploadSrc = await page.locator('img[alt="Article cover preview"]').getAttribute('src')

    const pasteZone = page.locator('[data-testid="editorial-cover-paste-zone"]')
    await pasteZone.click()
    await pastePng(pasteZone, 'round109-editorial-paste.png')
    await page.waitForFunction(
      (previousSrc) => {
        const image = document.querySelector('img[alt="Article cover preview"]')
        return Boolean(image?.getAttribute('src') && image.getAttribute('src') !== previousSrc)
      },
      uploadSrc,
    )

    const editorialDrafts = await fetchAdminJson('/api/editorial/articles?limit=40')
    const editorialDraft = (editorialDrafts || []).find((item) => item.title === editorialLabel)
    if (!editorialDraft) {
      throw new Error(`Editorial draft not found after cover upload: ${editorialLabel}`)
    }
    const editorialDetail = await fetchAdminJson(`/api/editorial/articles/${editorialDraft.id}`)
    if (!editorialDetail.cover_image_url?.startsWith('/editorial-uploads/covers/')) {
      throw new Error(`Editorial cover image url missing: ${editorialDetail.cover_image_url || 'empty'}`)
    }
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'editorial_cover.png'), fullPage: true })

    await openRoute(page, '/media-studio')
    await page.locator('select[name="kind"]').selectOption('video')
    await page.locator('input[name="title"]').fill(mediaLabel)
    await page.locator('input[accept*="image/png"]').setInputFiles({
      name: 'round109-media-cover.png',
      mimeType: 'image/png',
      buffer: Buffer.from(PNG_BASE64, 'base64'),
    })
    await page.locator('img[alt="Media cover preview"]').waitFor({ state: 'visible', timeout: 20000 })

    const mediaDraftPayload = await fetchAdminJson('/api/media/admin/items?kind=video&limit=40')
    const mediaDraft = (mediaDraftPayload.items || []).find((item) => item.title === mediaLabel)
    if (!mediaDraft) {
      throw new Error(`Media draft not found after cover upload: ${mediaLabel}`)
    }
    if (!mediaDraft.cover_image_url?.startsWith('/media-uploads/video/cover/')) {
      throw new Error(`Media cover image url missing: ${mediaDraft.cover_image_url || 'empty'}`)
    }
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_cover.png'), fullPage: true })

    await context.close()
    await browser.close()
    console.log({
      ok: true,
      output_dir: OUTPUT_DIR,
      temp_data_dir: TEMP_DATA_DIR,
      editorial_title: editorialLabel,
      media_title: mediaLabel,
    })
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
