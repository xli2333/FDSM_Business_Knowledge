# Round 63：公众号模板链路对齐

## 诊断结论
- [x] 当前站点文章页主渲染链路没有接入 `公众号排版` 项目中的真实 `fudan_business_knowledge` 自动排版实现
- [x] 当前批处理虽然写入了 `html_web_zh / html_wechat_zh / html_web_en / html_wechat_en`，但这些 HTML 由本仓库的简化版 `backend/services/html_renderer.py` 生成，不是 `公众号排版/server/wechatOfficialPublisherService.mjs` 的模板渲染结果
- [x] 当前前端文章页仍使用 `ReactMarkdown` 渲染 `formatted_markdown_zh / translation.content`，没有消费已生成的 HTML 成品
- [x] 当前 `html_renderer.py` 使用了渐变 Hero、圆角卡片、阴影、`overflow: hidden` 等样式，和 `公众号排版` 中 `fudan_business_knowledge` 的严格安全规则相反
- [x] 当前 relayout prompt 只写了抽象风格说明，没有接入 `fudan_meta / fudan_section / soft_tab / minimal_rows / full_bleed` 这套显式结构化排版计划
- [x] 因此现在就算重跑一轮全量 Gemini，也只会继续产出“内容被清理过的 Markdown + 错的渲染器”，不会自动变成你截图里的样子

## 真实差距
- [x] 你提供的目标样式包含：灰蓝双色元信息条、居中章节标题、`#1 / #2` 序号、句内强调高亮、克制留白、轻量表格边框
- [x] 当前站点样式表现为：大 Hero 卡片、摘要卡、互动卡、Markdown prose 长文区，视觉语言完全不同
- [x] 当前站点即使数据库里已有 HTML 成品，也没有在文章页真正渲染出来

## 修复顺序
- [ ] P0 | 链路 | 把 `公众号排版` 项目里 `fudan_business_knowledge` 的真实渲染逻辑移植或接入当前环境
- [ ] P0 | 数据 | 为现有中英文文章生成与保存正确模板下的 HTML 成品，不先重跑正文
- [ ] P0 | 前端 | 文章页改为优先渲染 HTML 成品，而不是 `ReactMarkdown`
- [ ] P0 | 兼容 | 处理摘要、付费预览、英文页、相关文章页在 HTML 成品模式下的展示与回退
- [ ] P0 | 批量 | 在渲染器对齐后，批量重渲染全部现有文章 HTML；只有当结构化强调仍明显不足时，才考虑再补一轮模型级处理
- [ ] P0 | 验收 | 截图对比当前站点与公众号模板目标样式，确认强调句、标题层级、段距、表格和元信息条一致
