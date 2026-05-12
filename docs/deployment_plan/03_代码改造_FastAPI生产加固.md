# 03 · 代码改造：FastAPI 生产加固

> **前置依赖**：[02_代码改造_数据库WAL](./02_代码改造_数据库WAL.md) 完成
> **预计耗时**：2-3 小时
> **完成标志**：
> - `GET /api/health` 返回真实状态（DB + FAISS 都能探测）
> - `APP_ENV=production` 下 `X-Debug-User-Id` 请求头被中间件剥离
> - `ALLOWED_ORIGINS` 在生产环境为 `*` 或空时启动直接报错
> - lifespan 管理初始化，重复启动不报错（幂等）
> - 现有测试全通过

---

## 背景与目标

当前 `backend/main.py` 有四个生产不可接受的问题：

### 问题 1：初始化代码在模块顶层

```python
# main.py 第 36-40 行
ensure_database_ready()
ensure_runtime_tables()
EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
sync_local_audio_library()
```

gunicorn 启 4 个 worker，每个 worker 都是一个独立 Python 进程，会**并发跑 4 次**这些初始化。问题：
- `ensure_database_ready()` 里如果需要重建 DB（虽然不会触发，但代码路径存在），4 个 worker 抢着写
- `sync_local_audio_library()` 每个 worker 都扫一遍 audio 目录，纯浪费

### 问题 2：健康检查是假的

```python
# main.py 第 81-86 行
@app.get("/")
def health_check():
    return {"status": "ok", "service": APP_TITLE, "scope": "business-only"}
```

永远返回 ok，Docker/Nginx/Uptime Robot 无法探测 DB 是否真的可用。

### 问题 3：CORS 默认全开

```python
# config.py 第 69 行
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]

# main.py 第 47 行
allow_origins=ALLOWED_ORIGINS or ["*"],
```

两层 fallback 到 `["*"]`。生产环境 CORS 全开 = 任何网站都能调用我们的 API。

### 问题 4：debug header 旁路裸奔

`supabase_auth_service.py:30` 的 `_build_debug_user` 在 `PREVIEW_AUTH_ENABLED=True` 时读 `X-Debug-User-Id` header 伪造身份。`.env.production` 里设 `DEV_AUTH_ENABLED=0` 就能禁用吗？**不能**——因为 `PREVIEW_AUTH_ENABLED = DEV_AUTH_ENABLED or not SUPABASE_AUTH_ENABLED`，只要 Supabase 没配成功，这个开关就仍是 True。

**必须用环境变量 + 中间件双保险**彻底堵死。

---

## 改动清单

- [ ] 步骤 1：改 `backend/main.py` 用 `lifespan` 管理初始化
- [ ] 步骤 2：改 `backend/main.py` 新增 `/api/health` 真实健康检查
- [ ] 步骤 3：改 `backend/main.py` 新增 `StripDebugHeadersMiddleware`
- [ ] 步骤 4：改 `backend/main.py` CORS 配置去掉 `or ["*"]` fallback
- [ ] 步骤 5：改 `backend/config.py` 生产环境 CORS 白名单强制校验
- [ ] 步骤 6：改 `backend/services/supabase_auth_service.py::_build_debug_user` 加生产守卫
- [ ] 步骤 7：本地验证 development 模式一切正常
- [ ] 步骤 8：本地验证 production 模式 debug header 失效
- [ ] 步骤 9：跑 pytest
- [ ] 步骤 10：Commit

**涉及的文件**：3 个
- `backend/main.py`
- `backend/config.py`
- `backend/services/supabase_auth_service.py`

---

## 原子步骤

### 步骤 1 · 改 `backend/main.py` 用 lifespan

**找到** `backend/main.py` 第 36-40 行的这段：
```python
ensure_database_ready()
ensure_runtime_tables()
EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
sync_local_audio_library()
```

**整段删掉**（不要保留）。

**找到** `app = FastAPI(title=APP_TITLE)` 这一行（第 42 行）。

