# Round 174 Docker 容器化上云路线与原子任务

> 日期：2026-04-21  
> 目标：先把当前项目以低风险 Docker 生产形态跑到云端，再按可验证步骤演进到高并发架构。  
> 核心判断：第一阶段不做完整高并发重构，不做多后端副本，不把 SQLite 强行一次性迁移到 Postgres。先上线、可备份、可回滚、可观测，再拆数据库、对象存储、缓存、任务队列和向量检索。

---

## 1. 当前项目画像

### 1.1 技术栈

- 后端：FastAPI + Uvicorn，当前入口为 `backend.main:app`。
- 前端：Vite + React，生产构建产物由静态服务器托管。
- AI：Gemini API，多 Key 配置入口为 `GOOGLE_API_KEY` / `GEMINI_API_KEYS`。
- RAG：SQLite 结构化数据 + FAISS 本地向量索引 + 本地 BM25/词法检索。
- 认证：Supabase Auth，开发态支持 `DEV_AUTH_ENABLED`。
- 编辑排版：Python 后端通过 subprocess 调用 Node 20 的 `backend/scripts/wechat_fudan_bridge.mjs`。
- 文件服务：FastAPI 挂载 `/audio-files`、`/editorial-uploads`、`/media-uploads`。

### 1.2 当前本地状态资产

- SQLite 主库：`fudan_knowledge_base.db`，约 737 MB。
- FAISS 索引：`faiss_index_business/`，约 163 MB。
- 上传目录：`uploads/`，约 251 MB。
- 音频目录：`audio/`，约 30 MB。
- 原始知识库语料：`Fudan_Business_Knowledge_Data/`，约 4 GB。

### 1.3 主要风险

- SQLite 适合单实例读多写少，不适合多个后端容器同时写。
- uploads/audio/FAISS 都是本地文件，容器重启或重新部署时如果没有持久盘会丢。
- Node 公众号排版运行时是后端业务路径的一部分，后端镜像必须具备 Node 20+。
- AI 生成、排版、翻译、RAG 回填属于长耗时任务，不应长期占用 HTTP 请求线程。
- 如果直接做 Postgres + Redis + 对象存储 + 队列 + 多副本，会一次性扩大故障面。

---

## 2. 总体路线

### 2.1 路线原则

- 代码进镜像，数据出镜像。
- 第一阶段只跑一个后端实例，避免 SQLite 多写冲突。
- `/data` 作为唯一持久化根目录，云厂商迁移时复制 `/data` 即可恢复核心状态。
- 先用 Docker Compose 单机上云，跑通域名、HTTPS、备份、监控、日志。
- 高并发能力通过独立阶段逐步引入，每一阶段都有验收标准。
- 云厂商相关能力只放在配置层，避免代码写死阿里云。

### 2.2 阶段划分

| 阶段 | 目标 | 结果 |
|---|---|---|
| Phase A | 单机 Docker 生产化 | 阿里云 ECS 可稳定访问 |
| Phase B | 观测与备份 | 有日志、健康检查、备份、回滚 |
| Phase C | 文件对象存储化 | uploads/audio 迁 OSS/S3/COS |
| Phase D | 运行时数据迁 Postgres | 用户、会员、互动、聊天、编辑台写入脱离 SQLite |
| Phase E | Redis 与后台任务 | 缓存热点接口，AI/排版/回填异步化 |
| Phase F | 后端横向扩容 | 多后端实例 + 负载均衡 |
| Phase G | 检索与向量库升级 | pgvector / Elasticsearch / OpenSearch |

---

## 3. 首发云服务器建议

### 3.1 首发推荐

- 云厂商：阿里云优先，后续可迁移到 AWS、腾讯云、华为云等。
- 实例：通用型 x86_64。
- 推荐规格：8 vCPU / 32 GB RAM。
- 系统盘：80 GB。
- 数据盘：200-300 GB SSD/NVMe，挂载到 `/srv/fdsmarticles/data` 或 `/data`。
- 操作系统：Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS。
- 网络：公网 IP + 安全组只开放 80/443/22。
- 域名：主站域名指向服务器，HTTPS 由 Nginx/Certbot 或云负载均衡证书托管。

### 3.2 为什么首发不选太小

