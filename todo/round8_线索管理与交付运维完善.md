# Round8 线索管理与交付运维完善

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round9` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核当前商业化闭环中还缺的运营与交付能力，锁定线索管理、导出与运维文档范围
- [x] P0 | 后端 | 新增演示申请列表与 CSV 导出接口，补齐线索管理闭环
- [x] P0 | 前端 | 新增轻量线索管理页，便于本地/演示环境直接查看预约记录
- [x] P0 | 文档 | 补齐商业化运行与验收文档，明确构建、验收、截图、索引与线索查看流程
- [x] P0 | 验收 | 执行后端编译、线索列表/导出烟雾测试、前端 lint/build/视觉截图，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录导出与文档结果，并判断是否需要开启 `round9`

## Round8 验收记录

- 已新增线索管理接口：
  - `GET /api/commerce/demo-requests`
  - `GET /api/commerce/demo-requests/export`
- 已新增线索管理页面：`/commercial/leads`
- 已新增商业化运行文档：`COMMERCIAL_RUNBOOK.md`
- 后端烟雾测试结果：
  - 演示申请写库成功，最新线索 `id = 2`
  - 线索列表返回成功，当前可读取到 `2` 条记录
  - CSV 导出返回成功，表头与最新记录均可读
- 视觉验收截图已补充：
  - `qa/screenshots/round7/desktop-commercial_leads.png`
- 前端验收：`npm run lint`、`npm run build`、`npm run visual:acceptance` 通过
- 后端验收：`python -m compileall backend`、`python backend/scripts/smoke_test.py` 通过
- 结论：当前已经覆盖业务文库、RAG 检索、AI 助理、专题体系、商业化落地页、演示申请、线索管理、运行文档与后台/视觉双验收链路，没有必须立刻开启 `round9` 才能继续推进交付的明确缺口
