# 12 · 日常运维与迁 CAS 预案

> **当前状态提示（2026-04-21）**：本文是早期运维和 CAS 迁移预案。当前 CAS 后端、前端回调、本地 session、管理员白名单和生产安全开关已落地；生产部署默认可以按 `.env.production.example` 开启 CAS。本文中基于 `IMAGE_TAG`、镜像仓库 `docker compose pull`、未来再迁 CAS 的步骤属于历史方案。当前运维和上线执行以 [16_私有云发布包_Nginx_HTTPS上线验收.md](./16_私有云发布包_Nginx_HTTPS上线验收.md)、[17_最终压测性能预算与交付清单.md](./17_最终压测性能预算与交付清单.md)、[18_部署文档对齐复查.md](./18_部署文档对齐复查.md) 为准。

> **前置依赖**：[11_云端部署](./11_云端部署原子步骤.md) 完成，服务已稳定运行
> **阅读时间**：1 小时
> **后续动作**：CAS 迁移时按本文档执行，预估 1.5-2 人日

---

## 本文档结构

1. **日常运维手册**：更新、回滚、日志、备份恢复、常见故障
2. **CAS 迁移完整方案**：代码 diff + 数据绑定 + 切换开关
3. **扩容路线**：什么时候换 Postgres、什么时候拆 FAISS 服务

---

## 第一部分 · 日常运维

### 1.1 代码更新流程

**本地改代码 → 测通 → 推镜像 → 服务器拉 → 重启**。

#### 小改动（Hot Fix）

```powershell
# 本地
cd C:\Users\LXG\fdsmarticles
git checkout deployment/docker-prod
# ...改代码...

# 本地验证（至少跑 §10 的关键几项：1、3、15、16）
docker compose build backend-web
docker compose up -d backend-web
# 手动测一下改了的功能

# 打新 tag
$NEW_TAG = "v1.0.1"
docker tag fdsm-knowledge-backend:local registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-backend:$NEW_TAG
docker push registry.cn-shanghai.aliyuncs.com/fdsm/fdsm-backend:$NEW_TAG

# commit + push
git add .
git commit -m "fix: <描述>"
git push origin deployment/docker-prod
```

```bash
# 服务器
cd /srv/fdsm/app
git pull

# 改 .env.production 的 IMAGE_TAG
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.0.1/' .env.production

# 拉新镜像
docker compose pull backend-web

# 滚动更新（backend-web 健康检查通过后老容器才停）
docker compose up -d backend-web

# 验证
sleep 30
curl https://knowledge.fdsm.fudan.edu.cn/api/health
docker compose logs backend-web --tail=30
```

**滚动更新怎么做到零停机**：
- docker-compose up -d 会先起新容器
- 新容器 healthcheck 通过后（90 秒）才停老的
- Nginx 连接池自动迁移

**如果改了 frontend**：
```bash
# 前端构建依赖 .env.production 里的 SUPABASE_URL（构建时内联）
# 所以前端改动必须重新 build
# 服务器上一般不 build（除非代码都推上去了）
# 最好还是本地 build + push，同 backend 流程
```

#### 大改动（涉及 DB schema / 依赖版本 / 架构变更）

**额外步骤**：

1. **测试环境先验证**：克隆一台小服务器跑新版本，拿一份 DB 备份的副本过一遍
2. **发布前公告**：用户群 / 邮件提前说"预计 X 点维护 30 分钟"
3. **手动先 stop backend-worker**（避免发布过程中 worker 跑到一半版本不匹配）
   ```bash
   docker compose stop backend-worker
   ```
4. **backend-web 更新**（同小改动）
5. **跑一次数据库迁移**（如果有新表/新列）
   ```bash
   docker compose exec backend-web python -c "from backend.database import ensure_runtime_tables; ensure_runtime_tables()"
   ```
6. **起 worker**
   ```bash
   docker compose up -d backend-worker
   ```

### 1.2 回滚

**版本级回滚**（镜像可用）：
```bash
# 服务器
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=v1.0.0/' .env.production   # 回到上一个 tag
docker compose pull backend-web
docker compose up -d backend-web
```