- Python worker、FAISS、BM25 缓存、SQLite、Node 排版、前端 Nginx 会同时存在。
- `Fudan_Business_Knowledge_Data/` 约 4 GB，虽然不一定全量在线读，但备份和迁移需要空间。
- AI/排版任务峰值会带来额外 CPU 和内存压力。
- 4C16G 可以跑，但 8C32G 更适合首发验收和问题排查。

### 3.3 架构约束

- 第一阶段不启用多个后端副本。
- 第一阶段不把 SQLite 放进镜像。
- 第一阶段不把上传文件放在容器层。
- 第一阶段不在启动时自动重建主库。
- 第一阶段优先 x86_64，避免 FAISS 跨架构索引兼容问题。

---

## 4. 首发 Docker 生产架构

### 4.1 服务拓扑

```text
用户浏览器
  |
  v
域名 / HTTPS
  |
  v
Nginx frontend 容器
  |-- 静态文件：frontend/dist
  |-- /api/*              -> backend:8000
  |-- /audio-files/*      -> backend:8000
  |-- /editorial-uploads/*-> backend:8000
  |-- /media-uploads/*    -> backend:8000
  |
  v
FastAPI backend 容器
  |-- Python FastAPI
  |-- Gunicorn + UvicornWorker
  |-- Node 20 公众号排版运行时
  |
  v
/data 持久卷
  |-- fudan_knowledge_base.db
  |-- faiss_index_business/
  |-- uploads/
  |-- audio/
```

### 4.2 宿主机目录规划

```text
/srv/fdsmarticles/
  app/                  # git clone 或发布包
  data/                 # 持久化数据根目录
    fudan_knowledge_base.db
    faiss_index_business/
    uploads/
    audio/
  backups/              # 本机备份暂存
  logs/                 # 可选，宿主机日志落盘
  env/
    backend.env         # 后端环境变量，不入库
```

容器内统一挂载：

```text
/data -> /srv/fdsmarticles/data
```

后端环境变量：

```env
FDSM_DATA_DIR=/data
```

### 4.3 后端镜像要求

- 基础镜像包含 Python 3.11+。
- 安装 `requirements.txt`。
- 安装 Node 20+，用于 `backend/scripts/wechat_fudan_bridge.mjs`。
- 安装 `backend/wechat_runtime/package-lock.json` 对应依赖。
- 暴露 8000。
- 不复制 `.env`。
- 不复制 `.db`、`uploads/`、`audio/`、`faiss_index_business/` 到镜像。

生产启动命令建议：

```bash
gunicorn backend.main:app \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers 4 \
  --timeout 180 \
  --graceful-timeout 30 \
  --keep-alive 5
```

### 4.4 前端镜像要求

- Node 构建阶段执行 `npm ci` 和 `npm run build`。
- Nginx 运行阶段只保留 `dist/`。
- `VITE_API_BASE_URL` 在构建阶段注入。
- Nginx 支持 SPA fallback。
- Nginx 反代 `/api` 到 backend。
- Nginx 设置上传体积限制，避免媒体上传被默认 1MB 限制截断。

### 4.5 Docker Compose 服务

首发服务建议：

```text
services:
  backend
  frontend
volumes:
  /srv/fdsmarticles/data:/data
```

第一阶段不加入：

- Postgres
- Redis
- Celery/RQ worker
- 多 backend 副本
- Elasticsearch/OpenSearch

这些在后续阶段单独引入。

---

## 5. 环境变量清单

### 5.1 后端必配

```env
FDSM_DATA_DIR=/data
ALLOWED_ORIGINS=https://你的域名
SITE_BASE_URL=https://你的域名
SUPABASE_URL=https://你的项目.supabase.co
SUPABASE_ANON_KEY=你的 Supabase anon key
ADMIN_EMAILS=admin@example.com
DEV_AUTH_ENABLED=0
PAYMENTS_ENABLED=0
PAYMENT_PROVIDER=mock
GOOGLE_API_KEY=你的主 Gemini Key
GEMINI_API_KEYS=key1,key2,key3
GEMINI_CHAT_MODEL=gemini-3.0-flash
GEMINI_FLASH_MODEL=gemini-3.0-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
```

### 5.2 前端构建必配

```env
VITE_API_BASE_URL=https://你的域名/api
VITE_SUPABASE_URL=https://你的项目.supabase.co
VITE_SUPABASE_ANON_KEY=你的 Supabase anon key
```

### 5.3 上线禁止项

