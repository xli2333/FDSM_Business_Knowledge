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

async function fetchAdminJson(pathname, init = {}) {
  const response = await fetch(`${BACKEND_URL}${pathname}`, {
    ...init,
    headers: {
      'X-Debug-User-Id': 'round106-admin',
      'X-Debug-User-Email': 'admin@example.com',
      ...(init.headers || {}),
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
    await page.getByText(/full transcript to AI first.*fallback extraction is only used when AI is unavailable/i).waitFor({
      timeout: 20000,
    })
    await page.getByRole('button', { name: /^New draft$/i }).click()
    await page.locator('select[name="kind"]').selectOption('video')
    await page.getByRole('button', { name: /^Upload script$/i }).waitFor({ state: 'visible', timeout: 20000 })

    await page.locator('[data-upload-slot="media"]').setInputFiles({
      name: 'round106-media.mp4',
      mimeType: 'video/mp4',
      buffer: Buffer.from('\x00\x00\x00\x18ftypmp42'),
    })
    await page.waitForFunction(() => {
      const mediaUrl = document.querySelector('input[name="media_url"]')
      return Boolean(mediaUrl?.value?.includes('/media-uploads/'))
    })
    const uploadedMediaUrl = await page.locator('input[name="media_url"]').inputValue()
    let mediaDraft = null
    const mediaDraftWaitStarted = Date.now()
    while (Date.now() - mediaDraftWaitStarted < 30000) {
      const draftPayload = await fetchAdminJson('/api/media/admin/items?kind=video&limit=80')
      const matchedDraft = (draftPayload.items || []).find((item) => item.media_url === uploadedMediaUrl || item.source_url === uploadedMediaUrl)
      if (matchedDraft?.id) {
        mediaDraft = matchedDraft
        break
      }
      await page.waitForTimeout(1000)
    }
    if (!mediaDraft?.id) {
      throw new Error(`Uploaded media did not resolve to a draft: ${uploadedMediaUrl}`)
    }

    await page.locator('input[name="title"]').fill(uniqueLabel)
    await page.locator('[data-upload-slot="text"]').setInputFiles({
      name: 'round106-transcript.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from(
        '# 转录\n\n发言人 1 00:00\n欢迎来到复旦商业知识。今天我们先抛出一个问题：媒体上传后为什么先进入草稿箱，而不是直接上线？\n\n发言人 1 00:42\n接下来真正要拆的是工作流逻辑：脚本上传、章节识别和生成文案为什么要放在同一个后台页面里。\n\n发言人 1 01:25\n最后回到发布动作，解释为什么正式上线后要自动离开草稿箱，并且从正式页重新进入编辑流。',
      ),
    })
    let uploadedDraft = null
    const chapterWaitStarted = Date.now()
    while (Date.now() - chapterWaitStarted < 30000) {
      const draftDetail = await fetchAdminJson(`/api/media/admin/items/${mediaDraft.id}`)
      if ((draftDetail.chapters || []).length >= 3) {
        uploadedDraft = draftDetail
        break
      }
      await page.waitForTimeout(1000)
    }
    if (!uploadedDraft || (uploadedDraft.chapters || []).length < 3) {
      throw new Error(`Uploaded script did not produce chapters for draft: ${uniqueLabel}`)
    }
    const uploadedChapterTitles = (uploadedDraft.chapters || []).map((item) => String(item.title || '').trim()).filter(Boolean)
    if (
      uploadedChapterTitles.some((title) =>
        ['发言人 1', '欢迎来到复旦商业知识', '接下来真正要拆的是', '最后回到发布动作', '：', ':'].some((token) => title.includes(token)),
      ) ||
      new Set(uploadedChapterTitles).size !== uploadedChapterTitles.length ||
      uploadedChapterTitles.some((title) => title.length < 6)
    ) {
      throw new Error(`Uploaded script produced weak chapter titles: ${uploadedChapterTitles.join(' | ')}`)
    }

    uploadedDraft = await fetchAdminJson(`/api/media/admin/items/${uploadedDraft.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        transcript_markdown:
          '# 转录\n\n发言人 1 00:00\n这段完整转录先解释为什么媒体上传后要先进入草稿箱。\n\n发言人 1 00:42\n这段完整转录再拆章节识别和生成文案为什么必须放在同一个工作台里。\n\n发言人 1 01:25\n这段完整转录最后回到发布后离开草稿箱与正式页重新编辑。',
        script_markdown: '00:00 脚本里故意写一个不该被采用的假主题\n09:09 脚本里故意写一个不该被采用的假收尾',
      }),
    })
    const transcriptFirstLabels = (uploadedDraft.chapters || []).map((item) => String(item.timestamp_label || '').trim())
    if (transcriptFirstLabels.includes('09:09')) {
      throw new Error(`Transcript-first fallback regressed and used script timestamps: ${transcriptFirstLabels.join(' | ')}`)
    }

    const staleChapters = (uploadedDraft.chapters || []).map((item, index) => ({
      timestamp_label: item.timestamp_label,
      timestamp_seconds: item.timestamp_seconds,
      title: `待重写旧标题${index + 1}`,
    }))
    await fetchAdminJson(`/api/media/admin/items/${uploadedDraft.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ chapters: staleChapters }),
    })

    const transcriptFieldCount = await page.locator('textarea[name="transcript_markdown"], textarea[name="script_markdown"]').count()
    if (transcriptFieldCount !== 0) {
      throw new Error(`Raw transcript/script editors should be hidden, found ${transcriptFieldCount}`)
    }

    await openRoute(page, `/media-studio?draft_id=${uploadedDraft.id}`)
    await page.waitForFunction(
      (expectedTitle) => {
        const title = document.querySelector('input[name="title"]')
        return title?.value === expectedTitle
      },
      uniqueLabel,
    )
    await page.getByRole('button', { name: /^Rewrite chapters$/i }).first().waitFor({ state: 'visible', timeout: 20000 })

    const rewrittenDraft = await fetchAdminJson(`/api/media/admin/items/${uploadedDraft.id}/rewrite-chapters`, { method: 'POST' })
    const rewrittenTitles = (rewrittenDraft.chapters || []).map((item) => String(item.title || '').trim())
    const rewrittenLabels = (rewrittenDraft.chapters || []).map((item) => String(item.timestamp_label || '').trim())
    if (
      rewrittenTitles.length < 3 ||
      rewrittenTitles.some((title) => title.startsWith('待重写旧标题')) ||
      rewrittenLabels.includes('09:09')
    ) {
      throw new Error(`Rewrite chapters did not replace stale titles: ${uniqueLabel}`)
    }

    const generatedDraft = await fetchAdminJson(`/api/media/admin/items/${uploadedDraft.id}/generate-copy`, { method: 'POST' })
    if (
      String(generatedDraft.summary || '').includes('不该被采用的假主题') ||
      String(generatedDraft.body_markdown || '').includes('不该被采用的假主题')
    ) {
      throw new Error(`Generate copy regressed to script-first source selection: ${uniqueLabel}`)
    }
    await openRoute(page, `/media-studio?draft_id=${generatedDraft.id}`)
    await page.waitForFunction(
      (expectedTitle) => {
        const title = document.querySelector('input[name="title"]')
        return title?.value === expectedTitle
      },
      uniqueLabel,
    )
    await page.waitForFunction(() => {
      const summary = document.querySelector('textarea[name="summary"]')
      const body = document.querySelector('textarea[name="body_markdown"]')
      return Boolean(summary?.value?.trim() && body?.value?.trim())
    })
    await page.waitForFunction(() => {
      const summaryPreview = document.querySelector('[data-media-markdown="draft-summary"]')
      const bodyPreview = document.querySelector('[data-media-markdown="draft-body"]')
      const summaryValue = document.querySelector('textarea[name="summary"]')?.value || ''
      const bodyValue = document.querySelector('textarea[name="body_markdown"]')?.value || ''
      const bulletCount = bodyPreview?.querySelectorAll('li')?.length || 0
      return Boolean(
        summaryPreview &&
          bodyPreview &&
          summaryValue.includes('**') &&
          bodyValue.includes('## ') &&
          bodyValue.includes('- ') &&
          bulletCount >= 1 &&
          bulletCount <= 3 &&
          !summaryPreview.textContent?.includes('**') &&
          !bodyPreview.textContent?.includes('## '),
      )
    })

    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_before_publish.png'), fullPage: true })

    const publishedDraft = await fetchAdminJson(`/api/media/admin/items/${generatedDraft.id}/publish`, { method: 'POST' })

    const draftPayloadAfterPublish = await fetchAdminJson('/api/media/admin/items?kind=video&limit=40')
    if ((draftPayloadAfterPublish.items || []).some((item) => item.title === uniqueLabel)) {
      throw new Error(`Draft still exists in draft box after publish: ${uniqueLabel}`)
    }

    await openRoute(page, '/video')
    const publishedCard = page.locator('article').filter({ hasText: uniqueLabel }).first()
    await publishedCard.waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForFunction((expectedTitle) => {
      const card = Array.from(document.querySelectorAll('article')).find((node) => node.textContent?.includes(expectedTitle))
      const summary = card?.querySelector('[data-media-markdown="hub-summary"]')
      return Boolean(summary && !summary.textContent?.includes('**'))
    }, uniqueLabel)
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_published_hub.png'), fullPage: true })

    await publishedCard.getByRole('link', { name: /View video details/i }).click()
    await page.waitForURL(new RegExp(`/video/${publishedDraft.slug}$`), { timeout: 20000 })
    await page.waitForFunction(() => {
      const detailRoot = document.querySelector('[data-media-detail-page="video"]')
      const body = document.querySelector('[data-media-markdown="detail-body"]')
      const chapters = document.querySelectorAll('[data-media-chapter-button]')
      return Boolean(
        detailRoot &&
          body &&
          chapters.length >= 2 &&
          !body.textContent?.includes('## '),
      )
    })
    await page.locator('[data-media-chapter-button="00:42"]').click()
    await page.waitForFunction(() => {
      const activeButton = document.querySelector('[data-media-chapter-button="00:42"]')
      const detailRoot = document.querySelector('[data-media-detail-page="video"]')
      return activeButton?.getAttribute('aria-pressed') === 'true' && detailRoot?.getAttribute('data-selected-chapter') === '42'
    })
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_detail_page.png'), fullPage: true })

    await page.getByRole('button', { name: /Edit again/i }).click()
    await page.waitForURL(/\/media-studio\?draft_id=\d+&reopened=1/, { timeout: 20000 })
    await page.waitForFunction(
      (expectedTitle) => {
        const title = document.querySelector('input[name="title"]')
        return title?.value === expectedTitle
      },
      uniqueLabel,
    )

    await page.getByText(/entered this draft from a published media card/i).first().waitFor({ state: 'visible', timeout: 20000 })
    await page.waitForFunction(() => {
      const summaryPreview = document.querySelector('[data-media-markdown="published-summary"]')
      const bodyPreview = document.querySelector('[data-media-markdown="published-body"]')
      const bulletCount = bodyPreview?.querySelectorAll('li')?.length || 0
      return Boolean(
        summaryPreview &&
          bodyPreview &&
          bulletCount >= 1 &&
          bulletCount <= 3 &&
          !summaryPreview.textContent?.includes('**') &&
          !bodyPreview.textContent?.includes('## '),
      )
    })
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'media_after_edit_again.png'), fullPage: true })

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