**代码级回滚**（紧急 bug，镜像已发布但不可接受）：
```bash
cd /srv/fdsm/app
git log --oneline -10                  # 看 commit
git checkout <old-commit-hash>         # 临时回到上一个稳定点
# 本地重新 build + push
# 或者直接用更老的 IMAGE_TAG
```

**数据库回滚**（schema 变更后发现严重问题）：
```bash
# 停服务
docker compose stop backend-web backend-worker

# 恢复 DB（用最近一个备份）
LATEST_BACKUP=$(ls -dt /srv/fdsm/app/backups/daily/* | head -1)
cp "$LATEST_BACKUP/fudan_knowledge_base.db" /srv/fdsm/app/data/

# 删 WAL 文件（备份里没有）
rm -f /srv/fdsm/app/data/fudan_knowledge_base.db-wal
rm -f /srv/fdsm/app/data/fudan_knowledge_base.db-shm

# 回退代码
git checkout <stable-tag>

# 起服务
docker compose up -d backend-web backend-worker
```

⚠️ **数据回滚会丢失备份之后的用户数据**。慎用。首选版本回滚。

### 1.3 日志

#### 实时查看

```bash
# 所有服务
docker compose logs -f

# 单个服务
docker compose logs -f backend-web

# 只看 error
docker compose logs -f backend-web | grep -iE "error|exception|traceback|5[0-9]{2}"

# 最近 1 小时
docker compose logs --since 1h backend-web

# 过滤 Nginx 访问日志（看用户行为）
docker compose logs frontend | grep -v "nginx-health"
```

#### 日志落盘

Docker json-file driver 默认把日志写在 `/var/lib/docker/containers/<id>/<id>-json.log`。`docker-compose.yml` 配了 `max-size: 50m` + `max-file: 5`，所以每个容器最多占 250MB。

**查日志盘占用**：
```bash
du -sh /var/lib/docker/containers/*/
```

#### 持久化到外部日志系统（可选）

**推荐**：Loki + Grafana（轻量）或 ELK（功能全）。

最简方案：把日志 tail 到一个文件，然后 rsync 到 S3：
```bash
docker compose logs --no-log-prefix -f backend-web >> /var/log/fdsm/backend-web.log &
# 配 logrotate
```

### 1.4 进容器调试

```bash
# 进 backend-web 容器
docker compose exec backend-web bash
# 在容器里：
python
>>> from backend.database import connection_scope
>>> with connection_scope() as c:
>>>     print(c.execute("SELECT COUNT(*) FROM articles").fetchone())

# 跑临时 Python 命令
docker compose exec backend-web python -c "from backend.services.catalog_service import *; print(fetch_article(1))"

# 进 redis
docker compose exec redis redis-cli
> KEYS *
> HGETALL pending:article_view_count

# 看 WAL 大小
docker compose exec backend-web sqlite3 /data/fudan_knowledge_base.db "PRAGMA wal_checkpoint(TRUNCATE)"
```

### 1.5 手动触发批处理脚本

```bash
# 在 backend-worker 容器里跑
docker compose exec backend-worker python -m backend.scripts.article_ai_batch --limit 50
docker compose exec backend-worker python -m backend.scripts.backfill_rag_corpus
docker compose exec backend-worker python -m backend.scripts.process_pending_ingestion_jobs
```

### 1.6 备份管理

#### 查备份

```bash
ls -lh /srv/fdsm/app/backups/daily/
# 每天一个目录：20260421_030000、20260422_030000、...

# 每个目录里：
ls -lh /srv/fdsm/app/backups/daily/20260421_030000/
# fudan_knowledge_base.db   ~700 MB

# 每周目录还有 FAISS + uploads 快照：
ls -lh /srv/fdsm/app/backups/weekly/*/
```

#### 从备份恢复

```bash
cd /srv/fdsm/app
docker compose stop backend-web backend-worker

# 恢复 SQLite
BACKUP_DIR=/srv/fdsm/app/backups/daily/20260421_030000
cp "$BACKUP_DIR/fudan_knowledge_base.db" data/
# 重要：清 WAL 残留
rm -f data/fudan_knowledge_base.db-wal data/fudan_knowledge_base.db-shm

# 恢复 FAISS（如果也要回退）
tar --zstd -xf /srv/fdsm/app/backups/weekly/20260420_030000/faiss.tar.zst -C data/ --overwrite

# 恢复 uploads
tar --zstd -xf /srv/fdsm/app/backups/weekly/20260420_030000/uploads.tar.zst -C data/ --overwrite

# 起服务
docker compose up -d
```