- 禁止 `DEV_AUTH_ENABLED=1` 用于正式公网。
- 禁止 `ALLOWED_ORIGINS=*` 用于正式公网。
- 禁止把 `.env` 提交到 Git。
- 禁止把 Google/Gemini/Supabase 密钥写进前端非 `VITE_` 以外的位置。
- 禁止把 service role key 放进前端。

---

## 6. 数据与备份策略

### 6.1 第一阶段备份对象

必须备份：

- `/data/fudan_knowledge_base.db`
- `/data/fudan_knowledge_base.db-wal`
- `/data/fudan_knowledge_base.db-shm`
- `/data/faiss_index_business/`
- `/data/uploads/`
- `/data/audio/`
- `/srv/fdsmarticles/env/backend.env`

可选备份：

- 原始语料 `Fudan_Business_Knowledge_Data/`
- 部署版本号、镜像 tag、Git commit hash

### 6.2 SQLite 备份原则

- 不直接在高写入时复制 `.db` 文件作为唯一备份。
- 优先使用 SQLite 在线备份命令或短暂停写窗口。
- 每次上线前做一次手动快照。
- 每日自动备份一次，至少保留 7 天。
- 每周做一次异地备份，至少保留 4 周。

### 6.3 回滚策略

每次部署必须记录：

```text
git commit:
backend image:
frontend image:
env version:
data snapshot:
deploy time:
operator:
```

回滚步骤：

1. 停止当前 compose。
2. 切回上一版镜像 tag。
3. 如涉及数据库结构变更，恢复对应数据快照。
4. 启动服务。
5. 验证首页、文章详情、登录、上传、编辑台、AI 对话。

---

## 7. 高并发演进设计

### 7.1 不能直接横向扩容的原因

当前 SQLite 是单文件数据库。多个 backend 容器同时写入会放大以下问题：

- 写锁等待变长。
- 收藏、点赞、浏览事件、聊天记录可能出现 `database is locked`。
- 多副本本地 uploads 不一致。
- 多副本本地 FAISS 索引更新不一致。
- 容器重建后本地文件丢失风险变高。

因此，第一阶段只允许一个 backend 容器。

### 7.2 Phase C：对象存储化

目标：把上传文件从本地 `/data/uploads` 迁到 OSS/S3/COS。

拆分顺序：

1. 新增统一文件存储接口。
2. 本地存储作为默认实现。
3. 新增 OSS/S3 兼容实现。
4. 上传接口写对象存储。
5. 返回 CDN URL 或签名 URL。
6. 旧 uploads 做迁移脚本。
7. FastAPI 静态挂载保留兼容期。

验收：

- 上传图片、音频、视频后，文件进入对象存储。
- 前端能访问资源。
- 旧资源 URL 不断。
- 删除草稿或媒体时资源处理策略明确。

### 7.3 Phase D：运行时表迁 Postgres

优先迁移高写入、用户态、运营态数据：

- `visitor_profiles`
- `article_view_events`
- `article_reactions`
- `user_saved_articles`
- `chat_sessions`
- `chat_messages`
- `user_memberships`
- `business_users`
- `billing_*`
- `editorial_articles`
- `media_items`
- `media_drafts`
- `home_content_slots`
- `retrieval_events`
- `answer_events`

暂时可保留在 SQLite 的只读或低频数据：

- `articles`
- `tags`
- `article_tags`
- `columns`
- `topics`
- `topic_articles`
- `article_ai_outputs`
- `article_translations`

验收：

- 用户登录后会员信息来自 Postgres。
- 文章浏览、收藏、点赞写入 Postgres。
- 聊天会话写入 Postgres。
- 编辑台草稿和媒体草稿写入 Postgres。
- SQLite 主要承担内容只读查询。

### 7.4 Phase E：Redis 与后台任务

Redis 用途：

- 首页 feed 缓存。
- 栏目页列表缓存。
- 文章详情轻缓存。
- 搜索建议缓存。
- Supabase 用户信息短缓存。
- 限流计数。
- 任务状态缓存。

后台任务用途：

- AI 摘要。
- AI 翻译。
- 公众号排版。
- RAG 入库。
- FAISS/向量索引更新。
- 媒体章节重写。

推荐任务队列：

- 简单阶段：RQ + Redis。
- 更完整阶段：Celery + Redis/RabbitMQ。
- 云原生阶段：阿里云 MNS / AWS SQS。

验收：

