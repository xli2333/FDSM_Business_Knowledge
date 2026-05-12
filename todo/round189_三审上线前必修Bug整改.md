# round189 三审上线前必修 Bug 整改

## 本轮目标

依据 `docs/deployment_plan/21_上线前最终审核报告v3.md`，修复上云前必须关闭的 1 个 P0 与 2 个 P1：付费音视频播放鉴权、blue-green 共享 SQLite schema 竞态、metrics 端点暴露面。严格保持中文 Todo 做一项勾一项。

## 原子 Todo

- [x] 1. 复核 B1/B2/B3 涉及的后端路由、前端播放、Nginx、blue-green 和 metrics 当前实现。
- [x] 2. 修复 B1：媒体 stream 支持受控 query token，前端播放 URL 自动附带 CAS token，并避免 token 写入 Nginx access log。
- [x] 3. 为 B1 增加/更新后端与前端验收覆盖，验证付费媒体 stream 带 token 可访问、无 token 拒绝。
- [x] 4. 修复 B3：移除根路径 `/metrics`，只保留 `/api/metrics`，并在 Nginx 增加专用 allowlist location。
- [x] 5. 修复 B2：blue-green 部署脚本识别 schema 变更并默认阻止并行候选发布，要求走非并行维护窗口部署或显式强制。
- [x] 6. 更新部署文档、总交付清单和本轮 Todo 验收记录。
- [x] 7. 运行 compileall、pytest、npm build/audit、compose config、Docker 重建健康检查、发布包扫描。
- [x] 8. 判断是否仍有明确提升空间；如有则新开下一轮中文 Todo。

## 验收记录

- B1/B2/B3 代码与配置已落地：stream query token、前端播放 URL 拼 token、Nginx stream access_log off、后端 access log 关闭、根 `/metrics` 删除、`/api/metrics` allowlist、blue-green schema guard。
- `python -m compileall backend deploy` 通过。
- 三审专项：`pytest backend\tests\test_media_stream_auth.py backend\tests\test_metrics_routes.py -q`，5 项通过。
- 核心回归：`pytest backend\tests\test_auth_backend_resolution.py backend\tests\test_auth_membership_permissions.py backend\tests\test_media_service.py backend\tests\test_media_stream_auth.py backend\tests\test_metrics_routes.py -q`，17 项通过。
- 前端：`npm --prefix frontend audit` 0 vulnerabilities；`npm --prefix frontend run build` 通过。
- Compose：`.env.docker` 与 `.env.production.example + docker-compose.prod.yml` config 通过；本机真实 `.env.production` 未填 `REDIS_PASSWORD`，按预期不能作为生产 config 输入。
- Docker：`backend-web/backend-worker/backend-housekeeping/frontend` 重建并健康；`/healthz`、`/api/ready`、`/api/metrics` 通过；backend 直连 `/metrics` 返回 404。
- 日志泄漏：构造 `/api/media/audio/round189-missing/stream?token=round189-clean-token` 后，backend/frontend 容器日志未出现 token。
- Shell：Git Bash `bash -n` 校验 `preflight/acceptance/bootstrap_https/blue_green/rollback` 通过；`SCHEMA_CHANGE_REQUIRED=1` 运行 blue-green 按预期拒绝并行候选发布。
- 发布包：已重建 `_publish_clean/fdsmarticles-cloud-release.zip`，manifest 532 行，zip 约 4.13 MB；敏感文件、真实数据、备份、node_modules、dist、数据库文件扫描未命中。
- 全量后端：`pytest backend\tests -q` 收集 152 项，142 通过、10 失败，集中在历史内容运营排序隔离、媒体草稿删除外键、RAG 入库队列隔离/健壮性。按规则新开 `round190_全量后端测试失败收口.md`。