**在这一行之前插入 lifespan 定义**：
```python
import os
import logging
from contextlib import asynccontextmanager

_lifespan_logger = logging.getLogger("app.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 启动/关闭钩子。每个 gunicorn worker 进程独立执行一次。

    顺序：
      1. 确保 DB 存在并跑迁移（ensure_database_ready + ensure_runtime_tables）
      2. 确保上传目录存在
      3. 只在一个 worker 上做 audio 同步，避免 N 次重复扫盘
    """
    _lifespan_logger.info("lifespan startup begin (pid=%s)", os.getpid())
    try:
        ensure_database_ready()
        ensure_runtime_tables()
        EDITORIAL_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        MEDIA_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # audio 扫描只让 worker 0 或独立 worker 做
        is_sync_worker = (
            os.getenv("SERVICE_ROLE") == "worker"
            or os.getenv("GUNICORN_WORKER_ID", "0") == "0"
            or os.getenv("APP_SYNC_AUDIO", "0") == "1"
        )
        if is_sync_worker:
            try:
                sync_local_audio_library()
                _lifespan_logger.info("audio library synced")
            except Exception:
                _lifespan_logger.exception("sync_local_audio_library failed (non-fatal)")

    except Exception:
        _lifespan_logger.exception("lifespan startup failed")
        raise

    _lifespan_logger.info("lifespan startup complete")
    yield
    _lifespan_logger.info("lifespan shutdown (pid=%s)", os.getpid())
```

**把**：
```python
app = FastAPI(title=APP_TITLE)
```

**改成**：
```python
app = FastAPI(title=APP_TITLE, lifespan=lifespan)
```

**为什么这样做**：
- 顶层的 5 行初始化移到 `lifespan` 里，每个 worker 启动时执行一次（不是 import module 时）
- `sync_local_audio_library` 只让一个 worker 做（用 `GUNICORN_WORKER_ID` 或 `SERVICE_ROLE` 判断）
- 失败不影响启动（catch 住异常，只打日志），但 `ensure_database_ready` 如果失败必须抛出（DB 不可用时不能启动）

---

### 步骤 2 · 新增真实健康检查

**找到** 第 81-86 行：
```python
@app.get("/")
def health_check():
    return {
        "status": "ok",
        "service": APP_TITLE,
        "scope": "business-only",
    }
```

**替换成**：
```python
from backend.config import FAISS_DB_DIR


@app.get("/")
def root_hint():
    """根路径给人看的提示，不是健康检查端点。"""
    return {
        "status": "ok",
        "service": APP_TITLE,
        "message": "use /api/health for health probe",
        "docs_url": "/docs",
    }


@app.get("/api/health")
def api_health():
    """真实健康检查：DB 可连 + 关键目录存在。Docker healthcheck 用这个。"""
    from backend.database import connection_scope

    checks = {}
    try:
        with connection_scope() as conn:
            row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
            checks["database"] = {"ok": True, "article_count": row[0] if row else 0}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)}

    faiss_ok = FAISS_DB_DIR.exists()
    checks["faiss_index"] = {"ok": faiss_ok, "path": str(FAISS_DB_DIR)}

    upload_ok = EDITORIAL_UPLOADS_DIR.exists() and MEDIA_UPLOADS_DIR.exists()
    checks["uploads"] = {"ok": upload_ok}

    all_ok = all(v.get("ok", False) for v in checks.values())

    if not all_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=checks)

    return {"status": "ok", "service": APP_TITLE, "checks": checks}
```

**注意**：
- `FAISS_DB_DIR` 从 `config.py` import。确认 `config.py` 里确实有这个变量（已有）
- DB 探测用 `SELECT COUNT(*) FROM articles` 而不是 `SELECT 1`——前者能同时验证表存在、WAL 正常、数据有效
- 任何一项失败返回 503 HTTP 状态，Docker healthcheck 和 Nginx upstream 会自动剔除

---

### 步骤 3 · 新增 StripDebugHeadersMiddleware

**在 `app.add_middleware(CORSMiddleware, ...)` 之前插入**。

**找到**：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    ...
)
```

**在这段前面插入**：
```python
from starlette.middleware.base import BaseHTTPMiddleware


