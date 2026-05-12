# 27 三审上线前必修 Bug 整改

> 本文承接 `21_上线前最终审核报告v3.md`。三审提出的 B1/P0、B2/P1、B3/P1 均合理，已作为上线前硬门槛完成代码、容器配置、Nginx 配置、脚本和专项测试收口。

## B1 付费音视频播放鉴权

原问题：浏览器原生 `<audio>` / `<video>` 请求不会携带前端 `fetch` 里的 `Authorization` header，导致已登录付费用户拿到 `/api/media/{kind}/{slug}/stream` 后播放仍被后端当作匿名请求拒绝。

当前实现：

- `backend/routers/media.py` 的 stream 路由同时接受 `Authorization` header 与受控 query 参数 `token`。
- `frontend/src/pages/MediaDetailPage.jsx` 只对本项目内部 `/api/media/.../stream` URL 自动追加当前 CAS session token，不处理外部 URL 或普通静态预览 URL。
- `deploy/nginx/default.conf` 与 `deploy/nginx/fdsmarticles-https.conf` 都为 `/api/media/(audio|video)/.../stream` 单独关闭 `access_log`，避免 query token 写入 Nginx 日志。
- `Dockerfile.backend` 关闭 Gunicorn/Uvicorn access log，只保留应用内结构化 JSON 请求日志；JSON 日志只记录路由 path，不记录 query，避免 token 写入后端容器日志。

上线验收：

```bash
# 未登录或无 token 的付费媒体应返回 401/403
curl -sS -o /dev/null -w "%{http_code}\n" \
  "https://knowledge.example.edu/api/media/audio/<paid-slug>/stream"

# 登录态页面中 audio/video Network 请求应带 token 参数，状态应为 200/206。
# 服务器日志中不得出现 token=。
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 backend-web frontend | grep 'token=' && exit 1 || true
sudo grep 'token=' /var/log/nginx/fdsmarticles.access.log && exit 1 || true
```

## B3 metrics 暴露面

原问题：后端同时注册 `/metrics` 与 `/api/metrics`，根路径 `/metrics` 对当前 Nginx 链路是死端/冗余端点，真正可达的 `/api/metrics` 缺少 Nginx IP 白名单。

当前实现：

- `backend/main.py` 删除根路径 `/metrics`，只保留 `/api/metrics`。
- `deploy/nginx/default.conf` 增加精确匹配 `location = /api/metrics`，只允许 `10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、`127.0.0.1`。
- `deploy/nginx/fdsmarticles-https.conf` 同步增加宿主机级 `/api/metrics` allowlist，并关闭该 location 访问日志。
- 后端仍保留 `METRICS_TOKEN`，形成 Nginx IP 白名单 + token 的双层保护。

上线验收：

```bash
curl -fsS -H "Authorization: Bearer ${METRICS_TOKEN}" \
  "http://127.0.0.1:${APP_PORT:-8080}/api/metrics" | grep fdsm_app_info

curl -sS -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:${APP_PORT:-8080}/metrics"
```

预期：`/api/metrics` 返回 Prometheus 文本；`/metrics` 不再由后端暴露。

## B2 blue-green 与 SQLite schema 变更

原问题：blue-green 候选栈和当前线上栈会共享同一份 `./data` SQLite。普通读流量短时并行可以接受，但带 schema DDL 的版本如果并行启动，候选栈执行 `ensure_runtime_tables()` 可能锁住线上栈。

当前实现：

- `deploy/blue_green_deploy.sh` 新增 `SCHEMA_CHANGE_GUARD=1` 默认保护。
- 若设置 `SCHEMA_CHANGE_REQUIRED=1`，脚本会默认拒绝 blue-green 并行候选发布。
- 若设置 `SCHEMA_CHANGE_BASE_REF=<git-ref>`，脚本会检测 `backend/database.py`、schema/migration 路径和新增 DDL/`ensure_runtime_tables` 差异，命中后默认拒绝。
- 只有人工复核后设置 `ALLOW_SCHEMA_BLUE_GREEN=1` 才能强制继续。

涉及数据库 schema 的版本推荐流程：

```bash
cd /srv/fdsm/app
docker compose --env-file .env.production -f docker-compose.prod.yml stop backend-web backend-worker backend-housekeeping
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build backend-web
bash deploy/acceptance_check.sh
docker compose --env-file .env.production -f docker-compose.prod.yml up -d backend-worker backend-housekeeping frontend redis backup
```

非 schema 版本仍可用 blue-green：

```bash
bash deploy/blue_green_deploy.sh
sudo SWITCH_NGINX=1 bash deploy/blue_green_deploy.sh
```

## 本地专项验收

- `python -m compileall backend` 通过。
- `pytest backend/tests/test_media_stream_auth.py backend/tests/test_metrics_routes.py -q`，5 项通过。
- `npm --prefix frontend run build` 通过，确认 JSX 无编译错误。
- `C:\Program Files\Git\bin\bash.exe -n deploy/blue_green_deploy.sh` 通过。
- `SCHEMA_CHANGE_REQUIRED=1 ... bash deploy/blue_green_deploy.sh` 按预期拒绝并行候选发布。
- Docker 重建后 backend-web、backend-worker、backend-housekeeping、frontend 均 healthy；构造带 query token 的 stream 请求后，backend/frontend 容器日志未出现 token。

最终发布包、Docker 重建、compose config、依赖审计、运行态健康检查和全量 pytest 结果见 `17_最终压测性能预算与交付清单.md` 的 round189/round190 小节；round190 已将全量后端测试从 142/152 修到 152/152。
