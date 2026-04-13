# Round76 AI对话助手与RAG切换Gemini3Flash

## 本轮目标

- [x] 将 AI 对话助手与 RAG 主模型从 `gemini-2.5-pro` 切到 `gemini-3-flash`
- [x] 处理当前 Gemini `v1beta` 接口下 `gemini-3-flash` 直调 404 的现实兼容问题
- [x] 用测试与真实调用验证新链路可运行，不引入中文编码或 JAX/JSX 问题

## 已完成事项

- [x] `backend/config.py` 默认 `GEMINI_CHAT_MODEL` 改为 `gemini-3-flash`
- [x] `.env` 中实际运行配置改为 `GEMINI_CHAT_MODEL=gemini-3-flash`
- [x] 新增运行时模型别名解析：配置名 `gemini-3-flash` 自动映射到当前可用接口 `gemini-3-flash-preview`
- [x] `backend/services/ai_service.py` 与 `backend/scripts/article_ai_batch.py` 统一接入别名解析，避免旧脚本链路因 404 失效
- [x] 新增模型别名测试，确保 LangChain 构造阶段不会继续打到不可用模型名

## 验收结果

- [x] 真实 REST 探针确认：`gemini-3-flash` 在当前 `v1beta` 下返回 `404`
- [x] 真实 REST 探针确认：`gemini-3-flash-preview` 在当前 `v1beta` 下返回 `200`
- [x] 真实 LangChain 探针确认：映射后的 `gemini-3-flash-preview` 可正常返回内容
- [x] 第二轮检查确认仍存在旧文档与说明残留，已进入下一轮收口
