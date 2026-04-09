# Round28 英文 HTML 收口与运行时迁移修复

## 本轮目标

- [x] 修复英文 Web / WeChat HTML 仍沿用中文 `lang`、中文字体栈与中文模板文案的问题
- [x] 修复老库执行 `ensure_runtime_tables()` 时因 `source_article_id` 索引先于补列创建而失败的问题
- [x] 修复 AI 摘要导入编辑稿时 `excerpt` 混入 Markdown 标题符号的问题
- [x] 将数据库内已完成英译的历史英文 HTML 全量回填到新模板，避免平台继续读取旧成品
- [x] 做真实验收并判断是否还有明确的下一轮平台接入提升空间

## 本轮交付

- [x] `backend/services/html_renderer.py` 新增中英文模板分流，英文模板使用 `lang="en"`、英文文案与英文字体栈
- [x] `backend/scripts/article_ai_batch.py` 英文渲染链路不再复用中文副标题与中文标签
- [x] `backend/database.py` 迁移顺序修复，老数据库可正常补齐 `source_article_id` 与 `ai_synced_at`
- [x] `backend/services/editorial_service.py` 直连服务时自动确保运行时表结构就绪，并将 AI 摘要导入为纯文本摘要
- [x] 数据库内 `2142` 篇英文 HTML 已按新模板完成回填

## 验收标准

- [x] `article_ai_outputs.html_web_en` 与 `html_wechat_en` 不再批量出现 `lang="zh-CN"`
- [x] `article_ai_outputs.html_web_en` 与 `html_wechat_en` 不再批量出现 `PingFang SC`
- [x] AI 导入编辑稿成功，且 `excerpt` 为纯文本摘要
- [x] `python -m compileall backend` 通过
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] 当前范围内未再发现明确的平台接入收口缺口，本轮后不再自动新开下一轮 Todo