#### 异地备份

当前备份只在本机。推荐每周同步一次到阿里云 OSS：

**用 ossutil**：
```bash
# 装 ossutil
wget https://gosspublic.alicdn.com/ossutil/1.7.17/ossutil64
chmod +x ossutil64
sudo mv ossutil64 /usr/local/bin/ossutil

# 配
ossutil config -e oss-cn-shanghai.aliyuncs.com -i <AccessKeyId> -k <AccessKeySecret>

# 测试
ossutil ls oss://your-bucket/

# 加到 cron
sudo crontab -e
# 每周一凌晨 4 点
0 4 * * 1 ossutil cp -r /srv/fdsm/app/backups/weekly/ oss://your-bucket/fdsm-backup/weekly/ --update
```

OSS 归档存储：¥0.033/GB/月（极低）。

### 1.7 常见故障速查

| 症状 | 优先级 | 排查命令 | 处理 |
|---|---|---|---|
| 网站打不开 | P0 | `curl -I https://domain/` | 看 Nginx 日志；看服务器是否活 |
| API 全 502 | P0 | `docker compose ps` | backend-web 挂了，重启 |
| API 全 503 | P0 | `docker compose logs backend-web \| grep -i busy` | 可能 SQLite 严重死锁；重启；长期看扩容 |
| 搜索失败 | P1 | `curl /api/health \| jq` | FAISS 加载失败；检查目录 |
| AI 任务不跑 | P1 | `docker compose logs backend-worker` | worker 挂了或 Gemini 不通 |
| 上传 413 | P2 | Nginx 日志 | 改 `client_max_body_size` |
| 证书过期 | P1 | `curl -vI https://...` | 续签 cron 没跑；手动 `certbot renew` |
| 磁盘满 | P0 | `df -h` | 清老备份；`docker system prune` |
| WAL 过大 | P2 | `ls -lh data/*.db-wal` | `PRAGMA wal_checkpoint(TRUNCATE)` |
| Gemini 全 429 | P1 | 后端日志 | 加 key |
| 被攻击 | P1 | Nginx 访问日志异常流量 | 看 IP 限流是否生效；考虑接 WAF |

### 1.8 资源监控

**内置命令**：
```bash
# 看资源（每 5 秒刷新）
watch -n 5 docker stats --no-stream

# 看磁盘
df -h
du -sh /srv/fdsm/app/data/
du -sh /srv/fdsm/app/backups/
du -sh /var/lib/docker/

# 看网络
iftop
```

**装 ctop**（Docker 版 top）：
```bash
sudo wget -O /usr/local/bin/ctop https://github.com/bcicen/ctop/releases/download/v0.7.7/ctop-0.7.7-linux-amd64
sudo chmod +x /usr/local/bin/ctop
ctop
```

**Prometheus + Grafana**（下一阶段）：
- 装 node_exporter 导系统指标
- 装 cadvisor 导容器指标
- Grafana 画板
- 大概 2 小时搞定

### 1.9 性能调优 Checklist

运行一段时间后看监控，按需要调：

- [ ] gunicorn `-w 4` 是否是最佳？可以观察 CPU 利用率：长期 > 80% 就加 worker，< 30% 就减
- [ ] `DB_WRITE_CONCURRENCY=4` 合适吗？偶见 503（信号量等待超时）说明写量偏大
- [ ] Redis 内存有没有逼近 1GB？近了就提到 2GB 或者清老 key
- [ ] WAL 文件稳定吗？超过 500MB 就手动 checkpoint 一次
- [ ] Nginx 限流 rate 合适吗？看 error log 里 `limiting requests` 出现频率

---

## 第二部分 · 迁 CAS 完整预案

### 2.1 触发条件

