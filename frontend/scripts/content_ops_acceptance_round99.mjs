import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round99_content_ops')
const TEMP_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), 'fdsm-round99-'))
const SOURCE_DB_PATH = path.join(PROJECT_ROOT, 'fudan_knowledge_base.db')
const BACKEND_PORT = 8014
const FRONTEND_PORT = 4179
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const PYTHON_SEED_SCRIPT = `
import json
from datetime import date, datetime, timedelta

from backend.database import connection_scope, ensure_runtime_tables

ensure_runtime_tables()

def insert_article(connection, article_id, title, slug, publish_date):
    now = f"{publish_date}T09:00:00"
    connection.execute(
        """
        INSERT OR REPLACE INTO articles (
            id, doc_id, slug, relative_path, source, source_mode, title, publish_date, link,
            content, excerpt, main_topic, article_type, series_or_column, primary_org_name,
            tag_text, people_text, org_text, search_text, word_count, cover_image_path,
            access_level, view_count, is_featured, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'editorial', 'cms', ?, ?, NULL,
                'first paragraph\\n\\nsecond paragraph', ?, 'Topic Governance', 'insight', 'Editorial',
                'Fudan Business Knowledge', '', '', 'Fudan Business Knowledge', ?, 24, NULL,
                'public', 0, 0, ?, ?)
        """,
        (
            article_id,
            f"round99-doc-{article_id}",
            slug,
            f"editorial/{slug}.md",
            title,
            publish_date,
            f"{title} excerpt",
            f"{title} first paragraph second paragraph",
            now,
            now,
        ),
    )

with connection_scope() as connection:
    today = date.today()
    hero_article_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM articles").fetchone()[0])
    editor_article_id = hero_article_id + 1
    month_article_id = hero_article_id + 2
    week_article_id = hero_article_id + 3
    insert_article(connection, hero_article_id, "Round99 Hero Article", "round99-hero-article", (today + timedelta(days=1)).isoformat())
    insert_article(connection, editor_article_id, "Round99 Editor Pick", "round99-editor-pick", today.isoformat())
    insert_article(connection, month_article_id, "Round99 Month Hot", "round99-month-hot", (today - timedelta(days=20)).isoformat())
    insert_article(connection, week_article_id, "Round99 Week Hot", "round99-week-hot", (today - timedelta(days=7)).isoformat())

    column_row = connection.execute("SELECT id FROM columns WHERE slug = 'insights'").fetchone()
    if column_row is not None:
        for article_id in (hero_article_id, editor_article_id, month_article_id, week_article_id):
            connection.execute(
                "INSERT OR REPLACE INTO article_columns (article_id, column_id, is_featured, sort_order) VALUES (?, ?, 1, 0)",
                (article_id, int(column_row["id"])),
            )

    tag_row = connection.execute("SELECT id FROM tags WHERE slug = 'round99-quick-tag'").fetchone()
    if tag_row is None:
        connection.execute(
            "INSERT INTO tags (name, slug, category, description, color, article_count) VALUES ('Round99 Quick Tag', 'round99-quick-tag', 'topic', NULL, '#0d0783', 0)"
        )

    topic_row = connection.execute("SELECT id FROM topics WHERE slug = 'round99-topic'").fetchone()
    if topic_row is None:
        topic_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM topics").fetchone()[0])
        connection.execute(
            """
            INSERT INTO topics (
                id, title, slug, description, cover_image, cover_article_id, type, auto_rules,
                status, created_at, updated_at, view_count
            )
            VALUES (?, 'Round99 Topic', 'round99-topic', 'Round99 topic description', NULL, NULL, 'editorial', NULL, 'published', ?, ?, 0)
            """,
            (topic_id, today.isoformat(), today.isoformat()),
        )
    else:
        topic_id = int(topic_row["id"])

    second_topic_row = connection.execute("SELECT id FROM topics WHERE slug = 'round99-governance-topic'").fetchone()
    if second_topic_row is None:
        second_topic_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM topics").fetchone()[0])
        connection.execute(
            """
            INSERT INTO topics (
                id, title, slug, description, cover_image, cover_article_id, type, auto_rules,
                status, created_at, updated_at, view_count
            )
            VALUES (?, 'Round99 Governance Topic', 'round99-governance-topic', 'Round99 governance topic description', NULL, NULL, 'editorial', NULL, 'published', ?, ?, 0)
            """,
            (second_topic_id, today.isoformat(), today.isoformat()),
        )
    else:
        second_topic_id = int(second_topic_row["id"])

    connection.execute("DELETE FROM home_content_slots")
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    slot_rows = [
        ('hero', 'article', hero_article_id, None, 0, timestamp, timestamp),
        ('editors_picks', 'article', editor_article_id, None, 0, timestamp, timestamp),
        ('quick_tags', 'tag', None, 'round99-quick-tag', 0, timestamp, timestamp),
        ('topic_starters', 'topic', topic_id, 'round99-topic', 0, timestamp, timestamp),
        ('column_navigation', 'column', None, 'insights', 0, timestamp, timestamp),
        ('topic_square', 'topic', topic_id, 'round99-topic', 0, timestamp, timestamp),
    ]
    connection.executemany(
        """
        INSERT INTO home_content_slots (
            slot_key, entity_type, entity_id, entity_slug, sort_order, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        slot_rows,
    )
    connection.execute("DELETE FROM home_trending_config")
    connection.execute(
        "INSERT INTO home_trending_config (default_window, view_weight, like_weight, bookmark_weight, updated_at) VALUES ('week', 1, 4, 6, ?)",
        (timestamp,),
    )

    for index in range(800):
        connection.execute(
            """
            INSERT OR IGNORE INTO article_view_events (
                article_id, visitor_id, user_id, view_date, source, created_at
            )
            VALUES (?, ?, NULL, ?, 'acceptance', ?)
            """,
            (month_article_id, f"month-viewer-{index}", (today - timedelta(days=15)).isoformat(), timestamp),
        )
    for index in range(400):
        connection.execute(
            """
            INSERT OR IGNORE INTO article_view_events (
                article_id, visitor_id, user_id, view_date, source, created_at
            )
            VALUES (?, ?, NULL, ?, 'acceptance', ?)
            """,
            (week_article_id, f"week-viewer-{index}", today.isoformat(), timestamp),
        )

    editorial_id = int(connection.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM editorial_articles").fetchone()[0])
    final_html = "<!doctype html><html><body><article><h1>Round99 Editorial Topic Draft</h1><p>First body paragraph.</p><p>Second body paragraph.</p></article></body></html>"
    connection.execute(
        """
        INSERT INTO editorial_articles (
            id, slug, title, subtitle, author, organization, publish_date, source_url, cover_image_url,
            primary_column_slug, article_type, main_topic, access_level, source_markdown, layout_mode,
            formatting_notes, content_markdown, plain_text_content, excerpt, tag_suggestion_payload_json,
            tag_payload_json, removed_tag_payload_json, primary_column_ai_slug, primary_column_manual,
            topic_selection_manual, final_html, html_web, html_wechat, editor_document_json, editor_source,
            editor_updated_at, render_metadata_json, publish_validation_json, status, draft_box_state,
            workflow_status, created_at, updated_at
        )
        VALUES (?, ?, 'Round99 Editorial Topic Draft', '', 'Editorial Desk', 'Fudan Business Knowledge', ?, '', '',
                'insights', 'insight', 'Topic Governance', 'public', 'source paragraph', 'auto', '',
                'source paragraph', 'First body paragraph. Second body paragraph.', 'Round99 topic draft excerpt',
                '[]', '[{"name":"Round99 Quick Tag","slug":"round99-quick-tag","category":"topic","confidence":0.9}]', '[]',
                'insights', 1, 1, ?, ?, ?, ?, 'manual_edited', ?, '{}', '[]', 'draft', 'active', 'draft', ?, ?)
        """,
        (
            editorial_id,
            f"round99-editorial-{editorial_id}",
            today.isoformat(),
            final_html,
            final_html,
            final_html,
            json.dumps({"schema": "editable-html-v1", "html": final_html}, ensure_ascii=False),
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    connection.execute(
        "INSERT INTO editorial_article_topics (editorial_id, topic_id, sort_order, created_at) VALUES (?, ?, 0, ?)",
        (editorial_id, topic_id, timestamp),
    )
    connection.execute(
        "INSERT INTO editorial_article_topics (editorial_id, topic_id, sort_order, created_at) VALUES (?, ?, 1, ?)",
        (editorial_id, second_topic_id, timestamp),
    )
    connection.commit()

print(json.dumps({"editorial_id": editorial_id}, ensure_ascii=False))
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

async function setAdminDebugAuth(page) {
  await page.addInitScript(() => {
    window.localStorage.setItem('fdsm-language', 'zh')
    window.localStorage.setItem(
      'fdsm-debug-auth',
      JSON.stringify({
        user_id: 'acceptance-admin',
        email: 'admin@example.com',
        display_name: 'Acceptance Admin',
        tier: 'admin',
      }),
    )
  })
}

async function openRoute(page, targetPath) {
  const targetUrl = targetPath === '/' ? FRONTEND_URL : `${FRONTEND_URL}${targetPath}`
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
  try {
    await page.waitForLoadState('networkidle', { timeout: 12000 })
  } catch {}
  await page.waitForTimeout(600)
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true })
  await fs.copyFile(SOURCE_DB_PATH, path.join(TEMP_DATA_DIR, 'fudan_knowledge_base.db'))
  const seed = await seedAcceptanceData()

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

    const browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ viewport: { width: 1440, height: 1400 } })
    const page = await context.newPage()
    await setAdminDebugAuth(page)

    await openRoute(page, '/admin/content-ops')
    await page.getByText('内容运营后台').first().waitFor({ timeout: 30000 })
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'round99-admin-content-ops.png'), fullPage: true })

    await openRoute(page, `/editorial?editorial_id=${seed.editorial_id}`)
    await page.getByText('专题选择').first().waitFor({ timeout: 30000 })
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'round99-editorial-topic-selection.png'), fullPage: true })

    await openRoute(page, '/')
    await page.getByText('Round99 Hero Article').first().waitFor({ timeout: 30000 })
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'round99-home-week.png'), fullPage: true })

    await page.getByRole('button', { name: 'month' }).click()
    await page.waitForTimeout(1200)
    await page.screenshot({ path: path.join(OUTPUT_DIR, 'round99-home-month.png'), fullPage: true })

    await browser.close()
  } finally {
    await terminateProcess(previewProcess)
    await terminateProcess(backendProcess)
  }
}

await main()
