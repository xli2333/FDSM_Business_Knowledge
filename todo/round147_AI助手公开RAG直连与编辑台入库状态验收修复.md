[x] 确认 GPU 新发布文章在 `articles`、`article_versions`、`article_chunks`、`article_chunk_embeddings`、`ingestion_jobs` 中的真实状态，定位是入库失败还是检索链路偏旧。
[x] 梳理 AI 助理普通问答与命令问答当前走的公开检索路径，识别仍然依赖旧 `rag_engine.search_articles` 候选筛选的入口。
[x] 将 AI 助理公开问答改为以 chunk RAG 为主链路，保证新发布文章发布后能直接被公开问答命中，不再被旧 lexical 候选挡住。
[x] 保留站内搜索与推荐接口已有返回结构，避免前台现有页面和命令型问答被新检索改坏。
[x] 为公开问答新增后端回归测试，覆盖“刚发布并完成 embedding 的 GPU 文章可以被 `/api/chat` 命中”。
[x] 为编辑台文章详情补充 RAG 状态字段，至少展示是否已进版本库、当前版本状态、chunk 数、embedding 数、最近任务状态与错误信息。
[x] 在编辑台详情页渲染可读的 RAG 状态面板，让管理员能直接判断“是否进库”和“是否完成 embedding”。
[x] 为 AI 助理聊天面板补上等待态的三点浮动动画，用户发送后在 assistant 位置明确显示“正在思考”。
[x] 为前端等待态和编辑台状态面板跑构建验收，避免引入 JSX 或样式回归。
[ ] 跑后端测试、前端构建、定点 API 烟测，确认“发布 -> 入库 -> embedding -> AI 助理命中 -> 编辑台可见状态”整链路通过。