复旦学院 IT 批准接入 CAS 后，给你：
- `CAS_URL`（如 `https://id.fudan.edu.cn/cas`）
- 服务白名单（你的 `CAS_SERVICE_URL` 必须在学院那边登记）

### 2.2 改动清单

**后端**：
- 新增 `backend/services/cas_auth_service.py`
- 新增 `backend/routers/cas_auth.py`
- 改 `backend/main.py` 挂新 router
- 改 `backend/routers/auth.py` 支持 `AUTH_BACKEND` 开关

**前端**：
- 新增 `frontend/src/pages/CasCallbackPage.jsx`
- 改 `frontend/src/App.jsx` 加路由
- 改 `frontend/src/auth/AuthProvider.jsx` 支持 CAS token
- 改 `frontend/src/api/index.js` 取 token 时考虑 CAS

**数据库**：
- 无 schema 变更（§04 已预留 `cas_employee_number`、`cas_username` 字段）

**配置**：
- `.env.production` 加 CAS 相关变量
- `AUTH_BACKEND` 从 `supabase` → `cas`（或 `dual` 过渡）

### 2.3 后端代码完整实现

#### 2.3.1 `backend/services/cas_auth_service.py`

```python
"""
复旦 CAS 统一身份认证服务。

CAS Protocol 2.0 流程（参考 docs/CAS接入文档.doc）：
  1. 用户点登录 → 重定向到 CAS_URL/login?service=SERVICE_URL
  2. 用户在 CAS 登录成功 → CAS 重定向回 SERVICE_URL?ticket=<ticket>
  3. 后端收到 ticket → 调 CAS_URL/serviceValidate?ticket=<ticket>&service=SERVICE_URL
  4. CAS 返回 XML，包含 user / employeeNumber / displayName
  5. 后端签发本地 session token，前端存 localStorage，以后带着走

业务代码拿到的 user 对象结构和 supabase_auth_service 完全一致：
    {"id": business_users.user_id, "email": ..., "raw_user": 原始 CAS attributes}
"""
from __future__ import annotations

import logging
import os
import secrets
import time
import xml.etree.ElementTree as ET
from threading import Lock
from urllib.parse import quote, urlencode

import requests

log = logging.getLogger("cas_auth")

CAS_URL = os.getenv("CAS_URL", "").rstrip("/")
CAS_SERVICE_URL = os.getenv("CAS_SERVICE_URL", "")
CAS_TIMEOUT = float(os.getenv("CAS_TIMEOUT_SECONDS", "8"))

_NS = {"cas": "http://www.yale.edu/tp/cas"}


# ========================================================================
# CAS 协议操作
# ========================================================================

def is_cas_enabled() -> bool:
    return bool(CAS_URL and CAS_SERVICE_URL)


def build_login_url(service_url: str | None = None) -> str:
    service = service_url or CAS_SERVICE_URL
    return f"{CAS_URL}/login?service={quote(service, safe='')}"


def build_logout_url(service_url: str | None = None) -> str:
    service = service_url or CAS_SERVICE_URL
    return f"{CAS_URL}/logout?service={quote(service, safe='')}"


def validate_ticket(ticket: str, service_url: str | None = None) -> dict | None:
    """用 CAS serviceValidate 校验 ticket。
    返回 {username, employee_number, display_name, attributes} 或 None。"""
    service = service_url or CAS_SERVICE_URL
    params = urlencode({"service": service, "ticket": ticket})
    url = f"{CAS_URL}/serviceValidate?{params}"

    try:
        resp = requests.get(url, timeout=CAS_TIMEOUT)
    except requests.RequestException as exc:
        log.error("CAS validate request failed: %s", exc)
        return None

    if resp.status_code != 200:
        log.error("CAS returned %s for ticket %s...", resp.status_code, ticket[:20])
        return None

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        log.error("CAS response XML parse error: %s", exc)
        return None

    success = root.find("cas:authenticationSuccess", _NS)
    if success is None:
        log.info("CAS ticket rejected")
        return None

    user_el = success.find("cas:user", _NS)
    attrs_el = success.find("cas:attributes", _NS)

    attributes = {}
    if attrs_el is not None:
        for child in attrs_el:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            attributes[tag] = (child.text or "").strip()

    return {
        "username": (user_el.text if user_el is not None else "").strip(),
        "employee_number": attributes.get("employeeNumber", ""),
        "display_name": attributes.get("displayName") or attributes.get("name") or "",
        "attributes": attributes,
    }


# ========================================================================
# 本地 session 管理
# ========================================================================
# CAS 本身不签发长效 token，我们签发自己的 session token 存给前端。
# token 是 URL-safe 随机串，存在 Redis（有 TTL）。

import json

_SESSION_TTL = int(os.getenv("CAS_SESSION_TTL_SECONDS", str(8 * 3600)))   # 默认 8 小时


def _get_redis():
    # 和 ai_task_service 共享 Redis 实例
    from backend.services.ai_task_service import get_redis
    return get_redis()


def issue_session(cas_user: dict) -> str:
    """CAS 校验成功后调用。返回 session token。"""
    local_user = _ensure_local_user_from_cas(cas_user)
    token = secrets.token_urlsafe(48)
    payload = {
        "user": local_user,
        "issued_at": time.time(),
    }
    _get_redis().setex(f"cas_session:{token}", _SESSION_TTL, json.dumps(payload))
    log.info("issued CAS session for user %s (employee_number=%s)",
             local_user["id"], cas_user.get("employee_number"))
    return token


def revoke_session(token: str) -> None:
    _get_redis().delete(f"cas_session:{token}")


def get_user_by_session(token: str) -> dict | None:
    raw = _get_redis().get(f"cas_session:{token}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data.get("user")


# ========================================================================
# 和业务代码对接的函数 —— 签名对齐 supabase_auth_service
# ========================================================================

def get_authenticated_user(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict | None:
    """业务代码调用。接口签名和 supabase_auth_service.get_authenticated_user 一致。
    实际不做 Supabase 校验，而是从 Redis 查本地 session。"""
    # 生产无条件禁 debug 旁路
    if os.getenv("APP_ENV", "").lower() == "production":
        debug_user_id = None

    if not authorization:
        if debug_user_id:
            return {
                "id": debug_user_id,
                "email": debug_user_email,
                "raw_user": {"debug": True},
            }
        return None

    text = authorization.strip()
    if not text.lower().startswith("bearer "):
        return None
    token = text[7:].strip()

    return get_user_by_session(token)


def get_auth_status_payload(
    authorization: str | None,
    *,
    debug_user_id: str | None = None,
    debug_user_email: str | None = None,
) -> dict:
    """替代 supabase 版的 status 接口实现。返回结构和 supabase 版完全一致。"""
    from backend.services.membership_service import get_membership_profile
    from backend.services.user_profile_service import get_business_profile, role_home_path_for_tier

    user = get_authenticated_user(authorization, debug_user_id=debug_user_id, debug_user_email=debug_user_email)
    membership = get_membership_profile(user)
    business_profile = get_business_profile(user, membership)

    return {
        "enabled": is_cas_enabled(),
        "authenticated": bool(user),
        "user": {"id": user["id"], "email": user.get("email")} if user else None,
        "auth_mode": "cas",
        "membership": membership,
        "business_profile": business_profile,
        "role_home_path": business_profile.get("role_home_path")
            or role_home_path_for_tier((membership or {}).get("tier")),
    }


# ========================================================================
# 本地 business_users 建档
# ========================================================================

def _ensure_local_user_from_cas(cas_user: dict) -> dict:
    """按 employee_number 找/建 business_users 记录。"""
    from backend.database import connection_scope
    from datetime import datetime

    employee_number = cas_user.get("employee_number", "")
    if not employee_number:
        raise ValueError("CAS user missing employee_number")

    username = cas_user.get("username", "")
    display_name = cas_user.get("display_name") or username or employee_number
    now_iso = datetime.now().replace(microsecond=0).isoformat()

    # 根据学校惯例构造邮箱（如 12345@fudan.edu.cn）
    # 如果 CAS attributes 里带 email 字段更好，按实际文档调整
    attrs = cas_user.get("attributes") or {}
    email = attrs.get("email") or f"{employee_number}@fudan.edu.cn"

    with connection_scope() as conn:
        # 路径 A：已绑定
        row = conn.execute(
            "SELECT user_id, email FROM business_users WHERE cas_employee_number = ?",
            (employee_number,),
        ).fetchone()
        if row:
            # 更新 last_seen
            conn.execute(
                "UPDATE business_users SET last_seen_at = ?, updated_at = ? WHERE user_id = ?",
                (now_iso, now_iso, row["user_id"]),
            )
            conn.commit()
            return {"id": row["user_id"], "email": row["email"] or email, "raw_user": cas_user}

        # 路径 B：同邮箱的 Supabase 账号（过渡期绑定）
        row = conn.execute(
            "SELECT user_id FROM business_users WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE business_users SET cas_employee_number = ?, cas_username = ?, "
                "auth_source = CASE WHEN supabase_user_id IS NOT NULL THEN 'dual' ELSE 'cas' END, "
                "last_seen_at = ?, updated_at = ? WHERE user_id = ?",
                (employee_number, username, now_iso, now_iso, row["user_id"]),
            )
            conn.commit()
            return {"id": row["user_id"], "email": email, "raw_user": cas_user}

        # 路径 C：全新用户
        local_id = f"cas_{employee_number}"
        conn.execute(
            """
            INSERT INTO business_users(
                user_id, email, display_name, tier, status, role_home_path,
                auth_source, locale, is_seed,
                cas_employee_number, cas_username,
                created_at, updated_at, last_seen_at
            ) VALUES (?, ?, ?, 'free_member', 'active', '/me', 'cas', 'zh-CN', 0, ?, ?, ?, ?, ?)
            """,
            (local_id, email, display_name, employee_number, username, now_iso, now_iso, now_iso),
        )
        conn.commit()
        return {"id": local_id, "email": email, "raw_user": cas_user}
```

