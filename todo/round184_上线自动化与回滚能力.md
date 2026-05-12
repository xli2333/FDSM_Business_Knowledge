# round184 上线自动化与回滚能力

## 本轮目标

在 round183 已满足 v2 严格审核主项的基础上，继续补齐私有云上线前的自动化质量门、蓝绿发布/回滚脚本和发布包纳入，降低手工部署时的误操作风险。

## 原子 Todo

- [x] 1. 增加 CI 质量门工作流，覆盖后端编译/专项测试、前端安装/构建/审计、Compose 解析。
- [x] 2. 增加私有云蓝绿发布脚本，支持候选栈启动、验收、切流提示、失败自动清理。
- [x] 3. 增加私有云回滚脚本，支持快速回到上一版 compose 项目或镜像标签。
- [x] 4. 将 CI、蓝绿、回滚脚本纳入发布包白名单/manifest。
- [x] 5. 更新部署文档，补齐蓝绿发布与失败回滚路线。
- [x] 6. 运行脚本语法检查、Compose config、专项测试、发布包重建与扫描。
- [x] 7. 回写本轮 Todo 与验收结果；若仍有明确提升空间，继续开启下一轮。

## 本轮验收记录

- GitHub Actions 质量门文件已新增：`.github/workflows/cloud-release-qa.yml`。
- 蓝绿脚本已新增：`deploy/blue_green_deploy.sh`，支持候选栈、探针、Nginx 切流和失败清理。
- 回滚脚本已新增：`deploy/rollback_release.sh`，支持启动回滚颜色、探针、Nginx 切回和故障栈清理。
- `preflight.sh` 已纳入蓝绿/回滚脚本存在性检查。
- `preflight.sh`、`acceptance_check.sh`、`blue_green_deploy.sh`、`rollback_release.sh` 已统一支持去除 `.env` 的 UTF-8 BOM 与 CRLF 后再 source。
- `bash -n deploy/preflight.sh deploy/acceptance_check.sh deploy/bootstrap_https.sh deploy/blue_green_deploy.sh deploy/rollback_release.sh` 通过。
- `docker compose --env-file .env.docker config` 通过。
- `docker compose --env-file .env.production.example -f docker-compose.prod.yml config` 通过。
- `python -m pytest backend/tests/test_auth_membership_permissions.py backend/tests/test_media_service.py` 通过，7 passed。
- 本机临时 green 候选栈演练通过：`PROJECT_PREFIX=fdsmarticles-round184`、`GREEN_PORT=18081`，候选探针全部通过，随后已清理临时容器、网络与 Redis volume。
- `python -m compileall backend deploy` 通过。
- `deploy/create_release_package.ps1` 重建发布包通过，manifest 516 行，zip 约 3.9 MB。
- 发布包 manifest 已包含 `.github/workflows/cloud-release-qa.yml`、`deploy/blue_green_deploy.sh`、`deploy/rollback_release.sh`、`docs/deployment_plan/22_上线自动化与回滚.md`，且未命中真实 `.env`、数据目录、备份、node_modules、dist、数据库文件。

## 后续判断

CI、蓝绿发布和回滚能力已闭环。仍有明确提升空间：依赖全 pin/锁定、Supabase 历史路径退场、wechat runtime 独立容器化、真实云端恢复演练记录。因此继续开启下一轮。
