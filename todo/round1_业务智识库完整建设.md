# Round1 业务智识库完整建设

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round2` 中文 Todo 继续推进。

- [x] P0 | 规划 | 核对 `PROJECT_BLUEPRINT.md`、既有 todo 与当前代码现状，锁定本轮交付范围
- [x] P0 | 数据 | 统计并校验 `Fudan_Business_Knowledge_Data` 的真实文章数、内容格式与可复用结构化产物
- [x] P0 | 数据 | 将 SQLite 知识库重建为 business-only 数据源，并补齐标签、栏目、专题等扩展表
- [x] P0 | 数据 | 基于业务文章与已有 `gemini_flash_batch` 产物生成可落地的标签、栏目、专题初始数据
- [x] P0 | 后端 | 将 `backend/main.py` 重构为模块化后端结构，并实现首页、文章、标签、栏目、专题、搜索、对话、时光机接口
- [x] P0 | 后端 | 将检索与对话逻辑收口为 business-only，避免继续暴露 news/wechat 数据
- [x] P0 | 前端 | 将单文件前端重构为多路由多页面结构，保持现有视觉风格与色系
- [x] P0 | 前端 | 实现首页、搜索页、文章页、栏目页、标签页、专题页、时光机页、AI 助理入口
- [x] P0 | 验收 | 执行数据库构建、前端构建、后端导入级检查，修复中文编码与 JSX/JAX 错误
- [x] P1 | 交付 | 回填本轮 Todo、记录验收结果，并判断是否需要开启 `round2`

## Round1 验收记录

- 实际入库文章数：`2142`
- 已生成标签数：`2406`
- 已生成专题数：`8`
- 已生成栏目映射数：`4522`
- 前端验收：`npm run lint`、`npm run build` 通过
- 后端验收：`python -m compileall backend`、`fastapi.testclient` 关键路由烟雾测试通过
- 结论：当前没有必须立刻开启 `round2` 才能交付的明确缺口，Round1 结束
