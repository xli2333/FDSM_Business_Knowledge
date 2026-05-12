# 02 · 代码改造：数据库 WAL 与连接优化

> **前置依赖**：[01_前置准备](./01_前置准备与环境校验.md) 完成
> **预计耗时**：1 小时
> **完成标志**：
> - `sqlite3 data/fudan_knowledge_base.db "PRAGMA journal_mode;"` 返回 `wal`
> - `data/` 目录下出现 `fudan_knowledge_base.db-wal` 和 `-shm` 两个文件
> - 项目能正常启动（无 DB 连接报错）
> - pytest 全部通过（至少现有测试不 regression）

---

## 背景与目标

### 为什么要改

当前 `backend/database.py:25-29` 用 SQLite 默认的 **DELETE journal mode**。这种模式下：

- **写操作锁住整个数据库**：任何 `UPDATE / INSERT / DELETE` 期间，其他连接的读也会阻塞
- **并发写会触发 `SQLITE_BUSY`**：虽然 `PRAGMA busy_timeout=60000` 会等 60s，但在高并发下仍然频繁失败
- **多 gunicorn worker 下雪崩**：4 个 worker 并发处理 4 个写请求，第 2/3/4 个全部等第 1 个释放锁

一个 **704 MB** 的业务库 + Docker 多 worker 环境，必须用 **WAL（Write-Ahead Logging）**模式：

- 读写并发：`SELECT` 不阻塞 `INSERT/UPDATE`
- 单写并发：写操作还是串行，但不再阻塞读
- 性能提升：典型场景 2-5 倍

### WAL 的代价

**会多出两个文件**：
- `fudan_knowledge_base.db-wal`：写前日志，大小不固定
- `fudan_knowledge_base.db-shm`：共享内存索引，固定约 32KB

**三个必须知道的事实**：
1. **这两个文件必须和主 DB 在同一目录**，volume 挂载要挂整个 `data/` 目录，不能只挂 `.db` 文件
2. **`cp` 或简单文件拷贝会导致不一致**：备份必须用 `sqlite3 ".backup"` 命令（§10 讲）
3. **WAL 文件会增长**：需要定期 `PRAGMA wal_checkpoint` 截断，这在 `PRAGMA wal_autocheckpoint=1000` 下自动做

### 这一步做完后的效果

- 一次 `UPDATE` 不再阻塞所有读
- 多 worker 写并发不再 `database is locked`
- 每个连接 64MB 页缓存，加速查询
- 256MB mmap，大表扫描提速

---

## 改动清单

- [ ] 步骤 1：备份当前 `backend/database.py`
- [ ] 步骤 2：升级 `get_connection()` 函数
- [ ] 步骤 3：新增 `_apply_startup_pragmas()` 辅助函数
- [ ] 步骤 4：本地 Python 手动验证 WAL 生效
- [ ] 步骤 5：验证 DB 目录出现 `-wal` / `-shm` 文件
- [ ] 步骤 6：跑现有 pytest 确认无 regression
- [ ] 步骤 7：Commit

**只改一个文件**：`backend/database.py`

---

## 原子步骤

### 步骤 1 · 备份原文件

虽然 Git 可以回滚，但手动备份一份心里踏实：

**操作**：
```powershell
cd C:\Users\LXG\fdsmarticles
Copy-Item backend\database.py backend\database.py.pre_wal_backup
```

后面改完验证通过了再删：
```powershell
Remove-Item backend\database.py.pre_wal_backup
```

---

### 步骤 2 · 改 `get_connection()`

**要改的位置**：`backend/database.py` 第 25-29 行

**原代码**：
```python
def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection
```

