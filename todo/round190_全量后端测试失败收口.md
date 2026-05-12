# round190 全量后端测试失败收口

## 本轮目标

承接 round189 的全量 QA 结果，修复 `pytest backend\tests -q` 暴露的 10 个失败。优先区分真实生产 bug 与测试隔离脆弱点：生产 bug 改业务代码，历史数据污染导致的测试脆弱点改测试隔离或查询约束，不掩盖真实问题。

## 原子 Todo

- [x] 1. 复核 10 个失败的具体原因，按内容运营排序、媒体草稿删除、RAG 入库、嵌入 key 轮转四组归类。
- [x] 2. 修复媒体草稿删除外键失败：退回草稿后删除 draft 时必须安全清理 linked `media_items`，覆盖视频/音频/本地 seed。
- [x] 3. 修复 RAG 入库队列健壮性：跳过或修复 `version_id` 为空的旧 pending job，确保新排队任务可处理。
- [x] 4. 修复内容运营测试隔离：避免历史高日期文章污染 latest/column 断言，保持真实排序逻辑不变。
- [x] 5. 修复媒体付费详情测试期望或预览逻辑，确认无独立 preview 文件时不泄露本地完整媒体。
- [x] 6. 复核嵌入 key 轮转全局状态，消除测试顺序依赖。
- [x] 7. 运行失败子集、核心专项、全量后端 pytest，确认 152 项全部通过或记录剩余非阻塞项。
- [x] 8. 重新运行 compileall、npm build/audit、compose config、Docker 健康检查、日志 token 扫描、发布包重建扫描。
- [x] 9. 更新部署文档、总交付清单和本轮 Todo 验收记录。
- [x] 10. 判断是否仍有明确提升空间；如有继续新开中文 Todo。

## 验收记录

- 生产代码修复：媒体 draft 删除顺序、正式文章删除前外键断开、RAG pending job `version_id=None` 自修复。
- 测试隔离修复：内容运营/英文专栏/RAG backfill 使用高日期 fixture，pending job 清理旧队列，embedding key 轮转重置全局计数器，付费媒体无独立 preview 文件时测试期望不泄露完整媒体。
- 失败子集：11 项全部通过。
- 全量后端：`pytest backend\tests -q`，152 passed，17 warnings，用时约 7 分 21 秒。
- `python -m compileall backend deploy` 通过。
- `npm --prefix frontend audit` 0 vulnerabilities；`npm --prefix frontend run build` 通过。
- Compose：`.env.docker` 与 `.env.production.example + docker-compose.prod.yml` config 通过。
- Docker：backend-web、backend-worker、backend-housekeeping、frontend 重建并 healthy；`/healthz`、`/api/ready`、`/api/metrics` 通过；backend 直连 `/metrics` 返回 404。
- 日志泄漏：构造 `/api/media/audio/round190-missing/stream?token=round190-clean-token` 后，backend/frontend 容器日志未出现 token。
- 发布包：`_publish_clean/fdsmarticles-cloud-release.zip` 重建完成，manifest 533 行，zip 约 4.13 MB；敏感文件、真实数据、备份、node_modules、dist、数据库文件扫描未命中。
- 当前没有新的本地可明确落地的上线阻断项；剩余仍是正式域名、CAS 白名单、HTTPS 证书、真实备份凭据、监控告警项目和云端压测窗口等私有云资源验收项，不新开下一轮本地 Todo。
