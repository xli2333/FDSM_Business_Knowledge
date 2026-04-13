import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round101_editorial')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round101-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8013
const FRONTEND_PORT = 4178
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ACCOUNTS = {
  admin: { email: 'admin@example.com', password: 'Admin2026!', homePath: '/admin' },
}

const PYTHON_SEED_SCRIPT = `
import json
from datetime import datetime

from backend.database import connection_scope, ensure_runtime_tables
from backend.services.editorial_service import create_editorial_article

ensure_runtime_tables()

summary_markdown = """### 核心摘要

- **23andMe** 的数据治理危机说明基因隐私不是普通的数据问题。
- 690 万人的链式暴露，来自高互联产品设计与薄弱安全治理的叠加。
""".strip()

summary_html = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; padding: 12px 8px 20px; background: #f8fbff; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
      .shell { max-width: 760px; margin: 0 auto; background: #ffffff; }
      .article { padding: 18px 18px 14px; background: #ffffff; }
      .inner { margin: 0 auto; width: 100%; max-width: 700px; }
      .dots { margin: 0 0 16px 4px; line-height: 0; }
      .dot { display: inline-block; width: 8px; height: 8px; margin-right: 28px; border-radius: 999px; background: #cbd5e1; }
      h3 { margin: 0 0 16px; color: #1f3251; font-size: 18px; line-height: 1.5; font-weight: 700; }
      p, li { margin: 0 0 14px; color: #475569; font-size: 15px; line-height: 1.92; }
      ul { margin: 0; padding-left: 22px; }
      strong { padding: 0 6px 1px; border-bottom: 1px solid #d3e6fb; background: #eaf3ff; color: #243b5a; font-weight: 700; }
    </style>
  </head>
  <body>
    <div class="shell summary-preview-shell">
      <section class="article">
        <article class="inner">
          <p class="dots"><span class="dot"></span><span class="dot"></span><span class="dot" style="margin-right:0;"></span></p>
          <h3>核心摘要</h3>
          <ul>
            <li><strong>23andMe</strong> 的数据治理危机说明基因隐私不是普通的数据问题。</li>
            <li>690 万人的链式暴露，来自高互联产品设计与薄弱安全治理的叠加。</li>
          </ul>
        </article>
      </section>
    </div>
  </body>
</html>"""

body_html = """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { margin: 0; padding: 16px 10px 32px; background: #f8fbff; font-family: "PingFang SC", "Microsoft YaHei", sans-serif; }
      .wechat-preview-shell { max-width: 760px; margin: 0 auto; background: #ffffff; }
      .hero { margin: 0 auto 28px; width: 100%; max-width: 700px; }
      .hero h1 { margin: 0 0 16px; font-size: 42px; line-height: 1.18; font-weight: 800; color: #111827; }
      .lead { margin: 0 0 18px; color: #64748b; font-size: 18px; line-height: 1.9; text-align: center; }
      .body { margin: 0 auto; width: 100%; max-width: 700px; color: #334155; }
      .body p { margin: 0 0 20px; font-size: 17px; line-height: 2; }
      .body strong { background: rgba(59, 130, 246, 0.12); padding: 0 4px; }
      .body h2 { margin: 40px 0 20px; text-align: center; font-size: 36px; line-height: 1.3; color: #3192f5; }
      table { width: 100%; margin: 28px 0; border-collapse: collapse; }
      th, td { border: 1px solid #cbd5e1; padding: 14px 16px; font-size: 15px; line-height: 1.8; }
      th { background: #edf4ff; color: #334155; text-align: left; }
    </style>
  </head>
  <body>
    <div class="wechat-preview-shell" data-wechat-decoration="1">
      <section class="hero">
        <h1>基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运</h1>
        <p class="lead">当不可更改的生命蓝图沦为商品，整个生物科技行业都需要重新回答“谁来承担最终责任”。</p>
      </section>
      <section class="body">
        <p>曾经估值 60 亿美元的硅谷明星企业 <strong>23andMe</strong>，正在用一场数据治理危机重新定义消费级基因检测平台的风险边界。</p>
        <h2>#1 690 万人的链式暴露</h2>
        <p>攻击者只攻破了约 14000 个账户，但 DNA Relatives 的关系网络把单点失守放大成了 690 万人的系统性泄露。</p>
        <table>
          <thead>
            <tr><th>风险维度</th><th>现实结果</th><th>直接后果</th></tr>
          </thead>
          <tbody>
            <tr><td>登录保护</td><td>未强制 MFA</td><td>撞库攻击得手</td></tr>
            <tr><td>网络拓扑</td><td>亲缘关系可连带抓取</td><td>单点入侵级联扩散</td></tr>
          </tbody>
        </table>
        <p>这不是一个页面上的小漏洞，而是一套增长逻辑与安全逻辑失衡后的结构性后果。</p>
      </section>
    </div>
  </body>
</html>"""

with connection_scope() as connection:
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    next_article_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM articles").fetchone()[0])
    older_article_id = next_article_id
    latest_article_id = next_article_id + 1
    editorial_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM editorial_articles").fetchone()[0])

    connection.execute(
        "DELETE FROM home_content_slots WHERE slot_key = 'column_navigation'"
    )

    connection.execute(
        """
        INSERT INTO articles (
            id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
            content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
            tag_text, people_text, org_text, search_text, word_count, cover_image_path,
            access_level, view_count, is_featured, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL, ?, ?, '数据治理', 'insight', 'Editorial',
                'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge', ?, ?, NULL,
                'public', 0, 0, ?, ?)
        """,
        (
            older_article_id,
            f'round101-older-{older_article_id}',
            'round101-older-featured-column-article',
            'editorial/round101-older-featured-column-article.md',
            '旧精选栏目文章',
            '2026-04-05',
            '这是一篇较早发布的栏目文章，用于验证旧精选位不再压住新稿。',
            '旧精选栏目文章摘要。',
            '旧精选栏目文章 旧精选栏目文章摘要。',
            24,
            timestamp,
            timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO articles (
            id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
            content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
            tag_text, people_text, org_text, search_text, word_count, cover_image_path,
            access_level, view_count, is_featured, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL, ?, ?, '数据治理', 'insight', 'Editorial',
                'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge', ?, ?, NULL,
                'public', 0, 0, ?, ?)
        """,
        (
            latest_article_id,
            f'round101-latest-{latest_article_id}',
            'round101-latest-summary-contract-article',
            'editorial/round101-latest-summary-contract-article.md',
            '基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运',
            '2026-04-10',
            '曾经估值 60 亿美元的硅谷明星企业 23andMe，正在经历成立以来最严峻的信任审判。',
            '基因密码的失守摘要。',
            '基因密码的失守 基因密码的失守摘要。',
            72,
            timestamp,
            timestamp,
        ),
    )

    insights_row = connection.execute("SELECT id FROM columns WHERE slug = 'insights'").fetchone()
    insights_id = int(insights_row["id"])
    connection.execute(
        "INSERT INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
        (older_article_id, insights_id),
    )
    connection.execute(
        "INSERT INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 0, 0)",
        (latest_article_id, insights_id),
    )

    connection.execute(
        """
        INSERT INTO home_content_slots (
            slot_key, entity_type, entity_id, entity_slug, sort_order, is_active, metadata_json, created_at, updated_at
        )
        VALUES ('column_navigation', 'column', ?, 'insights', 0, 1, '{}', ?, ?)
        """,
        (insights_id, timestamp, timestamp),
    )

    connection.commit()

editorial_payload = create_editorial_article(
    {
        'title': '基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运',
        'author': '小李的信息工坊',
        'organization': 'Fudan Business Knowledge',
        'publish_date': '2026-04-10',
        'source_markdown': '23andMe 数据治理危机与 1500 万人基因隐私的命运\\n\\n2023年10月，黑客利用撞库攻击打开了 23andMe 的连锁暴露入口。',
        'content_markdown': '23andMe 数据治理危机与 1500 万人基因隐私的命运\\n\\n2023年10月，黑客利用撞库攻击打开了 23andMe 的连锁暴露入口。',
        'excerpt': '曾经估值 60 亿美元的硅谷明星企业 23andMe，正在经历成立以来最严峻的信任审判。',
        'primary_column_slug': 'insights',
        'primary_column_manual': True,
        'tags': [{'name': '数据治理', 'slug': 'topic-data-governance', 'category': 'topic', 'confidence': 0.96}],
        'summary_markdown': summary_markdown,
        'summary_html': summary_html,
        'summary_editor_document': {'schema': 'editable-html-v1', 'html': summary_html},
        'final_html': body_html,
        'editor_document': {'schema': 'editable-html-v1', 'html': body_html},
    }
)
editorial_id = int(editorial_payload['id'])

published_editorial_payload = create_editorial_article(
    {
        'title': '基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运',
        'author': '小李的信息工坊',
        'organization': 'Fudan Business Knowledge',
        'publish_date': '2026-04-10',
        'source_markdown': '23andMe 数据治理危机与 1500 万人基因隐私的命运\\n\\n2023年10月，黑客利用撞库攻击打开了 23andMe 的连锁暴露入口。',
        'content_markdown': '23andMe 数据治理危机与 1500 万人基因隐私的命运\\n\\n2023年10月，黑客利用撞库攻击打开了 23andMe 的连锁暴露入口。',
        'excerpt': '曾经估值 60 亿美元的硅谷明星企业 23andMe，正在经历成立以来最严峻的信任审判。',
        'primary_column_slug': 'insights',
        'primary_column_manual': True,
        'tags': [{'name': '数据治理', 'slug': 'topic-data-governance', 'category': 'topic', 'confidence': 0.96}],
        'summary_markdown': summary_markdown,
        'summary_html': summary_html,
        'summary_editor_document': {'schema': 'editable-html-v1', 'html': summary_html},
        'final_html': body_html,
        'editor_document': {'schema': 'editable-html-v1', 'html': body_html},
    }
)
published_editorial_id = int(published_editorial_payload['id'])

with connection_scope() as connection:
    connection.execute(
        """
        UPDATE editorial_articles
        SET
            article_id = ?,
            status = 'published',
            workflow_status = 'draft',
            draft_box_state = 'active',
            formatter_model = 'gemini-3-flash-preview',
            last_formatted_at = ?,
            summary_model = 'gemini-2.5-flash',
            summary_updated_at = ?,
            published_summary_html = summary_html,
            published_final_html = final_html,
            manual_summary_html_backup = summary_html,
            manual_final_html_backup = final_html,
            html_web = final_html,
            html_wechat = final_html,
            ai_synced_at = ?,
            published_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (latest_article_id, timestamp, timestamp, timestamp, timestamp, timestamp, published_editorial_id),
    )
    connection.commit()

print(json.dumps({'editorial_id': editorial_id, 'article_id': latest_article_id, 'older_article_id': older_article_id}, ensure_ascii=False))
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
    if (input) child.stdin.write(input)
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
  const stdout = await runCommand(
    'python',
    ['-'],
    PROJECT_ROOT,
    {
      FDSM_DATA_DIR: TEMP_DATA_DIR,
    },
    PYTHON_SEED_SCRIPT,
  )
  return JSON.parse(stdout)
}

async function resolveFrame(page, title) {
  await page.locator(`iframe[title="${title}"]`).waitFor({ timeout: 30000 })
  const handle = await page.locator(`iframe[title="${title}"]`).elementHandle()
  const frame = await handle?.contentFrame()
  if (!frame) throw new Error(`Frame not available: ${title}`)
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

async function saveScreenshot(target, filename) {
  await target.screenshot({ path: path.join(OUTPUT_DIR, filename) })
}

async function getFrameChecks(frame, checks) {
  const result = {}
  for (const [key, action] of Object.entries(checks)) {
    result[key] = await action(frame)
  }
  return result
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
  const previewProcess = spawnServer(
    npmCommand,
    ['run', 'preview', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT)],
    FRONTEND_DIR,
    {
      VITE_API_BASE_URL: `${BACKEND_URL}/api`,
    },
  )

  try {
    await waitForHttp(`${BACKEND_URL}/`)
    await waitForHttp(FRONTEND_URL)

    const browser = await chromium.launch()
    const page = await browser.newPage({ viewport: { width: 1600, height: 1500 } })
    await configureLanguage(page, 'zh')
    await loginWithPassword(page, 'admin')

    await openRoute(page, `/editorial?editorial_id=${ids.editorial_id}`)

    const summaryPanel = page.locator('.fudan-panel').filter({ hasText: 'AI 摘要工作区' }).first()
    const bodyPanel = page.locator('.fudan-panel').filter({ hasText: '最终 HTML 预览' }).first()
    await summaryPanel.waitFor({ timeout: 30000 })
    await bodyPanel.waitFor({ timeout: 30000 })

    const summaryEditFrame = await resolveFrame(page, 'Editable editorial summary frame')
    const bodyEditFrame = await resolveFrame(page, 'Editable editorial document frame')

    await summaryEditFrame.locator('.summary-preview-shell').waitFor({ timeout: 30000 })
    await bodyEditFrame.locator('.wechat-preview-shell').waitFor({ timeout: 30000 })

    const initialEditorChecks = {
      summary_ready: await summaryEditFrame.locator('text=核心摘要').count(),
      body_title_ready: await bodyEditFrame.locator('text=基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运').count(),
      body_table_ready: await bodyEditFrame.locator('table').count(),
    }

    await saveScreenshot(await summaryEditFrame.locator('.summary-preview-shell').first(), 'round101-editorial-summary-edit.png')
    await saveScreenshot(await bodyEditFrame.locator('.wechat-preview-shell').first(), 'round101-editorial-body-edit.png')

    await summaryPanel.getByRole('button', { name: '预览' }).click()
    await bodyPanel.getByRole('button', { name: '预览' }).click()
    await page.waitForTimeout(800)

    const summaryPreviewFrame = await resolveFrame(page, 'Editorial summary preview frame')
    const bodyPreviewFrame = await resolveFrame(page, 'Editorial preview frame')
    await summaryPreviewFrame.locator('.summary-preview-shell').waitFor({ timeout: 30000 })
    await bodyPreviewFrame.locator('.wechat-preview-shell').waitFor({ timeout: 30000 })

    const editorialPreviewChecks = {
      summary_contains_strong: await summaryPreviewFrame.locator('strong').count(),
      summary_contains_core_line: await summaryPreviewFrame.locator('text=690 万人的链式暴露').count(),
      body_contains_title: await bodyPreviewFrame.locator('text=基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运').count(),
      body_contains_table: await bodyPreviewFrame.locator('table').count(),
      body_contains_strong: await bodyPreviewFrame.locator('strong').count(),
      body_contains_body_line: await bodyPreviewFrame.locator('text=这不是一个页面上的小漏洞').count(),
    }

    await saveScreenshot(await summaryPreviewFrame.locator('.summary-preview-shell').first(), 'round101-editorial-summary-preview.png')
    await saveScreenshot(await bodyPreviewFrame.locator('.wechat-preview-shell').first(), 'round101-editorial-body-preview.png')

    await openRoute(page, `/article/${ids.article_id}`)
    const articleSummaryFrame = await resolveFrame(page, 'Chinese summary preview')
    const articleBodyFrame = await resolveFrame(page, 'Chinese article preview')
    await articleSummaryFrame.locator('body').waitFor({ timeout: 30000 })
    await articleBodyFrame.locator('body').waitFor({ timeout: 30000 })
    await page.waitForTimeout(800)

    const articleSummaryText = await articleSummaryFrame.evaluate(() => document.body?.innerText || '')
    const articleBodyText = await articleBodyFrame.evaluate(() => document.body?.innerText || '')
    const articleBodyHtml = await articleBodyFrame.evaluate(() => document.body?.innerHTML || '')

    const articleChecks = {
      summary_contains_core_line: articleSummaryText.includes('690 万人的链式暴露'),
      body_contains_title: articleBodyText.includes('基因密码的失守：23andMe 数据治理危机与 1500 万人的隐私命运'),
      body_contains_table: articleBodyHtml.includes('<table'),
      body_contains_strong: articleBodyHtml.includes('<strong>23andMe</strong>'),
      body_contains_body_line: articleBodyText.includes('这不是一个页面上的小漏洞'),
    }

    await saveScreenshot(page.locator('[data-testid="article-summary-section"]').first(), 'round101-article-summary.png')
    await saveScreenshot(page.locator('[data-testid="article-body-section"]').first(), 'round101-article-body.png')

    await openRoute(page, '/column/insights')
    const columnCards = page.locator('.page-shell .grid a')
    await columnCards.first().waitFor({ timeout: 30000 })
    const firstColumnTitle = ((await columnCards.first().textContent()) || '').trim()
    await saveScreenshot(page, 'round101-column-page.png')

    await openRoute(page, '/')
    const homeColumnPanel = page.locator('.fudan-panel').filter({ hasText: '深度洞察' }).first()
    await homeColumnPanel.waitFor({ timeout: 30000 })
    const homeFirstColumnTitle = ((await homeColumnPanel.locator('a').nth(0).textContent()) || '').trim()
    await saveScreenshot(homeColumnPanel, 'round101-home-column-preview.png')

    await browser.close()

    console.log(
      JSON.stringify(
        {
          output_dir: OUTPUT_DIR,
          ids,
          initial_editor_checks: initialEditorChecks,
          editorial_preview_checks: editorialPreviewChecks,
          article_checks: articleChecks,
          column_order: {
            first_column_card_title: firstColumnTitle,
            home_first_preview_title: homeFirstColumnTitle,
          },
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
