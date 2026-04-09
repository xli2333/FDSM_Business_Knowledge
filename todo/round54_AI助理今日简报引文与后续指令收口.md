# Round 54：AI 助理今日简报引文与后续指令收口

## 待办
- [x] 修正英文 `/today` 引文被硬截断的问题，改成自然可读的摘要句
- [x] 压缩 `/today` 及相关文章的后续指令参数，避免整句级长参数
- [x] 跑一轮针对 `today` 命令的中英文验证并回填

## 验收重点
- [x] 英文 `Today Brief` 引文不再出现半句硬截断
- [x] `Today Brief` 返回的 follow-up 命令长度可读、可点、可继续执行

## 本轮结果
- `get_time_machine(language=...)` 的引文生成已改成自然句截断，不再在英文环境里截成半个单词。
- `Today Brief` 的 follow-up 不再返回带超长参数的命令串，改成自然语言继续操作按钮。
- 已完成 `python -m py_compile backend/routers/chat.py backend/services/catalog_service.py`。
- 已用本地降级路径验证中英文 `today` 命令输出与 follow-up。