- HTTP 请求不再等待长 AI 任务完成。
- 前端能轮询任务状态。
- 任务失败可重试。
- 任务日志可追踪到文章或媒体 ID。

### 7.5 Phase F：多后端副本

多副本前置条件：

- 写入型运行时数据已迁 Postgres。
- uploads/audio 已迁对象存储。
- 缓存使用 Redis。
- 长任务使用队列。
- 后端不依赖容器本地写入状态。
- 健康检查可用。

目标拓扑：

```text
CDN / WAF
  |
负载均衡
  |
backend x N
  |
Postgres + Redis + Object Storage + Queue
```

验收：

- backend 可从 1 扩到 2，再扩到 4。
- 任意一个 backend 重启不影响登录和上传。
- 任务 worker 可独立扩容。
- 压测中错误率、P95、P99 可观测。

### 7.6 Phase G：检索和向量库升级

选择一：Postgres + pgvector

- 优点：数据和向量同库，运维简单。
- 适合：中等规模 RAG、文章级/块级检索。
- 风险：超大规模或复杂全文检索时需要优化。

选择二：Elasticsearch/OpenSearch

- 优点：全文检索、过滤、聚合、向量检索能力更强。
- 适合：高并发搜索、复杂查询、运营筛选。
- 风险：运维成本高。

选择三：继续 FAISS

- 优点：当前代码成本低，单机快。
- 适合：第一阶段和低更新频率场景。
- 风险：多副本索引同步麻烦。

---

## 8. 上线验收清单

### 8.1 基础可用性

- 首页加载成功。
- 最新文章列表加载成功。
- 栏目页加载成功。
- 文章详情页加载成功。
- 文章封面加载成功。
- 中英文切换可用。
- 搜索建议可用。
- exact 搜索可用。
- smart 搜索对付费用户可用。

### 8.2 认证与会员

- Supabase 登录可用。
- 未登录用户权限正确。
- 免费会员权限正确。
- 付费会员权限正确。
- 管理员权限正确。
- `DEV_AUTH_ENABLED=0` 时预览账号不可用。
- `ADMIN_EMAILS` 自动提升管理员逻辑可用。

### 8.3 编辑台与媒体

- 编辑台列表加载成功。
- 创建草稿成功。
- 上传图片成功。
- 自动摘要成功或明确失败。
- 自动翻译成功或明确失败。
- 公众号排版 Node 运行时可用。
- 发布文章成功。
- 删除正式文章退回草稿箱可用。
- 媒体上传成功。
- 媒体发布成功。

### 8.4 静态与文件

- `/audio-files/*` 可访问。
- `/editorial-uploads/*` 可访问。
- `/media-uploads/*` 可访问。
- 大文件上传不被 Nginx 截断。
- 容器重启后上传文件仍存在。

### 8.5 数据安全

- 数据盘挂载正确。
- SQLite 文件存在且可读写。
- FAISS 索引存在。
- 每日备份任务可执行。
- 手动恢复演练完成。
- `.env` 不在 Git。
- 密钥不出现在前端构建产物中。

### 8.6 性能与稳定性

- 首页 P95 小于 800ms，首发目标。
- 文章详情 P95 小于 1000ms，首发目标。
- 非 AI 搜索 P95 小于 1500ms，首发目标。
- AI 请求允许更长耗时，但必须有清晰错误提示。
- 连续重启后服务可恢复。
- 日志能定位 500 错误。

---

## 9. 原子级 TODO

### 9.1 Phase A：Docker 单机生产化

