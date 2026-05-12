# round183 上线前严格审核 v2 整改

## 本轮目标

处理 `docs/deployment_plan/20_上线前严格审核报告v2.md` 提出的新增和残留问题。本轮继续遵守“能在本机落地的代码/容器/脚本/文档直接改；必须依赖真实云资源的项转为脚本化 runbook 和 preflight 硬门槛”的规则。

## 原子 Todo

- [x] 1. 复核 v2 报告，标记本轮可代码化整改项和外部硬门槛项。
- [x] 2. 增加 `APP_ENV` 白名单校验，避免误配导致生产安全开关失效。
- [x] 3. 增加 debug header 纵深防御，非开发环境即使路由参数存在也不能构造调试身份。
- [x] 4. 补齐 Gunicorn `preload` 开关、worker connections、access log format。
- [x] 5. 增加 HTTPS bootstrap 脚本，把正式域名、证书签发、续期、Nginx 替换流程脚本化。
- [x] 6. 改造 `backup_sqlite.py`，实现压缩、GPG 加密、rclone/ossutil/本地目录异地推送和失败退出。
- [x] 7. 增加 CAS session 定时清理 housekeeping，并接入 compose 生产运行。
- [x] 8. 增加基础可观测能力：request id、结构化 JSON 访问日志、`/metrics` 指标端点。
- [x] 9. compose 增加 `deploy.resources` reservations，保留本地 compose 兼容 limits。
- [x] 10. 更新 env 示例、preflight、部署文档和 v2 整改记录。
- [x] 11. 运行编译、测试、compose config、Docker 重建、压测、备份脚本 dry-run/本地推送、发布包扫描。
- [x] 12. 回写本轮 Todo 与 v2 报告满足情况；若仍有明确本地提升空间，继续开下一轮 Todo。

## 本轮验收记录

- `python -m compileall backend deploy` 通过。
- `docker compose --env-file .env.docker config` 通过。
- `docker compose --env-file .env.production.example -f docker-compose.prod.yml config` 通过。
- `docker compose --env-file .env.docker up -d --build backend-web backend-worker backend-housekeeping` 通过，`backend-web/backend-worker/backend-housekeeping/frontend/redis` 均 healthy。
- `/api/ready` 200；`/api/metrics` 200 且包含 request counter 与 app info；`X-Request-Id` 可回传。
- 生产容器中 `X-Debug-User-Id` 返回 400；debug query 参数不会伪造登录用户。
- 静态媒体 Range 探针 `/articles/does-not-exist.mp3` 返回 206。
- 容器内 `pip check` 通过；`npm audit --omit=dev` 0 vulnerabilities；`npm run build` 通过。
- `python -m pytest backend/tests/test_auth_membership_permissions.py backend/tests/test_media_service.py` 通过，顺手修复了会员媒体权限测试依赖长期本地种子数据的问题。
- `python deploy/load_test.py --base-url http://127.0.0.1:18080 --requests 120 --concurrency 24` 通过，120 请求 0 failure，p95 542 ms；429 为限流保护，503 为本地 CAS 未启用的登录跳转特殊可接受场景。
- 容器内 `python -m backend.scripts.concurrency_write_probe --total 80 --workers 16 --hold-seconds 0.02` 通过，80/80 完成，0 错误。
- 异步 worker 死信队列验证通过：构造 `qa.unsupported` 任务后进入 failed 与 dead-letter，并已清理 QA 任务。
- 备份容器实际生成 gzip 备份通过；本地临时库 `file://` 异地推送验证通过。
- `deploy/preflight.sh` 与 `deploy/bootstrap_https.sh` 通过 Git Bash 语法检查；Windows 默认 WSL `bash` 不可用，不影响 Linux 私有云执行。

## 后续判断

v2 报告中的 P0/P1 可本地代码化整改项已闭环。仍有明确提升空间：CI/CD、蓝绿发布脚本、依赖全 pin、Supabase 代码路径退场、wechat runtime 独立容器化。因此继续开启下一轮 Todo。