#### 2.3.2 `backend/routers/cas_auth.py`

```python
"""CAS 登录/回调/登出路由。挂到 /api/auth/cas。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse

from backend.config import SITE_BASE_URL
from backend.services.cas_auth_service import (
    build_login_url,
    build_logout_url,
    issue_session,
    revoke_session,
    validate_ticket,
)

router = APIRouter(prefix="/api/auth/cas", tags=["auth-cas"])


@router.get("/login")
def cas_login():
    """重定向用户到 CAS 登录页。"""
    return RedirectResponse(url=build_login_url(), status_code=302)


@router.get("/callback")
def cas_callback(ticket: str = Query(...)):
    """CAS 登录成功后回调。验证 ticket 并签发本地 session。"""
    cas_user = validate_ticket(ticket)
    if not cas_user:
        raise HTTPException(status_code=401, detail="CAS ticket validation failed")

    try:
        session_token = issue_session(cas_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 回跳前端，token 放 URL fragment（# 后，不会发到服务端日志）
    frontend_url = f"{SITE_BASE_URL}/login/cas-callback#token={session_token}"
    return RedirectResponse(url=frontend_url, status_code=302)


@router.post("/logout")
def cas_logout(authorization: str | None = None):
    """登出：revoke 本地 session + 重定向到 CAS 单点登出。"""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        revoke_session(token)
    # 前端可以选择是否调用这个端点
    return JSONResponse(content={"logout_url": build_logout_url()})
```

