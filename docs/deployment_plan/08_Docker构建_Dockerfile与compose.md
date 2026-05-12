# 08 · Docker 构建：Dockerfile 与 docker-compose

> **当前状态提示（2026-04-21）**：本文是早期 Docker 设计稿，保留用于理解当时的容器化方案。当前实际文件已调整为 `frontend/Dockerfile`、`docker-compose.yml`、`docker-compose.prod.yml`、`.env.docker.example`、`.env.production.example`；没有使用根目录 `Dockerfile.frontend`、`docker-compose.override.yml`、`IMAGE_TAG` 和容器内 HTTPS 作为当前部署主线。私有云执行命令以 [16_私有云发布包_Nginx_HTTPS上线验收.md](./16_私有云发布包_Nginx_HTTPS上线验收.md)、[17_最终压测性能预算与交付清单.md](./17_最终压测性能预算与交付清单.md)、[18_部署文档对齐复查.md](./18_部署文档对齐复查.md) 为准。

> **前置依赖**：[02-07] 所有代码改造完成
> **预计耗时**：3-4 小时（首次构建镜像 10 分钟）
> **完成标志**：
> - `docker compose build` 成功
> - `docker compose up -d` 启动 6 个容器：backend-web、backend-worker、frontend、redis、backup（+ 本地 override 下的 backend-web 热重载）
> - `docker compose ps` 显示所有服务 `healthy`
> - 前端 `http://localhost:8080` 能打开
> - 后端 `http://localhost:8080/api/health` 返回 `status: ok`

---

## 背景与目标

把 §02-07 做的所有代码改造、配置、环境变量，装进 Docker 镜像和 compose 编排。

**核心原则**：
1. **生产和本地共用同一份 `docker-compose.yml`**
2. 本地差异通过 `docker-compose.override.yml` 覆盖（Docker Compose 自动合并）
3. 所有密钥走 env_file，绝不 hardcode
4. 数据和代码分离：代码进镜像，数据挂 volume

---

## 改动清单

- [ ] 步骤 1：填 `Dockerfile.backend`（Python 3.13 + Node 20 + multi-stage）
- [ ] 步骤 2：填 `Dockerfile.frontend`（Vite build + Nginx serve）
- [ ] 步骤 3：填 `.dockerignore`
- [ ] 步骤 4：填 `docker-compose.yml`（生产和本地共用）
- [ ] 步骤 5：填 `docker-compose.override.yml`（仅本地）
- [ ] 步骤 6：填 `.env.example` / `.env.development` / `.env.production`
- [ ] 步骤 7：先只构建 backend 镜像验证
- [ ] 步骤 8：再构建 frontend 镜像验证
- [ ] 步骤 9：`docker compose up` 完整启动
- [ ] 步骤 10：Commit

**涉及文件**（都是 §01 创建的占位文件，现在填内容）：
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `.dockerignore`
- `docker-compose.yml`
- `docker-compose.override.yml`
- `.env.example`
- `.env.development`
- `.env.production`（至少填本地开发用的 Supabase/Gemini 值）

---

## 原子步骤

### 步骤 1 · `Dockerfile.backend` 完整内容

**打开 `Dockerfile.backend`**，替换占位内容为：

