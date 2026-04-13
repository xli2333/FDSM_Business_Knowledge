import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round95_editorial')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round95-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8012
const FRONTEND_PORT = 4177
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ACCOUNTS = {
  admin: { email: 'admin@example.com', password: 'Admin2026!', homePath: '/admin' },
}

const PYTHON_SEED_SCRIPT = `
import json
from datetime import datetime
from backend.database import connection_scope

sample_html = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Round95 编辑验收稿</title>
    <style>
      body { margin: 0; padding: 16px 10px 32px; background: #f8fbff; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
      .wechat-preview-shell { max-width: 760px; margin: 0 auto; background: #ffffff; }
      .hero { margin: 0 auto 28px; width: 100%; max-width: 700px; }
      .hero h1 { margin: 0 0 16px; font-size: 42px; line-height: 1.18; font-weight: 800; color: #111827; }
      .meta { margin: 0 0 24px; color: #94a3b8; font-size: 15px; line-height: 1.8; }
      .body { color: #334155; }
      .body p { margin: 0 0 20px; font-size: 17px; line-height: 2; }
      .highlight { background: rgba(59, 130, 246, 0.12); padding: 0 4px; }
      h2 { margin: 40px 0 20px; text-align: center; font-size: 36px; line-height: 1.3; color: #3192f5; }
      table { width: 100%; margin: 28px 0; border-collapse: collapse; }
      th, td { border: 1px solid #cbd5e1; padding: 14px 16px; font-size: 15px; line-height: 1.8; }
      th { background: #edf4ff; color: #334155; text-align: left; }
    </style>
  </head>
  <body>
    <div class="wechat-preview-shell" data-wechat-decoration="1">
      <section class="hero">
        <h1>Round95 编辑验收稿</h1>
        <p class="meta">文 小李的信息工坊　2026年4月10日 12:00　新加坡</p>
      </section>
      <section class="body">
        <p>这是正文第一段，<strong>需要保留强调</strong>，并且可以继续编辑。</p>
        <p><span class="highlight">这句是高亮样式</span>，用来验收模板保真。</p>
        <h2>#2 同质化竞争与B端市场的信任壁垒</h2>
        <table>
          <thead>
            <tr><th>数据维度</th><th>现实表现</th><th>结论指向</th></tr>
          </thead>
          <tbody>
            <tr><td>可持续收入比例</td><td>约20%</td><td>大多数会快速出局</td></tr>
          </tbody>
        </table>
        <p>这是正文第二段，用于验证保存后刷新仍然存在。</p>
      </section>
    </div>
  </body>
</html>"""

with connection_scope() as connection:
    editorial_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM editorial_articles").fetchone()[0])
    now = datetime.now().replace(microsecond=0).isoformat()
    connection.execute(
        \"\"\"
        INSERT INTO editorial_articles (
            id, article_id, slug, title, subtitle, author, organization, publish_date, source_url, cover_image_url,
            primary_column_slug, article_type, main_topic, content_markdown, plain_text_content, excerpt,
            tag_payload_json, html_web, html_wechat, status, created_at, updated_at, published_at, access_level,
            workflow_status, review_note, scheduled_publish_at, submitted_at, approved_at, source_article_id,
            ai_synced_at, source_markdown, layout_mode, formatting_notes, formatter_model, last_formatted_at,
            tag_suggestion_payload_json, removed_tag_payload_json, primary_column_ai_slug, primary_column_manual,
            final_html, render_metadata_json, publish_validation_json, published_final_html, editor_document_json,
            editor_source, editor_updated_at, manual_final_html_backup, draft_box_state
        )
        VALUES (?, NULL, ?, ?, '', ?, ?, '2026-04-10', '', '', 'insights', NULL, NULL, ?, ?, ?,
                ?, ?, ?, 'draft', ?, ?, NULL, 'public',
                'draft', NULL, NULL, NULL, NULL, NULL,
                NULL, ?, 'auto', '', NULL, NULL,
                '[]', '[]', 'insights', 1,
                ?, '{}', '[]', NULL, ?, 'manual_edited', ?, NULL, 'active')
        \"\"\",
        (
            editorial_id,
            f'round95-editorial-{editorial_id}',
            'Round95 编辑验收稿',
            '小李的信息工坊',
            'Fudan Business Knowledge',
            '这是正文第一段，需要保留强调，并且可以继续编辑。\\n\\n这是正文第二段，用于验证保存后刷新仍然存在。',
            '这是正文第一段，需要保留强调，并且可以继续编辑。这句是高亮样式，用来验收模板保真。#2 同质化竞争与B端市场的信任壁垒 数据维度 现实表现 结论指向 可持续收入比例 约20% 大多数会快速出局 这是正文第二段，用于验证保存后刷新仍然存在。',
            'Round95 编辑验收稿：标题、强调、表格和正文都要保留。',
            json.dumps([{'name': 'Round95', 'slug': 'round95', 'category': 'topic', 'confidence': 0.95}], ensure_ascii=False),
            sample_html,
            sample_html,
            now,
            now,
            '这是正文第一段，需要保留强调，并且可以继续编辑。\\n\\n这是正文第二段，用于验证保存后刷新仍然存在。',
            sample_html,
            json.dumps({'schema': 'editable-html-v1', 'html': sample_html}, ensure_ascii=False),
            now,
        ),
    )
    connection.commit()

print(json.dumps({'sample_editorial_id': editorial_id, 'template_editorial_id': 104}, ensure_ascii=False))
`

