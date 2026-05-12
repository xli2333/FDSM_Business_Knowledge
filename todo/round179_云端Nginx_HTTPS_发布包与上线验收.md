# round179 云端 Nginx HTTPS 发布包与上线验收

## 本轮目标

Docker 本地生产闭环、Worker、高并发写入治理、CAS 生产身份入口已经完成。下一轮进入真正上传私有云前的发布包和 HTTPS 反向代理闭环：保证服务器只需要准备 `.env.production`、数据目录、域名证书和 Docker Compose，就能按步骤启动、检查、回滚。

## 原子 Todo

- [x] 1. 梳理当前 Docker 文件、compose、Nginx、环境样例和部署文档，确认哪些文件必须随发布包走。
- [x] 2. 新增或完善生产 `.env.production.example`，覆盖端口、域名、CAS、Redis、数据库、备份、AI、CORS。
- [x] 3. 新增云端 `docker-compose.prod.yml` 或确认现有 compose 可直接作为私有云单机生产 compose。
- [x] 4. 新增外层 Nginx HTTPS 反向代理示例，覆盖 80->443、证书路径、`/api`、静态前端、上传和音频资源。
- [x] 5. 新增上线前服务器目录结构文档：`/srv/fdsm/app`、`data`、`backups`、`logs`、`secrets`。
- [x] 6. 新增一键预检脚本或命令清单：Docker、端口、磁盘、`.env`、数据文件、健康接口、CAS 配置。
- [x] 7. 新增发布包生成脚本或文档，明确排除 node_modules、__pycache__、本地 `.env`、临时 QA 产物。
- [x] 8. 新增上线验收脚本或 checklist：健康、首页、公开 feed、CAS login、debug header、Worker、备份、DB quick_check。
- [x] 9. 新增回滚步骤：镜像回退、代码回退、数据库备份恢复、CAS 关闭回退。
- [x] 10. 本地构建和 Docker 配置校验通过。
- [x] 11. 执行容器健康 QA：web、worker、frontend、redis、backup 全部 healthy/up。
- [x] 12. 执行发布包 QA：确认打包文件清单不含敏感 `.env` 和本地数据。
- [x] 13. 执行上线清单 dry-run：所有命令可执行或有明确服务器侧占位。
- [x] 14. 回写本轮 Todo 勾选状态、QA 结果和下一轮最终压测/性能预算 Todo。

## 验收标准

- 私有云服务器部署人员可以按文档从空目录完成启动。
- 生产域名、HTTPS、CAS service URL、CORS 变量关系清晰。
- 发布包不包含本地密钥、`.env.docker`、数据库、备份或上传文件。
- 上线前、上线后、回滚三个阶段都有明确命令。

## QA 结果

- 新增 `.env.production.example`，覆盖端口、正式域名、CAS、Redis、SQLite/PostgreSQL 预留、备份、AI、CORS。
- 新增 `docker-compose.prod.yml`，外层只把 frontend 绑定到 `127.0.0.1:${APP_PORT}`，适合宿主机 Nginx 反代。
- 新增 `deploy/nginx/fdsmarticles-https.conf`，覆盖 80->443、证书路径、代理头、上传大小、访问日志。
- 新增 `deploy/preflight.sh`、`deploy/acceptance_check.sh`、`deploy/create_release_package.ps1`。
- 新增 `docs/deployment_plan/16_私有云发布包_Nginx_HTTPS上线验收.md`，覆盖目录结构、首次部署、HTTPS、验收和回滚。
- `docker compose --env-file .env.production -f docker-compose.prod.yml config` 通过，本地 dry-run 使用 `APP_PORT=18081`、CAS 关闭。
- 第一次发布包脚本发现旧版 .NET 不支持 `Path.GetRelativePath`，已改成兼容 URI 相对路径实现。
- `powershell -ExecutionPolicy Bypass -File .\deploy\create_release_package.ps1` 通过，生成 `_publish_clean/fdsmarticles-cloud-release.zip`，大小约 4.0 MB，manifest 496 个文件。
- 发布包扫描通过：未发现真实 `.env`、`.env.docker`、`.env.production`、数据库、`data/`、`backups/`、`node_modules/`、`frontend/dist/`、`qa/`、`reports/`；仅保留 `.env.docker.example` 和 `.env.production.example`。
- 当前本地 Docker 容器健康：web、worker、frontend、redis healthy，backup up。
- 本地上线检查 dry-run：`/healthz`、`/api/health?details=1`、`/api/home/feed?language=zh` 均返回 200，DB 诊断脚本通过，Worker healthcheck 通过。

## 下一轮

进入 `round180_最终压测_性能预算与上云交付清单.md`，做最终压测、性能预算、服务器配置建议复核和交付清单收口。
