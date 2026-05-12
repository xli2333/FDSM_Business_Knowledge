# 复旦管院智识库 · 本地 Docker 构建到私有云部署完整指南

> **当前状态提示（2026-04-22）**：本文是迁移前的完整设计稿，保留用于理解架构取舍；当前实现已经完成后续落地调整。真实上云不要直接照本文中的旧文件名和旧命令执行，尤其是 `Dockerfile.frontend`、`docker-compose.override.yml`、`deploy/nginx.conf`、`deploy/default.conf`、容器内 HTTPS、`IMAGE_TAG`、镜像仓库 `docker compose pull`、前端内联 Supabase 变量、生产默认 Supabase/dual 鉴权、根路径 `/metrics`、媒体播放只依赖 Authorization header。当前权威执行入口是 `docs/deployment_plan/16_私有云发布包_Nginx_HTTPS上线验收.md`、`docs/deployment_plan/17_最终压测性能预算与交付清单.md`、`docs/deployment_plan/18_部署文档对齐复查.md`、`docs/deployment_plan/20_上线前严格审核整改记录.md`、`docs/deployment_plan/21_上线前严格审核v2整改记录.md`、`docs/deployment_plan/22_上线自动化与回滚.md`、`docs/deployment_plan/23_依赖锁定与构建可复现.md`、`docs/deployment_plan/24_备份恢复演练.md`、`docs/deployment_plan/25_前端Supabase依赖退场.md`、`docs/deployment_plan/26_后端Supabase生产路径硬隔离.md`、`docs/deployment_plan/27_三审上线前必修Bug整改.md`、`docker-compose.prod.yml` 和 `.env.production.example`。

> **文档版本**：v2.0 · 2026-04-21
> **读者**：项目作者本人
> **适用场景**：本地 Docker 先把项目做到"生产级完美"（多并发、数据持久化、限流、缓存、监控都跑通），镜像和配置直接推到 Linux 私有云的 Docker 环境，**云端只做鉴权切换或修 bug，不做架构改造**
> **写作原则**：原子级详细。每条命令能抄，每段代码能贴，每个配置项有明确的值和理由。

---

## 0. 必须先读：本项目的 19 个关键事实

下面都是基于当前代码（`master` + `archive_snapshot_20260413` 分支未提交改动）扒出来的事实。所有部署决策都建立在这些事实上。

| # | 事实 | 部署含义 |
|---|---|---|
| 1 | 后端 Python 3.13，FastAPI，启动入口 `backend/main.py` 用 `uvicorn.run(app, host="0.0.0.0", port=8000)` 单进程 | 必须换 gunicorn + uvicorn workers，详见 §4 |
| 2 | 业务数据库是 SQLite 单文件 `fudan_knowledge_base.db`（**704 MB**），`sqlite3.connect(..., timeout=60)` + `PRAGMA busy_timeout=60000`，**未启用 WAL** | 必须启用 WAL，详见 §3.1 |
| 3 | 向量索引是 FAISS 本地目录 `faiss_index_business/`（**156 MB**），用 `@lru_cache(maxsize=1)` 在首次检索时加载 | 每个 worker 进程都会加载一份，内存按 workers × 200MB 计 |
| 4 | 静态资产 `uploads/editorial`、`uploads/media`、`audio/`（合计 ~270 MB 且每天增长）由 FastAPI 的 `StaticFiles` 直接挂载 | 必须用 Docker volume；Nginx 直出比 FastAPI 快 10 倍，详见 §5 |
| 5 | 外部 API：Gemini（`.env` 里 5 个 key 做轮询）、Supabase（v1 上线就用它做邮箱注册/登录）；v2 会迁到复旦 CAS（`docs/CAS接入文档.doc`）| Gemini 在国内不通，服务器必须放境外或用代理；鉴权预留好字段，v2 切 CAS 只改 service | 
| 6 | `business_users` 表主键是 `user_id TEXT`（不是自增），已有 `auth_source` 字段（默认 `supabase`）| 迁 CAS 时复用这一套，详见 §9 |
| 7 | `PREVIEW_AUTH_ENABLED=True` 时前端可以通过 `X-Debug-User-Id` 头伪造任何用户（含 admin）| **上线前最高优先级必须堵死**，详见 §9.4 |
| 8 | 本轮未提交改动：新增 `daily_bookmark_service.py`、`user_daily_bookmarks` 表、`media_seed_tombstones` 表、`home_content_slots.language` 列、Gemini 模型统一 3.0-flash | 首次启动 `ensure_runtime_tables()` 会自动建表；但**必须在测试 DB 上验证迁移不报错** |
| 9 | `backend/wechat_runtime/` 是 Node.js 子运行时（`wechatOfficialPublisherService.mjs`），被 `backend/scripts/wechat_fudan_bridge.mjs` 调用 | 镜像必须同时装 Python 和 Node.js |
| 10 | AI 调用（摘要/翻译/格式化）**是同步阻塞**，一次 10-90 秒 | 必须异步化 + 独立 worker 容器，详见 §7 |
| 11 | 项目**没有** Celery / APScheduler / BackgroundTasks | 需要自建 worker loop，详见 §7.3 |
| 12 | 批处理脚本（`article_ai_batch.py` 等）靠手工运行 | worker 容器定时调度它们 |
| 13 | 前端 Vite + React 19（纯 SPA，无 SSR），通过 `fetch` 调 `/api/*` | 生产时前端 `dist/` 由 Nginx 直接出，和后端同域 |
| 14 | 前端已集成 `@supabase/supabase-js` 客户端（`frontend/src/auth/AuthProvider.jsx`）| 生产配 `VITE_SUPABASE_URL` 和 `VITE_SUPABASE_ANON_KEY` 就能直接跑 |
| 15 | `ALLOWED_ORIGINS` 默认 `*` | 生产必须白名单，详见 §3.3 |
| 16 | 有 ~20 张表，含 `articles`、`editorial_articles`（超大）、`article_chunks`、`user_daily_bookmarks` 等 | SQLite 完全扛得住，短期不用迁 Postgres |
| 17 | `.gitignore` 里 `*.db`、`faiss_index*`、`uploads/`、`audio/`、`.env` 都不入库 | 镜像也不带这些，走 volume 挂载 |
| 18 | Gemini 调用走 `requests` 直连 `generativelanguage.googleapis.com` | 国内私有云要走正向代理或走香港/新加坡节点 |
| 19 | 私有云要求不用 Supabase Postgres 存业务数据 | 业务数据全留 SQLite 本地；Supabase 只做鉴权网关 |

---

## 1. 总体策略

### 1.1 "本地即生产"的核心理念

本地开发机用 Docker Desktop 运行和线上**一模一样的 6 个容器**（Nginx + 4 worker 的 backend-web + backend-worker + Redis + backup + cron）。本地跑通就代表生产能跑。

```
本地 Windows + Docker Desktop (Linux 容器模式)
    │
    │ 1) docker compose build
    │ 2) docker compose up -d
    │ 3) 本地验收清单全过 (§12)
    │
    │ 4) docker push 到阿里云镜像仓库
    ▼
云端 Ubuntu 22.04 + Docker
    │
    │ 5) git clone 项目到 /srv/fdsm
    │ 6) 拷贝 data/ 数据
    │ 7) docker pull 镜像
    │ 8) 改 .env.production 里的域名和 SUPABASE_*
    │ 9) docker compose up -d
    │
    ▼
  上线
```

**本地和生产的唯一差异，全部收拢在 `.env.production` 里**。`docker-compose.yml`、镜像、代码都完全一样。

### 1.2 本地/生产差异收拢点（`.env` 对比）

| 变量 | 本地值 | 生产值 | 作用 |
|---|---|---|---|
| `APP_ENV` | `development` | `production` | 开关生产加固（debug header 剥离等） |
| `SITE_BASE_URL` | `http://localhost` | `https://knowledge.fdsm.fudan.edu.cn` | 站点外链 |
| `ALLOWED_ORIGINS` | `http://localhost,http://localhost:5173` | `https://knowledge.fdsm.fudan.edu.cn` | CORS 白名单 |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | 测试项目 | 生产项目 | 鉴权 |
| `DEV_AUTH_ENABLED` | `1` | `0` | 本地允许 debug 旁路方便调试 |
| `GEMINI_API_KEYS` | 可以共用 | 可以共用（最好生产项目独立 key） | AI 调用 |
| 前端构建 arg `VITE_API_BASE_URL` | `/api` | `/api` | 前端 API 路径（都走同域） |

### 1.3 所有目录结构（以项目根为基准）

```
C:\Users\LXG\fdsmarticles\          (本地)
├── backend/                        [入镜像]
├── frontend/                       [入镜像]
├── requirements.txt                [入镜像]
├── requirements.lock.txt           [入镜像，新生成]
├── docker-compose.yml              [入 Git]
├── docker-compose.override.yml     [本地开发用，不入生产]
├── Dockerfile.backend              [入 Git]
├── Dockerfile.frontend             [入 Git]
├── .dockerignore                   [入 Git]
├── .env.example                    [入 Git]
├── .env.development                [本地用，不入 Git]
├── .env.production                 [生产用，不入 Git]
├── deploy/                         [入 Git]
│   ├── nginx.conf
│   ├── default.conf
│   ├── smoke_test_auth.sh
│   ├── worker_loop.py
│   └── backup_loop.sh
└── data/                           [不入 Git、不入镜像]
    ├── fudan_knowledge_base.db
    ├── faiss_index_business/
    ├── rag_chunk_index/
    ├── uploads/
    ├── audio/
    └── redis/
```

