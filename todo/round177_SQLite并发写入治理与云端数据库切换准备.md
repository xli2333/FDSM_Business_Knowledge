# round177 SQLite 并发写入治理与云端数据库切换准备

## 本轮目标

在 round176 已经把 AI 长任务拆到 Redis + Worker 的基础上，继续降低上云后数据库写入争用风险。当前 Docker 闭环仍使用 SQLite，适合第一阶段私有云单机/小规模部署，但高并发下写入仍然是主要瓶颈。本轮先做不破坏现有业务的治理：统一写入重试、记录慢 SQL/锁等待、收敛运行期写入点，并补齐向 PostgreSQL 迁移前的配置和文档接口。

## 原子 Todo

- [x] 1. 扫描后端所有 SQLite 连接和直接写入点，区分公开读、后台写、任务写、审计写、上传写。
- [x] 2. 确认当前 `connection_scope` 和 `get_connection` 的事务边界，找出缺少 busy timeout 或提交控制的路径。
- [x] 3. 新增数据库运行配置：写入重试次数、重试间隔、慢 SQL 阈值、写入观测开关。
- [x] 4. 新增统一写事务 helper，封装 `BEGIN IMMEDIATE`、锁等待重试、提交、回滚和错误日志。
- [x] 5. 将异步任务状态更新改为统一写事务，避免 Worker 高峰期直接裸写。
- [x] 6. 将高频会员/访问/审计类运行表写入纳入统一 helper 或明确标记为下一轮延后。
- [x] 7. 新增数据库健康详情接口或扩展 `/api/health`，输出 WAL、quick_check、运行表可写性和任务表状态。
- [x] 8. 新增容器内数据库诊断脚本，便于上云前一键检查 SQLite 文件、WAL、索引、表大小和 quick_check。
- [x] 9. 新增 PostgreSQL 迁移准备文档，明确哪些表必须迁移、哪些文件资产仍走对象存储/卷挂载。
- [x] 10. 在 Docker 环境样例中补齐未来 PostgreSQL 变量，但默认继续 SQLite，避免当前部署破坏。
- [x] 11. 本地 Python 编译通过。
- [x] 12. Docker 重新构建并启动通过。
- [x] 13. 执行数据库健康 QA：容器内 quick_check、健康接口、写入测试均通过。
- [x] 14. 执行并发写入 QA：并发创建/更新异步任务或轻量运行记录，不出现 database is locked。
- [x] 15. 执行公开读 QA：并发写入期间 `/api/health` 与公开 feed 仍可响应。
- [x] 16. 回写本轮 Todo 勾选状态、QA 结果和下一轮 CAS/生产身份接入 Todo。

## 验收标准

- SQLite 写入路径有统一的重试和错误观测，不再只依赖默认连接行为。
- Worker 与 Web 同时写运行表时不会轻易触发 `database is locked`。
- 健康检查能暴露数据库文件状态、WAL 状态和关键运行表可用性。
- Docker 默认配置仍能本地一键启动，不强制要求 PostgreSQL。
- PostgreSQL 切换边界清晰，后续可以按文档迁移而不是临时猜。

## QA 结果

- `python -m compileall backend` 通过。
- `python -m backend.scripts.db_diagnostics` 本地通过，`quick_check=ok`，`journal_mode=wal`，`writable_probe.ok=true`。
- `docker compose --env-file .env.docker config` 通过，web/worker 均带上数据库治理环境变量。
- `docker compose --env-file .env.docker build backend-web backend-worker` 通过。
- `docker compose --env-file .env.docker up -d --force-recreate backend-web backend-worker frontend` 后 web、worker、frontend、redis、backup 均处于运行状态。
- 容器健康详情 `GET /api/health?details=1` 通过，返回 `quick_check=ok`、WAL 文件信息、运行表计数、`async_tasks` 状态计数、`writable_probe.ok=true`。
- 容器诊断脚本 `python -m backend.scripts.db_diagnostics` 通过。
- 并发写入 QA：60 个并发 `async_tasks` 写事务，16 workers，全部完成，错误列表为空；慢写日志按阈值输出，无 `database is locked`。
- 并发公开读 QA：写入期间对 `/api/health` 与 `/api/home/feed?language=zh` 发起 40 个并发请求，全部返回 200。
- 回归 QA：创建文章 `229` 后异步摘要任务 `967648479e0f4bec9c42eee2d094e09b` 完成，Worker 正常消费。

## 延后项

会员、访问、审计、RAG 入库等高频写表已在 `docs/deployment_plan/14_数据库并发治理与PostgreSQL切换准备.md` 标为 PostgreSQL 优先迁移范围。本轮先把 `async_tasks` 作为统一写事务试点，避免一次性改动所有业务写路径带来回归。

## 下一轮

进入 `round178_CAS生产身份接入与云端安全闭环.md`，处理生产身份、管理员权限和上云安全闭环。