#### 2.3.3 改 `backend/main.py` 挂 router

```python
# 文件顶部 import 区加
from backend.routers.cas_auth import router as cas_auth_router

# 在 app.include_router 区加（其他 router 同行）
app.include_router(cas_auth_router)
```

#### 2.3.4 改 `backend/routers/auth.py` 支持开关

```python
import os

_AUTH_BACKEND = os.getenv("AUTH_BACKEND", "supabase").lower()

if _AUTH_BACKEND == "cas":
    from backend.services.cas_auth_service import get_auth_status_payload as _status_impl
elif _AUTH_BACKEND == "dual":
    # 过渡期：优先看 Bearer token，先试 Supabase，失败再试 CAS session
    from backend.services.supabase_auth_service import (
        get_auth_status_payload as _supabase_status,
    )
    from backend.services.cas_auth_service import (
        get_auth_status_payload as _cas_status,
    )

    def _status_impl(authorization, **kwargs):
        # 先试 Supabase
        resp = _supabase_status(authorization, **kwargs)
        if resp.get("authenticated"):
            return resp
        # 再试 CAS
        return _cas_status(authorization, **kwargs)
else:
    from backend.services.supabase_auth_service import get_auth_status_payload as _status_impl


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(authorization: str | None = Header(default=None), ...):
    return _status_impl(authorization, ...)
```