class StripDebugHeadersMiddleware(BaseHTTPMiddleware):
    """生产环境下，无条件剥离所有 X-Debug-* 请求头。

    防御深度：
      1. config.py 禁止 production + DEV_AUTH_ENABLED=1 同时出现
      2. supabase_auth_service._build_debug_user 看 APP_ENV 守卫
      3. 这个中间件在路由层之前统一剥离
      即使 config 改错、守卫漏掉，header 也在最外层被吃掉。"""

    def __init__(self, app, *, enabled: bool):
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request, call_next):
        if self._enabled:
            # ASGI scope 的 headers 是 [(bytes, bytes), ...]，是 list 可以直接替换
            request.scope["headers"] = [
                (k, v)
                for k, v in request.scope["headers"]
                if not k.lower().startswith(b"x-debug-")
            ]
        return await call_next(request)


_is_production = os.getenv("APP_ENV", "").lower() == "production"
app.add_middleware(StripDebugHeadersMiddleware, enabled=_is_production)
```

**中间件顺序**：Starlette 中间件**反向注册、正向执行**。也就是说代码里后 `add_middleware` 的先执行。所以 `StripDebugHeadersMiddleware` 要在 `CORSMiddleware` **之前** `add_middleware`——这样实际请求进来时 CORS 先跑（处理预检），strip 后跑（剥离 debug 头）。

**这个顺序等效于**：
```
Request → CORSMiddleware → StripDebugHeadersMiddleware → Router
Response ← CORSMiddleware ← StripDebugHeadersMiddleware ← Router
```

---

### 步骤 4 · CORS 去掉 `or ["*"]` fallback

**找到**：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**改成**：
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,                                      # 删掉 or ["*"]
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], # 白名单，不用 *
    allow_headers=["Content-Type", "Authorization", "X-Visitor-Id"],    # 白名单
    expose_headers=["Content-Disposition"],                             # 允许前端读取
    max_age=3600,                                                       # 预检缓存 1 小时
)
```

**关键改动**：
- `allow_origins` 直接用 `ALLOWED_ORIGINS`，为空时启动会报错（靠下一步的 config.py 校验）
- `allow_methods` 和 `allow_headers` 改成白名单——和 `allow_credentials=True` 搭配时，某些浏览器对 `*` 不认
- 新增 `expose_headers` 让前端能读 `Content-Disposition`（下载文件用）

---

### 步骤 5 · 在 `config.py` 强制生产环境 CORS 白名单

**打开 `backend/config.py`**。

**找到现在第 69 行附近**：
```python
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
```

**改成**：
```python
_raw_allowed_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = [origin.strip() for origin in _raw_allowed_origins.split(",") if origin.strip()]

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

if APP_ENV == "production":
    if not ALLOWED_ORIGINS or ALLOWED_ORIGINS == ["*"]:
        raise RuntimeError(
            "ALLOWED_ORIGINS must be an explicit domain whitelist in production. "
            "Set ALLOWED_ORIGINS=https://your-domain.com in .env.production"
        )
    if os.getenv("DEV_AUTH_ENABLED", "0").strip() == "1":
        raise RuntimeError(
            "DEV_AUTH_ENABLED must be 0 in production. "
            "Having it enabled would let anyone forge identity via X-Debug-User-Id headers."
        )
```

**关键点**：
- `APP_ENV` 从环境变量读（容器的 `.env.production` 里会设 `APP_ENV=production`）
- 生产环境下 `ALLOWED_ORIGINS` 不能为空或 `*`
- 生产环境下 `DEV_AUTH_ENABLED` 不能为 1
- 两个条件任一不满足，**进程直接退出**，不允许带着漏洞启动

**本地开发时**：`.env.development` 里 `APP_ENV=development`，所有校验都跳过。

---

### 步骤 6 · 改 `supabase_auth_service.py::_build_debug_user`

**打开 `backend/services/supabase_auth_service.py`**。

**找到现在第 30-40 行**：
```python
def _build_debug_user(debug_user_id: str | None, debug_user_email: str | None) -> dict | None:
    if not PREVIEW_AUTH_ENABLED or not debug_user_id:
        return None
    user_id = debug_user_id.strip()
    if not user_id:
        return None
    return {
        "id": user_id,
        "email": debug_user_email.strip() if debug_user_email else None,
        "raw_user": {"debug": True},
    }
```

