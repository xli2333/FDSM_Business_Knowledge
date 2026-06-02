# GitHub 上传前最终检查

检查时间：2026-06-02

本文记录本地仓库上传 GitHub、交接给同事前的最后检查结论。口径以当前工作区为准。

## 1. 当前 Git 状态

- 当前分支：`archive_snapshot_20260413`
- 当前 HEAD：`8d38e70`
- 当前 remote：
  - `origin` -> `https://github.com/xli2333/FDSMNEWSCOLLECTION`
  - `archive` -> `https://github.com/xli2333/FDSM_Business_Knowledge.git`
- 当前工作区不是干净状态，`git status --porcelain` 约 173 条。

上传前必须先决定是：

1. 全量交接当前工作区。
2. 只提交最近六大板块、管理员编排、前端展开、交接文档相关改动。

如果选择第 2 种，不要直接 `git add .`。

## 2. 最近需要纳入交接的业务改动

最近几轮已经完成并验证的重点：

- 六大板块低风险改造：`todo/round191_六大板块栏目低风险改造.md`
- 访客隐藏时光机入口：`todo/round192_访客隐藏时光机入口.md`
- 管理员板块与专题文章编排：`todo/round193_管理员板块与专题文章编排对齐.md`
- 栏目文章列表逐步展开：`todo/round194_栏目文章列表逐步展开.md`

核心代码涉及：

- `backend/config.py`
- `backend/database.py`
- `backend/models/schemas.py`
- `backend/routers/admin.py`
- `backend/services/catalog_service.py`
- `backend/services/content_localization.py`
- `backend/services/content_operations_service.py`
- `backend/tests/test_admin_content_operations.py`
- `frontend/src/App.jsx`
- `frontend/src/api/index.js`
- `frontend/src/lib/roleExperience.js`
- `frontend/src/pages/AdminContentOperationsPage.jsx`
- `frontend/src/pages/ColumnPage.jsx`
- `frontend/src/pages/HomePage.jsx`
- `frontend/src/components/layout/Navbar.jsx`

这些改动已经做过本地构建、后端测试、Docker 运行态验证。

## 3. 归档目录判断

当前存在 `unused_project_assets/`，其中包括：

- `pretext-main/`
- `pretext/`
- `frontend-src-lib/pretextRichInline.js`

该目录已有 `unused_project_assets/README.md` 解释归档原因。当前 git 状态同时显示原路径下 `pretext-main/`、`pretext/`、`frontend/src/lib/pretextRichInline.js` 被删除。

如果确认这些资产已不再作为运行时、构建、发布包或业务代码依赖，应把以下内容作为同一个归档提交处理：

- 原路径删除：`pretext-main/`、`pretext/`、`frontend/src/lib/pretextRichInline.js`
- 新归档目录：`unused_project_assets/`
- 归档说明：`unused_project_assets/README.md`

如果不能确认，应先不要提交这些删除，避免同事误以为这是业务功能变更的一部分。

## 4. 文档与交接资料

当前建议一并提交：

- `交接文档/`
- `docs/六大板块需求低风险筛选.md`
- `docs/六大板块栏目复用改名方案.md`
- `docs/复旦商业知识 · 六大板块详细规格-宋朝阳反馈.pdf`
- `docs/服务器与Gemini接口申请附件.md`
- `todo/round191_六大板块栏目低风险改造.md`
- `todo/round192_访客隐藏时光机入口.md`
- `todo/round193_管理员板块与专题文章编排对齐.md`
- `todo/round194_栏目文章列表逐步展开.md`

`docs/` 下已有上线、部署、审计、项目手册类文档。若目标是运行代码仓库，可以保留；若目标是最小生产发布包，发布包脚本或压缩包应排除文档目录。

## 5. 密钥与敏感信息

已确认：

