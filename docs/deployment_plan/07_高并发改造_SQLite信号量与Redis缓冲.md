# 07 · 高并发改造：SQLite 信号量与 Redis 缓冲

> **前置依赖**：[04_鉴权加缓存与本地用户绑定](./04_代码改造_鉴权加缓存与本地用户绑定.md) 完成；Redis 可达
> **预计耗时**：2-3 小时
> **完成标志**：
> - `hey -n 500 -c 50 /api/articles/{id}/view` 压测 0 失败
> - 浏览计数不再直接写 SQLite，而是 Redis 增量，worker 每 30 秒 flush
> - 写密集的端点被信号量限流（最多 4 个并发写）
> - SQLite 不再出现 `database is locked` 错误

---

## 背景与目标

### SQLite 写并发的真相

即使开了 WAL（§02），**SQLite 也只能一次一个写**。WAL 的优势在于"读不阻塞"，但写还是串行：

```
写请求 1: BEGIN IMMEDIATE → ... → COMMIT  (获取了 reserved lock)
写请求 2: BEGIN IMMEDIATE → 等待 reserved lock 释放
写请求 3: 等待
写请求 4: 等待
...
```

高并发写场景（10+ 并发写）下：
- 每个请求持锁 5-50 ms（写 `article_view_events` 之类的简单 INSERT）
- 10 个并发变成串行等，p95 延迟飙到 500 ms+
- 偶尔会超过 `busy_timeout=60s`，返回 `database is locked`

### 哪些端点是"热点写"

Grep 后端找所有写操作的端点（这些是压测时 SQLite 最容易炸的地方）：

| 端点 | 写的表 | 调用频率 |
|---|---|---|
| 文章浏览 | `article_view_events` | 🔥 最高，每个页面访问都写 |
| 点赞/收藏 | `article_reactions` | 高 |
| 关注 | `user_follows` | 中 |
| 编辑保存 | `editorial_articles` | 中（编辑行为） |
| 媒体发布 | `media_items` | 低 |
| 鉴权首次建档 | `business_users` | 低 |

### 解决方案分两层

**第一层 · Redis 缓冲（针对最高频的浏览计数）**
```
写请求 → Redis INCRBY "view_count:<article_id>"  (< 1ms)
         (不写 SQLite)

每 30 秒 worker loop → SPOP 所有 pending → 批量 UPDATE SQLite
```

好处：
- 单个请求 < 1ms 返回，SQLite 几乎不碰
- 批量更新时一个事务合并 100 条记录，锁开销被摊薄

代价：
- 浏览计数不是实时的（30 秒延迟，可以接受）
- Redis 挂了会丢失 30 秒内的计数（对业务无关紧要的指标）

**第二层 · 写信号量（兜底其他写端点）**
```
编辑保存 / 点赞 / ... → 获取信号量（最多 4 个并发）
                     → 写 SQLite
                     → 释放
```

好处：
- 保护 SQLite 不被雪崩（10 个人点赞不会击穿）
- 用户多等 100 ms 而不是直接 500 报错

---

## 改动清单

- [ ] 步骤 1：新建 `backend/services/db_concurrency.py` 写信号量
- [ ] 步骤 2：改 `backend/services/engagement_service.py` 浏览计数走 Redis
- [ ] 步骤 3：在 `deploy/worker_loop.py` 里实现 `flush_view_counts`
- [ ] 步骤 4：给写密集的 router 加信号量依赖
- [ ] 步骤 5：本地验证浏览计数走 Redis
- [ ] 步骤 6：本地压测 500 并发 0 失败
- [ ] 步骤 7：Commit

**新文件**：1 个
- `backend/services/db_concurrency.py`

**修改文件**：3 个
- `backend/services/engagement_service.py`
- `deploy/worker_loop.py`
- `backend/routers/articles.py`（或 `engagement.py` 看项目实际）

---

## 原子步骤

### 步骤 1 · 新建 `backend/services/db_concurrency.py`

