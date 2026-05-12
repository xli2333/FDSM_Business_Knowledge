# 13 Docker 第一轮数据准备与启动验收

## 目标

本文件只服务第一轮 Docker 上云最小闭环：先让容器栈稳定启动、健康检查通过、静态资源和数据库路径正确。不要在这一轮同时做 AI 异步队列、Redis 写缓冲或 CAS 登录切换。

## 数据目录规则

Docker 内统一使用 `/data`，宿主机统一使用项目根目录下的 `data/`。

必须先复制，不要直接移动原始文件。确认 Docker 栈和本地非 Docker 启动都正常后，再决定是否清理旧目录。

推荐目录结构：

```text
data/
  fudan_knowledge_base.db
  faiss_index_business/
  Fudan_Business_Knowledge_Data/
  uploads/
    editorial/
    media/
  audio/
  rag_chunk_index/
```

## Windows PowerShell 数据准备

在项目根目录执行：

```powershell
New-Item -ItemType Directory -Force data
Copy-Item -LiteralPath .\fudan_knowledge_base.db -Destination .\data\fudan_knowledge_base.db -Force
Copy-Item -LiteralPath .\faiss_index_business -Destination .\data\faiss_index_business -Recurse -Force
Copy-Item -LiteralPath .\Fudan_Business_Knowledge_Data -Destination .\data\Fudan_Business_Knowledge_Data -Recurse -Force
Copy-Item -LiteralPath .\uploads -Destination .\data\uploads -Recurse -Force
Copy-Item -LiteralPath .\audio -Destination .\data\audio -Recurse -Force
```

如果某个目录不存在，不要手动创建空业务数据冒充成功，先记录缺失项并确认对应功能是否仍需要。

## 环境文件准备

```powershell
Copy-Item -LiteralPath .\.env.docker.example -Destination .\.env.docker -Force
```

本地 Docker 验收可以先用：

```env
APP_ENV=production
APP_PORT=8080
SITE_BASE_URL=http://127.0.0.1:8080
ALLOWED_ORIGINS=http://127.0.0.1:8080
DEV_AUTH_ENABLED=0
VITE_ENABLE_DEBUG_AUTH=0
```

如果要验收预览账号登录，不要在 production 模式打开 debug auth。另开开发模式验收：

```env
APP_ENV=development
DEV_AUTH_ENABLED=1
VITE_ENABLE_DEBUG_AUTH=1
```

## 启动命令

```powershell
docker compose --env-file .env.docker up -d --build
```

访问：

- 前端：http://127.0.0.1:8080
- Nginx 健康检查：http://127.0.0.1:8080/healthz
- 后端健康检查：http://127.0.0.1:8080/api/health

## 第一轮验收

- [ ] `docker compose ps` 中 `frontend`、`backend-web`、`redis` 为 healthy。
- [ ] `http://127.0.0.1:8080/healthz` 返回 `ok`。
- [ ] `http://127.0.0.1:8080/api/health` 返回 `database_ready: true`。
- [ ] 首页可以打开，浏览器 Network 中 API 请求走 `/api/...`，不是 `127.0.0.1:8000`。
- [ ] 生产模式下手动带 `X-Debug-User-Id` 请求 `/api/auth/status` 会被拒绝。
- [ ] `/audio-files/`、`/editorial-uploads/`、`/media-uploads/` 的真实资源路径可访问。
- [ ] `backups/` 内能生成 SQLite 备份文件。

## 上云前禁止项

- 不要把 `.env.docker` 提交到 Git。
- 不要把 `data/`、`backups/`、数据库、FAISS、uploads、audio 打进镜像。
- 不要在云端 production 打开 `DEV_AUTH_ENABLED=1`。
- 不要在第一轮混入 CAS 切换和 AI 异步队列改造。
