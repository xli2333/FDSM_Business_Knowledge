# Round 136：知识库 RAG 商业化升级实施第一轮

## 对齐结论
- [x] 本轮进入正式开发，不再停留在方案讨论。
- [x] 由于当前环境里没有现成的 Elasticsearch / PostgreSQL 连接配置，本轮采取“生产架构先落地、检索 provider 可切换”的实施方式。
- [x] 本轮优先完成商业化升级的底座部分：数据库模型、正式收藏关系、异步入库任务流、chunk 级检索骨架、统一作用域检索接口。
- [x] 所有修改继续按中文 Todo 勾选推进，完成一项勾一项，验收后若仍有明确提升空间则继续开下一轮。

## 原子任务
- [x] P0 | Todo | 新建本轮中文 Todo，并以实施为目标持续回填。
- [x] P0 | 配置 | 扩展检索 provider 配置，支持生产 provider 与本地 provider 切换。
- [x] P0 | 数据库 | 增加 `article_versions` 表。
- [x] P0 | 数据库 | 增加 `article_chunks` 表。
- [x] P0 | 数据库 | 增加 `ingestion_jobs` 表。
- [x] P0 | 数据库 | 增加 `user_saved_articles` 表。
- [x] P0 | 数据库 | 增加 `user_library_profiles` 表。
- [x] P0 | 数据库 | 增加 `user_theme_profiles` 表。
- [x] P0 | 数据库 | 增加 `retrieval_events` 表。
- [x] P0 | 数据库 | 增加 `answer_events` 表。
- [x] P0 | 兼容迁移 | 将现有 `bookmark` 关系兼容回填到 `user_saved_articles`。
- [x] P0 | 收藏同步 | 修改点赞/收藏写入逻辑，让 `bookmark` 与正式收藏关系保持同步。
- [x] P0 | Chunking | 新建结构化切块服务。
- [x] P0 | Ingestion | 新建文章版本与入库任务服务。
- [x] P0 | Ingestion | 实现文章切块、版本哈希、任务状态流转。
- [x] P0 | Ingestion | 实现文章发布后的 RAG 入库触发。
- [x] P0 | Retrieval | 新建统一 Retrieval Service。
- [x] P0 | Retrieval | 实现本地 chunk provider。
- [x] P0 | Retrieval | 预留 Elastic provider 接口与配置。
- [x] P0 | Retrieval | 支持 `global_public` / `my_library` / `my_theme` / `selected_articles` 作用域。
- [x] P0 | 用户资料库 | 让 `我的资料库` 返回正式收藏数据，并补充资料库摘要字段。
- [x] P0 | 主题问答 | 将主题问答切到统一 chunk 检索服务。
- [x] P0 | 测试 | 补数据库迁移、入库任务、收藏同步和主题问答范围检索测试。
- [x] P0 | 验证 | 运行后端测试、前端构建与知识库真实验收。

## 结束标准
- [x] 数据模型完成商业化升级所需的核心扩展。
- [x] 新文章发布后会进入正式入库任务流，而不是仅刷新旧搜索缓存。
- [x] 主题问答与后续资料库问答已经建立在统一 chunk 检索接口之上。
- [x] 收藏关系已从旧书签行为兼容迁移为正式资料库关系。
- [x] 本轮代码与验收通过；若仍有明确提升空间，则进入下一轮。