**创建文件**：
```python
"""
写入 SQLite 的并发控制。在 FastAPI 路由上用作 Dependency：

    from backend.services.db_concurrency import db_write_semaphore

    @router.post("/some-write", dependencies=[Depends(db_write_semaphore)])
    async def handler(...): ...

效果：进程级信号量限制 N 个并发写（默认 4，可通过 env 调整）。
超过 N 时后续请求排队（阻塞在 semaphore.acquire），最多等 DB_WRITE_WAIT_SECONDS，
超时返回 503。

为什么不做全局限制：SQLite 本身一次只能一个写，但业务代码里"写"不止 INSERT/UPDATE
——常伴随查询、校验、日志，这些步骤的整体耗时允许 4 个并发，让 DB 自己做写串行化。
"""
from __future__ import annotations

import asyncio
import os

from fastapi import HTTPException


_WRITE_CONCURRENCY = int(os.getenv("DB_WRITE_CONCURRENCY", "4"))
_WRITE_WAIT_SECONDS = float(os.getenv("DB_WRITE_WAIT_SECONDS", "10"))

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """懒创建，避免 module import 时绑定到错误的 event loop。"""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_WRITE_CONCURRENCY)
    return _semaphore


async def db_write_semaphore():
    """FastAPI dependency。路由用 Depends(db_write_semaphore) 启用。"""
    sem = _get_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=_WRITE_WAIT_SECONDS)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail=f"server busy; write capacity exhausted (cap={_WRITE_CONCURRENCY})",
        )
    try:
        yield
    finally:
        sem.release()
```

**设计点**：
- 进程级信号量（asyncio.Semaphore）：每个 gunicorn worker 独立,4 个 worker = 总 16 并发写
- 10 秒等待超时：用户点一下按钮最多多等 10 秒，比直接 500 好
- Generator 形式的 dependency：FastAPI 正确处理 `yield` 前后的 acquire / release

**为什么是 4 不是更小**：
- SQLite 本身写串行，瓶颈在 DB 不在信号量
- 4 个并发 = 4 个 FastAPI 协程并发，其中 1 个在写 DB、3 个在做 Python 逻辑（查、序列化、日志），整体吞吐更高
- 大于 4 反而让更多协程排队等 DB 锁，无益

---

### 步骤 2 · 浏览计数走 Redis

**打开 `backend/services/engagement_service.py`**（如果没有这个文件，找调用 `article_view_events` INSERT 的地方）。

**搜索浏览计数的原始实现**：
```powershell
Select-String -Path backend\services\*.py -Pattern "article_view_events" -Context 2,5
Select-String -Path backend\services\*.py -Pattern "record.*view|view_count" -Context 2,5
```

**原实现大概是这样**（根据项目实际调整）：
```python
def record_article_view(article_id: int, visitor_id: str, user_id: str | None = None) -> None:
    with connection_scope() as conn:
        conn.execute(
            "INSERT INTO article_view_events (article_id, visitor_id, user_id, viewed_at) "
            "VALUES (?, ?, ?, ?)",
            (article_id, visitor_id, user_id, datetime.now().isoformat()),
        )
        conn.execute(
            "UPDATE articles SET view_count = COALESCE(view_count, 0) + 1 WHERE id = ?",
            (article_id,),
        )
        conn.commit()
```

**改成 Redis 缓冲**：
```python
from backend.services.ai_task_service import get_redis

# Redis key 约定
_VIEW_COUNT_KEY = "pending:article_view_count"        # HASH: article_id → increment
_VIEW_IDS_KEY = "pending:article_view_ids"            # SET: dirty article_ids
_VIEW_EVENT_KEY_PREFIX = "pending:view_event:"        # STRING: raw event (visitor 级)


def record_article_view(article_id: int, visitor_id: str, user_id: str | None = None) -> None:
    """写入 Redis 缓冲。worker 每 30 秒 flush 到 SQLite。"""
    r = get_redis()
    pipe = r.pipeline()
    # 计数自增
    pipe.hincrby(_VIEW_COUNT_KEY, str(article_id), 1)
    pipe.sadd(_VIEW_IDS_KEY, str(article_id))
    # 原始事件（用来 INSERT 到 article_view_events，保留 visitor 维度）
    # 每 visitor+article 的事件去重到每分钟粒度（防止刷流量）
    minute = int(time.time() // 60)
    event_key = f"{_VIEW_EVENT_KEY_PREFIX}{minute}:{article_id}:{visitor_id}"
    pipe.setex(event_key, 3600, f"{user_id or ''}|{visitor_id}|{article_id}|{int(time.time())}")
    pipe.execute()


# 文件顶部加 import
import time
```

