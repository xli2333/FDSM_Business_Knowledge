# Round4 AI助理快捷指令与专题能力补齐

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round5` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核蓝图中 AI 助理与专题系统的剩余显性缺口，锁定本轮范围
- [x] P0 | AI 助理 | 为 `/summarize`、`/compare`、`/timeline`、`/today`、`/recommend` 实现后端快捷指令分发
- [x] P0 | AI 助理 | 在聊天页补充可点击的快捷指令入口，降低首次使用门槛
- [x] P0 | 专题 | 补齐专题时间线与专题洞察独立接口，和现有专题详情能力保持一致
- [x] P0 | 验收 | 执行后端编译、快捷指令与专题接口烟雾测试、前端 lint/build，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录指令与验收结果，并判断是否需要开启 `round5`

## Round4 验收记录

- AI 助理已支持：`/summarize`、`/compare`、`/timeline`、`/today`、`/recommend`
- 聊天页已增加可点击快捷指令按钮，降低首轮操作门槛
- 已补齐专题独立接口：`/api/topics/{id}/timeline`、`/api/topics/{id}/insights`
- 后端验收：`python -m compileall backend` 通过；五个快捷指令与专题独立接口烟雾测试通过
- 前端验收：`npm run lint`、`npm run build` 通过
- 结论：仍存在明确提升空间，主要在真正的 BM25 混合检索与二阶段重排，因此开启 `round5`