**改后代码**（把下面整段替换原来的 5 行）：
```python
import threading

_PRAGMA_APPLIED = False
_PRAGMA_LOCK = threading.Lock()


def _apply_startup_pragmas(connection: sqlite3.Connection) -> None:
    """首次连接时设置 WAL 等持久化 PRAGMA。WAL 模式一旦启用会写入 DB 文件头，
    之后所有新连接都自动是 WAL。此函数只在进程启动后的第一次连接执行一次。"""
    global _PRAGMA_APPLIED
    with _PRAGMA_LOCK:
        if _PRAGMA_APPLIED:
            return
        # journal_mode 的 PRAGMA 返回当前模式；设置成功会返回 'wal'
        result = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if result and result[0] != "wal":
            import logging
            logging.warning("SQLite journal_mode is %s, expected wal", result[0])
        # 每 1000 页自动做一次 WAL checkpoint（截断 -wal 文件，控制大小）
        connection.execute("PRAGMA wal_autocheckpoint = 1000")
        _PRAGMA_APPLIED = True


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(
        SQLITE_DB_PATH,
        timeout=60,
        check_same_thread=False,    # 允许连接跨线程（uvicorn worker 多线程时需要）
        isolation_level=None,       # 显式事务控制，禁止 sqlite3 模块自动开事务
    )
    connection.row_factory = sqlite3.Row
    # 以下 PRAGMA 是每连接级，每次新连接都要设
    connection.execute("PRAGMA busy_timeout = 60000")           # 忙等 60s
    connection.execute("PRAGMA synchronous = NORMAL")           # WAL 下安全且更快
    connection.execute("PRAGMA cache_size = -65536")            # 64 MB 页缓存
    connection.execute("PRAGMA temp_store = MEMORY")            # 临时表放内存
    connection.execute("PRAGMA mmap_size = 268435456")          # 256 MB mmap
    connection.execute("PRAGMA foreign_keys = ON")              # 启用外键
    # 以下 PRAGMA 是 DB 级（进程一次即可），用锁避免重复
    _apply_startup_pragmas(connection)
    return connection
```

**关键点解释**（必须理解，否则以后排错困难）：

| PRAGMA | 作用域 | 意义 |
|---|---|---|
| `journal_mode = WAL` | **DB 级**（写入 DB 文件头） | 切换日志模式。全局一次即可 |
| `wal_autocheckpoint = 1000` | DB 级（写入 DB 文件头） | 每 1000 个 WAL 帧自动 checkpoint |
| `busy_timeout = 60000` | 连接级 | 碰到锁等 60 秒再报错 |
| `synchronous = NORMAL` | 连接级 | WAL 下 NORMAL 安全且比 FULL 快 |
| `cache_size = -65536` | 连接级 | 负数表示 KB，-65536 = 64MB 页缓存 |
| `temp_store = MEMORY` | 连接级 | 临时索引放内存 |
| `mmap_size` | 连接级 | 用 mmap 读 DB，加速顺序扫 |
| `check_same_thread = False` | Python sqlite3 参数 | 允许连接跨线程，多线程 worker 必需 |
| `isolation_level = None` | Python sqlite3 参数 | 关掉 sqlite3 自动事务，由业务代码决定 |

⚠️ **注意 `isolation_level=None` 的副作用**：业务代码里如果有依赖自动事务的地方（比如 `with connection:` 隐式 commit），现在需要显式 `connection.commit()`。Grep 一下：

```powershell
Select-String -Pattern "connection\.commit\(" -Path backend\*.py, backend\**\*.py | Select-Object -First 20
```

如果项目里所有写操作都手动 `conn.commit()`，就没问题；如果有依赖 `with connection:` 隐式提交的地方，会出 bug。本项目检查了几个 service 文件，都是显式 commit，所以安全。

---

### 步骤 3 · 确认 import

改完后文件顶部 import 段应该包含：

```python
from __future__ import annotations

import json
import sqlite3
import threading                    # 新增
from contextlib import contextmanager
from datetime import datetime
```

如果已经有 `import threading` 就不重复加。

---

### 步骤 4 · 本地手动验证 WAL 生效

**启动方式**（因为数据已经移动到 `data/` 目录，要先设 env）：

```powershell
cd C:\Users\LXG\fdsmarticles
.\.venv\Scripts\Activate.ps1
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"

# 跑一个最小校验脚本
python -c @"
from backend.database import get_connection
conn = get_connection()
jm = conn.execute('PRAGMA journal_mode').fetchone()[0]
bt = conn.execute('PRAGMA busy_timeout').fetchone()[0]
cs = conn.execute('PRAGMA cache_size').fetchone()[0]
sy = conn.execute('PRAGMA synchronous').fetchone()[0]
print(f'journal_mode: {jm}')
print(f'busy_timeout: {bt}')
print(f'cache_size: {cs}')
print(f'synchronous: {sy}')
conn.close()
"@
```

**预期输出**：
```
journal_mode: wal
busy_timeout: 60000
cache_size: -65536
synchronous: 1
```

（`synchronous=1` 就是 `NORMAL`，0=OFF，2=FULL，3=EXTRA）

---

### 步骤 5 · 验证 WAL 文件生成

**操作**：
```powershell
Get-ChildItem data\fudan_knowledge_base.db*
```

