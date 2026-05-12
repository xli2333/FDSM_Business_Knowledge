# round187 前端 Supabase 依赖退场

## 本轮目标

在生产 CAS 认证路线已经稳定的前提下，移除前端未使用的 Supabase client 依赖和构建参数，减少前端包体、供应链面和生产配置歧义。后端 Supabase 兼容路径本轮不硬删，只继续由 `AUTH_BACKEND=cas` 与 preflight 约束隔离。

## 原子 Todo

- [x] 1. 复核前端 Supabase 使用面，确认无运行时引用。
- [x] 2. 移除前端 Supabase client 文件和 npm 依赖，更新 package-lock。
- [x] 3. 移除 frontend Dockerfile 与 compose 中的 `VITE_SUPABASE_*` 构建参数。
- [x] 4. 更新部署文档，说明前端已不再接入 Supabase。
- [x] 5. 运行前端构建、npm audit、Compose config、Docker 前端重建、发布包扫描。
- [x] 6. 回写本轮 Todo 与验收结果；若仍有明确提升空间，继续开启下一轮。

## 验收记录

- 前端源码、Dockerfile、compose、`package.json`、`package-lock.json` 扫描无 `VITE_SUPABASE`、`@supabase`、`supabaseClient`、`createClient`。
- `npm audit fix` 后构建期依赖漏洞清零；`npm audit` 与 `npm audit --omit=dev` 均为 0 vulnerabilities。
- `npm run build` 通过，Vite 版本为 `7.3.2`。
- 本地与生产 Compose config 通过，frontend build args 不再包含 `VITE_SUPABASE_*`。
- `docker compose --env-file .env.docker up -d --build frontend` 通过，frontend 与 backend-web 均 healthy。
- `http://127.0.0.1:18080/healthz` 与 `/api/ready` 均返回 200。
- frontend 镜像产物扫描无 Supabase 关键字。
- 发布包重建完成：manifest 524 行，zip 约 3.91 MB；敏感文件、真实数据、备份、node_modules、dist、数据库文件扫描未命中。

## 下一轮判断

仍有明确提升空间：后端 `supabase`/`dual` 历史鉴权分支仍可被生产配置误启用。下一轮开启 round188，目标是在不硬删历史代码的前提下，对生产默认鉴权路径做更强隔离。
