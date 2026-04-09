# Round 64：真实复旦模板接入与全量 HTML 回填

## P0 链路修复
- [x] 接入 `公众号排版/server/wechatOfficialPublisherService.mjs` 的真实 `fudan_business_knowledge` 渲染桥
- [x] 后端文章详情接口补充 `html_web / html_wechat`
- [x] 后端英文翻译接口补充 `summary_html / html_web / html_wechat`
- [x] 摘要接口补充 `summary_html`
- [x] 文章页正文区改为优先渲染真实模板 HTML iframe
- [x] 文章页摘要区改为同一视觉语言的 HTML iframe
- [x] 去掉正文页原先错误的大 Hero / Markdown 正文骨架，改为接近公众号成品的单栏阅读结构

## P0 验证
- [x] 后端模块导入通过
- [x] 前端 `npm run build` 通过
- [x] 抽样验证真实模板输出已包含 `wechat-preview-shell`
- [x] 抽样验证真实模板输出已包含章节号 `#1`
- [x] 抽样验证真实模板输出已包含 soft-tab 强调句

## P0 全量回填
- [x] 新增批量回填脚本 `backend/scripts/rerender_fudan_html_batch.py`
- [x] 后续 relayout 批处理改为写入真实复旦模板 HTML，而不再写旧 `html_renderer.py`
- [x] 对全部可见文章执行全量 HTML 回填
- [x] 对失败分片补跑
- [x] 回填后再次执行一轮无署名清洁版覆盖，清掉模板默认 author 元信息块

## P0 验收
- [x] 运行文章页视觉验收脚本
- [x] 截图核对中文正文页
- [x] 截图核对英文正文页
- [x] 判断当前没有明确的下一轮提升空间，不新开 Round 65

## 结果
- [x] `1700 / 1700` 可见文章已写回真实复旦模板 HTML
- [x] 中文正文页与英文正文页都已接入真实模板 iframe 渲染
- [x] 摘要区已改为同风格 HTML 渲染，并清除模板默认署名块