**改成**：
```python
import os


def _build_debug_user(debug_user_id: str | None, debug_user_email: str | None) -> dict | None:
    # 第一道防线：生产环境无条件禁用
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        return None
    # 第二道防线：显式开关（PREVIEW_AUTH_ENABLED 会被 DEV_AUTH_ENABLED 或 Supabase 未启用点亮）
    if not PREVIEW_AUTH_ENABLED or not debug_user_id:
        return None
    user_id = debug_user_id.strip()
    if not user_id:
        return None
    return {
        "id": user_id,
        "email": debug_user_email.strip() if debug_user_email else None,
        "raw_user": {"debug": True},
    }
```

**文件顶部**确认有 `import os`（多半已有，因为 `supabase_auth_service.py` 在后续步骤还会改）。

**这层防线的必要性**：即使中间件没装、即使 `APP_ENV` 配错，这个函数本身也会拒绝构造 debug user。配合 §3 的中间件和 §5 的 config 校验，是三层防御。

---

### 步骤 7 · 本地验证 development 模式

**目标**：development 模式下一切照旧，debug header 能用。

**操作**：
```powershell
cd C:\Users\LXG\fdsmarticles
.\.venv\Scripts\Activate.ps1
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
$env:APP_ENV = "development"
$env:DEV_AUTH_ENABLED = "1"
$env:ALLOWED_ORIGINS = "http://localhost:5173"

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**另开一个 PowerShell 测试**：
```powershell
# 健康检查
curl http://127.0.0.1:8000/api/health
# 预期：JSON，status=ok，checks.database.ok=true，article_count > 0

# 根路径
curl http://127.0.0.1:8000/
# 预期：root_hint 的 JSON

# debug header 能用（development 下）
curl http://127.0.0.1:8000/api/auth/status -H "X-Debug-User-Id: mock-admin" -H "X-Debug-User-Email: admin@example.com"
# 预期：authenticated=true，user.id=mock-admin

# 无凭证
curl http://127.0.0.1:8000/api/auth/status
# 预期：authenticated=false
```

**Ctrl+C 停掉 uvicorn**。

---

### 步骤 8 · 本地验证 production 模式

**目标**：production 模式下 debug header 被剥离。

**操作**：
```powershell
# 切 production 模式
$env:APP_ENV = "production"
$env:DEV_AUTH_ENABLED = "0"
$env:ALLOWED_ORIGINS = "http://localhost:5173"

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**另开 PowerShell 测试**：
```powershell
# 健康检查还是好用
curl http://127.0.0.1:8000/api/health
# 预期：JSON，status=ok

# debug header 应该被剥离，返回 authenticated=false
curl http://127.0.0.1:8000/api/auth/status -H "X-Debug-User-Id: mock-admin"
# 预期：authenticated=false （关键！如果 true 说明旁路没堵住）
```

**如果 production 模式下 debug header 还能登录**：
- 检查 `APP_ENV` 真的设成 production 了吗（`$env:APP_ENV` 或 `os.environ`）
- 检查中间件是否真的注册了（加日志）
- 检查 `_build_debug_user` 的守卫有没有生效

**Ctrl+C 停掉**。

---

### 步骤 9 · 再测 CORS 和 DEV_AUTH 强制校验

**测试 A**：production + ALLOWED_ORIGINS 空 → 启动失败

```powershell
$env:APP_ENV = "production"
$env:DEV_AUTH_ENABLED = "0"
Remove-Item env:ALLOWED_ORIGINS -ErrorAction SilentlyContinue

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 预期：
# RuntimeError: ALLOWED_ORIGINS must be an explicit domain whitelist in production
# 进程退出
```

**测试 B**：production + DEV_AUTH_ENABLED=1 → 启动失败

```powershell
$env:APP_ENV = "production"
$env:DEV_AUTH_ENABLED = "1"
$env:ALLOWED_ORIGINS = "https://example.com"

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 预期：
# RuntimeError: DEV_AUTH_ENABLED must be 0 in production
# 进程退出
```

**测试 C**：development 不做校验

```powershell
$env:APP_ENV = "development"
$env:DEV_AUTH_ENABLED = "1"
Remove-Item env:ALLOWED_ORIGINS -ErrorAction SilentlyContinue

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 预期：正常启动
```