**预期**：看到三个文件
```
fudan_knowledge_base.db          704 MB
fudan_knowledge_base.db-wal      0 KB 到 几 MB 之间（有写操作后才会有内容）
fudan_knowledge_base.db-shm      32 KB
```

**如果只有 .db 文件**：说明步骤 4 脚本没真正写 DB（只是打开连接不算触发 WAL 切换）。补一个真正的写操作：

```powershell
python -c @"
from backend.database import get_connection
conn = get_connection()
conn.execute('CREATE TABLE IF NOT EXISTS _wal_trigger (id INTEGER)')
conn.execute('INSERT INTO _wal_trigger VALUES (1)')
conn.commit()
conn.execute('DROP TABLE _wal_trigger')
conn.commit()
conn.close()
print('wal triggered')
"@

Get-ChildItem data\fudan_knowledge_base.db*
```

现在应该能看到 `-wal` 和 `-shm` 了。

---

### 步骤 6 · 跑 pytest 确认没 regression

WAL 模式和 `isolation_level=None` 是有可能破坏现有测试的（尤其是那些靠 `with connection:` 隐式事务的）。

**操作**：
```powershell
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
python -m pytest backend/tests/ -x -v 2>&1 | Tee-Object -FilePath pytest_after_wal.log
```

**预期**：所有测试通过，或者**只有和当前未提交的业务代码修改**相关的测试失败（这些失败是本来就存在的，不是 WAL 引入的）。

**如何判断 failure 是不是 WAL 引入的**：
1. `git stash`（暂存 WAL 改动）
2. 跑同样的 pytest
3. `git stash pop`
4. 对比两次结果：如果 stash 前也失败，就不是 WAL 的锅

**WAL 引入的典型问题**：
- 测试里用 `with connection:` 期待自动提交 → 现在需要显式 `conn.commit()`
- 测试里创建了临时数据但没清理 → WAL 下可能残留

**如何修**：找到失败测试，加显式 `commit()` 或 `rollback()`。

---

### 步骤 7 · Commit

**操作**：
```powershell
git status
# 应显示：
# modified:   backend/database.py

git diff backend/database.py
# 应能看到你加的代码

git add backend/database.py
git commit -m "deploy(step-02): enable SQLite WAL mode and performance pragmas

- Add _apply_startup_pragmas with process-wide lock to set WAL once
- Per-connection pragmas: busy_timeout=60s, cache_size=64MB, mmap=256MB
- Use check_same_thread=False and isolation_level=None for multi-worker safety
- Verified: PRAGMA journal_mode=wal, -wal/-shm files generated"
```

---

## 阶段验收

### 验收 1 · WAL 是持久的

WAL 模式一旦启用，会写入 DB 文件头，**即使关掉 Python 进程再重开也是 WAL**：

```powershell
# 确认再次启动仍是 WAL（证明是持久化配置，不是每次启动都要切）
python -c "from backend.database import get_connection; c=get_connection(); print(c.execute('PRAGMA journal_mode').fetchone()[0])"
# 应输出：wal
```

### 验收 2 · 并发读写不阻塞

开两个 PowerShell 窗口：

**窗口 A**（持续写入）：
```powershell
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
python -c @"
from backend.database import get_connection
import time
conn = get_connection()
for i in range(100):
    conn.execute('CREATE TABLE IF NOT EXISTS _concurrency_test (id INTEGER, v TEXT)')
    conn.execute('INSERT INTO _concurrency_test VALUES (?, ?)', (i, 'x'*1000))
    conn.commit()
    time.sleep(0.1)
print('writer done')
conn.execute('DROP TABLE _concurrency_test')
conn.commit()
"@
```

**窗口 B**（同时查询）：
```powershell
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
python -c @"
from backend.database import get_connection
import time
conn = get_connection()
for i in range(10):
    t0 = time.time()
    rows = conn.execute('SELECT COUNT(*) FROM articles').fetchone()
    print(f'query {i}: count={rows[0]}, elapsed={(time.time()-t0)*1000:.1f}ms')
    time.sleep(0.3)
"@
```

**预期**：
- 窗口 A 写入顺利，没有 `database is locked` 报错
- 窗口 B 每次查询 < 100 ms（WAL 下读不被写阻塞）
- 如果在旧的 DELETE 模式下，窗口 B 的查询会偶尔等几秒

### 验收 3 · PRAGMA 配置完整