```dockerfile
# syntax=docker/dockerfile:1.7
#
# fdsm-knowledge-backend
#
# 多阶段构建：
#   Stage 1 (builder):  装编译工具 + pip 依赖到 --user 目录
#   Stage 2 (runtime):  只带运行时二进制 + Node.js 20 + 拷贝依赖
# 镜像大小目标 ≈ 1.2 GB（Python 3.13 slim + numpy/faiss/pandas 这些大包）

# =====================================================================
# Stage 1: Builder
# =====================================================================
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

WORKDIR /build

# 编译期依赖（faiss-cpu, numpy, pillow 等需要 gcc/g++）
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc g++ \
        curl \
        libomp-dev libopenblas-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 只拷贝依赖清单，利用 Docker 层缓存
COPY requirements.lock.txt ./

# 装到 --user（体积小、不污染系统 Python；下一阶段整目录拷贝）
# 用阿里云镜像源加速（国内机器本地构建有用；海外机器忽略）
RUN pip install --user --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.lock.txt


# =====================================================================
# Stage 2: Runtime
# =====================================================================
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PATH=/home/app/.local/bin:$PATH \
    FDSM_DATA_DIR=/data \
    PORT=8000 \
    TZ=Asia/Shanghai

# 运行时系统依赖（编译器不装，省 200MB）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libopenblas0-pthread \
        curl ca-certificates tzdata \
        tini \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20（wechat_runtime 运行时用到）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x -o /tmp/nodesource.sh \
    && bash /tmp/nodesource.sh \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* /tmp/nodesource.sh \
    && npm config set registry https://registry.npmmirror.com \
    && npm --version

# 非 root 用户（UID 1000 对齐多数 Linux 桌面/服务器默认用户）
RUN groupadd -g 1000 app && useradd -m -u 1000 -g app -s /bin/bash app

WORKDIR /app

# 从 builder 拷贝 Python 依赖
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# 拷贝后端代码
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app deploy/ ./deploy/
COPY --chown=app:app requirements.lock.txt ./

# wechat_runtime 的 Node 依赖（如果 package.json 存在才装）
WORKDIR /app/backend/wechat_runtime
RUN if [ -f package.json ]; then \
        npm ci --omit=dev --no-audit --no-fund || echo "npm ci failed, ignoring"; \
    fi && \
    chown -R app:app /app/backend/wechat_runtime

WORKDIR /app

# 容器内数据挂载点（空目录，靠 volume 挂进来）
RUN mkdir -p /data/uploads/editorial \
             /data/uploads/media \
             /data/audio \
             /data/faiss_index_business \
             /data/rag_chunk_index \
             /data/redis \
    && chown -R app:app /data

USER app

EXPOSE 8000

# Healthcheck：curl 访问 /api/health
# 注意 --start-period 给 90 秒，因为首次加载 FAISS 要几十秒
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# tini 做 PID 1：正确转发 SIGTERM 给子进程，避免僵尸和数据损坏
ENTRYPOINT ["/usr/bin/tini", "--"]

# 默认 CMD：gunicorn + uvicorn workers。compose 会在 worker 容器里 override 这条。
CMD ["gunicorn", "backend.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "100", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info", \
     "--forwarded-allow-ips", "*"]
```

**参数逐条解释**：

| 参数 | 含义 | 为什么这样 |
|---|---|---|
| `python:3.13-slim-bookworm` | 基础镜像 | Debian 12 slim，比 bullseye 新、比 alpine 兼容性好（numpy/faiss 官方轮子是 glibc） |
| `--no-install-recommends` | apt 不装推荐包 | 省空间，几十 MB 差别 |
| `pip install --user` | 装到 $HOME/.local | 不进系统 Python，下一阶段 COPY --from 带走整个 .local |
| `tini` | PID 1 | gunicorn 自己是 master/worker 架构，但 Docker 的 SIGTERM 需要一个懂信号的 PID 1 |
| `curl -fsS ...` healthcheck | 真实探活 | `curl -f` 失败返回非 0，Docker 判定 unhealthy |
| `--start-period 90s` | 首次慢启动 | FAISS 加载 + DB 迁移首次要久 |
| `gunicorn -w 4` | 4 worker | 典型 8 核机器的配置 |
| `--timeout 120` | 请求超时 | AI 调用可能 90s，留余量（但 AI 已异步化，正常不该用到） |
| `--max-requests 1000` | 请求后重启 | 防内存泄漏（Gemini 客户端历史有泄漏） |
| `--forwarded-allow-ips *` | 信任 X-Forwarded-* | 因为 Nginx 在前 |

---

### 步骤 2 · `Dockerfile.frontend` 完整内容

**打开 `Dockerfile.frontend`**，替换占位内容为：

