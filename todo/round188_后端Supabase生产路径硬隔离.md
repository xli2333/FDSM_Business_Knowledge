# round188 后端 Supabase 生产路径硬隔离

## 本轮目标

承接 round187。前端 Supabase SDK 和构建变量已经退场，本轮继续收口后端历史兼容路径：生产默认只允许 CAS 鉴权，`supabase`/`dual` 后端分支必须显式打开逃生开关才可用于临时回退，避免 `.env.production` 误配导致 Supabase 路径重新暴露。

## 原子 Todo

- [x] 1. 复核后端鉴权分发和 preflight 当前行为。
- [x] 2. 增加生产 Supabase 历史路径显式逃生开关与默认禁用逻辑。
- [x] 3. 更新 `.env` 示例和 preflight，阻止生产误启用 `supabase`/`dual`/带 Supabase 密钥的配置。
- [x] 4. 增加后端单测覆盖鉴权后端解析。
- [x] 5. 更新部署文档和权威路线说明。
- [x] 6. 运行编译、单测、preflight 负向检查、Compose config、Docker 健康检查、发布包扫描。
- [x] 7. 回写本轮 Todo 与验收结果；若仍有明确提升空间，继续开启下一轮。

## 验收记录

- `python -m pytest backend/tests/test_auth_backend_resolution.py backend/tests/test_auth_membership_permissions.py backend/tests/test_media_service.py`：12 项通过。
- `python -m compileall backend deploy`：通过。
- `bash -n deploy/preflight.sh`：通过。
- preflight 临时 `.env` 正负向检查通过：合法 CAS 配置成功；`AUTH_BACKEND=supabase` 未开逃生开关失败；CAS 配置下误填 Supabase 密钥失败。
- 本地与生产 Compose config 通过。
- `npm run build` 与 `npm audit` 通过，前端 0 vulnerabilities。
- CI 已纳入 `test_auth_backend_resolution.py` 和完整前端 `npm audit`。
- `docker compose --env-file .env.docker up -d --build backend-web backend-worker backend-housekeeping frontend` 通过。
- backend-web、backend-worker、backend-housekeeping、frontend、redis 均 healthy，backup up。
- `/api/ready` 与 `/healthz` 返回 200；容器内 `auth_service._resolved_backend()` 返回 `cas`。
- 容器内 `pip check`、worker healthcheck、housekeeping 心跳均通过。
- 发布包重建完成：manifest 527 行，zip 约 3.92 MB；敏感文件、真实数据、备份、node_modules、dist、数据库文件扫描未命中。

## 下一轮判断

当前本地可闭环的上线前明确问题已处理完：前端 Supabase 依赖退场、后端 Supabase 生产路径硬隔离、依赖审计、preflight、Docker 健康检查和发布包扫描均已通过。剩余提升项主要依赖真实私有云资源，包括正式域名、CAS 白名单、HTTPS 证书、真实 GPG/rclone/OSS 凭据、Sentry/监控项目和线上压测窗口，因此不再新开本地整改 Todo；进入真实服务器验收阶段。
