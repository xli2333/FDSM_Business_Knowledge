# round176 高并发 AI 异步任务与 Worker 改造

## 本轮目标

在 round175 Docker 生产闭环已经跑通的基础上，把长耗时 AI 操作从 Web 请求线程中拆出去，避免并发访问时 Gunicorn worker 被 Gemini、RAG、排版、摘要、翻译等任务长时间占满。

本轮只做 AI 异步任务和 worker 闭环，不做 CAS，不做数据库迁移到 PostgreSQL，不做全站重构。

## 原子 Todo

- [x] 1. 扫描现有 AI 调用入口，区分必须同步返回的聊天请求和可以异步化的编辑/排版/摘要/翻译任务。
- [x] 2. 确定第一批异步化范围：优先处理编辑台长任务，保留公开浏览和普通查询同步路径。
- [x] 3. 补齐 Redis Python 依赖和运行配置。
- [x] 4. 新增异步任务数据表，记录任务类型、状态、进度、输入、输出、错误和时间戳。
- [x] 5. 新增任务队列服务，支持创建任务、入队、抢占、完成、失败、查询。
- [x] 6. 新增 Worker 循环入口，独立消费 Redis 队列并执行任务。
- [x] 7. 将编辑台 AI 自动排版改为异步任务入口。
- [x] 8. 将编辑台 AI 自动摘要改为异步任务入口。
- [x] 9. 将编辑台 AI 自动翻译改为异步任务入口。
- [x] 10. 新增任务查询 API，前端可以按 task_id 轮询。
- [x] 11. 前端 API 层新增异步任务查询方法。
- [x] 12. 前端编辑台接入任务轮询，提交后显示处理中，完成后回填结果。
- [x] 13. Docker Compose 新增 `backend-worker` 服务，与 `backend-web` 共用镜像和 `/data`。
- [x] 14. 后端 Dockerfile/compose 环境变量区分 web 与 worker。
- [x] 15. 本地 Python 编译和前端构建通过。
- [x] 16. Docker 重新构建并启动 web、worker、frontend、redis、backup。
- [x] 17. 执行队列级 QA：创建任务、worker 消费、状态完成、失败可记录。
- [x] 18. 执行前端级 QA：编辑台长任务提交后不会阻塞页面，并能轮询完成。
- [x] 19. 压测基础接口，确认健康检查和公开 feed 在任务运行时仍可响应。
- [x] 20. 回写本轮 Todo 勾选状态、QA 结果和下一轮 SQLite 写入缓冲 Todo。

## 验收标准

- Web 容器不直接执行第一批编辑台 AI 长任务。
- Worker 容器可以独立消费 Redis 队列。
- 任务状态在 SQLite 中可追踪，容器重启后不会丢失已创建任务记录。
- Redis 故障时 API 返回明确错误，不静默假成功。
- 前端不会因为 AI 长任务阻塞或超时白屏。

## QA 结果

- `python -m compileall backend` 通过。
- `npm run build` 通过，`EditorialWorkbenchPage` 无 JSX 构建错误。
- `docker compose --env-file .env.docker build backend-web backend-worker frontend` 通过。
- `docker compose --env-file .env.docker up -d --force-recreate` 后 web、worker、frontend、redis、backup 均启动；worker 空闲 25 秒后仍 healthy，重启次数为 0。
- 队列级真实 QA：创建文章 `228`，异步摘要任务 `4308ca98ee1b41fe8a5571dbcfdc4d07` 完成，异步翻译任务 `81925a5a94264f80a806ef809e635663` 在 Gemini Flash 未配置时进入 `failed` 并记录错误。
- 并发基础接口 QA：任务执行期间对 `/api/health` 和 `/api/home/feed?language=zh` 发起 30 个并发请求，全部返回 200。
- 前端级 QA：`npm run editorial:async:acceptance:round176` 通过，确认编辑台自动摘要按钮会保存草稿、创建异步任务、轮询 task_id 到完成，并生成截图 `qa/screenshots/round176_async_editorial/editorial_async_summary.png`。

## 下一轮

已进入 `round177_SQLite并发写入治理与云端数据库切换准备.md`，处理 SQLite 写入争用、运行期写操作观测、云端 PostgreSQL 切换前置抽象。
