import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round162_today_bookmark')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round162-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8031
const FRONTEND_PORT = 4187
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true })
}

async function copyDb() {
  await fs.copyFile(SOURCE_DB_PATH, path.join(TEMP_DATA_DIR, 'fudan_knowledge_base.db'))
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

async function fetchBookmarkSnapshot() {
  const response = await fetch(`${BACKEND_URL}/api/me/bookmark/today?language=zh`, {
    headers: {
      'X-Debug-User-Id': 'bookmark-acceptance-user',
      'X-Debug-User-Email': 'bookmark-acceptance@example.com',
    },
  })
  if (!response.ok) {
    throw new Error(`Failed to fetch bookmark snapshot: ${response.status}`)
  }
  return response.json()
}

async function seedBookmarkData() {
  const script = `
import sqlite3
from datetime import date

db_path = r"${path.join(TEMP_DATA_DIR, 'fudan_knowledge_base.db').replace(/\\/g, '\\\\')}"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
today = date.today().isoformat()
rows = conn.execute("""
    SELECT id
    FROM articles
    WHERE publish_date <= ?
      AND TRIM(COALESCE(title, '')) <> ''
      AND TRIM(COALESCE(content, '')) <> ''
      AND COALESCE(access_level, 'public') = 'public'
    ORDER BY publish_date DESC, id DESC
    LIMIT 5
""", (today,)).fetchall()

user_id = "bookmark-acceptance-user"
for index, row in enumerate(rows):
    article_id = int(row["id"])
    visitor_id = f"bookmark-acceptance-visitor-{article_id}"
    created_at = f"{today}T1{index}:00:00"
    conn.execute("""
        INSERT OR REPLACE INTO article_view_events (
            article_id, visitor_id, user_id, view_date, source, created_at
        ) VALUES (?, ?, ?, ?, 'article', ?)
    """, (article_id, visitor_id, user_id, today, created_at))
conn.commit()
conn.close()
`
  const child = spawn('python', ['-'], {
    cwd: PROJECT_ROOT,
    stdio: ['pipe', 'ignore', 'ignore'],
    shell: process.platform === 'win32',
    env: process.env,
  })
  child.stdin.write(script)
  child.stdin.end()
  await new Promise((resolve, reject) => {
    child.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`Seed script exited with code ${code}`))
    })
    child.on('error', reject)
  })
}

async function run() {
  await ensureDir(OUTPUT_DIR)
  await copyDb()
  await seedBookmarkData()
  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'

  const build = spawn(npmCommand, ['run', 'build'], {
    cwd: FRONTEND_DIR,
    stdio: 'ignore',
    shell: process.platform === 'win32',
    env: {
      ...process.env,
      VITE_API_BASE_URL: `${BACKEND_URL}/api`,
    },
  })
  await new Promise((resolve, reject) => {
    build.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`build exited with code ${code}`))
    })
    build.on('error', reject)
  })

  const backend = spawnServer(
    'python',
    ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    PROJECT_ROOT,
    {
      FDSM_DATA_DIR: TEMP_DATA_DIR,
      DEV_AUTH_ENABLED: '1',
      SITE_BASE_URL: FRONTEND_URL,
    },
  )

  const frontend = spawnServer(
    npmCommand,
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    FRONTEND_DIR,
  )

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)
    const bookmarkSnapshot = await fetchBookmarkSnapshot()
    const expectedTheme = String(bookmarkSnapshot?.primary_theme || '').trim()

    const browser = await chromium.launch({ headless: true })
    const page = await browser.newPage({ viewport: { width: 1440, height: 2200 }, deviceScaleFactor: 1 })
    await page.addInitScript(() => {
      window.localStorage.setItem('fdsm-language', 'zh')
      window.localStorage.setItem(
        'fdsm-debug-auth',
        JSON.stringify({
          user_id: 'bookmark-acceptance-user',
          email: 'bookmark-acceptance@example.com',
          display_name: 'Bookmark Acceptance',
          tier: 'paid_member',
        }),
      )
    })

    await page.goto(`${FRONTEND_URL}/me?tab=history`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 })
    } catch {}
    await page.waitForSelector('.today-bookmark-preview-card', { timeout: 30000 })
    if (expectedTheme) {
      await page.waitForFunction(
        (theme) => document.querySelector('.today-bookmark-preview-card')?.textContent?.includes(theme),
        expectedTheme,
        { timeout: 30000 },
      )
    } else {
      await page.waitForTimeout(2000)
    }

    await page.goto(`${FRONTEND_URL}/me/today-bookmark`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 })
    } catch {}
    await page.waitForSelector('.today-bookmark-canvas', { timeout: 30000 })
    if (expectedTheme) {
      await page.waitForFunction(
        (theme) => document.querySelector('.today-bookmark-canvas')?.textContent?.includes(theme),
        expectedTheme,
        { timeout: 30000 },
      )
    } else {
      await page.waitForTimeout(1200)
    }
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'today_bookmark_page.png'), fullPage: true })
    await page.locator('.today-bookmark-canvas').screenshot({ path: path.join(OUTPUT_DIR, 'today_bookmark_canvas.png') })

    await page.goto(`${FRONTEND_URL}/me?tab=history`, { waitUntil: 'domcontentloaded', timeout: 60000 })
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 })
    } catch {}
    await page.waitForSelector('.today-bookmark-preview-card', { timeout: 30000 })
    if (expectedTheme) {
      await page.waitForFunction(
        (theme) => document.querySelector('.today-bookmark-preview-card')?.textContent?.includes(theme),
        expectedTheme,
        { timeout: 30000 },
      )
    } else {
      await page.waitForTimeout(2000)
    }
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'my_library_today_bookmark_preview.png'), fullPage: true })

    await browser.close()
  } finally {
    await terminateProcess(frontend)
    await terminateProcess(backend)
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true })
  }
}

await run()
