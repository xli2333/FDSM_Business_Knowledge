# Round2 搜索体验与商业化可用性增强

> 范围约束：本轮处理的文章有且仅有 `Fudan_Business_Knowledge_Data` 中的文章。
> 执行规则：按本文件逐项推进，完成一项勾一项；若本轮验收后仍存在明确提升空间，则新开 `round3` 中文 Todo 继续推进。

- [x] P0 | 规划 | 复核 Round1 实装与蓝图差距，锁定本轮“真实可用性增强”目标
- [x] P0 | 搜索 | 为搜索页补齐排序、标签筛选、栏目筛选、日期筛选与本地搜索历史
- [x] P0 | 搜索 | 将筛选状态与 URL 参数同步，保证页面可分享、可回退、可复现
- [x] P0 | AI 助理 | 为 AI 助理补齐会话历史列表与会话回看能力
- [x] P0 | RAG | 构建 business-only FAISS 向量索引并接入现有 hybrid 检索逻辑
- [x] P0 | 商业化 | 为首页补充明确的产品价值与使用入口表达，提升最小商业化可展示度
- [x] P0 | 验收 | 执行后端编译、关键接口烟雾测试、前端 lint/build，并确认无中文编码与 JSX/JAX 问题
- [x] P1 | 交付 | 回填本轮 Todo，记录索引与验收结果，并判断是否需要开启 `round3`

## Round2 验收记录

- 搜索页已补齐：排序、日期筛选、标签筛选、栏目筛选、本地搜索历史、URL 参数同步
- AI 助理已补齐：会话列表、会话回看、新建会话入口
- 首页已补齐：产品价值表达与最小商业化展示入口
- 向量检索已落地：生成 `faiss_index_business/index.faiss` 与 `faiss_index_business/index.pkl`
- 索引文件大小：`index.faiss = 142258221` 字节，`index.pkl = 20620832` 字节
- Gemini 运行时已修正：切换为可用 key，并将 embedding model 更新为 `models/gemini-embedding-001`
- 后端验收：`python -m compileall backend` 通过；`/api/search`、`/api/suggest`、`/api/chat`、`/api/chat/session/{id}`、`/api/summarize_article/{id}` 烟雾测试通过
- 前端验收：`npm run lint`、`npm run build` 通过
- 结论：仍存在明确提升空间，主要是热度机制、趋势内容展示与连续浏览体验，因此开启 `round3`
