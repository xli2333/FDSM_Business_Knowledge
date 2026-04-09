# Round6 后台生成能力与脚本入口补齐

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round7` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核蓝图中后台生成与脚本化能力的剩余缺口，锁定本轮范围
- [x] P0 | 后端 | 新增标签批量生成服务与 `/api/tags/batch-generate` 接口
- [x] P0 | 后端 | 新增专题自动生成服务与 `/api/topics/auto-generate` 接口
- [x] P0 | 脚本 | 补齐 `backend/scripts/generate_tags.py`、`generate_topics.py`、`migrate_db.py` 入口
- [x] P0 | 验收 | 执行后端编译、生成接口与脚本烟雾测试、前端 lint/build，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录生成结果与验收结论，并判断是否需要开启 `round7`

## Round6 验收记录

- 已新增标签批量生成服务与接口：`POST /api/tags/batch-generate`
- 已新增专题自动生成服务与接口：`POST /api/topics/auto-generate`
- 已补齐脚本入口：`backend/scripts/generate_tags.py`、`backend/scripts/generate_topics.py`、`backend/scripts/migrate_db.py`
- 生成结果：标签批量生成入口当前返回 `processed_count = 0`，说明现有业务文库已完成标签覆盖；专题自动生成已新增 `科技互联网观察`、`创业创新专题`、`文化传媒观察` 等自动专题
- 后端验收：`python -m compileall backend` 通过；生成接口与三个脚本入口均可执行
- 前端验收：`npm run lint`、`npm run build` 通过
- 结论：当前已覆盖蓝图中的核心产品能力、核心检索能力、AI 助理能力、专题能力、后台生成能力与脚本入口，没有必须立刻开启 `round7` 才能继续推进交付的明确缺口
