# 14 数据库并发治理与 PostgreSQL 切换准备

## 当前阶段结论

第一阶段私有云 Docker 部署继续使用 SQLite + WAL，适合单机、小团队编辑和公开阅读流量。round176 已把 AI 长任务拆到 Redis + Worker，round177 继续处理剩余的数据库写入争用风险：统一运行期写事务、增加锁等待重试、暴露数据库健康详情。

这不是最终高并发数据库形态。只要出现多台后端实例、较高频用户行为写入、持续 RAG 入库或商业化会员订单写入，就应迁移到 PostgreSQL。

## SQLite 保留范围

- 文章、栏目、标签、专题等内容数据。
- 编辑台草稿、媒体草稿、AI 生成结果。
- 第一阶段运行表：`async_tasks`、`ingestion_jobs`、`article_view_events`、`retrieval_events`、`answer_events`。
- 单机 Docker Compose 中的快速备份和恢复。

## 必须优先迁移到 PostgreSQL 的表

- 身份与会员：`business_users`、`user_memberships`、`membership_audit_events`、`billing_orders`。
- 高频用户行为：`article_view_events`、`article_reactions`、`user_saved_articles`、`user_follows`。
- 任务与审计：`async_tasks`、`ingestion_jobs`、`retrieval_events`、`answer_events`。
- 编辑发布核心：`editorial_articles`、`article_versions`、`article_chunks`、`article_chunk_embeddings`。

## 文件资产仍不进数据库

- 上传文件继续走 `/data/uploads`，云端正式形态建议迁到对象存储。
- 音频文件继续走 `/data/audio`，云端正式形态建议迁到对象存储或 CDN 源站。
- FAISS/RAG 本地索引继续走 `/data/rag_chunk_index` 或 `/data/faiss_index_business`，后续可替换成 Elasticsearch/OpenSearch/向量数据库。

## 本轮新增配置

```env
DATABASE_BACKEND=sqlite
DATABASE_URL=
DB_WRITE_RETRY_ATTEMPTS=5
DB_WRITE_RETRY_BASE_DELAY_SECONDS=0.05
DB_SLOW_QUERY_MS=750
DB_OBSERVABILITY_ENABLED=1
```

`DATABASE_URL` 先只作为 PostgreSQL 迁移预留变量，不改变当前 SQLite 路径。真正切换 PostgreSQL 时，需要单独做 schema migration、数据迁移、连接池和 ORM/SQL 适配。

## 上云前检查命令

```bash
docker compose --env-file .env.docker exec backend-web python -m backend.scripts.db_diagnostics
curl "http://127.0.0.1:${APP_PORT:-8080}/api/health?details=1"
```

健康结果应满足：

- `quick_check` 为 `ok`。
- `pragma.journal_mode` 为 `wal`。
- `writable_probe.ok` 为 `true`。
- `runtime_table_counts.async_tasks` 能正常返回。
- 并发写入 QA 不出现 `database is locked`。

## PostgreSQL 切换步骤草案

1. 云端创建 PostgreSQL 实例，开启自动备份和监控。
2. 增加应用侧数据库抽象或迁移到 SQLAlchemy/Core，避免继续散落 sqlite 专属 SQL。
3. 将 schema 转换为 PostgreSQL DDL，处理 `INTEGER PRIMARY KEY AUTOINCREMENT`、`ON CONFLICT`、JSON 字段和索引差异。
4. 停写 SQLite，导出内容表和运行表。
5. 导入 PostgreSQL，执行行数、关键字段和抽样内容校验。
6. 后端切 `DATABASE_BACKEND=postgresql` 与 `DATABASE_URL`。
7. 保留 SQLite 只读快照一轮发布周期，确认无数据回滚需求后归档。