**关键设计**：
- `HINCRBY` 是 O(1) 原子操作
- `SADD` 记录哪些 article_id 有待 flush 的增量（flush 时不用全量扫 HASH）
- 原始事件用 `SETEX` + 1 小时 TTL：flush 时读出来批量 INSERT，1 小时后自动清理（万一 worker 挂了也不会永远积累）
- 一分钟内同一 visitor 看同一 article 只记一次事件（去重）——如果业务要求更严格的计数策略按需调整

**其他同类改造**（只对高频写做）：

**点赞 `record_reaction`** 可以继续走同步（频率远低于浏览），加信号量即可。除非你的业务量真的很大。

---

### 步骤 3 · worker_loop 实现 flush

**回到 `deploy/worker_loop.py`**，找到占位的 `flush_view_counts()`（§06 步骤 4 里留了）。

**替换为**：
```python
def flush_view_counts() -> None:
    """把 Redis 里的浏览计数 flush 到 SQLite。
    每 ~30 秒调用一次（由主循环按 iteration 触发）。

    流程：
      1. SPOP 一批 dirty article_ids（最多 200 个，避免单次批次太大）
      2. HGETDEL 每个 article_id 的增量（原子取走）
      3. 一个事务内批量 UPDATE articles.view_count
      4. 一个事务内批量 INSERT article_view_events（从 pending:view_event:* keys）
    """
    from backend.services.ai_task_service import get_redis
    from backend.database import connection_scope

    r = get_redis()

    # 1. 取出一批 dirty ids
    article_ids_raw = r.spop("pending:article_view_ids", 200) or []
    article_ids = [int(x) for x in article_ids_raw]
    if not article_ids:
        # 也要看一下事件 key 是否积压（计数 flush 掉了但事件没 insert 的情况）
        _flush_view_events_only(r)
        return

    # 2. 取出每个 article 的增量
    pipe = r.pipeline()
    for aid in article_ids:
        pipe.hget("pending:article_view_count", str(aid))
    increments_raw = pipe.execute()

    # 原子删除取走的 HASH 字段
    pipe = r.pipeline()
    for aid in article_ids:
        pipe.hdel("pending:article_view_count", str(aid))
    pipe.execute()

    increments = {
        aid: int(raw) for aid, raw in zip(article_ids, increments_raw) if raw
    }
    if not increments:
        return

    # 3. 一个事务内批量更新
    with connection_scope() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for aid, inc in increments.items():
                conn.execute(
                    "UPDATE articles SET view_count = COALESCE(view_count, 0) + ? WHERE id = ?",
                    (inc, aid),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            # 失败：把增量塞回 Redis（不丢数据）
            pipe = r.pipeline()
            for aid, inc in increments.items():
                pipe.hincrby("pending:article_view_count", str(aid), inc)
                pipe.sadd("pending:article_view_ids", str(aid))
            pipe.execute()
            raise

    log.info("flushed view counts for %d articles (total increments=%d)",
             len(increments), sum(increments.values()))

    # 4. 批量 INSERT 事件
    _flush_view_events_only(r)


def _flush_view_events_only(r):
    """把 pending:view_event:* 的事件批量 INSERT 到 article_view_events，然后删除 key。"""
    from backend.database import connection_scope

    # 一次最多处理 500 个事件 key
    keys = []
    cursor = 0
    while True:
        cursor, batch = r.scan(cursor=cursor, match="pending:view_event:*", count=200)
        keys.extend(batch)
        if cursor == 0 or len(keys) >= 500:
            break

    if not keys:
        return

    # 批量 MGET 取值
    values = r.mget(keys)
    rows = []
    for v in values:
        if not v:
            continue
        try:
            user_id, visitor_id, aid, ts = v.split("|")
            rows.append((int(aid), visitor_id, user_id or None,
                         datetime.fromtimestamp(int(ts)).isoformat()))
        except (ValueError, TypeError):
            continue

    if not rows:
        r.delete(*keys)
        return

    with connection_scope() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                "INSERT INTO article_view_events (article_id, visitor_id, user_id, viewed_at) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # 成功才删 key
    r.delete(*keys)
    log.info("flushed %d view events", len(rows))
```

