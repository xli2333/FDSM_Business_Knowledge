# 25 前端 Supabase 依赖退场

本文承接 round187，用于把生产 CAS 路线下已经不用的前端 Supabase SDK、构建参数和文档口径收口。

## 改动范围

- 删除 `frontend/src/lib/supabaseClient.js`。
- 从 `frontend/package.json` 和 `frontend/package-lock.json` 移除 `@supabase/supabase-js`。
- `frontend/Dockerfile` 不再声明或注入 `VITE_SUPABASE_URL`、`VITE_SUPABASE_ANON_KEY`。
- `docker-compose.yml` 与 `docker-compose.prod.yml` 的 frontend build args 不再传递 `VITE_SUPABASE_*`。
- `.env.docker.example` 与 `.env.production.example` 中的 `SUPABASE_*` 仅保留为后端历史兼容变量，CAS 生产默认保持为空。

## 当前认证边界

- 生产主线：`AUTH_BACKEND=cas`、`CAS_ENABLED=1`。
- 前端：只走同域 `/api` 与 CAS 跳转回调，不再内联 Supabase URL 或 anon key。
- 后端：`supabase_auth_service.py` 仍作为历史兼容路径保留，本轮不硬删；生产通过 `AUTH_BACKEND=cas`、preflight 和 `APP_ENV` 白名单隔离。

## 验收标准

```bash
cd frontend
npm run build
npm audit --omit=dev

cd ..
docker compose --env-file .env.docker config
docker compose --env-file .env.production.example -f docker-compose.prod.yml config
docker compose --env-file .env.docker up -d --build frontend
powershell -ExecutionPolicy Bypass -File .\deploy\create_release_package.ps1
```

额外扫描：

```bash
rg -n "VITE_SUPABASE|@supabase|supabaseClient|createClient" frontend/src frontend/Dockerfile docker-compose.yml docker-compose.prod.yml frontend/package.json frontend/package-lock.json
```

预期：实际前端源码、前端 Dockerfile、compose 和前端依赖中不再出现 Supabase SDK 或 `VITE_SUPABASE_*`。

## 云端注意事项

- `.env.production` 里不要新增 `VITE_SUPABASE_URL` 或 `VITE_SUPABASE_ANON_KEY`。
- `SUPABASE_URL`、`SUPABASE_ANON_KEY` 对 CAS 生产环境应保持为空；如果未来临时回退到 Supabase 后端鉴权，需要单独开一轮回归。
- 发布包内仍允许包含 `.env.production.example` 的空占位变量，但不能包含真实 Supabase 项目地址或密钥。

## round187 本地 QA 结果

- 前端源码、前端 Dockerfile、compose 和前端依赖扫描无 `VITE_SUPABASE`、`@supabase`、`supabaseClient`、`createClient` 命中。
- `npm audit fix` 已清理构建期依赖漏洞，Vite 升级到 `7.3.2`，Rollup 升级到 `4.60.2`。
- `npm run build` 通过。
- `npm audit` 与 `npm audit --omit=dev` 均为 0 vulnerabilities。
- 本地/生产 Compose config 通过，frontend build args 只保留 `VITE_API_BASE_URL` 与 `VITE_ENABLE_DEBUG_AUTH`。
- `docker compose --env-file .env.docker up -d --build frontend` 通过，frontend 与 backend-web 均 healthy。
- `http://127.0.0.1:18080/healthz` 与 `/api/ready` 返回 200。
- frontend 镜像产物 `/usr/share/nginx/html` 扫描无 Supabase 关键字。
- 发布包重建通过，manifest 524 行，zip 约 3.91 MB；敏感文件、真实数据、备份、node_modules、dist 和数据库文件扫描未命中。
