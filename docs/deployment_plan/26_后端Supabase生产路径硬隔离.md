# 26 后端 Supabase 生产路径硬隔离

本文承接 round188。round187 已经移除前端 Supabase SDK 和 `VITE_SUPABASE_*` 构建变量，本轮继续把后端历史 Supabase 鉴权路径从生产默认路径中隔离出去。

## 改动范围

- `backend/config.py`
  - 新增 `VALID_AUTH_BACKENDS` 校验。
  - 新增 `ALLOW_LEGACY_SUPABASE_AUTH` 逃生开关，默认 `0`。
  - 生产环境显式配置 `AUTH_BACKEND=supabase` 或 `AUTH_BACKEND=dual` 时，如果未设置 `ALLOW_LEGACY_SUPABASE_AUTH=1`，启动直接失败。
- `backend/services/auth_service.py`
  - 生产默认不再因为 `AUTH_BACKEND=auto` 且 Supabase 变量存在而解析到 Supabase。
  - 未打开逃生开关时，生产 `auto` 只会优先解析 CAS；即使只有 Supabase 被配置，也会回落到 CAS 路径并保持未登录。
  - development/test 仍保留预览鉴权和历史路径，避免破坏本地测试。
- `deploy/preflight.sh`
  - 生产 `.env.production` 只允许 `cas/auto/dual/supabase` 四种枚举值。
  - 未打开 `ALLOW_LEGACY_SUPABASE_AUTH=1` 时，禁止 `AUTH_BACKEND=supabase/dual`。
  - 未打开逃生开关时，禁止填写 `SUPABASE_URL` 或 `SUPABASE_ANON_KEY`。
  - Windows Git Bash 下跳过 NTFS 不可靠的 `.env` mode 检查；Linux 私有云仍强制 `.env.production` 不可 world-readable。
- `.env.docker.example` / `.env.production.example`
  - 新增 `ALLOW_LEGACY_SUPABASE_AUTH=0`。
- `.github/workflows/cloud-release-qa.yml`
  - CI backend focused tests 纳入 `test_auth_backend_resolution.py`。
  - 前端 CI 同时执行完整 `npm audit` 与生产依赖审计。

## 逃生开关使用规则

正常生产必须保持：

```env
AUTH_BACKEND=cas
ALLOW_LEGACY_SUPABASE_AUTH=0
SUPABASE_URL=
SUPABASE_ANON_KEY=
```

只有在 CAS 故障且明确决定短时回退历史 Supabase 鉴权时，才允许临时设置：

```env
ALLOW_LEGACY_SUPABASE_AUTH=1
AUTH_BACKEND=supabase
SUPABASE_URL=https://...
SUPABASE_ANON_KEY=...
```

该回退必须重新执行 `deploy/preflight.sh`、`deploy/acceptance_check.sh` 和登录回归；问题解除后必须恢复 CAS。

## round188 本地 QA 结果

- `python -m pytest backend/tests/test_auth_backend_resolution.py backend/tests/test_auth_membership_permissions.py backend/tests/test_media_service.py`：12 项通过。
- `python -m compileall backend deploy`：通过。
- `bash -n deploy/preflight.sh`：通过。
- preflight 临时 `.env` 正负向检查：
  - 合法 CAS 配置通过。
  - `AUTH_BACKEND=supabase` 且未设置逃生开关会失败。
  - `AUTH_BACKEND=cas` 但填写 `SUPABASE_URL/SUPABASE_ANON_KEY` 会失败。
- 本地/生产 Compose config 通过。
- `npm run build` 与 `npm audit` 通过，前端仍为 0 vulnerabilities。
- CI 配置已同步新增鉴权解析单测和完整前端依赖审计。
- `backend-web`、`backend-worker`、`backend-housekeeping`、`frontend` 镜像重建并启动，容器均 healthy。
- `/api/ready` 与 `/healthz` 返回 200；容器内 `_resolved_backend()` 在 `.env.docker` 下返回 `cas`。
- 容器内 `pip check`、worker healthcheck、housekeeping 心跳均通过。
- 发布包重建通过，manifest 527 行，zip 约 3.92 MB；敏感文件、真实数据、备份、node_modules、dist 和数据库文件扫描未命中。
