# round181 部署文档一致性复查

## 本轮目标

复查 `docs` 下部署相关文档是否与当前 Docker、发布包、CAS、Nginx、压测和私有云执行命令一致。旧路线文档如仍有历史方案内容，不强行全文重写，但必须明确标注当前上云应以哪些文档和命令为准，避免实机部署时误用旧文件名或旧架构。

## 原子 Todo

- [x] 1. 梳理 `docs` 下部署相关文档清单。
- [x] 2. 对照当前实际文件：`Dockerfile.backend`、`frontend/Dockerfile`、`docker-compose.yml`、`docker-compose.prod.yml`、`.env.production.example`、`deploy/` 脚本。
- [x] 3. 标记旧文档中与当前实现不一致的部署口径。
- [x] 4. 新增当前部署文档对齐复查文档，列出权威执行入口、已对齐项、历史差异项和最终建议。
- [x] 5. 在旧入口文档顶部增加“历史方案/以 16-18 为准”的提示。
- [x] 6. 复查文档中关键路径、命令和发布包文件名。
- [x] 7. 回写本轮 Todo 和结论。

## 复查结论

- 当前真正可执行的私有云部署链路以 `docs/deployment_plan/16_私有云发布包_Nginx_HTTPS上线验收.md`、`docs/deployment_plan/17_最终压测性能预算与交付清单.md`、`docs/deployment_plan/18_部署文档对齐复查.md` 为准。
- 旧文档 `00-12` 和 `docs/云端部署方案_Docker上云完整指南.md` 中仍有历史设计内容，已在关键入口顶部加提示，避免误用旧文件名和旧命令。
- 主要历史差异包括：`Dockerfile.frontend` 已改为 `frontend/Dockerfile`；不再使用 `docker-compose.override.yml` 作为部署主线；不再用容器内 HTTPS 和 `HTTPS_PORT`；当前为宿主机 Nginx 终止 HTTPS；发布包路线暂不依赖 `IMAGE_TAG` 和镜像仓库 pull。
- `16` 已补充 `APP_PORT` 与宿主机 Nginx upstream 端口必须一致的提醒。
- 没发现 `16/17` 当前执行命令与实际文件存在阻塞级不一致。
- 文档修正后已重新生成 `_publish_clean/fdsmarticles-cloud-release.zip`，manifest `502` 行；扫描仅命中 `.env.docker.example` 与 `.env.production.example` 两个示例 env。