- `.env`、`.env.docker`、`.env.production` 存在于本地，但被 `.gitignore` 忽略。
- 被 git 跟踪的是 `.env.docker.example` 和 `.env.production.example`。
- `frontend/dist` 被忽略。
- 文档/TODO/交接资料中的 `AIza...` 形态 Gemini/Google API key 已替换为 `<GEMINI_API_KEY>`。
- 复扫 `docs/`、`todo/`、`交接文档/` 后，没有发现 `AIza...` 或 `sk-...` 形态 key-like secret。

仍需注意：

- 不要使用 `git add -f .env*`。
- 不要把本地数据库、上传文件、音频、FAISS 索引、日志、备份作为代码仓库提交。
- Docker 当前运行数据保留在 `data/`；根目录旧数据库和同名素材副本已归档到 `archive/legacy_pre_knowledge_base/local_runtime_duplicates_20260602/`，该目录被 Git 忽略。
- 数据交接应走单独安全渠道；最新本地数据库压缩备份为 `backups/fudan_knowledge_base.handoff_20260602-142839.db.gz`。
- 如果曾经把真实 key 写进旧 commit，公开仓库前仍应轮换这些 key。

## 6. 当前大文件风险

检查结果：

- 已跟踪文件中没有超过 50MB 的文件。
- 未跟踪文件中最大的是 `unused_project_assets/pretext-main/accuracy/*.json`，单个约 1.63MB。
- `data/`、`backups/`、`archive/legacy_pre_knowledge_base/`、`_publish_clean/` 均被忽略；这些本地数据和归档不会进入 GitHub。
- 当前没有触发 GitHub 单文件 100MB 限制的待提交可见文件。

## 7. 已完成的验证

最近一次功能验证包括：

- `python -m compileall backend/services/content_operations_service.py backend/routers/admin.py backend/models/schemas.py backend/services/catalog_service.py`
- `pytest backend/tests/test_admin_content_operations.py -q`
- `npm run build`
- `docker compose --env-file .env.docker up -d --build frontend`
- `docker compose --env-file .env.docker ps`
- Docker 前端运行态 chunk 检查，确认内容运营页包含逐步展开控制。

当前 Docker 状态：

- `backend-web` healthy
- `backend-worker` healthy
- `backend-housekeeping` healthy
- `frontend` healthy
- `redis` healthy

## 8. 推荐提交方式

为了减少交接风险，建议分三类提交：

1. `feature: align six-section content operations`
   - 六大板块、管理员编排、专题文章管理、前端展开、相关测试。
2. `docs: add handoff and deployment materials`
   - `交接文档/`、`docs/` 需求与部署资料、`todo/round191` 至 `round194`。
3. `chore: archive unused pretext assets`
   - `pretext-main/`、`pretext/`、`frontend/src/lib/pretextRichInline.js` 删除，以及 `unused_project_assets/`。

如果想快速交接，也可以合并为一个提交，但 commit message 必须说明同时包含业务功能、文档、历史资产归档。

## 9. 上传前命令建议

先复查：

```powershell
git -c core.quotepath=false status --short
git diff --check -- .
npm run build
pytest backend\tests\test_admin_content_operations.py -q
```

确认提交范围后再执行：

```powershell
git add <明确要提交的路径>
git status --short
git commit -m "feature: align six-section content operations handoff"
git push archive archive_snapshot_20260413
```

如果要推到 `origin`，先确认 `origin` 是否就是交接同事要看的仓库；当前 `origin` 和 `archive` 指向不同仓库。

## 10. 交接提醒

交接给同事时应明确：

- 当前代码可在 Docker 本地跑通，但正式生产仍需要真实域名、CAS、Gemini key、Redis 密码、备份目标、服务器架构验证。
- 本地真实 `.env*` 不在仓库里，需要通过安全渠道单独交接。
- 数据资产不应通过 GitHub 交接，应通过单独数据包或服务器数据目录交接。
- 如果是公开 GitHub 仓库，上传后仍建议立刻轮换曾出现在历史文档或本地环境中的 Gemini key。