---

## 2. 资源规划

### 2.1 服务器配置推荐（Linux 私有云）

| 档位 | CPU | 内存 | 磁盘 | 带宽 | 适用场景 |
|---|---|---|---|---|---|
| 起步 | 4c | 8G | 100G SSD | 5M | 日 UV < 500 |
| **推荐** ⭐ | **8c** | **16G** | **200G SSD** | **10M** | 日 UV 500-3000，20-50 并发 |
| 高流量 | 16c | 32G | 500G SSD | 20M | 日 UV 3000+，机构客户 |

**推荐版 16GB 内存账**：
- 4 个 gunicorn worker × 800MB（含 FAISS 200MB） = 3.2GB
- 2 个 backend-worker × 800MB = 1.6GB
- Redis = 1GB
- Nginx + 系统 + Docker overhead = 2GB
- **剩下 ~8GB 做 SQLite 页缓存 + Linux 文件缓存**（这是 SQLite 性能的关键）

### 2.2 系统和组件版本

| 组件 | 版本 | 说明 |
|---|---|---|
| 操作系统 | Ubuntu 22.04 LTS | 云端；别用 CentOS（已 EOL） |
| 本地开发 | Docker Desktop 4.30+ （Linux 容器模式） | 开 WSL2 后端 |
| Docker Engine | 24.0+ | 云端 |
| Docker Compose | v2.20+ | 用 `docker compose`（不是 `docker-compose`）|
| Python | 3.13（容器内） | 对齐本地 |
| Node.js | 20 LTS（容器内）| `wechat_runtime` 需要 |
| Nginx | 1.27-alpine | |
| Redis | 7-alpine | |

### 2.3 网络与域名

- 域名：`knowledge.fdsm.fudan.edu.cn`（示例）
- DNS A 记录 → 服务器公网 IP
- 安全组放行：**22（SSH）、80、443**；其他端口全部拒绝
- SSL：Let's Encrypt 免费证书（certbot 续签）
- **国内访问 Gemini 不通**的解决：
  - 方案 A（推荐）：服务器放阿里云香港/新加坡节点
  - 方案 B：国内服务器 + 单独开一台境外小机器做正向代理，Gemini 调用走 `HTTP_PROXY` env

---

## 3. 代码改造清单（必做项）

下面每一项都要在**本地 Docker 跑起来之前**改完。每项都给出原因、原代码位置、修改后代码。

### 3.1 `backend/database.py` 启用 WAL 和性能 PRAGMA

**原因**：SQLite 默认 `DELETE` journal 模式下，**写操作会锁全库**。704 MB 的 DB 在多 worker 下会频繁触发 `database is locked`。WAL（Write-Ahead Logging）允许读写并发。

**原代码**（`backend/database.py:25-29`）：
```python
def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection
```

**改为**：
```python
_PRAGMA_APPLIED = False
_PRAGMA_LOCK = __import__("threading").Lock()

def _apply_startup_pragmas(connection: sqlite3.Connection) -> None:
    """只在首次连接时应用 WAL 等持久化配置（WAL 一旦设置就写入 DB 文件，之后所有连接都生效）。"""
    global _PRAGMA_APPLIED
    with _PRAGMA_LOCK:
        if _PRAGMA_APPLIED:
            return
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA wal_autocheckpoint = 1000")
        _PRAGMA_APPLIED = True

def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(
        SQLITE_DB_PATH,
        timeout=60,
        check_same_thread=False,    # 允许跨线程用同一连接（worker 多线程必需）
        isolation_level=None,       # 显式事务控制
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    connection.execute("PRAGMA synchronous = NORMAL")       # WAL 下安全
    connection.execute("PRAGMA cache_size = -65536")        # 64 MB 页缓存（每连接）
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA mmap_size = 268435456")      # 256 MB mmap
    connection.execute("PRAGMA foreign_keys = ON")
    _apply_startup_pragmas(connection)
    return connection
```

**结果**：DB 目录里会多出 `fudan_knowledge_base.db-wal` 和 `-shm` 两个文件。**volume 挂载整个目录即可，不要只挂 .db 文件本身**。

### 3.2 `backend/main.py` 改 lifespan + 真实健康检查

**原因**：现在 `ensure_database_ready()` 在模块顶层跑，gunicorn 启 4 个 worker 会并发跑 4 次初始化，而且 `/` 的健康检查只返回常量字符串，不真正检查 DB 可达。

**原代码**（`backend/main.py:36-86`，摘要）：
```python
ensure_database_ready()
ensure_runtime_tables()
EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
sync_local_audio_library()

app = FastAPI(title=APP_TITLE)
...
@app.get("/")
def health_check():
    return {"status": "ok", "service": APP_TITLE, "scope": "business-only"}
```

**改为**：
```python
from contextlib import asynccontextmanager
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # worker 启动时做一次初始化；ensure_* 都是幂等的
    ensure_database_ready()
    ensure_runtime_tables()
    EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # 只在 worker-0（或 SERVICE_ROLE=worker）做 audio 同步，避免 N 个 worker 各扫一遍
    if os.getenv("GUNICORN_WORKER_ID", "0") == "0" or os.getenv("SERVICE_ROLE") == "worker":
        try:
            sync_local_audio_library()
        except Exception:
            import logging
            logging.exception("sync_local_audio_library failed")
    yield

app = FastAPI(title=APP_TITLE, lifespan=lifespan)

# ... CORS、mount、router 保持不变 ...

@app.get("/api/health")
def health_check():
    # 真实探活：DB 可达 + FAISS 目录存在
    try:
        from backend.database import connection_scope
        with connection_scope() as conn:
            conn.execute("SELECT 1").fetchone()
        if not FAISS_DB_DIR.exists():
            raise RuntimeError("FAISS index directory missing")
        return {"status": "ok", "service": APP_TITLE}
    except Exception as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(exc))

@app.get("/")
def root():
    return {"status": "ok", "service": APP_TITLE, "docs": "/docs"}
```

**把顶层的 5 行初始化全部移除**（`ensure_database_ready()` 到 `sync_local_audio_library()`）。

### 3.3 `backend/main.py` 加生产加固中间件

**原因**：`DEV_AUTH_ENABLED=True` 时前端可以用 `X-Debug-User-Id` 头伪造用户。上线前必须堵死。

**在 `app.add_middleware(CORSMiddleware, ...)` 之前插入**：
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Receive, Scope, Send

class StripDebugHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if os.getenv("APP_ENV", "").lower() == "production":
            # ASGI scope headers 是 list of (bytes, bytes)
            request.scope["headers"] = [
                (k, v) for k, v in request.scope["headers"]
                if not k.lower().startswith(b"x-debug-")
            ]
        return await call_next(request)

app.add_middleware(StripDebugHeadersMiddleware)
```

同时改 `backend/services/supabase_auth_service.py::_build_debug_user`，第一行加守卫：
```python
def _build_debug_user(debug_user_id, debug_user_email):
    if os.getenv("APP_ENV", "").lower() == "production":
        return None
    if not PREVIEW_AUTH_ENABLED or not debug_user_id:
        return None
    # ... 其余不变 ...
```

文件顶部 `import os`。

### 3.4 `backend/config.py` 生产环境 CORS 白名单

**原因**：`ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")` 默认是 `*`，CORS 全开。

**在 `config.py` 尾部追加**：
```python
if os.getenv("APP_ENV", "").lower() == "production" and (not ALLOWED_ORIGINS or ALLOWED_ORIGINS == ["*"]):
    raise RuntimeError("ALLOWED_ORIGINS must be an explicit whitelist in production")
```

同时 `main.py` 里改：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,       # 删掉 "or ['*']" 的 fallback
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Visitor-Id"],
)
```

### 3.5 前端 API base url 和 token 取用

**原因**：`frontend/src/api/index.js` 当前默认 `http://127.0.0.1:8000/api`，生产要同域（`/api`）。

**改 `frontend/src/api/index.js` 顶部**：
```javascript
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const API_ORIGIN = API_BASE_URL.startsWith('http')
  ? API_BASE_URL.replace(/\/api\/?$/, '')
  : ''  // 同域时为空
```

**确认前端带 Supabase token**：检查 `frontend/src/auth/AuthProvider.jsx` 里是否把 `supabase.auth.getSession()` 拿到的 token 注入请求。如果 `debugAuth.js` 里有 `X-Debug-User-Id` 头的发送逻辑，**生产构建时加 env 守卫**：

`frontend/src/auth/debugAuth.js`（按实际内容改）：
```javascript
export function getDebugAuthHeaders() {
  // 生产构建时永远返回空对象
  if (import.meta.env.PROD) return {}
  // 开发时可读 localStorage 伪造身份
  const id = localStorage.getItem('debug_user_id')
  const email = localStorage.getItem('debug_user_email')
  return id ? { 'X-Debug-User-Id': id, ...(email && { 'X-Debug-User-Email': email }) } : {}
}
```