**同样要改 business 代码里所有 `from backend.services.supabase_auth_service import get_authenticated_user`**：

最干净的做法是**创建一个统一入口** `backend/services/auth_service.py`：
```python
import os

_AUTH_BACKEND = os.getenv("AUTH_BACKEND", "supabase").lower()

if _AUTH_BACKEND == "cas":
    from backend.services.cas_auth_service import get_authenticated_user
elif _AUTH_BACKEND == "dual":
    from backend.services.supabase_auth_service import get_authenticated_user as _sb
    from backend.services.cas_auth_service import get_authenticated_user as _cas
    def get_authenticated_user(authorization, **kwargs):
        return _sb(authorization, **kwargs) or _cas(authorization, **kwargs)
else:
    from backend.services.supabase_auth_service import get_authenticated_user

__all__ = ["get_authenticated_user"]
```

然后**全局搜索替换**所有 `from backend.services.supabase_auth_service import get_authenticated_user`：
```powershell
Select-String -Path backend\routers\*.py -Pattern "supabase_auth_service import get_authenticated_user" -List
# 然后把找到的文件里这行改成：
# from backend.services.auth_service import get_authenticated_user
```

### 2.4 前端代码

#### 2.4.1 `frontend/src/pages/CasCallbackPage.jsx`

```jsx
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function CasCallbackPage() {
  const navigate = useNavigate()

  useEffect(() => {
    // 从 URL fragment 提取 token
    const hash = window.location.hash || ''
    const match = /token=([^&]+)/.exec(hash)

    if (match && match[1]) {
      const token = decodeURIComponent(match[1])
      localStorage.setItem('fdsm-cas-token', token)
      // 清除 URL fragment
      window.history.replaceState({}, '', window.location.pathname)
      navigate('/', { replace: true })
    } else {
      navigate('/login?cas_error=missing_token', { replace: true })
    }
  }, [navigate])

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p>正在完成登录，请稍候...</p>
    </div>
  )
}
```

#### 2.4.2 `frontend/src/App.jsx` 加路由

```jsx
// import 区
import CasCallbackPage from './pages/CasCallbackPage'

// routes 里加
<Route path="/login/cas-callback" element={<CasCallbackPage />} />
```

#### 2.4.3 `frontend/src/api/index.js` 双源 token

```javascript
async function getAuthToken() {
  // 优先 CAS token
  const casToken = typeof window !== 'undefined'
    ? window.localStorage.getItem('fdsm-cas-token')
    : null
  if (casToken) return casToken

  // fallback 到 Supabase
  try {
    const { supabase } = await import('../auth/supabaseClient.js')
    const { data } = await supabase.auth.getSession()
    return data?.session?.access_token ?? null
  } catch {
    return null
  }
}

// request() 里用 getAuthToken() 替代之前的 getSupabaseAccessToken()
```

#### 2.4.4 登录按钮

`frontend/src/pages/LoginPage.jsx` 加：
```jsx
<a
  href={`${API_ORIGIN || ''}/api/auth/cas/login`}
  className="btn-primary w-full"
>
  使用复旦统一身份认证登录
</a>
```

### 2.5 部署切换

**步骤**（在生产服务器上做）：

1. **本地构建新版镜像并推仓库**（tag: `v2.0.0-cas`）
2. **服务器更新代码**：
   ```bash
   cd /srv/fdsm/app
   git checkout deployment/cas-migration
   git pull
   ```
3. **改 `.env.production`**：
   ```
   AUTH_BACKEND=dual                        # 过渡期，Supabase + CAS 同时支持
   CAS_URL=https://id.fudan.edu.cn/cas
   CAS_SERVICE_URL=https://knowledge.fdsm.fudan.edu.cn/api/auth/cas/callback
   CAS_TIMEOUT_SECONDS=8
   CAS_SESSION_TTL_SECONDS=28800
   IMAGE_TAG=v2.0.0-cas
   ```
