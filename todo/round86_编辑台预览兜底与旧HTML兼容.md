# Round 86：编辑台预览兜底与旧 HTML 兼容

## 已完成
- [x] P0 | 后端 | 编辑稿详情序列化时补齐 `final_html -> published_final_html -> html_web -> html_wechat` 的回退链。
- [x] P0 | 后端 | `html_web / html_wechat` 返回值互相兜底，避免旧稿只存一份 HTML 时前端取空。
- [x] P0 | 前端 | 预览 iframe 改为按 `final_html -> html_web -> html_wechat -> EMPTY_PREVIEW` 顺序兜底。
- [x] P0 | 验收 | 直接校验现有旧稿 `46` 与新稿 `65` 的详情接口，三份 HTML 字段均可取到。
- [x] P0 | 验收 | `python -m compileall backend`
- [x] P0 | 验收 | `npm run build`
