import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round106_media')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round106-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8014
const FRONTEND_PORT = 4179
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

async function fetchAdminJson(pathname) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, {
    headers: {
      'X-Debug-User-Id': 'round106-admin',
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
    const uniqueLabel = `Round106 Media ${Date.now()}`

    await loginAdmin(page)
    await openRoute(page, '/media-studio')
    await page.getByRole('heading', { name: /Manage audio and video with article-style draft flow/i }).waitFor({ timeout: 20000 })
    await page.locator('select[name="kind"]').selectOption('video')
    await page.getByRole('button', { name: /^Upload script$/i }).waitFor({ state: 'visible', timeout: 20000 })

    await page.locator('input[type="file"]').nth(0).setInputFiles({
      name: 'round106-media.mp4',
      mimeType: 'video/mp4',
      buffer: Buffer.from('\x00\x00\x00\x18ftypmp42'),
    })
    await page.waitForFunction(() => {
      const mediaUrl = document.querySelector('input[name="media_url"]')
      return Boolean(mediaUrl?.value?.includes('/media-uploads/'))
    })

    await page.locator('input[name="title"]').fill(uniqueLabel)
    await page.locator('input[type="file"]').nth(1).setInputFiles({
      name: 'round106-transcript.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from('# Transcript\n\n00:00 Opening context\n\n00:42 Workflow alignment\n\n01:25 Republish and reopen flow'),
    })
    await page.waitForTimeout(1200)
    const transcriptFieldCount = await page.locator('textarea[name="transcript_markdown"], textarea[name="script_markdown"]').count()
    if (transcriptFieldCount !== 0) {
      throw new Error(`Raw transcript/script editors should be hidden, found ${transcriptFieldCount}`)
    }

    await page.getByRole('button', { name: /Generate copy/i }).first().click()
    await page.waitForFunction(() => {
      const summary = document.querySelector('textarea[name="summary"]')
      const body = document.querySelector('textarea[name="body_markdown"]')
      return Boolean(summary?.value?.trim() && body?.value?.trim())
    })

    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_before_publish.png'), fullPage: true })

    await page.getByRole('button', { name: /^Publish$/i }).first().click()
    await page.getByText(/removed from the draft box automatically/i).first().waitFor({ state: 'visible', timeout: 20000 })

    const draftPayloadAfterPublish = await fetchAdminJson('/api/media/admin/items?kind=video&limit=40')
    if ((draftPayloadAfterPublish.items || []).some((item) => item.title === uniqueLabel)) {
      throw new Error(`Draft still exists in draft box after publish: ${uniqueLabel}`)
    }

    const sourcePayload = await fetchAdminJson('/api/media/admin/source-items?kind=video&limit=40')
    const reopenIndex = (sourcePayload.items || []).findIndex((item) => item.title === uniqueLabel)
    if (reopenIndex < 0) {
      throw new Error(`Published media item not found in source list: ${uniqueLabel}`)
    }

    await page.getByRole('button', { name: /Send to draft box/i }).nth(reopenIndex).waitFor({ state: 'visible', timeout: 20000 })
    await page.getByRole('button', { name: /Send to draft box/i }).nth(reopenIndex).click()
    await page.getByText(/sent back to the draft box/i).first().waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForFunction(
      (expectedTitle) => {
        const title = document.querySelector('input[name="title"]')
        return title?.value === expectedTitle
      },
      uniqueLabel,
    )

    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_after_reopen.png'), fullPage: true })

    await context.close()
    await browser.close()
    console.log({ ok: true, output_dir: OUTPUT_DIR, temp_data_dir: TEMP_DATA_DIR, title: uniqueLabel })
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