**都测完后 Ctrl+C，清环境变量**：
```powershell
Remove-Item env:APP_ENV -ErrorAction SilentlyContinue
Remove-Item env:DEV_AUTH_ENABLED -ErrorAction SilentlyContinue
Remove-Item env:ALLOWED_ORIGINS -ErrorAction SilentlyContinue
```

---

### 步骤 10 · 跑 pytest

```powershell
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
python -m pytest backend/tests/ -x -v
```

**预期**：所有测试通过。

**可能的 regression**：
- 某些测试可能直接调 `app = FastAPI(...)` 而不是我们的 app，不受 lifespan 影响
- 某些测试可能用 `X-Debug-User-Id` 模拟用户登录；检查测试有没有设 `APP_ENV=production`（如果有，这是测试本身的问题，development 模式下不剥离）

**如果测试里没法控制 APP_ENV**：在 `conftest.py` 里加 fixture：
```python
import os, pytest

@pytest.fixture(autouse=True)
def _reset_app_env():
    old = os.environ.pop("APP_ENV", None)
    os.environ["APP_ENV"] = "development"
    yield
    if old is None:
        os.environ.pop("APP_ENV", None)
    else:
        os.environ["APP_ENV"] = old
```

---

### 步骤 11 · Commit

```powershell
git status
# 应显示：
# modified:   backend/main.py
# modified:   backend/config.py
# modified:   backend/services/supabase_auth_service.py

git add backend/main.py backend/config.py backend/services/supabase_auth_service.py
git commit -m "deploy(step-03): harden FastAPI for production

- main.py: lifespan-based startup (idempotent per worker)
- main.py: real /api/health probing DB and FAISS directory
- main.py: StripDebugHeadersMiddleware active when APP_ENV=production
- main.py: CORS whitelist methods and headers, remove '*' fallback
- config.py: refuse to start in production without ALLOWED_ORIGINS whitelist
- config.py: refuse to start in production with DEV_AUTH_ENABLED=1
- supabase_auth_service.py: _build_debug_user denies production env"
```

---

## 阶段验收

### 验收 1 · 健康检查真实

```powershell
# 启动（development 模式）
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
$env:APP_ENV = "development"
$env:ALLOWED_ORIGINS = "http://localhost:5173"
Start-Process python -ArgumentList "-m","uvicorn","backend.main:app","--port","8000"
Start-Sleep -Seconds 5

# 健康检查
curl http://127.0.0.1:8000/api/health
```

**预期 JSON**（格式化后）：
```json
{
  "status": "ok",
  "service": "复旦管院商业智识库 API",
  "checks": {
    "database": { "ok": true, "article_count": 2110 },
    "faiss_index": { "ok": true, "path": "..." },
    "uploads": { "ok": true }
  }
}
```

**手动模拟故障**：
```powershell
# 暂时把 faiss 目录改名
Rename-Item data\faiss_index_business data\faiss_index_business_renamed

curl http://127.0.0.1:8000/api/health -i
# 预期：HTTP 503，detail 里 faiss_index.ok=false

# 改回来
Rename-Item data\faiss_index_business_renamed data\faiss_index_business
```

### 验收 2 · 生产模式 debug 旁路完全堵死

```powershell
# 停掉 development 进程
Get-Process python -ErrorAction SilentlyContinue | Stop-Process

# 切 production
$env:APP_ENV = "production"
$env:DEV_AUTH_ENABLED = "0"
$env:ALLOWED_ORIGINS = "http://localhost:5173"

Start-Process python -ArgumentList "-m","uvicorn","backend.main:app","--port","8000"
Start-Sleep -Seconds 5

# 攻击测试
curl http://127.0.0.1:8000/api/auth/status -H "X-Debug-User-Id: attacker" -H "X-Debug-User-Email: a@b.c" -i
```

**预期**：
- HTTP 200
- 响应 JSON 里 `authenticated: false`，`user: null`

**如果看到 `authenticated: true`**：立即回到 §8/§6 检查改动是否完整。

### 验收 3 · lifespan 只做必要事

启动日志里应该看到：
```
lifespan startup begin (pid=12345)
lifespan startup complete
```