```dockerfile
# syntax=docker/dockerfile:1.7
#
# fdsm-knowledge-frontend
#
# 多阶段：Node 构建 → Nginx serve
# 这个容器同时做：
#   1. 静态文件（frontend/dist）
#   2. 反向代理到 backend-web:8000（路径 /api/*）
#   3. 静态资产直出（/audio-files, /editorial-uploads, /media-uploads）
# 也就是说这一个容器就是整个对外的 HTTP/HTTPS 入口

# =====================================================================
# Stage 1: Vite 构建
# =====================================================================
FROM node:20-alpine AS builder

WORKDIR /build

# 先拷 package.json 利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline --no-audit --no-fund

# 拷代码
COPY frontend/ ./

# 构建 env 通过 docker-compose 的 args 注入
ARG VITE_API_BASE_URL=/api
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN npm run build

# 验证产物存在
RUN ls -la dist/ && test -f dist/index.html


# =====================================================================
# Stage 2: Nginx
# =====================================================================
FROM nginx:1.27-alpine

# 清默认配置
RUN rm -f /etc/nginx/conf.d/default.conf

# 拷 nginx 配置
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/_proxy_base.conf /etc/nginx/conf.d/_proxy_base.conf

# 拷前端构建产物
COPY --from=builder /build/dist /usr/share/nginx/html

# 数据目录挂载点（ro 挂载给 Nginx 直出）
RUN mkdir -p /data/uploads /data/audio && chown -R nginx:nginx /data

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost/nginx-health || exit 1

# Nginx 前台运行
CMD ["nginx", "-g", "daemon off;"]
```

---

### 步骤 3 · `.dockerignore` 完整内容

**打开 `.dockerignore`**（项目根目录），替换占位为：

```
# ==================== Git 和控制文件 ====================
.git
.gitignore
.gitattributes
.github

# ==================== Python ====================
.venv
venv/
ENV/
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
.mypy_cache
.ruff_cache
*.egg-info
pip-log.txt
pip-delete-this-directory.txt

# ==================== Node ====================
node_modules
frontend/node_modules
frontend/dist
npm-debug.log*
yarn-debug.log*
.npm
.yarn

# ==================== 数据和二进制产物（绝不进镜像） ====================
data/
backups/
*.db
*.db-wal
*.db-shm
faiss_index*/
rag_chunk_index/
uploads/
audio/
Fudan_Business_Knowledge_Data/
Fudan_News_Data/
archive/
_publish_clean/

# ==================== 环境/密钥 ====================
.env
.env.*
!.env.example
frontend/.env.*
!frontend/.env.example

# ==================== SSL 证书 ====================
deploy/certbot/conf/
deploy/certbot/www/

# ==================== IDE / OS ====================
.vscode
.idea
.DS_Store
Thumbs.db
desktop.ini
*.swp
*.swo
*~

# ==================== 工具 / 文档 ====================
.claude/
docs/
reports/
qa/
*.log
*.tmp
backend/tests/_tmp_*/
backend/tests/__pycache__/
backend/__pycache__/
.coverage
coverage.xml
htmlcov/

# ==================== Docker 构建副产物 ====================
.dockerignore.bak
docker-compose.override.yml.bak
.docker-build-cache/

# ==================== 大型二进制文档 ====================
*.xlsx
*.pdf
*.doc
*.docx
!requirements*.txt
```

**关键行**：
- `!.env.example` 在 `.env.*` 排除后允许 example 进镜像
- `!requirements*.txt` 保留所有 requirements 文件
- `data/`、`backups/` 是绝对不能进镜像的

**验证 dockerignore 生效**：
```powershell
# 构建镜像前先看 Docker 会拷贝多少东西
docker build --no-cache --progress=plain --target=builder -f Dockerfile.backend -t _test . 2>&1 | Select-String "transferring context"
# 应该 < 50 MB（只有代码），不是 GB 级（数据都进去了）
```

---

### 步骤 4 · `docker-compose.yml` 完整内容

**打开 `docker-compose.yml`**（项目根目录），替换占位为：

