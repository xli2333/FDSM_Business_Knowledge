# round182 上线前严格审核 P0/P1 整改

## 本轮目标

按照 `docs/deployment_plan/19_上线前严格审核报告.md` 的建议，先关闭本地代码和部署配置可以直接修复的阻塞项。真实域名、证书、异地备份、合规评估、云防护等外部资源项不能在本机伪造完成，但必须转成上线前硬检查或明确的云端验收门槛。

## 原子 Todo

- [x] 1. 复核审核报告 P0/P1/P2 建议，标记本轮可代码化整改项。
- [x] 2. Redis 增加生产密码配置，`REDIS_URL` 改为带密码形式，健康检查同步鉴权。
- [x] 3. 前端生产构建强制关闭 debug auth，避免运维误传 `VITE_ENABLE_DEBUG_AUTH=1`。
- [x] 4. 前端容器不再挂载整个 `./data`，改为只读挂载 `audio`、`uploads/editorial`、`uploads/media`。
- [x] 5. 增加媒体私有文件鉴权下载流，付费音视频不再依赖可绕过的裸直链。
- [x] 6. Nginx 增加 internal media location、限流、HSTS、index.html no-cache、静态下载安全头。
- [x] 7. 生产 compose 增加容器资源限制、日志轮转、Gunicorn 可调参数和 readiness healthcheck。
- [x] 8. SQLite 补齐 cache/mmap/temp_store/wal_autocheckpoint PRAGMA。
- [x] 9. 上传增加应用层大小上限、基础 MIME/魔数校验、禁高危 HTML 上传。
- [x] 10. 生产 CORS 改为白名单硬失败，收窄 headers/methods。
- [x] 11. CAS 过期 session 清理、异步任务失败/重试语义补强。
- [x] 12. 补充云端硬门槛文档：HTTPS、异地加密备份、secrets、监控、合规、PostgreSQL 迁移边界。
- [x] 13. 运行编译、前端构建、compose config、Docker 重建、读写压测、worker 回归、发布包扫描。
- [x] 14. 回写本轮 Todo 与对 19 审核报告的满足情况。

## 本轮结果

- `19_上线前严格审核报告.md` 的判断合理：原状态只能算灰度/内测级，不能直接商用高并发公开上线。
- 本轮已完成本地可代码化整改：Redis 密码、生产 debug auth 强制关闭、frontend 挂载面收窄、媒体鉴权流、Nginx internal/限流/HSTS/no-cache、安全上传、CORS 硬失败、readiness、SQLite PRAGMA、CAS session 清理、异步任务重试和 dead-letter、资源限制、日志轮转、preflight 硬门槛。
- 外部依赖项没有伪造完成，已写入 `docs/deployment_plan/20_上线前严格审核整改记录.md`：真实 HTTPS、CAS 白名单、异地加密备份、监控告警、合规、安全组、回滚演练和 PostgreSQL 迁移边界必须在真实私有云验收。
- 本地 QA 通过：Python 编译、前端构建、Compose config、Docker 重建、依赖检查、读压测、写压测、worker retry/dead-letter、媒体直链阻断、X-Accel Range 流、发布包扫描。