4. **拉镜像 + 重启**：
   ```bash
   docker compose pull
   docker compose up -d
   ```
5. **验证**：访问 `https://domain/api/auth/cas/login` 应重定向到 CAS 登录页
6. **过渡期 1-2 周**：新用户走 CAS 登录，老用户继续用 Supabase（但下次登录提示绑定 CAS）
7. **切换正式**：改 `AUTH_BACKEND=cas`，禁用 Supabase 入口

### 2.6 用户迁移

过渡期登录页可以加一个横幅：
> "您的账号还未绑定复旦统一身份认证。登录后请点'绑定 CAS' 完成合并，以后可直接使用 CAS 登录。"

"绑定 CAS" 按钮点击后走 `/api/auth/cas/login`，回调时后端（§2.3.4 的 `_ensure_local_user_from_cas`）的路径 B 会自动把 CAS 工号写到现有 `business_users.cas_employee_number`。

---

## 第三部分 · 长期扩容路线

### 3.1 何时换 Postgres

**触发信号**（任一）：
- `data/fudan_knowledge_base.db` > **5 GB**
- 并发写 qps 持续 > **50**
- 需要多机部署（负载均衡多台 backend-web）
- 复杂分析查询（窗口函数、递归 CTE、全文搜索 FTS5 不够）
- SQLite 频繁 `database is locked` 哪怕加了信号量

**迁移工作量**：3-5 人日

**大致路径**：
1. 服务器加一个 Postgres 容器（`docker-compose.yml` 加 service）
2. 装 `pgloader` 把 SQLite 一键迁 Postgres
3. 引入 SQLAlchemy + asyncpg
4. 改 `backend/database.py` 支持 `DATABASE_URL` 环境变量切换
5. 跑双写一段时间验证
6. 切换到 Postgres-only

### 3.2 何时拆 FAISS 服务

**触发信号**：
- `faiss_index_business/` > **2 GB**
- 每 gunicorn worker 加载 1.5+ GB 内存，机器吃不消
- 需要支持实时索引更新（当前方案重建索引要停机）

**迁移工作量**：2-3 人日（换 Qdrant 或自建 Elasticsearch）

**路径**：
1. 起一个 Qdrant 容器
2. 写脚本把 FAISS 导出 → 灌到 Qdrant
3. `rag_engine.py` 改查询方式（`RAG_SEARCH_PROVIDER=qdrant`）
4. 验证召回效果对齐
5. 切换

### 3.3 何时加 CDN

**触发信号**：
- 音频/视频下载量大（超过服务器带宽 80%）
- 用户地理分布广（国内/海外混合）

**推荐**：阿里云 DCDN + 源站走 OSS

路径：
1. uploads/audio 从本地 volume 迁 OSS
2. CDN 回源到 OSS
3. 改 API 返回的 URL 从 `/audio-files/xxx` 改成 `https://cdn.xxx.com/xxx`

### 3.4 何时拆多机

**触发信号**：
- 单机 CPU 长期 > 70%
- 单机内存 > 80%
- 有高可用需求（单机宕机就挂）

**路径**：
1. 前置 SLB（阿里云负载均衡）
2. 起 2-3 台 backend-web 机器
3. Redis 和 SQLite 拆独立机器
4. 或者干脆上 Kubernetes

---

## 结语

做到这里，完整的 12 份文档全部执行完毕。项目状态：

- ✅ 本地 Docker = 生产 Docker（除 `.env` 和 SSL）
- ✅ 高并发就绪（worker + 信号量 + Redis 缓冲）
- ✅ 生产加固（限流、HTTPS、日志、备份、监控）
- ✅ 鉴权解耦（Supabase v1 → CAS v2 零业务代码改动）
- ✅ 有完整的更新/回滚/监控流程
- ✅ 清晰的扩容触发信号和路径

上线后按本文档 §1 运维即可。出问题回查 §1.7 常见故障；要做大改动按 §1.1 大改动流程；要迁 CAS 按 §2。

祝顺利。
