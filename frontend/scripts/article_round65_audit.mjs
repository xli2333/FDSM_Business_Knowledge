import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'reports')
const BACKEND_PORT = 8012
const FRONTEND_PORT = 4177
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

async function auditArticle(page, articleId, language) {
  await configureLanguage(page, language)
  await openArticlePage(page, articleId, language)
  await waitForStableIframes(page)

  return page.evaluate((pageLanguage) => {
    function readBox(selector) {
      const node = document.querySelector(selector)
      if (!node) return null
      const rect = node.getBoundingClientRect()
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    }

    function readFrameAudit(title) {
      const frame = Array.from(document.querySelectorAll('iframe')).find((item) => item.title === title)
      if (!frame) return null
      try {
        const doc = frame.contentDocument
        const body = doc?.body
        const root = doc?.documentElement
        const text = body?.innerText || ''
        const headings = doc?.querySelectorAll('h1, h2, h3, h4').length || 0
        const paragraphs = doc?.querySelectorAll('p').length || 0
        const strongs = doc?.querySelectorAll('strong, b').length || 0
        const tables = doc?.querySelectorAll('table').length || 0
        const bodyHeight = Math.max(body?.scrollHeight || 0, root?.scrollHeight || 0)
        return {
          bodyHeight,
          headings,
          paragraphs,
          strongs,
          tables,
          hasRawMarkdownHeading: /(^|\n)\s{0,3}#{1,6}\s/.test(text),
          hasRawBulletFlood: (text.match(/(^|\n)\s*[-*]\s+/g) || []).length >= 8,
        }
      } catch {
        return null
      }
    }

    const rootStyle = getComputedStyle(document.documentElement)
    const fudanBlue = rootStyle.getPropertyValue('--color-fudan-blue').trim()
    const fudanOrange = rootStyle.getPropertyValue('--color-fudan-orange').trim()
    const mainBox = readBox('[data-testid=\"article-main-column\"]')
    const sidebarBox = readBox('[data-testid=\"article-sidebar\"]')
    const summaryBox = readBox('[data-testid=\"article-summary-section\"]')
    const bodyBox = readBox('[data-testid=\"article-body-section\"]')
    const relatedBox = readBox('[data-testid=\"article-related-recommendations\"]')

    const relatedExists = Boolean(document.querySelector('[data-testid=\"article-related-recommendations\"]'))
    const summaryText = document.querySelector('[data-testid=\"article-summary-section\"]')?.innerText || ''
    const bodyText = document.querySelector('[data-testid=\"article-body-section\"]')?.innerText || ''

    const summaryAudit = readFrameAudit(pageLanguage === 'en' ? 'English summary preview' : 'Chinese summary preview')
    const bodyAudit = readFrameAudit(pageLanguage === 'en' ? 'English article preview' : 'Chinese article preview')

    return {
      fudanBlue,
      fudanOrange,
      mainBox,
      sidebarBox,
      summaryBox,
      bodyBox,
      relatedBox,
      relatedExists,
      sidebarOnRight: Boolean(mainBox && sidebarBox && sidebarBox.x > mainBox.x + mainBox.width * 0.66),
      summaryVisible: Boolean(summaryBox && summaryBox.height > 180),
      bodyVisible: Boolean(bodyBox && bodyBox.height > 500),
      summaryTextLength: summaryText.length,
      bodyTextLength: bodyText.length,
      summaryAudit,
      bodyAudit,
    }
  }, language)
}

function validateAudit(audit) {
  const failures = []
  if (!audit.sidebarOnRight) failures.push('sidebar_not_on_right')
  if (!audit.relatedExists) failures.push('related_missing')
  if (!audit.summaryVisible) failures.push('summary_not_visible')
  if (!audit.bodyVisible) failures.push('body_not_visible')
  if (!audit.fudanBlue || !audit.fudanOrange) failures.push('site_colors_missing')

  if (!audit.summaryAudit || audit.summaryAudit.bodyHeight < 180) failures.push('summary_iframe_height_low')
  if (!audit.bodyAudit || audit.bodyAudit.bodyHeight < 700) failures.push('body_iframe_height_low')
  if (audit.summaryAudit?.headings === 0 && audit.summaryAudit?.paragraphs < 2) failures.push('summary_structure_too_flat')
  if (audit.bodyAudit?.paragraphs < 6) failures.push('body_paragraphs_too_few')
  if (audit.summaryAudit?.hasRawMarkdownHeading) failures.push('summary_raw_markdown_heading')
  if (audit.bodyAudit?.hasRawMarkdownHeading) failures.push('body_raw_markdown_heading')

  return failures
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
    const results = []

    for (const language of ['zh', 'en']) {
      for (const articleId of ARTICLE_IDS) {
        const audit = await auditArticle(page, articleId, language)
        const failures = validateAudit(audit)
        results.push({ articleId, language, failures, audit })
      }
    }

    await browser.close()

    const report = {
      generatedAt: new Date().toISOString(),
      total: results.length,
      passed: results.filter((item) => item.failures.length === 0).length,
      failed: results.filter((item) => item.failures.length > 0).length,
      results,
    }
    await fs.writeFile(path.join(OUTPUT_DIR, 'round65_audit.json'), JSON.stringify(report, null, 2), 'utf-8')
    console.log(JSON.stringify({ report: path.join(OUTPUT_DIR, 'round65_audit.json'), passed: report.passed, failed: report.failed }, null, 2))
    if (report.failed > 0) {
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
