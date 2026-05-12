# round175 Docker 上云第一轮生产闭环改造

## 本轮目标

在不一次性引入 AI 异步任务、Redis 写缓冲、CAS 实装的前提下，先完成可验收的 Docker 上云最小生产闭环：

- 本地可以用 Docker Compose 启动前端、后端、Redis、备份服务。
- 后端具备生产健康检查、SQLite WAL、数据目录外置、debug auth 生产硬封。
- 前端生产构建默认走同源 `/api`，避免云端仍请求 `127.0.0.1:8000`。
- Nginx 可以服务前端静态资产并反代 API，静态上传资源路径清晰。
- 形成后续第二轮高并发改造 Todo。

## 原子 Todo

- [x] 1. 扫描现有后端入口、数据库配置、前端 API、部署文档与工作区脏改，确认第一轮只做生产闭环边界。
- [x] 2. 固化本轮执行策略：先 Docker 最小闭环，再高并发，再 CAS，不把三类改造混在一个不可回滚大改里。
- [x] 3. 后端配置增加明确的 `APP_ENV` / `IS_PRODUCTION`，生产环境禁止自动启用预览鉴权。
- [x] 4. 后端 SQLite 连接增加 WAL、busy timeout、synchronous NORMAL、foreign keys，不改变事务语义。
- [x] 5. 后端启动逻辑迁移到 FastAPI lifespan，避免模块导入时直接做运行时初始化。
- [x] 6. 后端新增 `/api/health`，用于 Docker 与云端健康检查。
- [x] 7. 后端生产环境硬拒绝 `X-Debug-User-Id` / `X-Debug-User-Email` 调试鉴权头。
- [x] 8. 后端静态资源目录统一从 `FDSM_DATA_DIR` 派生，保留本地默认兼容。
- [x] 9. 前端 API 默认值改为开发走本机、生产走同源 `/api`。
- [x] 10. 前端生产构建禁用 debug auth header，避免上线后浏览器继续带调试用户。
- [x] 11. 补齐后端生产运行依赖 `gunicorn`。
- [x] 12. 新增 `.dockerignore`，排除数据库、FAISS、上传、音频、node_modules、缓存和历史归档。
- [x] 13. 新增后端 Dockerfile，使用 Python 3.12 与 Node 20，构建失败必须中断。
- [x] 14. 新增前端 Dockerfile，使用 Node 构建与 Nginx 运行。
- [x] 15. 新增 Nginx 配置，包含 SPA fallback、API 反代、上传体积、静态资源 alias 与基础缓存策略。
- [x] 16. 新增 Docker Compose，定义 backend-web、frontend、redis、backup 四个第一轮服务。
- [x] 17. 新增 `.env.docker.example`，明确云端和本地 Docker 必填变量。
- [x] 18. 新增 SQLite 备份脚本，使用只读连接与 SQLite backup API。
- [x] 19. 新增 Docker 数据准备说明，禁止直接移动原始数据，先 copy 后验收。
- [x] 20. 执行后端语法检查。
- [x] 21. 执行前端生产构建检查。
- [x] 22. 如本机 Docker 可用，执行 Docker 构建检查；不可用则记录阻塞。
- [x] 23. 回写本轮 Todo 勾选状态、验收结果和下一轮提升 Todo。

## 下一轮预置方向

- 第二轮：Redis 队列 + AI 异步任务 + Worker 容器。
- 第三轮：SQLite 写信号量 + 浏览量缓冲落库。
- 第四轮：CAS dual mode 接入与 Supabase 迁移预案。
- 第五轮：云服务器真实部署、域名、HTTPS、备份恢复演练。

## 本轮 QA 记录

- [x] `python -m compileall backend deploy` 通过。
- [x] `npm run build` 通过，未出现 JSX 构建错误。
- [x] `docker compose --env-file .env.docker.example config` 通过。
- [x] `docker compose --env-file .env.docker build backend-web frontend` 通过。
- [x] Docker Desktop 未启动时已自动启动并复验 Docker daemon。
- [x] `data/` 已按复制不移动原则准备，原始数据库与素材未被移动。
- [x] `docker compose --env-file .env.docker up -d --force-recreate` 已启动。
- [x] `backend-web`、`frontend`、`redis` 均为 healthy。
- [x] 本机 `8080` 被其他容器占用，`.env.docker` 本地验收端口已切到 `18080`。
- [x] `http://127.0.0.1:18080/healthz` 返回 `ok`。
- [x] `http://127.0.0.1:18080/api/health` 返回 `database_ready: true`。
- [x] 生产模式请求携带 `X-Debug-User-Id` 被拒绝，返回 400。
- [x] `http://127.0.0.1:18080/api/home/feed?language=zh` 返回 200。
- [x] `/audio-files/` 真实音频资源返回 200，且不再出现重复 `Cache-Control`。
- [x] SQLite 备份脚本已改为临时文件成功后 rename，手动备份通过 `PRAGMA quick_check`。
- [x] `npm audit --omit=dev` 返回 0 个生产依赖漏洞。
- [x] 容器内 `pip check` 返回无破损依赖。
- [x] 容器内 `rank_bm25`、`PIL`、`faiss` 关键运行依赖导入通过。

## 本轮修复过的 QA 问题

- [x] Docker compose 首次 config 因 `.env.docker` 不存在失败，已改为 `env_file.required=false`。
- [x] 后端容器缺少 `rank_bm25` 与 `pillow`，已补入 `requirements.txt`。
- [x] 备份容器只读挂载在 WAL 场景下无法完成 backup，已改为挂载读写、脚本只读连接。
- [x] 备份脚本中断会留下半成品 `.db`，已改为临时文件原子 rename 并清理半成品。
- [x] Gunicorn 多 worker 会重复执行运行时初始化，已加容器内启动锁和 sentinel。