### 3.6 `requirements.lock.txt` 锁版本

**原因**：当前 `requirements.txt` 只有 11 行，严重不全（代码实际用了 bs4、lxml、numpy、pillow 等）。必须锁版本才能保证"本地能跑的镜像推到云端也能跑"。

**操作**（本地 venv 里跑）：
```powershell
cd C:\Users\LXG\fdsmarticles
.\.venv\Scripts\Activate.ps1
pip freeze > requirements.lock.txt
```

打开 `requirements.lock.txt`，**手动删除 Windows 专属包**：
- `pywin32==...`
- `pywin32-ctypes==...`
- `pypiwin32==...`
- 任何 `pathlib2`（Py3 原生有）

**补加必需包**（下面的改造会用到）：
```
gunicorn==22.0.0
PyJWT==2.9.0             # 未来 CAS 会用
redis==5.2.0
```

### 3.7 `backend/database.py` 为未来迁 CAS 预留字段

**原因**：`business_users` 表的 `user_id` 现在是 `TEXT PRIMARY KEY`，`auth_source` 默认 `supabase`。迁 CAS 时要能按工号找到用户。

**在 `ensure_runtime_tables()` 的 `business_users` 建表后追加**（文件末尾 `_upgrade_schema()` 类似地方）：
```python
def _ensure_business_users_columns(connection: sqlite3.Connection) -> None:
    existing = {row["name"] for row in connection.execute("PRAGMA table_info(business_users)")}
    if "supabase_user_id" not in existing:
        connection.execute("ALTER TABLE business_users ADD COLUMN supabase_user_id TEXT")
    if "cas_employee_number" not in existing:
        connection.execute("ALTER TABLE business_users ADD COLUMN cas_employee_number TEXT")
    if "cas_username" not in existing:
        connection.execute("ALTER TABLE business_users ADD COLUMN cas_username TEXT")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_business_users_supabase_user_id "
        "ON business_users(supabase_user_id) WHERE supabase_user_id IS NOT NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_business_users_cas_employee "
        "ON business_users(cas_employee_number) WHERE cas_employee_number IS NOT NULL"
    )
```

在 `ensure_runtime_tables()` 最后调用 `_ensure_business_users_columns(connection)`。

### 3.8 Supabase 鉴权加缓存层

**原因**：当前 `supabase_auth_service.get_authenticated_user` 每次 API 都远程验 token（见 `backend/services/supabase_auth_service.py:55-63`），延迟 100-300ms 且有 8s 超时风险。

**在 `supabase_auth_service.py` 顶部加**：
```python
import time
from threading import Lock

_AUTH_CACHE: dict[str, tuple[float, dict | None]] = {}
_AUTH_CACHE_LOCK = Lock()
_AUTH_CACHE_TTL = 300  # 5 分钟（Supabase token 本身 1 小时过期，缓存 5 分钟安全）
_AUTH_CACHE_MAX = 10000
```

**改 `get_authenticated_user()` 的 Supabase 验签段落**：
```python
def get_authenticated_user(authorization, *, debug_user_id=None, debug_user_email=None):
    if not is_supabase_auth_enabled():
        return _build_debug_user(debug_user_id, debug_user_email)
    access_token = _extract_bearer_token(authorization)
    if not access_token:
        return _build_debug_user(debug_user_id, debug_user_email)

    now = time.time()
    with _AUTH_CACHE_LOCK:
        entry = _AUTH_CACHE.get(access_token)
        if entry and (now - entry[0]) < _AUTH_CACHE_TTL:
            return entry[1]

    try:
        response = requests.get(
            _user_endpoint(),
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {access_token}"},
            timeout=SUPABASE_AUTH_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        with _AUTH_CACHE_LOCK:
            _AUTH_CACHE[access_token] = (now, None)
        return None

    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        return None
    user = {"id": user_id, "email": payload.get("email"), "raw_user": payload}

    # 绑定本地 business_users 记录
    local_user = _ensure_local_user_from_supabase(user)

    with _AUTH_CACHE_LOCK:
        _AUTH_CACHE[access_token] = (now, local_user)
        if len(_AUTH_CACHE) > _AUTH_CACHE_MAX:
            # 清掉最老的一半
            keys = sorted(_AUTH_CACHE.keys(), key=lambda k: _AUTH_CACHE[k][0])
            for k in keys[: _AUTH_CACHE_MAX // 2]:
                _AUTH_CACHE.pop(k, None)
    return local_user
```

**在文件末尾追加**：
```python
def _ensure_local_user_from_supabase(user: dict) -> dict:
    """首次登录时把 Supabase 用户落地到 business_users。"""
    from backend.database import connection_scope
    supabase_uid = user["id"]
    email = user.get("email")
    with connection_scope() as conn:
        row = conn.execute(
            "SELECT user_id, email FROM business_users WHERE supabase_user_id = ?",
            (supabase_uid,),
        ).fetchone()
        if row:
            return {"id": row["user_id"], "email": row["email"], "raw_user": user}

        if email:
            row = conn.execute(
                "SELECT user_id FROM business_users WHERE lower(email) = lower(?)",
                (email,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE business_users SET supabase_user_id = ?, auth_source = 'supabase' "
                    "WHERE user_id = ?",
                    (supabase_uid, row["user_id"]),
                )
                conn.commit()
                return {"id": row["user_id"], "email": email, "raw_user": user}

        import uuid
        now = __import__("datetime").datetime.now().replace(microsecond=0).isoformat()
        local_id = f"supabase_{supabase_uid[:12]}_{uuid.uuid4().hex[:8]}"
        conn.execute(
            "INSERT INTO business_users(user_id, email, display_name, tier, status, "
            "role_home_path, auth_source, locale, is_seed, supabase_user_id, "
            "created_at, updated_at, last_seen_at) "
            "VALUES (?, ?, ?, 'free_member', 'active', '/me', 'supabase', 'zh-CN', 0, ?, ?, ?, ?)",
            (local_id, email, (email or local_id).split("@")[0], supabase_uid, now, now, now),
        )
        conn.commit()
        return {"id": local_id, "email": email, "raw_user": user}
```

**关键**：业务代码调用方拿到的 `user["id"]` 永远是 `business_users.user_id`（本地主键），不是 Supabase UUID。这一条是 §9 CAS 迁移"零改动业务代码"的基石。

### 3.9 改造清单 checklist

改完挨个勾：

- [ ] §3.1 WAL + PRAGMA
- [ ] §3.2 lifespan + `/api/health`
- [ ] §3.3 `StripDebugHeadersMiddleware` + `_build_debug_user` 生产守卫
- [ ] §3.4 CORS 白名单强制
- [ ] §3.5 前端 `API_BASE_URL` + `getDebugAuthHeaders` 生产守卫
- [ ] §3.6 `requirements.lock.txt` 生成且过滤 Windows 包
- [ ] §3.7 `business_users` 预留 3 个字段 + 2 个索引
- [ ] §3.8 Supabase 鉴权加缓存 + `_ensure_local_user_from_supabase`

---

## 4. Dockerfile

### 4.1 `Dockerfile.backend`（项目根目录新建）

```dockerfile
# syntax=docker/dockerfile:1.7

# =====================================================================
# Stage 1: 依赖构建层（含编译工具链）
# =====================================================================
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# 编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ curl \
        libomp-dev libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# 只 COPY requirements 先装依赖（利用 Docker 层缓存）
COPY requirements.lock.txt ./
RUN pip install --user --no-cache-dir -r requirements.lock.txt

# =====================================================================
# Stage 2: 运行时
# =====================================================================
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/app/.local/bin:$PATH \
    FDSM_DATA_DIR=/data \
    PORT=8000

# 运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libopenblas0 \
        curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20（wechat_runtime 运行时需要）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm config set registry https://registry.npmmirror.com

# 非 root 用户（UID=1000 对齐宿主机默认用户）
RUN groupadd -g 1000 app && useradd -m -u 1000 -g app app

WORKDIR /app

# 从 builder 拷贝 Python 依赖
COPY --from=builder --chown=app:app /root/.local /home/app/.local

# 拷贝代码
COPY --chown=app:app backend/ ./backend/
COPY --chown=app:app requirements.lock.txt ./

# 装 wechat_runtime 的 Node 依赖
WORKDIR /app/backend/wechat_runtime
RUN if [ -f package.json ]; then npm ci --omit=dev; fi \
    && chown -R app:app /app/backend/wechat_runtime
WORKDIR /app

# 容器内数据挂载点（空目录，靠 volume 挂进来）
RUN mkdir -p /data/uploads/editorial /data/uploads/media /data/audio \
             /data/faiss_index_business /data/rag_chunk_index \
    && chown -R app:app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# tini 做 PID 1，正确处理信号（gunicorn 优雅退出）
ENTRYPOINT ["/usr/bin/tini", "--"]

# 默认启动命令（docker-compose 会按 SERVICE_ROLE 覆盖）
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
     "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s %(M)sms"]
```