```yaml
# fdsm-knowledge · Docker Compose 主配置
#
# 本地开发 + 生产部署共用这份文件。本地通过 docker-compose.override.yml 追加
# 热重载、debug 账号、无 HTTPS 等开发设置；生产环境删掉 override 文件即可。
#
# 服务拓扑：
#   frontend (nginx)  ─ 80/443 ─▶ 对外
#        │
#        ├─▶ backend-web (gunicorn × 4 workers)  ─▶ redis
#        │                                       ─▶ SQLite (via ./data volume)
#        │
#        └─▶ 静态资产直出 (audio-files, uploads)
#
#   backend-worker (独立进程，消费 Redis 任务队列)
#   redis (缓存、限流、任务队列、浏览计数缓冲)
#   backup (定时备份 SQLite + FAISS)

name: fdsm-knowledge

services:

  # =======================================================================
  # Backend Web —— 主 API 服务
  # =======================================================================
  backend-web:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    container_name: fdsm-backend-web
    env_file:
      - .env.production
    environment:
      SERVICE_ROLE: web
      APP_SYNC_AUDIO: "0"          # web 不做 audio 扫描（交给 worker）
    volumes:
      - ./data:/data
    networks:
      - app-net
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 5g
          cpus: "4.0"
        reservations:
          memory: 2g
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      start_period: 90s
      retries: 3

  # =======================================================================
  # Backend Worker —— 异步任务消费者
  # =======================================================================
  backend-worker:
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    container_name: fdsm-backend-worker
    env_file:
      - .env.production
    environment:
      SERVICE_ROLE: worker
      APP_SYNC_AUDIO: "1"          # worker 负责 audio 扫描
      WORKER_LOG_LEVEL: INFO
    command: ["python", "-m", "deploy.worker_loop"]
    volumes:
      - ./data:/data
    networks:
      - app-net
    depends_on:
      redis:
        condition: service_healthy
      backend-web:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2g
          cpus: "2.0"
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

  # =======================================================================
  # Frontend + Nginx —— 对外入口
  # =======================================================================
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
      args:
        VITE_API_BASE_URL: /api
        VITE_SUPABASE_URL: ${SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
    image: fdsm-knowledge-frontend:${IMAGE_TAG:-local}
    container_name: fdsm-frontend
    ports:
      - "${HTTP_PORT:-80}:80"
      - "${HTTPS_PORT:-443}:443"
    volumes:
      # 静态资产与后端共享（只读）
      - ./data/audio:/data/audio:ro
      - ./data/uploads:/data/uploads:ro
      # SSL 证书（生产用；本地 override 里可能跳过）
      - ./deploy/certbot/conf:/etc/letsencrypt:ro
      - ./deploy/certbot/www:/var/www/certbot:ro
    networks:
      - app-net
    depends_on:
      backend-web:
        condition: service_healthy
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/nginx-health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # =======================================================================
  # Redis —— 缓存 / 限流 / 任务队列 / 浏览计数缓冲
  # =======================================================================
  redis:
    image: redis:7-alpine
    container_name: fdsm-redis
    command:
      - redis-server
      - --maxmemory
      - 1gb
      - --maxmemory-policy
      - allkeys-lru
      - --appendonly
      - "yes"
      - --appendfsync
      - everysec
      - --save
      - "900 1"
      - --save
      - "300 10"
    volumes:
      - ./data/redis:/data
    networks:
      - app-net
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1500m
          cpus: "1.0"
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # =======================================================================
  # Backup —— 定时备份 SQLite + FAISS
  # =======================================================================
  backup:
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    container_name: fdsm-backup
    env_file:
      - .env.production
    entrypoint: ["/bin/bash", "/app/deploy/backup_loop.sh"]
    volumes:
      - ./data:/data:ro
      - ./backups:/backups
    networks:
      - app-net
    restart: unless-stopped
    depends_on:
      - backend-web
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

networks:
  app-net:
    driver: bridge
    name: fdsm-knowledge-net
```

**关键设计说明**：