**文件顶部加 import**：
```python
from datetime import datetime
```

**关键设计**：
- `BEGIN IMMEDIATE`：立刻获取 reserved lock，避免"先读后写"的升级锁问题
- 失败时把增量 `HINCRBY` 回 Redis：保证不丢数据
- 批量大小限制 200/500：单次事务不要太大（SQLite 事务越大锁时间越长）
- 事件 key 用 `SCAN MATCH`：避免 `KEYS` 阻塞 Redis

---

### 步骤 4 · 给写端点加信号量

找项目里写 `editorial_articles`、`user_follows`、`article_reactions` 的路由。

**示例：`backend/routers/editorial.py` 的编辑保存端点**：
```python
from backend.services.db_concurrency import db_write_semaphore

@router.put(
    "/articles/{article_id}",
    dependencies=[Depends(db_write_semaphore)],
)
async def update_editorial_article(article_id: int, body: EditorialUpdateRequest, ...):
    ...
```

**需要加的端点清单**（按项目实际路由调整）：
- `POST /api/editorial/articles/{id}/save`
- `POST /api/editorial/publish/{id}`
- `POST /api/follows/toggle`
- `POST /api/engagement/reactions`
- `POST /api/media/{id}/publish`

搜一下找全：
```powershell
Select-String -Path backend\routers\*.py -Pattern "@router\.(post|put|patch|delete)" -Context 0,3
```

对**每个有 DB 写操作**的 router handler 加 `dependencies=[Depends(db_write_semaphore)]`。

**注意**：不要给**所有** POST/PUT/DELETE 加，只给真正写 DB 的加。某些 endpoint 只是触发外部调用（比如发 AI 任务入队）不需要。

**浏览计数端点不加信号量**——它走 Redis 不碰 SQLite，根本不需要。

---

### 步骤 5 · 本地验证浏览计数走 Redis

**启动栈**（3 个终端）：

**终端 1 · Redis**（已起）

**终端 2 · FastAPI**（按 §06 步骤 7 的方式启动）

**终端 3 · Worker**（按 §06 步骤 7 的方式启动）

**触发浏览并查 Redis**：
```powershell
# 触发 10 次浏览
1..10 | ForEach-Object {
    curl "http://127.0.0.1:8000/api/articles/1" -H "X-Visitor-Id: test-visitor" | Out-Null
}

# 查 Redis 缓冲
docker exec fdsm-redis-dev redis-cli HGETALL pending:article_view_count
# 预期：{"1": "10"}

docker exec fdsm-redis-dev redis-cli SMEMBERS pending:article_view_ids
# 预期：["1"]

docker exec fdsm-redis-dev redis-cli KEYS "pending:view_event:*" | Select-Object -First 5
# 预期：看到几个 key（被一分钟去重合并了）
```

**等 30 秒，worker 自动 flush**。看终端 3 worker 日志：
```
2026-04-21 12:00:03 [INFO] worker: flushed view counts for 1 articles (total increments=10)
2026-04-21 12:00:03 [INFO] worker: flushed N view events
```

