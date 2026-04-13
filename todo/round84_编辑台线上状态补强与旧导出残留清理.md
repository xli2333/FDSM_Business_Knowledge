# Round 84：编辑台线上状态补强与旧导出残留清理

## 已完成
- [x] P0 | 状态 | 为编辑稿详情补充“线上已发布但当前改动尚未重新发布”的判定。
- [x] P0 | 数据 | 用 `published_final_html` 固化线上正式 HTML，避免已发布稿在重新排版时提前污染正式文章页。
- [x] P0 | 前端 | 编辑台预览状态文案补上“线上文章已发布，当前改动待重新发布”。
- [x] P0 | 前端 | 删除前端 API 里的旧 `editorialHtmlExportUrl` 残留。
- [x] P0 | 脚本 | 更新 `backend/scripts/smoke_test.py`，把旧导出验收改为“导出能力已下线”的断言。
- [x] P0 | 测试 | 补充二次发布验收，验证重新自动排版后，正式文章页在二次发布前仍读取旧的线上 HTML，二次发布后才切换到新的 HTML。
- [x] P0 | 验收 | `python -m compileall backend`
- [x] P0 | 验收 | `pytest backend/tests/test_admin_editorial_media_features.py`
- [x] P0 | 验收 | `npm run build`
