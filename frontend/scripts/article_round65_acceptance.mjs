import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round65_articles')
const BACKEND_PORT = 8011
const FRONTEND_PORT = 4176
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const ARTICLE_IDS = [2142, 2141, 2139, 2135, 2132, 2128, 2124, 2121, 2119, 2114]

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

async function openArticlePage(page, articleId, language) {
  const targetUrl = `${FRONTEND_URL}/article/${articleId}${language === 'en' ? '?lang=en' : ''}`
  const unavailablePattern = language === 'en' ? 'This article is temporarily unavailable.' : '当前文章暂时不可用。'

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
    try {
      await page.waitForLoadState('networkidle', { timeout: 15000 })
    } catch {}
    await page.waitForTimeout(1500)

    const pageText = await page.locator('body').innerText().catch(() => '')
    if (!pageText.includes(unavailablePattern)) {
      await page.waitForFunction(
        () => Boolean(document.querySelector('[data-testid="article-page-layout"]')) && document.querySelectorAll('iframe').length >= 2,
        null,
        { timeout: 120000 },
      )
      return
    }

    if (attempt < 2) {
      await page.waitForTimeout(2500)
    }
  }

  throw new Error(`Article ${articleId} (${language}) remained unavailable after retries.`)
}

async function waitForStableIframes(page) {
  const startedAt = Date.now()
  let previousSignature = ''
  while (Date.now() - startedAt < 15000) {
    const signature = await page.evaluate(() => {
      const frames = Array.from(document.querySelectorAll('iframe'))
      return frames
        .map((frame) => {
          try {
            const doc = frame.contentDocument
            const bodyHeight = doc?.body?.scrollHeight || 0
            const htmlHeight = doc?.documentElement?.scrollHeight || 0
            return `${Math.max(bodyHeight, htmlHeight)}`
          } catch {
            return '0'
          }
        })
        .join('|')
    })
    if (signature && signature === previousSignature && !signature.includes('0') && signature.split('|').length >= 2) {
      return
    }
    previousSignature = signature
    await page.waitForTimeout(500)
  }
}

async function captureArticle(page, articleId, language) {
  await openArticlePage(page, articleId, language)
  await waitForStableIframes(page)
  await page.screenshot({
    path: path.join(OUTPUT_DIR, `${language}-article-${articleId}.png`),
    fullPage: false,
  })
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
  const previewProcess = spawnServer(
    npmCommand,
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    FRONTEND_DIR,
  )

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const browser = await chromium.launch()
    const page = await browser.newPage({ viewport: { width: 1440, height: 1600 } })

    for (const language of ['zh', 'en']) {
      await configureLanguage(page, language)
      for (const articleId of ARTICLE_IDS) {
        await captureArticle(page, articleId, language)
      }
    }

    await browser.close()
    console.log(JSON.stringify({ output_dir: OUTPUT_DIR, screenshots: ARTICLE_IDS.length * 2 }, null, 2))
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