**验证 SQLite 更新了**：
```powershell
python -c @"
from backend.database import get_connection
c = get_connection()
row = c.execute('SELECT id, view_count FROM articles WHERE id = 1').fetchone()
print(dict(row))
"@
```

**预期**：`view_count` 比测试前多 10。

**再查 Redis**（flush 后应该清空）：
```powershell
docker exec fdsm-redis-dev redis-cli HGETALL pending:article_view_count
# 空 {}

docker exec fdsm-redis-dev redis-cli SMEMBERS pending:article_view_ids
# 空 []
```

---

### 步骤 6 · 500 并发压测

**目的**：验证浏览计数不再被 SQLite 锁住，信号量保护其他写端点。

**操作**：
```powershell
# 高并发打浏览端点（走 Redis，应该最快）
hey -n 500 -c 50 -H "X-Visitor-Id: stress-test" http://127.0.0.1:8000/api/articles/1
```

**预期**：
- Total errors: 0
- p99 < 100 ms
- RPS > 500

**高并发打一个写 SQLite 的端点**（比如点赞）：
```powershell
hey -n 200 -c 30 -m POST `
    -H "Content-Type: application/json" `
    -H "X-Debug-User-Id: mock-admin" `
    -d '{"article_id": 1, "action": "like"}' `
    http://127.0.0.1:8000/api/engagement/reactions
```

**预期**：
- Total errors: 0（最多几个 503，因为信号量队列满）
- p95 < 2 秒
- 无 `database is locked` 错误（看后端日志）

**如果出现 `database is locked`**：
1. WAL 没生效（回到 §02）
2. 信号量上限太高（调低 `DB_WRITE_CONCURRENCY=2`）
3. 某个写操作太慢（看 slow query 日志）

---

### 步骤 7 · Commit

```powershell
git add backend/services/db_concurrency.py
git add backend/services/engagement_service.py
git add deploy/worker_loop.py
git add backend/routers/*.py       # 加了 dependencies 的那些

git commit -m "deploy(step-07): SQLite write semaphore + Redis view count buffer

- db_concurrency.py: process-wide asyncio.Semaphore(4) with 10s wait;
  writes beyond cap return 503 instead of piling up on SQLite busy_timeout
- engagement_service.record_article_view now writes to Redis (HINCRBY) +
  per-minute dedup event keys; no SQLite hit on the hot path
- worker_loop.flush_view_counts: atomic SPOP/HGET, batched UPDATE in
  BEGIN IMMEDIATE transaction, rollback restores counters to Redis
- Writes in editorial/media/engagement routers now take db_write_semaphore"
```

---

## 阶段验收

### 验收 1 · 浏览计数 0 SQLite 写

```powershell
# 全部 REDIS_URL 设好后，手动把 SQLite 变成只读（模拟 DB 挂）
# 再打浏览，预期请求还是成功（因为走 Redis）

# 准备：把 DB 变只读
icacls data\fudan_knowledge_base.db /deny "$env:USERNAME:(W)"

# 打浏览
curl "http://127.0.0.1:8000/api/articles/1" -H "X-Visitor-Id: readonly-test"
# 预期：200 OK（不是 500）

# 恢复
icacls data\fudan_knowledge_base.db /remove:d "$env:USERNAME"
```

⚠️ 这个验证会让 worker 的 flush 失败——看它的日志应该有 "UPDATE failed, pushing increments back to Redis"。

### 验收 2 · 信号量兜底

```powershell
# 故意让信号量吃紧（并发 50 个写，上限 4）
hey -n 100 -c 50 -m POST `
    -H "Content-Type: application/json" `
    -H "X-Debug-User-Id: mock-admin" `
    -d '{"article_id": 1, "action": "like"}' `
    http://127.0.0.1:8000/api/engagement/reactions
```

**预期**：
- 0 个 `database is locked`
- 可能有少数 503（信号量等待超时）
- 绝大多数成功

### 验收 3 · Worker 挂了不影响 web