- [ ] P0 | 审计 | 确认 `.gitignore` 排除 `.env`、`*.db`、`uploads/`、`audio/`、`faiss_index_business/`。
- [ ] P0 | 审计 | 确认后端所有持久化路径都能通过 `FDSM_DATA_DIR=/data` 定位。
- [ ] P0 | 审计 | 确认 `backend/main.py` 启动时不会在生产缺库时误触发长时间全量重建。
- [ ] P0 | 后端镜像 | 新增 `Dockerfile.backend`。
- [ ] P0 | 后端镜像 | 在后端镜像中安装 Python 依赖。
- [ ] P0 | 后端镜像 | 在后端镜像中安装 Node 20+。
- [ ] P0 | 后端镜像 | 在后端镜像中安装 `backend/wechat_runtime` 的 npm 依赖。
- [ ] P0 | 后端镜像 | 增加 `gunicorn` 到生产依赖或镜像安装步骤。
- [ ] P0 | 后端镜像 | 设置后端默认启动命令为 Gunicorn + UvicornWorker。
- [ ] P0 | 后端镜像 | 确认镜像不复制 `.env`、`.db`、`uploads/`、`audio/`、`faiss_index_business/`。
- [ ] P0 | 前端镜像 | 新增 `Dockerfile.frontend`。
- [ ] P0 | 前端镜像 | 使用 Node 构建 Vite 前端。
- [ ] P0 | 前端镜像 | 使用 Nginx 托管 `dist/`。
- [ ] P0 | 前端镜像 | 注入 `VITE_API_BASE_URL`。
- [ ] P0 | Nginx | 新增生产 Nginx 配置。
- [ ] P0 | Nginx | 配置 SPA fallback 到 `index.html`。
- [ ] P0 | Nginx | 配置 `/api/` 反代到 backend。
- [ ] P0 | Nginx | 配置上传大小限制。
- [ ] P0 | Nginx | 配置代理超时，覆盖 AI/上传接口的长耗时。
- [ ] P0 | Compose | 新增 `docker-compose.prod.yml`。
- [ ] P0 | Compose | 挂载 `/srv/fdsmarticles/data:/data`。
- [ ] P0 | Compose | 配置 backend healthcheck。
- [ ] P0 | Compose | 配置 frontend healthcheck。
- [ ] P0 | Compose | 配置容器自动重启策略。
- [ ] P0 | 数据 | 在本地模拟 `/data` 目录。
- [ ] P0 | 数据 | 将 `fudan_knowledge_base.db` 复制到 `/data` 模拟目录。
- [ ] P0 | 数据 | 将 `faiss_index_business/` 复制到 `/data` 模拟目录。
- [ ] P0 | 数据 | 将 `uploads/` 复制到 `/data` 模拟目录。
- [ ] P0 | 数据 | 将 `audio/` 复制到 `/data` 模拟目录。
- [ ] P0 | 验证 | 本地执行后端镜像构建。
- [ ] P0 | 验证 | 本地执行前端镜像构建。
- [ ] P0 | 验证 | 本地执行 `docker compose -f docker-compose.prod.yml up`。
- [ ] P0 | 验证 | 验证 `GET /` 返回健康状态。
- [ ] P0 | 验证 | 验证 `GET /api/home/feed` 返回首页数据。
- [ ] P0 | 验证 | 验证文章详情页可打开。
- [ ] P0 | 验证 | 验证媒体上传目录可访问。
- [ ] P0 | 验证 | 验证 Node 公众号排版运行时可调用。

### 9.2 Phase B：阿里云首发部署

- [ ] P0 | 云资源 | 购买阿里云 ECS，首发建议 8C32G x86_64。
- [ ] P0 | 云资源 | 创建并挂载 200-300GB 数据盘。
- [ ] P0 | 云资源 | 将数据盘格式化并挂载到 `/srv/fdsmarticles/data`。
- [ ] P0 | 云资源 | 配置安全组，只开放 22、80、443。
- [ ] P0 | 系统 | 安装 Docker Engine。
- [ ] P0 | 系统 | 安装 Docker Compose plugin。
- [ ] P0 | 系统 | 配置 Docker 开机自启。
- [ ] P0 | 系统 | 创建 `/srv/fdsmarticles/app`。
- [ ] P0 | 系统 | 创建 `/srv/fdsmarticles/backups`。
- [ ] P0 | 系统 | 创建 `/srv/fdsmarticles/env`。
- [ ] P0 | 发布 | 将项目代码同步到 `/srv/fdsmarticles/app`。
- [ ] P0 | 发布 | 将 `/data` 资产上传到 `/srv/fdsmarticles/data`。
- [ ] P0 | 发布 | 创建生产 `backend.env`。
- [ ] P0 | 发布 | 确认 `DEV_AUTH_ENABLED=0`。
- [ ] P0 | 发布 | 确认 `ALLOWED_ORIGINS` 为正式域名。
- [ ] P0 | 发布 | 执行生产 compose 构建。
- [ ] P0 | 发布 | 启动生产 compose。
- [ ] P0 | 域名 | 配置域名 A 记录到 ECS 公网 IP。
- [ ] P0 | HTTPS | 配置 HTTPS 证书。
- [ ] P0 | HTTPS | 验证 HTTP 自动跳转 HTTPS。
- [ ] P0 | 验收 | 按上线验收清单逐项测试。
- [ ] P0 | 回滚 | 记录首次上线镜像 tag 和 Git commit。
- [ ] P0 | 回滚 | 做一次上线后数据快照。