用 gunicorn 多 worker 启动：
```powershell
# 先装 gunicorn（如果还没装）
pip install gunicorn

python -m gunicorn backend.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
```

每个 worker 应该各打一行 `lifespan startup begin`（4 次），但 `audio library synced` 只有 1 次（因为只有 worker 0 做）。

### 验收 4 · CORS 真实生效

```powershell
# 生产模式，ALLOWED_ORIGINS 只允许一个域
$env:APP_ENV = "production"
$env:DEV_AUTH_ENABLED = "0"
$env:ALLOWED_ORIGINS = "https://knowledge.fdsm.fudan.edu.cn"

Start-Process python -ArgumentList "-m","uvicorn","backend.main:app","--port","8000"
Start-Sleep -Seconds 5

# 白名单里的 origin
curl http://127.0.0.1:8000/api/home/feed -H "Origin: https://knowledge.fdsm.fudan.edu.cn" -i
# 响应头应含：Access-Control-Allow-Origin: https://knowledge.fdsm.fudan.edu.cn

# 不在白名单的 origin
curl http://127.0.0.1:8000/api/home/feed -H "Origin: https://evil.com" -i
# 响应头**不**包含 Access-Control-Allow-Origin（浏览器会拒绝跨域）
```

### 验收 5 · 配置校验拒绝错误启动

已经在步骤 9 跑过（测试 A、B、C），确认：
- production + 无 ALLOWED_ORIGINS → 启动失败
- production + DEV_AUTH_ENABLED=1 → 启动失败
- development → 不做校验

---

## 常见错误与排查

| 症状 | 原因 | 修复 |
|---|---|---|
| `TypeError: lifespan() missing arg` | FastAPI 版本 < 0.93 | 升级 `pip install -U fastapi` |
| 启动后 `/api/health` 404 | router 顺序问题 | 健康检查要在 `app.include_router` 之前定义 |
| `database.ok: false` | WAL 还没生效 / DB 路径错 | §2 的验证再跑一遍 |
| `faiss_index.ok: false` | 路径不对 | 检查 `FDSM_DATA_DIR` 是否含 `faiss_index_business/` |
| CORS 预检 OPTIONS 返回 400 | `allow_methods` 没含 OPTIONS | 检查已含 `"OPTIONS"` |
| 生产模式下 API 完全访问不了 | 中间件顺序反了 | 确认 `StripDebugHeadersMiddleware` 在 `CORSMiddleware` **之前** 注册 |
| 多 worker 下 audio 同步跑了 4 次 | 所有 worker 都满足条件 | 检查 `GUNICORN_WORKER_ID` 是否存在（gunicorn 22+ 自动设） |
| pytest 大量失败 | testclient 不触发 lifespan | 用 `from fastapi.testclient import TestClient` 并在 `with TestClient(app):` 上下文里跑 |

---

## 关于 GUNICORN_WORKER_ID 的说明

gunicorn 22.0+ 会自动给每个 worker 设一个 `GUNICORN_WORKER_ID=0/1/2/3` 环境变量。我们用它判断哪个 worker 做 audio 同步。

如果发现日志里 worker 1/2/3 也在同步，说明 gunicorn 没设这个变量。两种修法：

**方式 A**：用 gunicorn 的 `post_fork` 钩子（写到 `deploy/gunicorn_config.py`）：
```python
def post_fork(server, worker):
    import os
    os.environ["GUNICORN_WORKER_ID"] = str(worker.age)
```

**方式 B**：在 docker-compose 里给 backend-worker 显式设 `SERVICE_ROLE=worker`，web 容器不设——lifespan 里会优先看 SERVICE_ROLE。

本项目用方式 B 即可（见 §08 Docker 配置）。

---

## 下一步

**去 [04_代码改造_鉴权加缓存与本地用户绑定.md](./04_代码改造_鉴权加缓存与本地用户绑定.md)** 继续。

这一步做完后你已经：
- ✅ DB 层 WAL + 性能调优
- ✅ 启动流程生产级（lifespan + 幂等）
- ✅ 健康检查真实
- ✅ 生产环境 CORS 和 debug 旁路强制关闭

接下来要做鉴权缓存（每次 API 不再 100-300ms 去 Supabase）和本地用户绑定（为 CAS 迁移打地基）。