**参数解释**：
- `-w 4`：4 worker。8 核机器上典型配置，不是越多越好（SQLite 写串行）
- `--timeout 120`：AI 调用可能 90s，留余量
- `--max-requests 1000 --max-requests-jitter 100`：每处理 900-1100 请求自动重启，防内存泄漏
- `--keep-alive 5`：Nginx 到 gunicorn 的 keepalive 5s
- `tini`：确保收到 SIGTERM 时 gunicorn 能优雅退出，避免数据损坏

### 4.2 `Dockerfile.frontend`

```dockerfile
# syntax=docker/dockerfile:1.7

# =====================================================================
# Stage 1: Vite 构建
# =====================================================================
FROM node:20-alpine AS builder

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline --no-audit

COPY frontend/ ./

# 构建时注入 env（在 docker-compose.yml 的 args 里传）
ARG VITE_API_BASE_URL=/api
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_ANON_KEY=$VITE_SUPABASE_ANON_KEY

RUN npm run build

# =====================================================================
# Stage 2: Nginx
# =====================================================================
FROM nginx:1.27-alpine

# 删除默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 拷贝我们的配置
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/default.conf /etc/nginx/conf.d/default.conf

# 拷贝构建产物
COPY --from=builder /build/dist /usr/share/nginx/html

# 静态资源挂载点
RUN mkdir -p /data/uploads /data/audio && chown -R nginx:nginx /data

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s \
    CMD wget -qO- http://localhost/nginx-health || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

### 4.3 `.dockerignore`（项目根目录新建）

```
# Git 和 Python
.git
.gitignore
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.pytest_cache
*.egg-info

# Node
node_modules
frontend/node_modules
frontend/dist

# 数据和 artifact（绝不进镜像）
data/
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

# 环境和密钥
.env
.env.*
!.env.example

# IDE 和 OS
.vscode
.idea
.DS_Store
Thumbs.db

# 工具目录
.claude/
docs/
reports/
qa/
_publish_clean/
backups/

# 日志和临时
*.log
*.tmp
backend/tests/_tmp_*/