```powershell
python -c @"
from backend.database import get_connection
conn = get_connection()
pragmas = ['journal_mode', 'busy_timeout', 'synchronous', 'cache_size',
           'temp_store', 'mmap_size', 'foreign_keys', 'wal_autocheckpoint']
for p in pragmas:
    v = conn.execute(f'PRAGMA {p}').fetchone()
    print(f'{p}: {v[0] if v else None}')
"@
```

**预期**：
```
journal_mode: wal
busy_timeout: 60000
synchronous: 1
cache_size: -65536
temp_store: 2
mmap_size: 268435456
foreign_keys: 1
wal_autocheckpoint: 1000
```

### 验收 4 · 项目能正常启动

```powershell
$env:FDSM_DATA_DIR = "C:\Users\LXG\fdsmarticles\data"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

**预期**：
- 看到 `Uvicorn running on http://127.0.0.1:8000`
- `Application startup complete.`
- 无任何 Traceback

访问 `http://127.0.0.1:8000/`，应该看到健康检查的 JSON。

**Ctrl+C 停掉**。

### 验收 5 · 备份目录里可以安全被 sqlite3 backup 命令读

这是为后面 §10 备份脚本预验证：

```powershell
sqlite3 data\fudan_knowledge_base.db ".backup data\_test_backup.db"
Get-Item data\_test_backup.db | Select-Object Name, Length
# 应该生成一个 ~700 MB 的备份文件
Remove-Item data\_test_backup.db
```

（如果没装 `sqlite3` CLI，Windows 上可以下载：https://www.sqlite.org/download.html 的 `sqlite-tools-win32-x86-*.zip`）

---

## 常见错误与排查

| 症状 | 原因 | 修复 |
|---|---|---|
| `sqlite3.OperationalError: database is locked` | 有旧 Python 进程抱着连接 | `Get-Process python | Stop-Process -Force` |
| `PRAGMA journal_mode` 返回 `delete` | WAL 切换失败 | 检查 DB 文件是否只读；检查是否有其他进程打开着；删 `-wal`、`-shm` 文件重试 |
| 启动时报 `unable to open database file` | `FDSM_DATA_DIR` 没设对 | `$env:FDSM_DATA_DIR` 指向含 `.db` 的目录 |
| pytest 里大量 `database is locked` | 测试 fixture 没关连接 | 这通常是测试本身的问题，不是 WAL 引入 |
| WAL 文件越来越大（几 GB） | `wal_autocheckpoint` 没触发 | 手动 `sqlite3 db 'PRAGMA wal_checkpoint(TRUNCATE)'` |
| `check_same_thread=False` 导致数据错乱 | 多个线程用同一个连接对象 | 代码里应该每个请求开新连接（`connection_scope()` 已经这么做） |
| 升级后某些测试断言数据不一致 | `isolation_level=None` 关掉了自动事务 | 在 test fixture 里确认 setUp/tearDown 有显式 `commit()` |

---

## 为什么不用其他方案

**为什么不用 `with connection:` 上下文管理器的隐式事务？**
因为 `isolation_level=None` 已经禁用。我们选择显式控制事务边界，让业务代码里的 `conn.commit()` 变得明确可读。

**为什么不加 SQLAlchemy？**
项目当前是裸 sqlite3，加 SQLAlchemy 需要重写大量代码，风险远大于收益。SQLite + WAL 在 704MB 规模下完全够用。真到扛不住时再迁 Postgres，见 [12_日常运维与迁CAS预案.md](./12_日常运维与迁CAS预案.md)。

**为什么不每次连接都 `PRAGMA journal_mode=WAL`？**
WAL 设置是**持久化**的——一次设好写入 DB 文件头，之后所有连接自动是 WAL。重复设无害但浪费一次往返。我们用 `_PRAGMA_APPLIED` 标志避免重复。

---

## 下一步

**去 [03_代码改造_FastAPI生产加固.md](./03_代码改造_FastAPI生产加固.md)** 开始 FastAPI 层改造。

做完 02 之前：
- **不要运行** `git stash pop` 把老改动合回来（会和 WAL 冲突）
- 可以本地继续跑项目，但要记得每次先设 `$env:FDSM_DATA_DIR`
- 观察 `data/fudan_knowledge_base.db-wal` 文件大小：每运行一段时间如果涨到几百 MB 就说明 checkpoint 没触发，可以手动 `PRAGMA wal_checkpoint(TRUNCATE)` 处理；正常情况下它会在几 MB 范围波动
