# Round 139：知识库 RAG 商业化升级实施第四轮 Gemini 语义检索与整链路验收

## 对齐结论
- [x] 前三轮已经完成版本化入库、正式收藏、主题问答、资料库问答、公开搜索和 backfill / pending job 运维入口。
- [x] 当前仍有明确缺口：新的 chunk 检索尚未真正接入 Gemini embedding，整链路验收也还没有覆盖“管理员发布新文章 -> 用户加入主题 -> 用户发起 RAG 提问”的最终流程。
- [x] 本轮目标不是局部修补，而是补齐 Gemini 语义检索闭环，并把用户侧与管理员侧完整验收跑通。

## 原子任务
- [x] P0 | Todo | 新建第四轮中文 Todo，并明确 Gemini 语义检索与整链路验收缺口。
- [x] P0 | 数据库 | 增加 `article_chunk_embeddings` 表，用于持久化 chunk 级 embedding。
- [x] P0 | Embedding | 新建 Gemini chunk embedding 服务，支持文档 chunk 与 query 向量生成。
- [x] P0 | Ingestion | 将 chunk embedding 写入正式入库流水线，并与版本状态一起维护。
- [x] P0 | Retrieval | 将本地 provider 改为 lexical + Gemini chunk vector 混合检索。
- [x] P0 | 搜索兼容 | 移除公开搜索对旧 article-level FAISS 向量候选的依赖，统一到新 chunk 语义检索。
- [x] P0 | 测试 | 补 chunk embedding 持久化与混合检索测试。
- [x] P0 | 验收 | 新增“管理员发布新文章 -> 用户创建/加入知识库 -> 主题提问命中新文章”的真实验收脚本。
- [x] P0 | 验证 | 跑后端测试、前端构建、知识库旧验收脚本与新整链路验收脚本。
- [x] P0 | 回填 | 若整链路验收暴露问题，继续开下一轮 Todo 并修复，直到无明确缺口。

## 结束标准
- [x] 新 RAG 链路已经真实使用 Gemini chunk embedding，而不是仅靠 lexical chunk 检索。
- [x] 管理员发布的新文章可以进入正式入库并被后续知识库问答检索到。
- [x] 用户视角与管理员视角的关键流程均已通过真实验收。
- [x] 如果真实验收仍失败，必须进入下一轮 Todo；如果通过且无明确缺口，才允许结束。
