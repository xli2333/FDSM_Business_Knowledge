import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round143_knowledge_ui')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round143-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8020
const FRONTEND_PORT = 4185
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

async function seedRound143Data() {
  const script = `
import os
import sqlite3

db = os.path.join(os.environ['FDSM_DATA_DIR'], 'fudan_knowledge_base.db')
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

def next_article_id():
    return int(conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM articles").fetchone()[0])

def ensure_column(article_id, slug='insights'):
    row = conn.execute("SELECT id FROM columns WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return
    conn.execute(
        "INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
        (article_id, int(row['id'])),
    )

def insert_article(title, slug, publish_date, excerpt, content, cover_image_path=None):
    existing = conn.execute("SELECT id FROM articles WHERE slug = ?", (slug,)).fetchone()
    if existing is not None:
        return int(existing['id'])
    article_id = next_article_id()
    timestamp = f"{publish_date}T09:00:00"
    conn.execute(
        """
        INSERT INTO articles (
            id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
            content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
            tag_text, people_text, org_text, search_text, word_count, cover_image_path,
            access_level, view_count, is_featured, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL, ?, ?, 'Round143 Topic', '深度分析',
                'Editorial', 'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge',
                ?, ?, ?, 'public', 0, 0, ?, ?)
        """,
        (
            article_id,
            f"round143-{article_id}",
            slug,
            f"editorial/{slug}.md",
            title,
            publish_date,
            content,
            excerpt,
            f"{title} {excerpt} {content}",
            max(1, len(content.replace('\\n', ''))),
            cover_image_path,
            timestamp,
            timestamp,
        ),
    )
    ensure_column(article_id)
    return article_id

legacy_id = insert_article(
    'Round143 Legacy Default Cover',
    'round143-legacy-default-cover',
    '2099-12-31',
    'This legacy article keeps the system default gradient cover.',
    'Legacy article body for round143 visual acceptance.',
    '/legacy-covers/round143-legacy.png',
)
theme_ids = [
    insert_article(
        'Round143 Theme Article A',
        'round143-theme-article-a',
        '2099-12-30',
        'Theme article A excerpt.',
        'Theme article A body.',
    ),
    insert_article(
        'Round143 Theme Article B',
        'round143-theme-article-b',
        '2099-12-29',
        'Theme article B excerpt.',
        'Theme article B body.',
    ),
    insert_article(
        'Round143 Theme Article C',
        'round143-theme-article-c',
        '2099-12-28',
        'Theme article C excerpt.',
        'Theme article C body.',
    ),
]

conn.commit()
conn.close()

print(str(legacy_id))
print(','.join(str(item) for item in theme_ids))
`.trim()

  return new Promise((resolve, reject) => {
    const child = spawn('python', ['-'], {
      cwd: PROJECT_ROOT,
      shell: process.platform === 'win32',
      env: {
        ...process.env,
        FDSM_DATA_DIR: TEMP_DATA_DIR,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    let stdout = ''
    let stderr = ''
    child.stdin.write(script)
    child.stdin.end()
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code !== 0) {
        reject(new Error(stderr || `python exited with ${code}`))
        return
      }
      const [legacyLine, themeLine] = stdout.trim().split(/\r?\n/)
      resolve({
        legacyArticleId: Number(legacyLine),
        themeArticleIds: String(themeLine || '')
          .split(',')
          .map((item) => Number(item))
          .filter((item) => Number.isFinite(item) && item > 0),
      })
    })
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

    const seeded = await seedRound143Data()
    if (!seeded.legacyArticleId || seeded.themeArticleIds.length !== 3) {
      throw new Error(`Round143 seed failed: ${JSON.stringify(seeded)}`)
    }

    const themeTitle = 'Round143 AI Theme'
    const createdTheme = await fetchPaidJson('/api/me/knowledge/themes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: themeTitle,
        description: '用于 round143 验收的主题卡片。',
        initial_article_id: seeded.themeArticleIds[0],
      }),
    })

    await fetchPaidJson(`/api/me/knowledge/themes/${createdTheme.id}/articles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article_id: seeded.themeArticleIds[1] }),
    })
    await fetchPaidJson(`/api/me/knowledge/themes/${createdTheme.id}/articles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ article_id: seeded.themeArticleIds[2] }),
    })

    const browser = await chromium.launch({ headless: true })
    const page = await browser.newPage({ viewport: { width: 1660, height: 1280 } })

    try {
      await login(page, {
        email: 'paid@example.com',
        password: 'Paid2026!',
        expectedPath: '/membership',
      })

      await openRoute(page, '/')

      const heroTitle = await page.locator('body').textContent()
      if (!heroTitle?.includes('Fudan Business Knowledge')) {
        throw new Error('Home hero kicker did not update to Fudan Business Knowledge')
      }

      await page.getByRole('button', { name: 'EN' }).click()
      await page.waitForTimeout(500)
      await page.getByRole('button', { name: '中' }).click()
      await page.waitForTimeout(500)

      const desktopActionTexts = await page.locator('[data-navbar-desktop-action]').allTextContents()
      const lingeringEnglish = ['Membership', 'AI Assistant', 'Knowledge Base', 'My Library'].filter((label) =>
        desktopActionTexts.some((text) => text.includes(label)),
      )
      if (lingeringEnglish.length) {
        throw new Error(`Navbar language switch failed: ${JSON.stringify(desktopActionTexts)}`)
      }

      const legacyCard = page.locator('article').filter({ hasText: 'Round143 Legacy Default Cover' }).first()
      await legacyCard.waitFor({ timeout: 15000 })
      const legacyCardImageCount = await legacyCard.locator('img').count()
      if (legacyCardImageCount !== 0) {
        throw new Error('Legacy article card still renders a manual cover image')
      }

      await page.screenshot({ path: path.join(OUTPUT_DIR, 'home_round143.png'), fullPage: false })
      await legacyCard.screenshot({ path: path.join(OUTPUT_DIR, 'legacy_cover_card_round143.png') })

      await openRoute(page, '/me/knowledge')
      const themeCard = page.locator(`[data-knowledge-theme-card="${createdTheme.slug}"]`)
      await themeCard.waitFor({ timeout: 15000 })

      const themeAlignment = await themeCard.evaluate((node) => {
        const labels = [...node.querySelectorAll('.knowledge-console-label')]
        const countLabel = labels.find((item) => item.textContent?.includes('文章数') || item.textContent?.includes('Articles'))
        const countBox = countLabel?.parentElement
        const firstArticleCard = node.querySelector('a[href^="/article/"]')
        if (!countBox || !firstArticleCard) return null
        const countRect = countBox.getBoundingClientRect()
        const articleRect = firstArticleCard.getBoundingClientRect()
        return {
          countRight: Math.round(countRect.right),
          articleRight: Math.round(articleRect.right),
          delta: Math.round(Math.abs(countRect.right - articleRect.right)),
        }
      })
      if (!themeAlignment || themeAlignment.delta > 4) {
        throw new Error(`Knowledge theme count box alignment failed: ${JSON.stringify(themeAlignment)}`)
      }

      await themeCard.screenshot({ path: path.join(OUTPUT_DIR, 'knowledge_theme_card_round143.png') })

      await openRoute(page, '/')
      await page.evaluate(() => window.scrollTo({ top: 1200, left: 0, behavior: 'auto' }))
      await page.waitForTimeout(300)
      const legacyCardLink = page.locator('article').filter({ hasText: 'Round143 Legacy Default Cover' }).first().locator('a').first()
      await Promise.all([
        page.waitForURL(new RegExp(`${FRONTEND_URL}/article/\\d+$`), { timeout: 20000 }),
        legacyCardLink.click(),
      ])
      await page.waitForTimeout(800)
      const scrollY = await page.evaluate(() => window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0)
      if (scrollY > 40) {
        throw new Error(`Article scroll reset failed, scrollY=${scrollY}`)
      }

      await page.screenshot({ path: path.join(OUTPUT_DIR, 'article_scroll_reset_round143.png'), fullPage: false })
    } finally {
      await page.close()
      await browser.close()
    }
  } finally {
    await Promise.all([terminateProcess(previewProcess), terminateProcess(backendProcess)])
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true })
  }
}

await main()