| 选项 | 作用 |
|---|---|
| `name: fdsm-knowledge` | 项目名（compose v2 语法）。容器名前缀和 network 名都基于这个 |
| `${IMAGE_TAG:-local}` | 环境变量插值：本地构建时默认 `local`，生产部署时设 `v1.0` |
| `env_file: .env.production` | 所有 env 都从这个文件读（本地 override 可以再追加其他 env） |
| `depends_on.service_healthy` | 新 compose 语法，等 healthcheck 通过才启动依赖方 |
| `deploy.resources.limits` | Docker Swarm 和 docker-compose 都认，单机部署也生效（需要 compose v3+） |
| `logging.options.max-size/file` | 日志 rotation，防止单机日志打爆磁盘 |

---

### 步骤 5 · `docker-compose.override.yml`（本地用）

**打开 `docker-compose.override.yml`**，替换占位为：

```yaml
# 本地开发 override
# docker compose 会自动合并这份文件和 docker-compose.yml
# 生产部署时：
#   mv docker-compose.override.yml docker-compose.override.yml.local-only
# 或者启动时加 -f docker-compose.yml 明确忽略 override

services:

  backend-web:
    environment:
      APP_ENV: development
      DEV_AUTH_ENABLED: "1"
      ALLOWED_ORIGINS: "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080"
      # 覆盖生产的多 worker 为单 worker + reload
    command:
      - uvicorn
      - backend.main:app
      - --host
      - 0.0.0.0
      - --port
      - "8000"
      - --reload
      - --log-level
      - debug
    volumes:
      # 代码热重载（宿主机改代码容器立即看到）
      - ./backend:/app/backend
      - ./data:/data
    deploy:
      resources:
        limits:
          memory: 3g           # 本地开发少给点
          cpus: "2.0"

  backend-worker:
    environment:
      APP_ENV: development
      WORKER_LOG_LEVEL: DEBUG
    volumes:
      - ./backend:/app/backend
      - ./deploy:/app/deploy
      - ./data:/data

  frontend:
    ports:
      # 本地不占 80/443，走 8080
      - "8080:80"
      # 本地不用 HTTPS
    build:
      args:
        VITE_API_BASE_URL: /api
        VITE_SUPABASE_URL: ${SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}

  # 本地不跑定时备份
  backup:
    profiles: ["disabled"]
```

**说明**：
- `profiles: ["disabled"]` 让 backup 容器**默认不启动**（只有 `docker compose --profile disabled up` 才启）
- 本地 HTTPS 跳过（Nginx 配置里 443 server 块会因为证书不存在而启动失败——这个问题在 §09 解决）
- `volumes: ./backend:/app/backend` 让你本地改 Python 文件，容器内 uvicorn `--reload` 会重启

---

### 步骤 6 · `.env.example` / `.env.development` / `.env.production`

**`.env.example`**（项目根，入 Git）：
```bash
# ============ 环境 ============
APP_ENV=production                        # production 或 development
IMAGE_TAG=local                           # 镜像标签
HTTP_PORT=80
HTTPS_PORT=443

# ============ 数据路径（容器内） ============
FDSM_DATA_DIR=/data

# ============ 站点 ============
SITE_BASE_URL=https://your-domain.com
ALLOWED_ORIGINS=https://your-domain.com

# ============ Gemini ============
GOOGLE_API_KEY=
GEMINI_API_KEYS=
GEMINI_CHAT_MODEL=gemini-3.0-flash
GEMINI_FLASH_MODEL=gemini-3.0-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001

# ============ Supabase ============
AUTH_BACKEND=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJxxxx
SUPABASE_AUTH_TIMEOUT_SECONDS=8
DEV_AUTH_ENABLED=0

# ============ 管理员 ============
ADMIN_EMAILS=admin@example.com

# ============ Redis ============
REDIS_URL=redis://redis:6379/0

# ============ DB 写并发 ============
DB_WRITE_CONCURRENCY=4
DB_WRITE_WAIT_SECONDS=10

# ============ RAG ============
RAG_SEARCH_PROVIDER=local_chunk
RAG_ENABLE_INLINE_INGESTION=1
RAG_CHUNK_EMBEDDINGS_ENABLED=1
RAG_CHUNK_CHAR_LIMIT=900
RAG_CHUNK_OVERLAP=120
RAG_RETRIEVAL_CANDIDATE_LIMIT=48

# ============ 支付（先关） ============
PAYMENTS_ENABLED=0
PAYMENT_PROVIDER=mock

# ============ CAS（v2 启用时填） ============
# CAS_URL=https://id.fudan.edu.cn/cas
# CAS_SERVICE_URL=https://your-domain.com/api/auth/cas/callback
```