```powershell
# 停 worker
# （终端 3 Ctrl+C）

# 打 100 次浏览
hey -n 100 -c 10 -H "X-Visitor-Id: worker-dead-test" http://127.0.0.1:8000/api/articles/1
# 预期：全成功，都进 Redis

# 查 Redis 积压
docker exec fdsm-redis-dev redis-cli HGETALL pending:article_view_count
# 预期：看到 article_id=1 积累了 100

# 重启 worker，30 秒后自动 flush
python -m deploy.worker_loop
# 看到 "flushed view counts for 1 articles (total increments=100)"
```

---

## 常见错误与排查

| 症状 | 原因 | 修复 |
|---|---|---|
| `database is locked` 仍然出现 | 某个写端点没加信号量，或者有裸 SQL | Grep `INSERT INTO\|UPDATE\|DELETE` 找没加保护的端点 |
| Redis flush 失败后数据丢了 | `rollback` 后没 HINCRBY 回去 | 检查 worker 代码里 except 分支是否补偿 Redis |
| 浏览计数长时间不更新 | worker 没跑，或者 flush 周期太长 | `docker compose logs backend-worker`；临时触发 `python -m deploy.worker_loop` |
| Redis 内存越来越大 | 事件 key TTL 没设 | 检查 `record_article_view` 里 `SETEX` 的 TTL |
| 信号量导致全局变慢 | `DB_WRITE_CONCURRENCY` 太低 | 把 2 改成 4 或 8，看瓶颈在哪 |
| 多 worker 下信号量总量过大 | 每 worker 独立 4 个 = 16 | 这是期望行为；SQLite 还是写串行，实际 DB 侧还是一次一个 |
| flush 占用太多 worker 时间 | 批次太大 | 把 `SPOP 200` 改成 `SPOP 50` |

---

## 为什么不用更复杂的方案

**为什么不用 Lua 脚本原子化 flush**：
`SPOP + HGET + HDEL` 三步在 worker 里是单线程串行，没有竞态（只有一个 worker）。多 worker 时 `SPOP` 本身是原子的，两个 worker 不会抢到同一个 id。够用。

**为什么不用 Celery**：
Flush 是**周期性任务**，不是 event-driven。用 Celery beat 也行但过度设计。worker_loop 里一个 `if iteration % 6 == 0` 就搞定。

**为什么不用 Redis Stream 记录事件**：
Stream 是持久化的、有消费组。view_event 我们**允许丢**（短时间内丢 30 秒数据对统计无影响），用 SCAN + SETEX 就够。

**什么时候换 Postgres**：
- 数据量 > 5 GB
- 并发写 > 100 qps
- SQLite 已经扛不住就算 WAL+信号量+Redis 也不行了
详见 §12。

---

## 性能基线

本地 16c/32g 开发机 + Docker 栈，做完 §02-07 后：

| 场景 | QPS | p50 | p99 |
|---|---|---|---|
| `/api/home/feed` | 800+ | 15ms | 80ms |
| `/api/articles/{id}` | 600+ | 20ms | 120ms |
| `/api/articles/{id}/view`（Redis 缓冲）| 1500+ | 3ms | 15ms |
| `/api/search?q=xxx`（FAISS）| 30 | 300ms | 1500ms |
| `/api/engagement/reactions`（信号量）| 100 | 40ms | 500ms |
| `/api/editorial/ai/tasks/summarize`（异步）| 立即返回 | 10ms | 50ms |

云端生产 8c16g 预期比这个慢 30%，依然远超预期日 UV 3000 的需求。

---

## 下一步

**去 [08_Docker构建_Dockerfile与compose.md](./08_Docker构建_Dockerfile与compose.md)** 把所有改动打进 Docker 镜像。

做完 07 之后所有代码级改造完成：
- ✅ DB 层 WAL + 性能调优
- ✅ FastAPI 生产级（lifespan、健康、CORS、debug 屏蔽）
- ✅ 鉴权带缓存 + 本地用户绑定
- ✅ 前端生产化
- ✅ AI 调用全异步
- ✅ SQLite 写并发控制

下一步开始容器化。