### 9.3 Phase B：日志、监控、备份

- [ ] P0 | 日志 | 确认 backend stdout/stderr 可通过 Docker logs 查看。
- [ ] P0 | 日志 | 确认 frontend Nginx access/error logs 可查看。
- [ ] P0 | 日志 | 增加后端请求错误日志字段。
- [ ] P0 | 监控 | 配置 CPU 使用率告警。
- [ ] P0 | 监控 | 配置内存使用率告警。
- [ ] P0 | 监控 | 配置磁盘使用率告警。
- [ ] P0 | 监控 | 配置容器重启告警。
- [ ] P0 | 监控 | 配置 5xx 错误告警。
- [ ] P0 | 备份 | 编写 SQLite 在线备份脚本。
- [ ] P0 | 备份 | 编写 uploads/audio/faiss 打包备份脚本。
- [ ] P0 | 备份 | 配置每日自动备份。
- [ ] P0 | 备份 | 配置备份保留策略。
- [ ] P0 | 备份 | 配置异地备份目标。
- [ ] P0 | 备份 | 完成一次恢复演练。
- [ ] P1 | 观测 | 增加关键接口耗时日志。
- [ ] P1 | 观测 | 增加 SQLite 锁等待和异常统计。
- [ ] P1 | 观测 | 增加 Gemini 调用失败率统计。

### 9.4 Phase C：对象存储迁移

- [ ] P1 | 设计 | 定义统一文件存储接口。
- [ ] P1 | 设计 | 定义文件 key 命名规则。
- [ ] P1 | 设计 | 定义公开资源与私有资源访问策略。
- [ ] P1 | 后端 | 保留本地存储实现。
- [ ] P1 | 后端 | 新增 OSS/S3 兼容存储实现。
- [ ] P1 | 后端 | 上传接口改为调用统一存储接口。
- [ ] P1 | 后端 | 媒体上传接口支持对象存储返回 URL。
- [ ] P1 | 后端 | 编辑台上传接口支持对象存储返回 URL。
- [ ] P1 | 数据 | 编写旧 uploads 迁移脚本。
- [ ] P1 | 数据 | 迁移旧 editorial uploads。
- [ ] P1 | 数据 | 迁移旧 media uploads。
- [ ] P1 | 前端 | 验证对象存储 URL 在所有页面可展示。
- [ ] P1 | 兼容 | 保留旧本地静态挂载一个过渡周期。
- [ ] P1 | 验收 | 上传、访问、删除、回滚全链路验收。

### 9.5 Phase D：Postgres 渐进迁移

- [ ] P1 | 设计 | 新增 `DATABASE_URL` 配置设计。
- [ ] P1 | 设计 | 定义 SQLite 与 Postgres 双存储边界。
- [ ] P1 | 设计 | 选择数据库访问层改造方式。
- [ ] P1 | Schema | 为 `visitor_profiles` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `article_view_events` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `article_reactions` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `chat_sessions` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `chat_messages` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `user_memberships` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `business_users` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `billing_*` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `editorial_articles` 设计 Postgres 表。
- [ ] P1 | Schema | 为 `media_items` / `media_drafts` 设计 Postgres 表。
- [ ] P1 | 迁移 | 编写 SQLite 到 Postgres 的一次性迁移脚本。
- [ ] P1 | 迁移 | 编写迁移校验脚本。
- [ ] P1 | 后端 | 会员服务读写切到 Postgres。
- [ ] P1 | 后端 | 互动服务读写切到 Postgres。
- [ ] P1 | 后端 | 聊天服务读写切到 Postgres。
- [ ] P1 | 后端 | 编辑台服务读写切到 Postgres。
- [ ] P1 | 后端 | 媒体服务读写切到 Postgres。
- [ ] P1 | 验收 | Postgres 写入链路通过后，关闭对应 SQLite 写入。
- [ ] P1 | 回滚 | 保留 Postgres 迁移回滚脚本。

### 9.6 Phase E：Redis 与任务队列

