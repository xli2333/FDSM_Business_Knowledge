# Round5 检索质量升级与重排能力补强

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round6` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核蓝图中检索系统仍未落地的核心缺口，锁定 BM25 混合检索与二阶段重排范围
- [x] P0 | 依赖 | 引入并校验 `rank_bm25`，为 business-only 文库构建可复用的 BM25 语料索引
- [x] P0 | 搜索 | 将当前 smart search 升级为“BM25 + 向量 + 词项规则分”的混合召回
- [x] P0 | 搜索 | 为 smart search 增加可控的 AI 二阶段重排，优先重排 Top 候选结果
- [x] P0 | 验收 | 执行后端编译、搜索接口烟雾测试、前端 lint/build，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录检索升级与验收结果，并判断是否需要开启 `round6`

## Round5 验收记录

- 已安装并接入 `rank_bm25`
- smart search 已升级为 `词项规则分 + BM25 + FAISS 向量` 的混合召回
- smart search 已增加 AI 二阶段重排，重排器可返回候选相关性分并影响最终排序
- 后端验收：`python -m compileall backend` 通过；`/api/search` 的 smart/exact/date 模式烟雾测试通过
- 前端验收：`npm run lint`、`npm run build` 通过
- 结论：仍存在明确提升空间，主要在批量标签生成、专题自动生成和脚本化入口，因此开启 `round6`