**`.env.development`**（项目根，不入 Git）：
```bash
APP_ENV=development
IMAGE_TAG=local
HTTP_PORT=8080
HTTPS_PORT=8443

FDSM_DATA_DIR=/data
SITE_BASE_URL=http://localhost:8080
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:5173

# Gemini（本地可以用你当前 .env 的值）
GOOGLE_API_KEY=AIzaSyBGeIsH6eYrhOhRVKSJhnH69GLzJWpPEFQ
GEMINI_API_KEYS=AIzaSyBGeIsH6eYrhOhRVKSJhnH69GLzJWpPEFQ,AIzaSyAKJ7YgmEsXMiiMcdPU-33O-9Pp96Nz7Q4
GEMINI_CHAT_MODEL=gemini-3.0-flash
GEMINI_FLASH_MODEL=gemini-3.0-flash

# Supabase 测试项目
SUPABASE_URL=https://测试项目.supabase.co
SUPABASE_ANON_KEY=eyJ测试
DEV_AUTH_ENABLED=1

ADMIN_EMAILS=你的邮箱@example.com
REDIS_URL=redis://redis:6379/0

RAG_SEARCH_PROVIDER=local_chunk
RAG_CHUNK_CHAR_LIMIT=900

DB_WRITE_CONCURRENCY=4
```

**`.env.production`**（项目根，不入 Git，上线时在服务器上填）：
```bash
APP_ENV=production
IMAGE_TAG=v1.0
HTTP_PORT=80
HTTPS_PORT=443

FDSM_DATA_DIR=/data
SITE_BASE_URL=https://knowledge.fdsm.fudan.edu.cn
ALLOWED_ORIGINS=https://knowledge.fdsm.fudan.edu.cn

GOOGLE_API_KEY=<生产 key>
GEMINI_API_KEYS=<生产 keys>

SUPABASE_URL=https://生产项目.supabase.co
SUPABASE_ANON_KEY=<生产 anon>
DEV_AUTH_ENABLED=0
ADMIN_EMAILS=admin@fdsm.fudan.edu.cn

REDIS_URL=redis://redis:6379/0
DB_WRITE_CONCURRENCY=4
```

**本地先放一份**（为了 compose build 时能读到 VITE_SUPABASE_URL）。

---

### 步骤 7 · 先单独构建 backend 验证

**不要**一上来就 `docker compose build`，单独构建 backend 先发现问题：

```powershell
cd C:\Users\LXG\fdsmarticles

# 构建（带进度显示）
docker build -f Dockerfile.backend -t _test-backend . --progress=plain

# 预期：
# 1. transferring context 应该 < 50 MB（.dockerignore 生效）
# 2. Stage 1 装依赖 3-8 分钟（看网络）
# 3. Stage 2 拷贝 + 装 Node 1-2 分钟
# 4. 最后输出：Successfully built ...

# 看镜像大小
docker images _test-backend
# 预期：1.0 - 1.5 GB
```

**如果构建失败**：

| 错误 | 修复 |
|---|---|
| `transferring context` 几 GB | `.dockerignore` 没生效，检查有没有把 `data/` 排除 |
| `pip install` 超时 | 换源（已配阿里源）；或者国内机器直接用 pypi 加 retries |
| `faiss-cpu` 编译报错 | 缺 `libopenblas-dev`（已装）；或者 lock 文件版本太新 |
| `Node 安装失败` | 网络；或者跳过 wechat_runtime（`if [ -f package.json ]` 已经做了兜底） |

**确认镜像能跑**：
```powershell
docker run --rm -it -v ${PWD}/data:/data -e FDSM_DATA_DIR=/data -e APP_ENV=development -p 8000:8000 _test-backend
# 几秒后应该看到 gunicorn 启动日志
```