- [ ] P1 | Redis | 新增 Redis 连接配置。
- [ ] P1 | Redis | 为首页 feed 增加缓存。
- [ ] P1 | Redis | 为栏目列表增加缓存。
- [ ] P1 | Redis | 为专题列表增加缓存。
- [ ] P1 | Redis | 为搜索建议增加缓存。
- [ ] P1 | Redis | 为认证状态短缓存设计过期策略。
- [ ] P1 | 队列 | 选择 RQ 或 Celery。
- [ ] P1 | 队列 | 新增 worker 容器。
- [ ] P1 | 队列 | 将自动摘要改为异步任务。
- [ ] P1 | 队列 | 将自动翻译改为异步任务。
- [ ] P1 | 队列 | 将公众号排版改为异步任务。
- [ ] P1 | 队列 | 将 RAG 入库改为异步任务。
- [ ] P1 | 队列 | 前端增加任务状态轮询。
- [ ] P1 | 队列 | 后端增加任务失败重试策略。
- [ ] P1 | 验收 | AI 长任务不再阻塞 HTTP 请求。

### 9.7 Phase F：横向扩容

- [ ] P2 | 前置检查 | 确认运行时写表已迁 Postgres。
- [ ] P2 | 前置检查 | 确认上传文件已迁对象存储。
- [ ] P2 | 前置检查 | 确认热点缓存已走 Redis。
- [ ] P2 | 前置检查 | 确认长任务已走队列。
- [ ] P2 | 部署 | 引入云负载均衡。
- [ ] P2 | 部署 | backend 从 1 副本扩到 2 副本。
- [ ] P2 | 部署 | 验证任意 backend 重启不影响用户态。
- [ ] P2 | 部署 | backend 从 2 副本扩到 4 副本。
- [ ] P2 | 压测 | 对首页做并发压测。
- [ ] P2 | 压测 | 对文章详情做并发压测。
- [ ] P2 | 压测 | 对搜索做并发压测。
- [ ] P2 | 压测 | 对登录态接口做并发压测。
- [ ] P2 | 压测 | 记录 P50/P95/P99/错误率。

### 9.8 Phase G：检索升级

- [ ] P2 | 评估 | 统计当前文章数、chunk 数、向量维度、索引大小。
- [ ] P2 | 评估 | 对比 FAISS、pgvector、Elasticsearch/OpenSearch。
- [ ] P2 | 方案 | 设计 chunk 表和 embedding 表。
- [ ] P2 | 方案 | 设计增量索引更新流程。
- [ ] P2 | 方案 | 设计索引回滚流程。
- [ ] P2 | 实施 | 实现 pgvector 或 Elasticsearch/OpenSearch 试验分支。
- [ ] P2 | 实施 | 搜索接口支持新旧检索后端切换。
- [ ] P2 | 验收 | 对比新旧检索召回质量。
- [ ] P2 | 验收 | 对比新旧检索延迟。
- [ ] P2 | 切换 | 灰度切换到新检索后端。

---

## 10. 明确暂不做

- [ ] P0 | 决策 | 第一阶段不做 Kubernetes。
- [ ] P0 | 决策 | 第一阶段不做多 backend 副本。
- [ ] P0 | 决策 | 第一阶段不强迁全量 Postgres。
- [ ] P0 | 决策 | 第一阶段不替换 FAISS。
- [ ] P0 | 决策 | 第一阶段不把对象存储作为上线阻塞项。
- [ ] P0 | 决策 | 第一阶段不把 AI 长任务全部重构为队列作为上线阻塞项。

---

## 11. 首发完成定义

首发上云完成必须同时满足：

- Docker Compose 可一键启动。
- 域名 HTTPS 可访问。
- 首页、文章、搜索、登录、会员、编辑台、媒体基本链路通过。
- SQLite、FAISS、uploads、audio 全部在持久盘。
- 容器重启后数据不丢。
- 每日备份可执行。
- 至少完成一次恢复演练。
- 生产环境关闭 DEV_AUTH。
- 关键密钥没有进入 Git。
- 有明确回滚步骤。

---

## 12. 下一步执行顺序

1. 做 Phase A 的 Docker 文件和 Compose。
2. 本地用 `/data` 模拟生产目录跑通。
3. 修正容器内路径、Node 运行时、上传大小、健康检查。
4. 准备阿里云 ECS 和数据盘。
5. 上传 `/data` 资产。
6. 配生产 `.env`。
7. 启动服务并绑定域名。
8. 做首轮验收。
9. 配备份和监控。
10. 进入对象存储和 Postgres 渐进迁移。
