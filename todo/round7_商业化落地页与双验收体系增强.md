# Round7 商业化落地页与双验收体系增强

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round8` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核当前距离“可对外销售展示”的差距，锁定商业化落地页、线索留存与双验收范围
- [x] P0 | 后端 | 新增商业化概览接口与演示申请/线索留存接口，并保证可直接用代码烟雾测试验收
- [x] P0 | 前端 | 新增独立商业化落地页，补齐产品能力、场景、套餐、信任背书与明确 CTA
- [x] P0 | 前端 | 将导航、首页、页脚中的商业化入口串联起来，形成完整转化路径
- [x] P0 | 视觉验收 | 新增前端截图脚本，生成首页/商业化页/搜索页/AI 助理页的验收截图
- [x] P0 | 后端验收 | 新增后端烟雾测试脚本，覆盖核心接口、商业化接口与线索写入流程
- [x] P0 | 验收 | 执行后端编译、烟雾测试、前端 lint/build、视觉截图验收，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录截图与验收结果，并判断是否需要开启 `round8`

## Round7 验收记录

- 已新增商业化接口：`GET /api/commerce/overview`、`POST /api/commerce/demo-request`
- 已新增商业化落地页：`/commercial`
- 已将导航、首页、页脚的 CTA 串联到商业化页与演示申请入口
- 已新增后端验收脚本：`backend/scripts/smoke_test.py`
- 已新增视觉验收脚本：`frontend/scripts/visual_acceptance.mjs`
- 后端烟雾测试通过：健康检查、首页、搜索、聊天、商业化概览、演示申请写库均成功
- 视觉验收截图已生成：
  - `qa/screenshots/round7/desktop-home.png`
  - `qa/screenshots/round7/desktop-commercial.png`
  - `qa/screenshots/round7/desktop-search_q_AI_mode_smart.png`
  - `qa/screenshots/round7/desktop-chat.png`
  - `qa/screenshots/round7/mobile-home.png`
  - `qa/screenshots/round7/mobile-commercial.png`
- 前端验收：`npm run lint`、`npm run build`、`npm run visual:acceptance` 通过
- 后端验收：`python -m compileall backend`、`python backend/scripts/smoke_test.py` 通过
- 结论：仍存在明确提升空间，主要在演示线索的查看/导出和商业化交付运维文档，因此开启 `round8`