**打开浏览器** `http://localhost:8000/api/health`：
- 预期：`{"status": "ok", ...}`

**Ctrl+C 停**。

---

### 步骤 8 · 单独构建 frontend 验证

frontend 构建依赖 backend 镜像构建时的东西吗？不依赖，但需要 `deploy/nginx.conf` 等文件——这些在 §09 才填。所以**这一步先跳**，等 §09 nginx 配置填完再做。

或者临时用一个最简 nginx.conf 验证构建流程通：

**临时 `deploy/nginx.conf`**（最简版，就为了让构建过）：
```nginx
events {}
http {
    include /etc/nginx/mime.types;
    server {
        listen 80;
        location / { return 200 "hello"; }
        location /nginx-health { return 200 "ok\n"; }
    }
}
```

**临时 `deploy/default.conf`**（空文件即可，主配置 include 不到会跳过）

**临时 `deploy/_proxy_base.conf`**（空文件）

**构建**：
```powershell
docker build -f Dockerfile.frontend -t _test-frontend . --progress=plain
```

**预期**：
- Stage 1 npm ci 1-3 分钟
- Stage 2 拷贝产物 < 30 秒
- 镜像大小 ~60 MB（nginx:alpine 基础）

**跑一下**：
```powershell
docker run --rm -p 8080:80 _test-frontend
# 浏览器打开 http://localhost:8080
# 预期：能看到前端首页（但所有 API 请求会 404，因为后端没起）
```

**清理测试镜像**：
```powershell
docker rmi _test-backend _test-frontend
```

**注意**：§09 会用真正的 nginx 配置覆盖掉临时版本。

---

### 步骤 9 · 完整 compose 启动

**前提**：
- `.env.development` 已填（Supabase 值至少有占位）
- Redis 开发容器 `fdsm-redis-dev` 如果在跑，先停掉（compose 会起自己的）：
  ```powershell
  docker stop fdsm-redis-dev
  docker rm fdsm-redis-dev
  ```

**启动**：
```powershell
cd C:\Users\LXG\fdsmarticles

# 用 development env 启动（compose 会自动读 .env 文件做变量插值，
# 但实际 env 注入容器走 env_file: .env.production——所以我们本地让 .env.production 
# 等于 .env.development 的内容，最简单）

# 临时方案：拷贝一份
Copy-Item .env.development .env.production -Force

# 构建
docker compose build --progress=plain

# 启动
docker compose up -d

# 看状态
docker compose ps

# 看日志
docker compose logs -f backend-web
```

**预期**：
- `docker compose ps` 显示 5 个服务（backend-web、backend-worker、frontend、redis；backup 因为 profile 是 disabled 默认不启）
- backend-web 状态最终变 `healthy`（要等 90 秒 start_period）
- frontend 状态 `healthy`
- redis 状态 `healthy`

**看各服务日志**：
```powershell
docker compose logs backend-web | Select-Object -Last 30
docker compose logs backend-worker | Select-Object -Last 20
docker compose logs frontend | Select-Object -Last 10
docker compose logs redis | Select-Object -Last 5
```

**端到端测试**：
```powershell
# 健康检查
curl http://localhost:8080/api/health

# 首页
Start-Process http://localhost:8080/
```

---

### 步骤 10 · Commit

```powershell
git status

git add Dockerfile.backend Dockerfile.frontend
git add docker-compose.yml docker-compose.override.yml
git add .dockerignore
git add .env.example
git add deploy/nginx.conf deploy/default.conf deploy/_proxy_base.conf  # 占位，§09 完整填充

# .env.development、.env.production 不入 Git

git commit -m "deploy(step-08): Dockerfiles and docker-compose stack

- Dockerfile.backend: multi-stage, Python 3.13 + Node 20, tini, gunicorn
  with 4 uvicorn workers, healthcheck on /api/health
- Dockerfile.frontend: multi-stage, Vite build + Nginx 1.27-alpine, serves
  frontend dist and reverse-proxies /api/*
- docker-compose.yml: backend-web + backend-worker + frontend + redis +
  backup, all with healthchecks, resource limits, log rotation
- docker-compose.override.yml: local dev with --reload, code mount,
  port 8080, backup disabled
- .dockerignore: exclude data/, backups/, env files, docs, tests
- .env.example with every required variable documented"
```