# 文档和报告
*.xlsx
*.pdf
docs/*.doc
docs/*.md
```

---

## 5. Nginx 配置

### 5.1 `deploy/nginx.conf`（主配置）

```nginx
user nginx;
worker_processes auto;
worker_rlimit_nofile 65535;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 基础
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    keepalive_requests 1000;
    server_tokens off;
    server_names_hash_bucket_size 64;

    # 超时
    client_header_timeout 30s;
    client_body_timeout 120s;
    send_timeout 60s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    # body size
    client_max_body_size 100m;
    client_body_buffer_size 128k;

    # 日志
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';
    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;

    # gzip
    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types
        text/plain text/css text/xml text/javascript
        application/json application/javascript application/xml
        application/xml+rss application/atom+xml
        image/svg+xml;

    # 限流
    limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=api_ai:10m rate=5r/s;
    limit_req_zone $binary_remote_addr zone=api_auth:10m rate=10r/s;
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;

    # upstream
    upstream backend {
        server backend-web:8000 max_fails=3 fail_timeout=10s;
        keepalive 32;
        keepalive_requests 1000;
        keepalive_timeout 60s;
    }

    # 包含 server 块
    include /etc/nginx/conf.d/*.conf;
}
```

### 5.2 `deploy/default.conf`（server 块）

```nginx
# =====================================================================
# HTTP：Let's Encrypt 验证 + 跳转 HTTPS
# =====================================================================
server {
    listen 80 default_server;
    server_name _;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location /nginx-health {
        access_log off;
        return 200 "ok\n";
    }

    location / {
        # 生产启用跳转
        return 301 https://$host$request_uri;
    }
}

# =====================================================================
# HTTPS 主站
# =====================================================================
server {
    # 本地开发时只开 80 够了，生产启用 443
    listen 443 ssl http2;
    server_name knowledge.fdsm.fudan.edu.cn;

    ssl_certificate /etc/letsencrypt/live/knowledge.fdsm.fudan.edu.cn/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/knowledge.fdsm.fudan.edu.cn/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # 每 IP 并发连接数
    limit_conn conn_per_ip 20;

    # 前端静态
    root /usr/share/nginx/html;
    index index.html;

    # Vite 带 hash 的静态资源强缓存
    location ~* ^/assets/.+\.(js|css|woff2?|png|jpg|jpeg|gif|svg|webp|ico)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 健康检查
    location = /nginx-health {
        access_log off;
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }

    # 登录/鉴权相关：中等限流
    location ~ ^/api/auth {
        limit_req zone=api_auth burst=20 nodelay;
        proxy_pass http://backend;
        include /etc/nginx/conf.d/_proxy_base.conf;
    }

    # AI 相关：严格限流，超长超时
    location ~ ^/api/(chat|search|editorial/ai|editorial/summarize|editorial/translate) {
        limit_req zone=api_ai burst=10 nodelay;
        proxy_pass http://backend;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
        include /etc/nginx/conf.d/_proxy_base.conf;
    }

    # 通用 API
    location /api/ {
        limit_req zone=api_general burst=50 nodelay;
        proxy_pass http://backend;
        include /etc/nginx/conf.d/_proxy_base.conf;
    }

    # 静态资产（Nginx 直接从 volume 读，不经过 FastAPI）
    location /audio-files/ {
        alias /data/audio/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }
    location /editorial-uploads/ {
        alias /data/uploads/editorial/;
        expires 7d;
    }
    location /media-uploads/ {
        alias /data/uploads/media/;
        expires 7d;
    }

    # 拒绝所有 dotfile
    location ~ /\. {
        deny all;
        access_log off;
    }
}
```

### 5.3 `deploy/_proxy_base.conf`（proxy 公共配置）

```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header Connection "";
proxy_buffering on;
proxy_buffer_size 16k;
proxy_buffers 8 16k;
proxy_busy_buffers_size 32k;
```

---

## 6. docker-compose 配置

### 6.1 `docker-compose.yml`（本地和生产共用）

```yaml
name: fdsm-knowledge

services:
  # =====================================================================
  # FastAPI Web（主 API，处理前端请求）
  # =====================================================================
  backend-web:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    env_file:
      - .env.production
    environment:
      SERVICE_ROLE: web
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

  # =====================================================================
  # Worker（长任务：AI 批处理、RAG 重建、每日书签）
  # =====================================================================
  backend-worker:
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    env_file:
      - .env.production
    environment:
      SERVICE_ROLE: worker
    command: ["python", "-m", "deploy.worker_loop"]
    volumes:
      - ./data:/data
      - ./deploy:/app/deploy:ro
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

  # =====================================================================
  # Frontend + Nginx（同时做反代）
  # =====================================================================
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
      args:
        VITE_API_BASE_URL: /api
        VITE_SUPABASE_URL: ${SUPABASE_URL}
        VITE_SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
    image: fdsm-knowledge-frontend:${IMAGE_TAG:-local}
    ports:
      - "${HTTP_PORT:-80}:80"
      - "${HTTPS_PORT:-443}:443"
    volumes:
      # 静态资源和后端共享 volume（只读）
      - ./data/audio:/data/audio:ro
      - ./data/uploads:/data/uploads:ro
      # SSL 证书
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

  # =====================================================================
  # Redis（缓存 + 限流 + 任务队列）
  # =====================================================================
  redis:
    image: redis:7-alpine
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
    volumes:
      - ./data/redis:/data
    networks:
      - app-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # =====================================================================
  # Backup（定时备份 SQLite + FAISS）
  # =====================================================================
  backup:
    image: fdsm-knowledge-backend:${IMAGE_TAG:-local}
    env_file:
      - .env.production
    entrypoint: ["/bin/bash", "/app/deploy/backup_loop.sh"]
    volumes:
      - ./data:/data:ro
      - ./backups:/backups
      - ./deploy:/app/deploy:ro
    networks:
      - app-net
    restart: unless-stopped

networks:
  app-net:
    driver: bridge
```

### 6.2 `docker-compose.override.yml`（本地用，不入生产）

Docker Compose 会自动读 `override.yml` 合并。**云端部署时删掉这个文件**。

```yaml
services:
  backend-web:
    environment:
      APP_ENV: development
      DEV_AUTH_ENABLED: "1"
    volumes:
      # 本地代码热重载
      - ./backend:/app/backend
    # 本地只开一个 worker，带 --reload
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

  backend-worker:
    environment:
      APP_ENV: development
    volumes:
      - ./backend:/app/backend

  frontend:
    # 本地不开 HTTPS，443 映射关掉
    ports:
      - "8080:80"

  # 本地不跑备份
  backup:
    profiles: ["disabled"]
```

---

## 7. 高并发设计（本地就要跑通）

这一节是"本地 Docker 要做到生产级完美"的核心。三个主要痛点分别给方案。

### 7.1 SQLite 写锁：信号量 + Redis 缓冲

**场景**：多个用户同时给同一篇文章点赞，FastAPI 并发写 `article_reactions`，SQLite 会报 `database is locked`。

**方案 A · FastAPI 写锁中间件**（兜底）

新建 `backend/services/db_concurrency.py`：
```python
import asyncio
from fastapi import Request

_WRITE_SEMAPHORE = asyncio.Semaphore(4)  # 最多 4 个并发写请求

async def db_write_semaphore(request: Request):
    """给写接口加并发上限，避免 SQLite 雪崩。"""
    async with _WRITE_SEMAPHORE:
        yield
```

在写密集的 router 里当 dependency 用：
```python
from fastapi import Depends
from backend.services.db_concurrency import db_write_semaphore

@router.post("/engagement", dependencies=[Depends(db_write_semaphore)])
async def add_reaction(...):
    ...
```

**方案 B · 热点写走 Redis 缓冲**（推荐 v2 做）

文章浏览计数这种写多读少、不需要实时一致的场景，先写 Redis，每分钟 flush 到 SQLite：

```python
# backend/services/engagement_service.py 新增
import redis, os
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

def record_article_view(article_id: int, visitor_id: str):
    # 只写 Redis，完全不锁 SQLite
    _redis.hincrby("pending:view_count", str(article_id), 1)
    _redis.sadd("pending:view_ids", str(article_id))
    _redis.expire("pending:view_count", 3600)
```

然后在 `deploy/worker_loop.py` 里加定时 flush（见 §7.3）。

### 7.2 AI 调用阻塞：BackgroundTasks + 轮询

**场景**：编辑点"AI 生成摘要"，Gemini 调用 60 秒，web worker 被占满。

**方案**：改成异步任务模式。

`backend/services/ai_task_service.py`（新建）：
```python
import redis, os, uuid, json, time
_redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
_TTL = 3600

def create_task(task_type: str, payload: dict) -> str:
    task_id = uuid.uuid4().hex
    _redis.setex(f"aitask:{task_id}", _TTL, json.dumps({
        "status": "pending",
        "type": task_type,
        "payload": payload,
        "created_at": time.time(),
    }))
    _redis.lpush("aitask:queue", task_id)
    return task_id

def get_task(task_id: str) -> dict | None:
    data = _redis.get(f"aitask:{task_id}")
    return json.loads(data) if data else None

def update_task(task_id: str, patch: dict):
    data = get_task(task_id) or {}
    data.update(patch)
    _redis.setex(f"aitask:{task_id}", _TTL, json.dumps(data))

def pop_task(timeout: int = 5) -> tuple[str, dict] | None:
    result = _redis.brpop("aitask:queue", timeout=timeout)
    if not result:
        return None
    _, task_id = result
    return task_id, get_task(task_id) or {}
```

编辑接口改造（以摘要为例）：
```python
# backend/routers/editorial.py
from backend.services.ai_task_service import create_task, get_task

@router.post("/ai/summarize")
def trigger_summarize(body: SummarizeRequest):
    task_id = create_task("editorial.summarize", body.dict())
    return {"task_id": task_id, "status": "pending"}

@router.get("/ai/tasks/{task_id}")
def poll_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found or expired")
    return task
```

Worker 端消费（在 `deploy/worker_loop.py`）：
```python
task_id, task = pop_task(timeout=5) or (None, None)
if task:
    update_task(task_id, {"status": "running"})
    try:
        if task["type"] == "editorial.summarize":
            result = editorial_service.generate_summary(**task["payload"])
        # ... 其他任务类型 ...
        update_task(task_id, {"status": "done", "result": result})
    except Exception as e:
        update_task(task_id, {"status": "failed", "error": str(e)})
```

前端配合：轮询 `/api/editorial/ai/tasks/{task_id}`（每 2 秒一次，最多 90 秒）。

### 7.3 `deploy/worker_loop.py`（独立 worker 主循环）

```python
"""
长时间任务 worker。在 backend-worker 容器里运行。
处理：AI 任务队列、每日书签生成、Redis 浏览计数 flush、RAG 摄入任务。
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("worker")

# ============ 初始化（一次性） ============
from backend.database import ensure_database_ready, ensure_runtime_tables
ensure_database_ready()
ensure_runtime_tables()

from backend.services.ai_task_service import pop_task, update_task
import redis

_redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)


# ============ 任务分发 ============
def handle_ai_task(task_id: str, task: dict):
    task_type = task.get("type")
    payload = task.get("payload", {})
    update_task(task_id, {"status": "running", "started_at": time.time()})
    try:
        if task_type == "editorial.summarize":
            from backend.services.editorial_service import generate_summary_for_task
            result = generate_summary_for_task(**payload)
        elif task_type == "editorial.translate":
            from backend.services.editorial_service import translate_for_task
            result = translate_for_task(**payload)
        elif task_type == "editorial.format":
            from backend.services.editorial_service import format_for_task
            result = format_for_task(**payload)
        elif task_type == "rag.ingest_article":
            from backend.services.knowledge_ingestion_service import ingest_article
            result = ingest_article(**payload)
        else:
            raise ValueError(f"unknown task type: {task_type}")
        update_task(task_id, {"status": "done", "result": result, "finished_at": time.time()})
    except Exception as exc:
        log.exception("task %s failed", task_id)
        update_task(task_id, {"status": "failed", "error": str(exc), "finished_at": time.time()})


def flush_view_counts():
    """把 Redis 里的浏览计数 flush 到 SQLite。"""
    article_ids = _redis.spop("pending:view_ids", 100) or set()
    if not article_ids:
        return
    from backend.database import connection_scope
    with connection_scope() as conn:
        for aid in article_ids:
            count = _redis.hget("pending:view_count", str(aid))
            if not count:
                continue
            _redis.hdel("pending:view_count", str(aid))
            conn.execute(
                "UPDATE articles SET view_count = COALESCE(view_count, 0) + ? WHERE id = ?",
                (int(count), int(aid)),
            )
        conn.commit()
    log.info("flushed view counts for %d articles", len(article_ids))


def run_daily_bookmark():
    """每天 03:00 生成一次每日书签。"""
    today = datetime.now().date().isoformat()
    if _redis.get(f"daily_bookmark:done:{today}"):
        return
    hour = datetime.now().hour
    if hour != 3:
        return
    from backend.services.daily_bookmark_service import refresh_daily_bookmarks
    log.info("generating daily bookmarks for %s", today)
    refresh_daily_bookmarks()
    _redis.setex(f"daily_bookmark:done:{today}", 86400, "1")


# ============ 主循环 ============
def main():
    log.info("worker started, pid=%d", os.getpid())
    iteration = 0
    while True:
        iteration += 1
        try:
            # 1. 优先消费 AI 任务（阻塞等 5 秒）
            result = pop_task(timeout=5)
            if result:
                task_id, task = result
                handle_ai_task(task_id, task)
                continue

            # 2. 每 30 秒 flush 一次浏览计数
            if iteration % 6 == 0:
                flush_view_counts()

            # 3. 每分钟尝试每日书签
            if iteration % 12 == 0:
                run_daily_bookmark()

        except Exception:
            log.exception("worker iteration failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
```

### 7.4 FAISS 内存优化

4 个 web worker × 200MB FAISS = 800MB 内存重复。短期忍受（16G 机器完全扛得住），长期可以把 FAISS 拆成独立服务（V2 规划）。

现在本地先验证：启动后 `docker stats` 看各容器内存占用，确认 backend-web 总和 < 4GB。

---

## 8. `.env` 模板

### 8.1 `.env.example`（入 Git，给参考用）

```bash
# ============ 环境标记 ============
APP_ENV=production                        # production / development
IMAGE_TAG=local
HTTP_PORT=80
HTTPS_PORT=443

# ============ 数据路径（容器内绝对路径，不要改） ============
FDSM_DATA_DIR=/data

# ============ 站点配置 ============
SITE_BASE_URL=https://your-domain.com
ALLOWED_ORIGINS=https://your-domain.com

# ============ Gemini（必填） ============
GOOGLE_API_KEY=xxx
GEMINI_API_KEYS=key1,key2,key3
GEMINI_CHAT_MODEL=gemini-3.0-flash
GEMINI_FLASH_MODEL=gemini-3.0-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001

# ============ Supabase 鉴权（v1 必填） ============
AUTH_BACKEND=supabase                     # v1=supabase, v2=cas
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
SUPABASE_AUTH_TIMEOUT_SECONDS=8
DEV_AUTH_ENABLED=0                        # 生产必须 0

# ============ CAS（v2 启用，v1 保持注释） ============
# CAS_URL=https://id.fudan.edu.cn/cas
# CAS_SERVICE_URL=https://your-domain.com/api/auth/cas/callback
# CAS_TIMEOUT_SECONDS=8

# ============ 管理员 ============
ADMIN_EMAILS=admin@fudan.edu.cn

# ============ RAG ============
RAG_SEARCH_PROVIDER=local_chunk
RAG_ENABLE_INLINE_INGESTION=1
RAG_CHUNK_EMBEDDINGS_ENABLED=1
RAG_CHUNK_CHAR_LIMIT=900
RAG_CHUNK_OVERLAP=120
RAG_RETRIEVAL_CANDIDATE_LIMIT=48

# ============ Redis ============
REDIS_URL=redis://redis:6379/0

# ============ 支付（先关） ============
PAYMENTS_ENABLED=0
PAYMENT_PROVIDER=mock
```

### 8.2 `.env.development`（本地用）

```bash
APP_ENV=development
IMAGE_TAG=local
HTTP_PORT=8080
HTTPS_PORT=8443

FDSM_DATA_DIR=/data
SITE_BASE_URL=http://localhost:8080
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:5173

# 本地用测试 Supabase 项目
SUPABASE_URL=https://测试项目.supabase.co
SUPABASE_ANON_KEY=eyJxxxx测试
DEV_AUTH_ENABLED=1

# Gemini 可共用
GOOGLE_API_KEY=AIzaSyBGeIsH6eYrhOhRVKSJhnH69GLzJWpPEFQ
GEMINI_API_KEYS=AIzaSyBGeIsH6eYrhOhRVKSJhnH69GLzJWpPEFQ,...

# 其他跟 .env.example 一样
```

### 8.3 `.env.production`（生产用，上线前 fill in）

```bash
APP_ENV=production
IMAGE_TAG=v1.0
HTTP_PORT=80
HTTPS_PORT=443

FDSM_DATA_DIR=/data
SITE_BASE_URL=https://knowledge.fdsm.fudan.edu.cn
ALLOWED_ORIGINS=https://knowledge.fdsm.fudan.edu.cn

GOOGLE_API_KEY=<生产主 key>
GEMINI_API_KEYS=<生产 key 轮询>
...

AUTH_BACKEND=supabase
SUPABASE_URL=<生产 Supabase URL>
SUPABASE_ANON_KEY=<生产 anon key>
DEV_AUTH_ENABLED=0

ADMIN_EMAILS=admin@fdsm.fudan.edu.cn,xd2320@columbia.edu
REDIS_URL=redis://redis:6379/0
```

**权限**：`chmod 600 .env.production`，绝不入 Git（`.gitignore` 里 `.env.*` 已排除）。

---

## 9. 鉴权：Supabase v1 + CAS v2 预留

详细内容见前文 §3.7、§3.8 的代码改造。这一节补充**前端层的落地**和**未来迁 CAS 的路径**。

### 9.1 Supabase 项目创建

1. https://supabase.com 注册 → New Project
2. Name: `fdsm-knowledge-prod`，Region: **Singapore**，Plan: Free
3. Settings → API 复制两个 key：
   - `Project URL` → `SUPABASE_URL`
   - `anon public` → `SUPABASE_ANON_KEY`
   - ⚠️ `service_role` key **不要** 放进任何 .env 或前端代码
4. Authentication → URL Configuration：
   - Site URL: `https://knowledge.fdsm.fudan.edu.cn`
   - Redirect URLs: 加上 `https://knowledge.fdsm.fudan.edu.cn/*` 和 `http://localhost:8080/*`
5. Authentication → Email Templates：改成中文模板（§3.4 早些版本有示例）

### 9.2 前端集成确认

检查 `frontend/src/auth/AuthProvider.jsx` 是否正确用环境变量：
```javascript
import { createClient } from '@supabase/supabase-js'
const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)
```

检查 `frontend/src/api/index.js` 的 `request()` 是否把 `supabase.auth.getSession()` 的 `access_token` 注入 `Authorization` 头。如果没有，加上：
```javascript
import { supabase } from '../auth/supabaseClient'

async function request(path, options = {}) {
  let token = options.authToken
  if (!token) {
    const { data } = await supabase.auth.getSession()
    token = data.session?.access_token
  }
  // 其余逻辑
}
```

### 9.3 首次 admin 账号

上线后第一步：
1. 前端注册一个账号（填你自己的邮箱，Supabase 会发确认邮件）
2. 确认邮箱后，DB 里 `business_users` 会自动建一条 `tier='free_member'` 的记录（由 §3.8 的 `_ensure_local_user_from_supabase` 创建）
3. 手动把它升级为 admin：
```bash
docker compose exec backend-web python -c "
from backend.database import connection_scope
with connection_scope() as c:
    c.execute(\"UPDATE business_users SET tier='admin', role_home_path='/admin' WHERE email=?\", ('admin@fdsm.fudan.edu.cn',))
    c.commit()
    print(c.execute('SELECT user_id, email, tier FROM business_users WHERE email=?', ('admin@fdsm.fudan.edu.cn',)).fetchone())
"
```

### 9.4 debug header 旁路验证（P0，每次上线都跑）

`deploy/smoke_test_auth.sh`：
```bash
#!/usr/bin/env bash
set -e

DOMAIN=${1:-https://knowledge.fdsm.fudan.edu.cn}
echo "Testing: $DOMAIN"

# 1. 无凭证
echo -n "[1] anonymous /api/auth/status ... "
RESP=$(curl -s "$DOMAIN/api/auth/status")
AUTH=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['authenticated'])")
[ "$AUTH" = "False" ] && echo "ok (false)" || { echo "FAIL: $RESP"; exit 1; }

# 2. 伪造 debug header（生产必须返回 false）
echo -n "[2] X-Debug-User-Id bypass test ... "
RESP=$(curl -s "$DOMAIN/api/auth/status" -H "X-Debug-User-Id: attacker@evil.com")
AUTH=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['authenticated'])")
if [ "$AUTH" = "True" ]; then
    echo "❌ 严重安全漏洞！debug header 旁路未堵死！"
    exit 1
fi
echo "ok (blocked)"

# 3. 健康检查
echo -n "[3] /api/health ... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$DOMAIN/api/health")
[ "$STATUS" = "200" ] && echo "ok" || { echo "FAIL: $STATUS"; exit 1; }

echo "✅ all checks passed"
```

### 9.5 v2 迁 CAS 工作量

到时新建 `backend/services/cas_auth_service.py`，暴露同名的 `get_authenticated_user` 和 `get_auth_status_payload`，然后在 `routers/auth.py` 里根据 `AUTH_BACKEND` env 切换 import 源。业务代码零改动。预估 1.5-2 人日。

---

## 10. 备份

### 10.1 `deploy/backup_loop.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR=/backups
DATA_DIR=/data
RETENTION_DAILY=14
RETENTION_WEEKLY=8

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

while true; do
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    TODAY=$(date +%u)   # 1=Mon ... 7=Sun

    # 每天 SQLite 热备份（online backup API，不阻塞写）
    DAILY_DIR="$BACKUP_DIR/daily/$TIMESTAMP"
    mkdir -p "$DAILY_DIR"
    echo "[$(date)] backing up SQLite ..."
    sqlite3 "$DATA_DIR/fudan_knowledge_base.db" ".backup '$DAILY_DIR/fudan_knowledge_base.db'"

    # 每周日 tar 一次 FAISS 和 uploads
    if [ "$TODAY" = "7" ]; then
        WEEKLY_DIR="$BACKUP_DIR/weekly/$TIMESTAMP"
        mkdir -p "$WEEKLY_DIR"
        echo "[$(date)] weekly snapshot ..."
        tar --zstd -cf "$WEEKLY_DIR/faiss.tar.zst" -C "$DATA_DIR" faiss_index_business
        tar --zstd -cf "$WEEKLY_DIR/uploads.tar.zst" -C "$DATA_DIR" uploads audio 2>/dev/null || true
        cp "$DAILY_DIR/fudan_knowledge_base.db" "$WEEKLY_DIR/"
    fi

    # 清理过期
    find "$BACKUP_DIR/daily" -maxdepth 1 -type d -mtime +$RETENTION_DAILY -exec rm -rf {} + 2>/dev/null || true
    find "$BACKUP_DIR/weekly" -maxdepth 1 -type d -mtime +$((RETENTION_WEEKLY * 7)) -exec rm -rf {} + 2>/dev/null || true

    echo "[$(date)] backup done: $DAILY_DIR"

    # 可选：同步到对象存储
    # ossutil cp -r "$DAILY_DIR" oss://fdsm-backup/daily/$TIMESTAMP/

    sleep 86400
done
```

**关键点**：用 `sqlite3 ... .backup` 而不是 `cp`。WAL 模式下 `cp` 会拷到不一致状态。

### 10.2 异地备份

挂载一个 OSS 存储桶，`backup_loop.sh` 里取消注释。成本极低（100GB × ¥0.12 ≈ ¥12/月）。

---

## 11. 本地构建和验收（原子级步骤）

### 11.1 一次性准备（只做一次）

```powershell
# 在 Windows PowerShell 里
cd C:\Users\LXG\fdsmarticles

# 1. 新建目录
New-Item -ItemType Directory -Force -Path data, backups, deploy\certbot\conf, deploy\certbot\www

# 2. 把现有数据移进 data/
Move-Item -Force fudan_knowledge_base.db data\
Move-Item -Force faiss_index_business data\
Move-Item -Force uploads data\
Move-Item -Force audio data\

# 3. 生成 requirements.lock.txt
.\.venv\Scripts\Activate.ps1
pip freeze | Where-Object { $_ -notmatch "pywin32|pypiwin32" } | Set-Content requirements.lock.txt
# 补齐生产用包
Add-Content requirements.lock.txt "gunicorn==22.0.0"
Add-Content requirements.lock.txt "PyJWT==2.9.0"
Add-Content requirements.lock.txt "redis==5.2.0"
deactivate

# 4. 拷贝配置模板
Copy-Item .env.example .env.development
Copy-Item .env.example .env.production
notepad .env.development         # 填本地值
notepad .env.production          # 填生产值（或先填测试值）

# 5. 把所有新文件、改动文件加入 Git
git add Dockerfile.backend Dockerfile.frontend docker-compose.yml docker-compose.override.yml
git add .dockerignore .env.example
git add deploy/
git add requirements.lock.txt
git add backend/main.py backend/database.py backend/config.py backend/services/supabase_auth_service.py
git add frontend/src/api/index.js frontend/src/auth/debugAuth.js
git status
```

### 11.2 本地第一次构建（5-10 分钟）

```powershell
# 先确认 Docker Desktop 在 Linux 容器模式
docker version --format "{{.Server.Os}}"      # 必须是 linux

# 构建镜像
docker compose build --progress=plain

# 看结果
docker images | Select-String fdsm
# 应该看到 fdsm-knowledge-backend:local 和 fdsm-knowledge-frontend:local
```

### 11.3 本地启动

```powershell
# 启动
docker compose up -d

# 看状态
docker compose ps
# 所有服务应该 running 或 healthy

# 看日志
docker compose logs -f backend-web
# 看到 "Uvicorn running" 和 "Application startup complete" 就 OK
# Ctrl+C 退出（不会停容器）
```

### 11.4 本地验收清单（全部通过才算本地完美）

逐条执行，出错就改完再来：

```powershell
# [1] 健康检查
curl http://localhost:8080/api/health
# 预期：{"status":"ok","service":"复旦管院商业智识库 API"}

# [2] 前端能打开
start http://localhost:8080
# 预期：看到首页，不报错

# [3] API 返回数据
curl http://localhost:8080/api/home/feed?language=zh
# 预期：返回 JSON，含文章列表

# [4] 受保护接口无凭证拒绝
curl -s http://localhost:8080/api/auth/status | python -m json.tool
# 预期：authenticated: false

# [5] debug 旁路在开发模式可用（确认正常流程）
curl -s -H "X-Debug-User-Id: mock-admin" http://localhost:8080/api/auth/status | python -m json.tool
# 预期：authenticated: true, user.id=mock-admin

# [6] 切成 production 模式，再跑 smoke test
# 临时把 .env.development 里 APP_ENV 改成 production，docker compose restart backend-web frontend
docker compose exec backend-web bash -c "cat /app/backend/main.py | grep APP_ENV"
bash deploy/smoke_test_auth.sh http://localhost:8080
# 预期：全部 ok，debug header 旁路被堵

# [7] 改回 development 继续开发
# 恢复 APP_ENV=development，restart

# [8] WAL 生效验证
docker compose exec backend-web sqlite3 /data/fudan_knowledge_base.db "PRAGMA journal_mode;"
# 预期：wal

# [9] Redis 通
docker compose exec redis redis-cli ping
# 预期：PONG

# [10] Worker 在跑
docker compose logs backend-worker --tail=20
# 预期：看到 "worker started, pid=..."

# [11] 静态资源走 Nginx（不经过 FastAPI）
curl -I http://localhost:8080/audio-files/
# 预期：Server: nginx/... 头

# [12] FAISS 搜索能用
curl "http://localhost:8080/api/search?q=人工智能"
# 预期：返回搜索结果数组

# [13] 资源占用合理
docker stats --no-stream
# backend-web 总和应 < 4GB；redis < 100MB

# [14] 文件上传
# 浏览器登录 admin → 编辑工作台 → 上传封面 → 确认文件出现在 data/uploads/editorial/

# [15] AI 任务排队正常
# 浏览器 → 点 "AI 摘要"
# docker compose logs -f backend-worker
# 应该看到 "handle_ai_task" 日志

# [16] 并发压测
# 装 hey: https://github.com/rakyll/hey
hey -n 500 -c 20 http://localhost:8080/api/home/feed?language=zh
# 预期：p99 < 2s，0% 失败

# [17] AI 端点限流
hey -n 100 -c 20 http://localhost:8080/api/chat
# 预期：部分请求返回 429（Nginx 限流生效）
```

**全部通过 → 本地 ok，可以准备上云。**

### 11.5 本地出问题怎么查

| 症状 | 检查 | 修法 |
|---|---|---|
| backend-web 启动就挂 | `docker compose logs backend-web` | 看 Python traceback，多半是 env 漏填或代码 bug |
| 502 Bad Gateway | backend-web 还没 healthy | `docker compose ps` 看 health；等 90 秒 |
| AI 调不通 | `docker compose logs backend-web | grep -i gemini` | Gemini 在国内被墙；本地需 VPN 或走代理 |
| Supabase 验签超时 | 本地 DNS 问题 | Docker Desktop 开启 "Use WSL 2 based engine" |
| 容器之间连不上 | `docker network inspect fdsm-knowledge_app-net` | 确认所有容器在同一 network |
| `database is locked` | WAL 没开 | §3.1 检查 `PRAGMA journal_mode` |

---

## 12. 云端部署（上线原子步骤）

**前提**：§11.4 本地验收全部通过，代码已 commit。

### 12.1 服务器初始化（只做一次，5 分钟）

```bash
# SSH 上服务器
ssh root@your.server.ip

# 1. 更新 + 安装 Docker
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 2. 装 docker compose v2（新版 Docker 自带，确认一下）
docker compose version

# 3. 创建非 root 用户
adduser fdsm
usermod -aG docker fdsm
su - fdsm

# 4. 创建工作目录
mkdir -p /srv/fdsm
sudo chown fdsm:fdsm /srv/fdsm
cd /srv/fdsm

# 5. 拷贝 SSH key 方便 Git clone
# 在本地：ssh-copy-id fdsm@server  （或者直接用 HTTPS + token）

# 6. 防火墙
sudo apt install -y ufw
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable

# 7. 系统调优
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
echo "net.core.somaxconn=65535" | sudo tee -a /etc/sysctl.conf
echo "fs.file-max=1000000" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 12.2 把代码和镜像推到服务器（两种方式二选一）

**方式 A · 通过镜像仓库（推荐）**

本地：
```powershell
# 登录阿里云容器镜像服务（免费；先在控制台建个个人实例）
docker login registry.cn-shanghai.aliyuncs.com
# 用户名：阿里云账号；密码：在控制台设置的 registry 密码

# 打 tag 并推
$TAG="v1.0"
$NS="fdsm"   # 你的命名空间
docker tag fdsm-knowledge-backend:local registry.cn-shanghai.aliyuncs.com/$NS/fdsm-backend:$TAG
docker tag fdsm-knowledge-frontend:local registry.cn-shanghai.aliyuncs.com/$NS/fdsm-frontend:$TAG
docker push registry.cn-shanghai.aliyuncs.com/$NS/fdsm-backend:$TAG
docker push registry.cn-shanghai.aliyuncs.com/$NS/fdsm-frontend:$TAG
```

服务器：
```bash
cd /srv/fdsm

# Clone 代码（只为了拿 docker-compose.yml 和 deploy/ 配置）
git clone https://github.com/你的账号/fdsmarticles.git app
cd app

# 删掉本地 override（生产不用）
rm -f docker-compose.override.yml

# 登录镜像仓库
docker login registry.cn-shanghai.aliyuncs.com

# 改 docker-compose.yml 里的 image 字段（或在 .env.production 里加 IMAGE_REGISTRY 变量）
# 最简单做法：改 .env.production
cat >> .env.production <<EOF
IMAGE_TAG=v1.0
EOF

# 改 docker-compose.yml（或用 sed）
sed -i 's|image: fdsm-knowledge-backend:|image: registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-backend:|g' docker-compose.yml
sed -i 's|image: fdsm-knowledge-frontend:|image: registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-frontend:|g' docker-compose.yml

# 拉镜像
docker compose pull backend-web frontend
```

**方式 B · 服务器上直接 build**（简单但慢）

```bash
cd /srv/fdsm
git clone https://github.com/你的账号/fdsmarticles.git app
cd app
rm -f docker-compose.override.yml
docker compose build
```

### 12.3 传数据（只第一次）

本地：
```powershell
# 打包数据
cd C:\Users\LXG\fdsmarticles
tar --zstd -cf fdsm-data.tar.zst data\

# 用 WSL 里的 rsync，或直接 scp
scp fdsm-data.tar.zst fdsm@server:/srv/fdsm/app/
```

服务器：
```bash
cd /srv/fdsm/app
tar --zstd -xf fdsm-data.tar.zst
ls data/    # 确认看到 fudan_knowledge_base.db 等
chmod -R 755 data/
rm fdsm-data.tar.zst
```

### 12.4 填生产 env

```bash
cd /srv/fdsm/app
nano .env.production
```

至少确认这些生产值：
- `APP_ENV=production`
- `SITE_BASE_URL=https://knowledge.fdsm.fudan.edu.cn`
- `ALLOWED_ORIGINS=https://knowledge.fdsm.fudan.edu.cn`
- `SUPABASE_URL` / `SUPABASE_ANON_KEY`（生产项目）
- `DEV_AUTH_ENABLED=0`
- `ADMIN_EMAILS`
- `GEMINI_API_KEYS`

```bash
chmod 600 .env.production
```

### 12.5 首次启动

```bash
cd /srv/fdsm/app

# 先用 http-only 模式启动（还没签 SSL 证书）
# 临时把 deploy/default.conf 的 443 server 块注释掉，或者直接让 docker 先不挂 SSL

# 启动
docker compose up -d

# 看状态
docker compose ps
docker compose logs -f backend-web
# 等到看到 "Uvicorn running on http://0.0.0.0:8000"，Ctrl+C
```

### 12.6 签 SSL 证书

```bash
# 前置：DNS A 记录已经指向这台机器
# 前置：安全组放行 80、443

# 跑 certbot（用独立容器）
sudo docker run --rm \
  -v /srv/fdsm/app/deploy/certbot/conf:/etc/letsencrypt \
  -v /srv/fdsm/app/deploy/certbot/www:/var/www/certbot \
  -p 80:80 \
  certbot/certbot certonly --standalone \
  -d knowledge.fdsm.fudan.edu.cn \
  --email admin@fdsm.fudan.edu.cn --agree-tos --no-eff-email

# 重启 frontend，它会挂载证书
docker compose restart frontend

# 测试
curl -I https://knowledge.fdsm.fudan.edu.cn
# 预期：HTTP/2 200，证书有效
```

### 12.7 上线冒烟测试

```bash
cd /srv/fdsm/app
bash deploy/smoke_test_auth.sh https://knowledge.fdsm.fudan.edu.cn
# 全部 ok
```

浏览器打开 `https://knowledge.fdsm.fudan.edu.cn`：
1. 首页能看
2. 注册一个账号（Supabase 发确认邮件）
3. 确认后登录
4. `/api/auth/status` 返回 `authenticated: true`
5. DB 里 `business_users` 有这条记录
6. 手动 UPDATE 成 admin（§9.3）
7. 进 /admin 后台，各页能访问

### 12.8 SSL 自动续签（每月一次）

```bash
sudo crontab -e
# 添加：
0 3 1 * * cd /srv/fdsm/app && docker run --rm -v /srv/fdsm/app/deploy/certbot/conf:/etc/letsencrypt -v /srv/fdsm/app/deploy/certbot/www:/var/www/certbot certbot/certbot renew && docker compose restart frontend
```

### 12.9 监控与告警

推荐接 **Uptime Robot**（免费）：
- 每 5 分钟检查 `https://knowledge.fdsm.fudan.edu.cn/api/health`
- 失败时邮件/微信告警

服务器装 `ctop` 随时看容器状态：
```bash
sudo wget -O /usr/local/bin/ctop https://github.com/bcicen/ctop/releases/download/v0.7.7/ctop-0.7.7-linux-amd64
sudo chmod +x /usr/local/bin/ctop
ctop
```

---

## 13. 日常运维

### 13.1 更新代码（小改动）

本地改完测好 → push → 服务器拉取 → 重启。

本地：
```powershell
cd C:\Users\LXG\fdsmarticles
# ...改代码...
docker compose build backend-web    # 本地先测
# ...本地验收通过...
docker tag fdsm-knowledge-backend:local registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-backend:v1.1
docker push registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-backend:v1.1
git commit -am "fix: xxx"
git push
```

服务器：
```bash
cd /srv/fdsm/app
git pull
sed -i 's|IMAGE_TAG=v1.0|IMAGE_TAG=v1.1|' .env.production
docker compose pull backend-web
docker compose up -d backend-web
# 零停机滚动更新
docker compose logs -f backend-web
```

### 13.2 回滚

```bash
sed -i 's|IMAGE_TAG=v1.1|IMAGE_TAG=v1.0|' .env.production
docker compose pull backend-web
docker compose up -d backend-web
```

### 13.3 查日志

```bash
docker compose logs -f --tail=200 backend-web
docker compose logs --since=1h backend-worker
docker compose logs frontend | grep -i error
```

### 13.4 进容器调试

```bash
docker compose exec backend-web bash
# 里面：python -c "from backend.database import connection_scope; ..."
```

### 13.5 手动触发批处理

```bash
docker compose exec backend-worker python -m backend.scripts.article_ai_batch --limit 50
docker compose exec backend-worker python -m backend.scripts.backfill_rag_corpus
```

### 13.6 备份恢复

```bash
cd /srv/fdsm/app
docker compose stop backend-web backend-worker
cp backups/daily/20260421_030000/fudan_knowledge_base.db data/
tar --zstd -xf backups/weekly/20260420_030000/faiss.tar.zst -C data/
docker compose start backend-web backend-worker
```

---

## 14. 常见坑位速查

| 症状 | 原因 | 修复 |
|---|---|---|
| Gemini 超时 | 国内网络不通 | 走境外节点或 HTTP_PROXY |
| `database is locked` | WAL 没开 / 长事务 | `PRAGMA journal_mode=wal;` |
| FAISS 加载慢 | 首次访问触发 | `start_period` 加到 90s |
| Nginx 502 | backend-web 还没 ready | 看 healthcheck 状态 |
| 上传 permission denied | volume owner 和容器 UID 不一致 | `chown -R 1000:1000 data/` |
| WAL 文件越来越大 | 没 checkpoint | 备份脚本里加 `PRAGMA wal_checkpoint(TRUNCATE);` |
| 内存 OOM | worker 数过多或泄漏 | 降到 2 worker / 加 `--max-requests` |
| Gemini 429 | key 限流 | 加 key、降 QPS |
| Supabase 验签慢 | 缓存没生效 | 看 §3.8 的 `_AUTH_CACHE` |
| debug header 还能用 | `APP_ENV` 没设 production | 检查 `docker compose config` |
| SSL 证书签发失败 | 80 端口被占 / DNS 没生效 | `dig A knowledge.xxx` 验证 |
| `sync_local_audio_library` 被多 worker 重复调 | 没加 worker_id 判断 | §3.2 lifespan 守卫 |

---

## 15. 未来规划（路线图）

| 阶段 | 触发条件 | 变更 |
|---|---|---|
| v1（当前） | - | 本文档方案 |
| v1.1 | 上线 1 周稳定 | 引入 OSS 存 uploads，CDN 静态资源 |
| v2 | 学院批准 CAS 接入 | 按 §9.5 迁 CAS |
| v2.1 | 日 AI 请求 > 1000 | 引入 Celery 替代 worker_loop |
| v3 | DB > 5GB 或写并发 > 50qps | SQLite 迁自建 Postgres（不是 Supabase 的） |
| v3.1 | 同上 | FAISS 换 Qdrant 独立服务 |

---

## 附录 A · 完整文件清单

上线时 Git 仓库里应该有的**新增/修改**文件（`git status` 校验）：

**新增**：
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `docker-compose.yml`
- `docker-compose.override.yml`（开发用，可选入 Git）
- `.dockerignore`
- `.env.example`
- `deploy/nginx.conf`
- `deploy/default.conf`
- `deploy/_proxy_base.conf`
- `deploy/worker_loop.py`
- `deploy/backup_loop.sh`
- `deploy/smoke_test_auth.sh`
- `requirements.lock.txt`
- `backend/services/ai_task_service.py`
- `backend/services/db_concurrency.py`

**修改**（§3 列举）：
- `backend/main.py`（lifespan、健康检查、中间件、CORS）
- `backend/database.py`（WAL、business_users 预留字段）
- `backend/config.py`（CORS 强制白名单）
- `backend/services/supabase_auth_service.py`（缓存、_ensure_local_user）
- `frontend/src/api/index.js`（API_BASE_URL）
- `frontend/src/auth/debugAuth.js`（生产守卫）

**不入 Git**：
- `.env.development`
- `.env.production`
- `data/**`
- `backups/**`

---

## 附录 B · 上线日前一天 checklist

24 小时前：
- [ ] 本地 §11.4 所有 17 项验收通过
- [ ] `requirements.lock.txt` 已提交
- [ ] 镜像已推到仓库 或 服务器能 build
- [ ] Supabase 生产项目已建好，邮件模板改中文
- [ ] DNS A 记录已切向生产服务器
- [ ] 安全组已开放 22/80/443

上线当天：
- [ ] 服务器数据已传
- [ ] `.env.production` 已填
- [ ] `docker compose up -d` 起来
- [ ] SSL 证书签发成功
- [ ] `deploy/smoke_test_auth.sh` 过
- [ ] 注册 admin 账号并升权
- [ ] 手动浏览 10 个主要页面，无错
- [ ] AI 对话能用
- [ ] 搜索能用
- [ ] 上传能用
- [ ] 监控告警已接
- [ ] 备份 cron 已验证（`docker compose logs backup`）

上线后 24 小时内：
- [ ] `docker stats` 看资源占用稳定
- [ ] 没有 OOM
- [ ] 没有 429 风暴
- [ ] 首日备份文件已生成

---

**文档到此为止。跑通 §11.4 的 17 项，就可以进入 §12 云端部署。**