const PYTHON_VERIFY_SCRIPT = `
import json
from backend.database import connection_scope

editorial_id = int("__EDITORIAL_ID__")

with connection_scope() as connection:
    row = connection.execute(
        "SELECT final_html FROM editorial_articles WHERE id = ?",
        (editorial_id,),
    ).fetchone()

html = str(row["final_html"] or "")
print(json.dumps({
    "title_persisted": "已通过" in html,
    "table_persisted": "已验证" in html,
    "body_persisted": "新增一句。" in html,
}, ensure_ascii=False))
`

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

function runCommand(command, args, cwd, extraEnv = {}, input = '') {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: process.platform === 'win32',
      env: {
        ...process.env,
        ...extraEnv,
      },
    })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    if (input) {
      child.stdin.write(input)
    }
    child.stdin.end()
    child.on('error', reject)
    child.on('exit', (code) => {
      if (code === 0) {
        resolve(stdout.trim())
        return
      }
      reject(new Error(`${command} ${args.join(' ')} exited with code ${code}\n${stderr}`))
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

async function copyRuntimeDatabase() {
  await fs.mkdir(TEMP_DATA_DIR, { recursive: true })
  await fs.copyFile(SOURCE_DB_PATH, path.join(TEMP_DATA_DIR, 'fudan_knowledge_base.db'))
}

async function seedAcceptanceData() {
  const stdout = await runCommand('python', ['-'], PROJECT_ROOT, {
    FDSM_DATA_DIR: TEMP_DATA_DIR,
  }, PYTHON_SEED_SCRIPT)
  return JSON.parse(stdout)
}

async function resolveEditorFrame(page) {
  await page.locator('iframe[title="Editable editorial document frame"]').waitFor({ timeout: 30000 })
  const handle = await page.locator('iframe[title="Editable editorial document frame"]').elementHandle()
  const frame = await handle.contentFrame()
  if (!frame) throw new Error('Editable frame not available')
  return frame
}

async function resolvePreviewFrame(page) {
  await page.locator('iframe[title="Editorial preview frame"]').waitFor({ timeout: 30000 })
  const handle = await page.locator('iframe[title="Editorial preview frame"]').elementHandle()
  const frame = await handle.contentFrame()
  if (!frame) throw new Error('Preview frame not available')
  return frame
}

async function clickAndPlaceCaretAtEnd(frame, selector) {
  await frame.locator(selector).first().click({ timeout: 30000 })
  await frame.evaluate((targetSelector) => {
    const element = document.querySelector(targetSelector)
    if (!element) throw new Error(`Missing editable element: ${targetSelector}`)
    const selection = window.getSelection()
    const range = document.createRange()
    range.selectNodeContents(element)
    range.collapse(false)
    selection.removeAllRanges()
    selection.addRange(range)
    window.focus()
    if (document.body && typeof document.body.focus === 'function') document.body.focus()
  }, selector)
}

async function saveScreenshot(page, filename) {
  await page.screenshot({ path: path.join(OUTPUT_DIR, filename), fullPage: true })
}

async function saveFrameScreenshot(frame, filename, selector = 'body') {
  const target = frame.locator(selector).first()
  await target.waitFor({ timeout: 30000 })
  await target.screenshot({ path: path.join(OUTPUT_DIR, filename) })
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true })
  await copyRuntimeDatabase()
  const ids = await seedAcceptanceData()

  const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  await runCommand(npmCommand, ['run', 'build'], FRONTEND_DIR, {
    VITE_API_BASE_URL: `${BACKEND_URL}/api`,
  })

  const sharedEnv = {
    FDSM_DATA_DIR: TEMP_DATA_DIR,
    DEV_AUTH_ENABLED: '1',
    ADMIN_EMAILS: 'admin@example.com',
    PAYMENTS_ENABLED: '0',
    PAYMENT_PROVIDER: 'mock',
  }

  const backendProcess = spawnServer(
    'python',
    ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    PROJECT_ROOT,
    sharedEnv,
  )
  const previewProcess = spawnServer(npmCommand, ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)], FRONTEND_DIR, {
    VITE_API_BASE_URL: `${BACKEND_URL}/api`,
  })

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const browser = await chromium.launch()
    const page = await browser.newPage({ viewport: { width: 1600, height: 1400 } })
    await configureLanguage(page, 'zh')
    await loginWithPassword(page, 'admin')

    await openRoute(page, `/editorial?editorial_id=${ids.template_editorial_id}`)
    const realTemplateFrame = await resolveEditorFrame(page)
    await realTemplateFrame.locator('body').waitFor({ timeout: 30000 })
    const realTemplateTitleVisible = await realTemplateFrame.locator('text=朋友圈里的“小丑”与“死者”：一场让渡体面的社交自救').count()
    await saveFrameScreenshot(realTemplateFrame, 'round95-real-template-edit.png', '.wechat-preview-shell')

    await openRoute(page, `/editorial?editorial_id=${ids.sample_editorial_id}`)
    const sampleFrame = await resolveEditorFrame(page)
    await sampleFrame.locator('h1').waitFor({ timeout: 30000 })

    const initialChecks = {
      title_visible: (await sampleFrame.locator('h1').textContent())?.includes('Round95 编辑验收稿') || false,
      table_visible: (await sampleFrame.locator('table').count()) > 0,
      emphasis_visible: (await sampleFrame.locator('strong').textContent())?.includes('需要保留强调') || false,
      body_visible: (await sampleFrame.locator('text=这是正文第二段').count()) > 0,
    }

    await clickAndPlaceCaretAtEnd(sampleFrame, 'h1')
    await page.keyboard.type(' 已通过')
    await page.waitForTimeout(250)

    await clickAndPlaceCaretAtEnd(sampleFrame, 'tbody td:last-child')
    await page.keyboard.type(' / 已验证')
    await page.waitForTimeout(250)

    await clickAndPlaceCaretAtEnd(sampleFrame, 'p:last-of-type')
    await page.keyboard.type(' 新增一句。')
    await page.waitForTimeout(250)

    await sampleFrame.locator('text=Round95 编辑验收稿 已通过').waitFor({ timeout: 30000 })
    await sampleFrame.locator('text=已验证').waitFor({ timeout: 30000 })
    await sampleFrame.locator('text=新增一句。').waitFor({ timeout: 30000 })
    await saveFrameScreenshot(sampleFrame, 'round95-sample-edit.png', '.wechat-preview-shell')

    await page.getByRole('button', { name: '保存' }).click()
    await page.getByText('草稿已保存。').waitFor({ timeout: 30000 })

    await page.getByRole('button', { name: '预览' }).click()
    await page.waitForTimeout(800)
    const previewFrame = await resolvePreviewFrame(page)
    await previewFrame.locator('text=Round95 编辑验收稿 已通过').waitFor({ timeout: 30000 })
    await previewFrame.locator('text=已验证').waitFor({ timeout: 30000 })
    await previewFrame.locator('text=新增一句。').waitFor({ timeout: 30000 })
    await saveFrameScreenshot(previewFrame, 'round95-sample-preview.png', '.wechat-preview-shell')

    const persistedChecks = JSON.parse(
      await runCommand(
        'python',
        ['-'],
        PROJECT_ROOT,
        {
          FDSM_DATA_DIR: TEMP_DATA_DIR,
        },
        PYTHON_VERIFY_SCRIPT.replace('__EDITORIAL_ID__', String(ids.sample_editorial_id)),
      ),
    )

    await browser.close()

    console.log(
      JSON.stringify(
        {
          output_dir: OUTPUT_DIR,
          ids,
          real_template_title_visible: realTemplateTitleVisible > 0,
          initial_checks: initialChecks,
          persisted_checks: persistedChecks,
        },
        null,
        2,
      ),
    )
  } finally {
    await Promise.all([terminateProcess(backendProcess), terminateProcess(previewProcess)])
    await fs.rm(TEMP_DATA_DIR, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