---

## 阶段验收

### 验收 1 · 镜像大小合理

```powershell
docker images | Select-String "fdsm-knowledge"
# 预期：
#   fdsm-knowledge-backend:local   ≈ 1.2 GB
#   fdsm-knowledge-frontend:local  ≈ 60 MB
```

### 验收 2 · compose 配置无错误

```powershell
docker compose config --quiet
# 无输出 = ok；有错误会打出来
```

### 验收 3 · 所有服务 healthy

```powershell
docker compose ps
```

列应该都是 `Up X minutes (healthy)`。

### 验收 4 · 容器日志无错误

```powershell
# backend-web 不应该有 traceback
docker compose logs backend-web 2>&1 | Select-String -Pattern "traceback|error|exception" -NotMatch | Select-Object -Last 20

# worker 不应该 crash loop
docker compose logs backend-worker | Select-String "worker main loop started"
```

### 验收 5 · 资源占用

```powershell
docker stats --no-stream
```

预期：
- backend-web: 300-600 MB
- backend-worker: 200-400 MB
- frontend (nginx): 10 MB
- redis: 50 MB
- 总和 < 2 GB（给 FAISS 加载后 + 1 GB）

---

## 常见错误与排查

| 症状 | 原因 | 修复 |
|---|---|---|
| `transferring context` 几 GB | `.dockerignore` 没生效 | 确认 `data/` 在 `.dockerignore` 里；`docker build` 重跑前 `docker system prune` |
| `COPY requirements.lock.txt not found` | 文件真没生成 | 回到 §01 重新生成 |
| Stage 2 报 `No package libopenblas0-pthread` | Debian 11 没这个包 | 基础镜像用 `python:3.13-slim-bookworm`（Debian 12） |
| backend-web 启动日志报 `ModuleNotFoundError` | pip 装了但 PATH 不对 | 检查 `ENV PATH=/home/app/.local/bin:$PATH` 在 runtime 阶段设了 |
| healthcheck `command not found: curl` | 没装 curl | runtime 阶段 `apt-get install -y curl`（已装） |
| frontend 启动报 `nginx: emerg open /etc/letsencrypt/...` | SSL 证书不存在 | §09 里 nginx 配置要能无证书也启动 |
| `depends_on service_healthy` 一直等 | 被依赖方 healthcheck 失败 | 查被依赖方日志 |
| worker crash loop | `deploy.worker_loop` 模块找不到 | 确认 `COPY deploy/ ./deploy/` 在 Dockerfile 里；运行 `docker compose exec backend-worker ls /app/deploy` |
| compose 报 `port 80 already in use` | Windows 上别的程序占用 | `netstat -ano \| findstr :80`；或者改 `HTTP_PORT=8080` |
| 镜像超大 (3+ GB) | pip 缓存没清 / 数据进镜像 | 检查 `.dockerignore`；Dockerfile 里 `--no-cache-dir` |

---

## 关于开发模式热重载

`docker-compose.override.yml` 里挂 `./backend:/app/backend` 让你在宿主机改 Python 代码容器自动 reload。

**注意**：
- 只对 `.py` 文件生效（uvicorn `--reload` 监听）
- 改 `requirements.lock.txt` 后要重新 `docker compose build backend-web`
- 改 `deploy/worker_loop.py` 要手动 restart worker：`docker compose restart backend-worker`

**常见踩坑**：Windows 上 volume 挂载性能比 Linux/Mac 差，首次 `--reload` 扫描文件可能要几秒。

---

## 下一步

**去 [09_Nginx配置与静态资产.md](./09_Nginx配置与静态资产.md)** 填真正的 Nginx 配置。

做完 08 之后：
- ✅ Dockerfile 完成
- ✅ docker-compose 编排完成
- ✅ 容器能起、健康检查过

但 Nginx 配置只是个临时占位，静态资产还没直出、限流还没配、HTTPS 也没弄。§09 把这些补齐。
