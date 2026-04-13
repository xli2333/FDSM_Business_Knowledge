# Round 83：编辑台与公众号排版链路重构对齐

## 已完成
- [x] P0 | 审计 | 核对正式站当前编辑台、原 `公众号排版` 工程、文章详情页和发布链路，确认真实差距。
- [x] P0 | 审计 | 确认正式站已经有 `fudan_wechat_renderer` 桥接层，可直接复用原公众号排版引擎，不需要重写整套模板系统。
- [x] P0 | 数据 | 为 `editorial_articles` 增补 AI 标签建议、管理员移除标签、AI 栏目建议、栏目人工覆盖、最终 HTML、排版元数据、发布前校验等字段。
- [x] P0 | 数据 | 为 `editorial_articles` 增补 `published_final_html`，分离“当前工作稿 HTML”和“线上正式 HTML”。
- [x] P0 | 服务 | 序列化编辑稿详情时同时返回 `tags / ai_tags / removed_tags / final_html / render_metadata / publish_validation`。
- [x] P0 | 服务 | 自动排版改为同时产出排版稿 Markdown、最终 HTML 和排版元数据快照。
- [x] P0 | 服务 | 最终 HTML 改走真实的复旦公众号排版桥接器，不再使用旧的简化 `html_renderer` 作为正式成品来源。
- [x] P0 | 服务 | 自动打标签改为保留 AI 建议标签、管理员最终保留标签和已移除标签三份状态。
- [x] P0 | 服务 | 自动打标签后自动给出 AI 栏目建议；管理员手动改栏目后，后续重打标签不再覆盖。
- [x] P0 | 服务 | `article_type / main_topic` 从编辑台主表单移除，继续只作为后端自动推断元数据使用。
- [x] P0 | 服务 | 发布前强校验标题、原稿、排版稿 Markdown、最终 HTML、最终标签、主栏目是否齐备。
- [x] P0 | 服务 | 发布逻辑改为显式阻断缺少最终 HTML 的稿件，不再在发布时偷偷补渲染。
- [x] P0 | 服务 | 发布后正式文章详情页优先读取编辑台产出的正式 HTML，不再只认普通 AI 产物 HTML。
- [x] P0 | 服务 | 同一篇编辑稿二次发布时复用原 `article_id`，不重复创建正式文章。
- [x] P0 | 前端 | `/editorial` 重构为“左原稿、右最终 HTML 预览”的双栏主视图。
- [x] P0 | 前端 | 去掉主表单里的 `article_type / main_topic` 输入。
- [x] P0 | 前端 | 去掉原来的 WeChat/Web 切换、导出 HTML 按钮、右侧发布信息卡片。
- [x] P0 | 前端 | 新增标签确认区，支持管理员逐个移除保留标签，并支持恢复为 AI 建议。
- [x] P0 | 前端 | 新增栏目确认区，明确显示“当前栏目来自 AI 建议还是人工指定”。
- [x] P0 | 前端 | 页面底部动作收口为保存、自动排版、自动打标签、发布。
- [x] P0 | 前端 | API 错误透传改为解析后端 `detail`，发布校验失败时前端能看到明确原因。
- [x] P0 | 接口 | 站内导出 HTML 接口停用，避免工作台继续暴露旧导出模式。
- [x] P0 | 验收 | `python -m compileall backend`
- [x] P0 | 验收 | `pytest backend/tests/test_admin_editorial_media_features.py`
- [x] P0 | 验收 | `npm run build`

## 待后续继续观察
- [ ] P1 | 排版策略 | 继续把自动排版阶段向原公众号工程里的 render plan 复用和块级策略回显靠拢。
- [ ] P1 | 前端回显 | 若管理员后续需要更强的诊断信息，再补充 render metadata 的高级调试展示。
- [ ] P1 | 清理 | 继续扫描全仓库，清除与旧导出模式相关的更多低频残留入口。
