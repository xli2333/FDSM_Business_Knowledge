import fs from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import { spawn } from 'node:child_process'
import { chromium } from 'playwright'

const FRONTEND_DIR = process.cwd()
const PROJECT_ROOT = path.resolve(FRONTEND_DIR, '..')
const OUTPUT_DIR = path.join(PROJECT_ROOT, 'qa', 'screenshots', 'round176_async_editorial')
const FRONTEND_PORT = 4196
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`
const MOCK_API_BASE_URL = 'http://127.0.0.1:65535/api'

const now = () => new Date().toISOString()

let article = {
  id: 176001,
  article_id: null,
  title: 'round176 异步编辑台 QA 草稿',
  subtitle: '',
  author: 'FDSM QA',
  organization: 'Fudan Business Knowledge',
  publish_date: '2026-04-21',
  source_url: '',
  cover_image_url: '',
  primary_column_slug: 'insights',
  primary_column_ai_slug: 'insights',
  primary_column_manual: false,
  access_level: 'public',
  layout_mode: 'auto',
  formatting_notes: '',
  source_markdown: '# round176 异步编辑台 QA\n\n这篇草稿用于验证前端点击自动摘要后进入异步任务轮询，而不是等待同步 AI 请求。',
  content_markdown: '# round176 异步编辑台 QA\n\n这篇草稿用于验证前端点击自动摘要后进入异步任务轮询，而不是等待同步 AI 请求。',
  excerpt: '',
  final_html: '',
  summary_html: '',
  summary_markdown: '',
  summary_model: null,
  status: 'draft',
  workflow_status: 'draft',
  workflow_label: '草稿',
  draft_box_state: 'active',
  tags: [],
  selected_topics: [],
  topic_candidates: [],
  translation_ready: false,
  translation_status: 'pending',
  rag_status: {
    article_id: null,
    version_exists: false,
    in_knowledge_base: false,
    current_version_status: null,
    current_version: null,
    chunk_count: 0,
    embedding_count: 0,
    has_embeddings: false,
    embedding_dimensions: 0,
    embedding_provider: null,
    latest_job: null,
    last_error_message: null,
  },
  created_at: now(),
  updated_at: now(),
}

function startFrontend() {
  return spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(FRONTEND_PORT), '--strictPort'], {
    cwd: FRONTEND_DIR,
    env: {
      ...process.env,
      VITE_API_BASE_URL: MOCK_API_BASE_URL,
      VITE_ENABLE_DEBUG_AUTH: '1',
    },
    shell: process.platform === 'win32',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
}

function terminateProcess(child) {
  return new Promise((resolve) => {
    if (!child?.pid) return resolve()
    if (process.platform !== 'win32') {
      child.kill()
      resolve()
      return
    }
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
      stdio: 'ignore',
      shell: true,
    })
    killer.on('exit', () => resolve())
    killer.on('error', () => resolve())
  })
}

async function waitForServer(url, timeoutMs = 30000) {
  const startedAt = Date.now()
  let lastError = null
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
  throw new Error(`Frontend server did not start: ${lastError?.message || url}`)
}

function adminStatusPayload() {
  return {
    enabled: true,
    auth_mode: 'password',
    role_home_path: '/admin',
    membership: {
      tier: 'admin',
      tier_label: '管理员',
      status: 'active',
      status_label: '有效',
      is_authenticated: true,
      is_admin: true,
      can_access_member: true,
      can_access_paid: true,
      user_id: 'round176-admin',
      email: 'round176-admin@example.com',
      benefits: [],
    },
    business_profile: {
      user_id: 'round176-admin',
      email: 'round176-admin@example.com',
      display_name: 'round176 QA Admin',
      title: 'QA',
      organization: 'FDSM',
      bio: null,
      tier: 'admin',
      tier_label: '管理员',
      status: 'active',
      status_label: '有效',
      role_home_path: '/admin',
      auth_source: 'debug',
      locale: 'zh-CN',
      is_seed: true,
      is_authenticated: true,
      is_admin: true,
    },
  }
}

function dashboardPayload() {
  return {
    draft_count: 1,
    published_count: 0,
    recent_articles: [article],
  }
}

async function fulfillJson(route, payload, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json; charset=utf-8',
    body: JSON.stringify(payload),
  })
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true })
  const server = startFrontend()
  let browser = null
  const calls = []
  let taskPollCount = 0

  try {
    await waitForServer(FRONTEND_URL)
    browser = await chromium.launch()
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })

    await page.addInitScript(() => {
      window.localStorage.setItem(
        'fdsm-debug-auth',
        JSON.stringify({
          user_id: 'round176-admin',
          email: 'round176-admin@example.com',
          display_name: 'round176 QA Admin',
          tier: 'admin',
        }),
      )
    })

    await page.route(`${MOCK_API_BASE_URL}/**`, async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const apiPath = url.pathname.replace(/^\/api/, '') || '/'
      calls.push(`${request.method()} ${apiPath}`)

      if (apiPath === '/auth/status') {
        return fulfillJson(route, adminStatusPayload())
      }

      if (apiPath === '/columns') {
        return fulfillJson(route, [{ slug: 'insights', name: '深度洞察' }])
      }

      if (apiPath === '/editorial/articles' && request.method() === 'GET') {
        return fulfillJson(route, [article])
      }

      if (apiPath === '/editorial/dashboard') {
        return fulfillJson(route, dashboardPayload())
      }

      if (apiPath === `/editorial/articles/${article.id}` && request.method() === 'GET') {
        return fulfillJson(route, article)
      }

      if (apiPath === `/editorial/articles/${article.id}` && request.method() === 'PUT') {
        const payload = JSON.parse(request.postData() || '{}')
        article = { ...article, ...payload, updated_at: now() }
        return fulfillJson(route, article)
      }

      if (apiPath === `/editorial/articles/${article.id}/tasks/auto-summary` && request.method() === 'POST') {
        return fulfillJson(route, {
          id: 'round176-summary-task',
          task_type: 'editorial.auto_summary',
          status: 'queued',
          progress: 0,
          result: {},
        })
      }

      if (apiPath === '/editorial/tasks/round176-summary-task') {
        taskPollCount += 1
        if (taskPollCount < 2) {
          return fulfillJson(route, {
            id: 'round176-summary-task',
            task_type: 'editorial.auto_summary',
            status: 'running',
            progress: 35,
            result: {},
          })
        }
        article = {
          ...article,
          summary_html: '<section><h2>异步摘要已生成</h2><p>Worker 完成后前端刷新草稿详情。</p></section>',
          summary_markdown: '异步摘要已生成',
          summary_model: 'round176-mock-worker',
          updated_at: now(),
        }
        return fulfillJson(route, {
          id: 'round176-summary-task',
          task_type: 'editorial.auto_summary',
          status: 'completed',
          progress: 100,
          result: { editorial_id: article.id },
        })
      }

      return fulfillJson(route, { detail: `Unexpected mock route: ${request.method()} ${apiPath}` }, 500)
    })

    await page.goto(`${FRONTEND_URL}/editorial`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { name: /上方最终成品/ }).waitFor({ timeout: 15000 })
    await page.getByRole('button', { name: /自动生成摘要/ }).click()
    await page.getByText(/自动摘要已进入队列/).waitFor({ timeout: 5000 })
    await page.getByText('AI 摘要已生成。').waitFor({ timeout: 15000 })

    if (!calls.includes(`PUT /editorial/articles/${article.id}`)) {
      throw new Error('Expected draft persistence before creating the async task.')
    }
    if (!calls.includes(`POST /editorial/articles/${article.id}/tasks/auto-summary`)) {
      throw new Error('Expected async summary task endpoint to be called.')
    }
    if (taskPollCount < 2) {
      throw new Error(`Expected task polling to continue until completion, got ${taskPollCount}.`)
    }

    await page.screenshot({ path: path.join(OUTPUT_DIR, 'editorial_async_summary.png'), fullPage: true })
    console.log(
      JSON.stringify(
        {
          ok: true,
          taskPollCount,
          screenshot: path.relative(PROJECT_ROOT, path.join(OUTPUT_DIR, 'editorial_async_summary.png')),
        },
        null,
        2,
      ),
    )
  } catch (error) {
    if (browser) {
      try {
        const pages = browser.contexts().flatMap((context) => context.pages())
        const page = pages[0]
        if (page) {
          await page.screenshot({ path: path.join(OUTPUT_DIR, 'editorial_async_failure.png'), fullPage: true })
          console.error(
            JSON.stringify(
              {
                currentUrl: page.url(),
                bodyText: (await page.locator('body').innerText().catch(() => '')).slice(0, 1200),
                calls,
                screenshot: path.relative(PROJECT_ROOT, path.join(OUTPUT_DIR, 'editorial_async_failure.png')),
              },
              null,
              2,
            ),
          )
        }
      } catch {}
    }
    throw error
  } finally {
    if (browser) await browser.close()
    await terminateProcess(server)
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
