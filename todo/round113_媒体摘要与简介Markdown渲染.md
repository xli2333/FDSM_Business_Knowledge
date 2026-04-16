# Round 113：媒体摘要与简介 Markdown 渲染

## 对齐结论
- [x] 当前媒体后台的 AI 文案链路里，`body_markdown` 已经是 Markdown 字段，但展示层此前主要还是按纯文本看待；`summary` 也主要按普通字符串生成和展示，缺少最基本的排版渲染。
- [x] 本轮目标不是重做复杂详情页，而是给媒体摘要与节目简介补一套轻量 Markdown 生成与渲染方案：AI 输出直接带轻量 Markdown，前端统一识别并做简单排版。
- [x] 本轮范围只落在媒体工作台与正式 `/audio`、`/video` 展示链路，不改动 `round111`、`round112` 已经验收通过的重编入口与后台布局主链路。
- [x] 全部 todo 文档与代码改动保持 UTF-8 中文，没有引入中文编码错误或 JSX 语法错误。

## 原子任务
- [x] P0 | 后端 AI | 调整媒体 AI 文案生成约束，让 `summary` 输出为轻量 Markdown 摘要，保持一段式、轻强调、无复杂层级。
- [x] P0 | 后端 AI | 保持 `body_markdown` 继续作为 Markdown 节目简介输出，并让 fallback 也直接生成可渲染 Markdown。
- [x] P0 | 后端服务 | 补媒体摘要 Markdown 归一化能力，发布前统一收口为轻量 Markdown；摘要提要抽取先去掉 Markdown 标记，避免正式页出现原始 `**`、`##`。
- [x] P0 | 前端组件 | 新增统一的 `MediaMarkdownBlock.jsx` 轻渲染组件，负责摘要与节目简介的简单排版样式。
- [x] P0 | 前端工作台 | 在 `MediaStudioPage.jsx` 为当前摘要与节目简介增加渲染预览区，生成后和手工编辑后都能看到效果。
- [x] P0 | 前端工作台 | 把线上摘要与线上节目简介从纯文本展示改成 Markdown 渲染展示。
- [x] P0 | 前端正式页 | 把 `/audio`、`/video` 卡片里的摘要改成 Markdown 渲染，避免正式页直接露出原始 Markdown 符号。
- [x] P0 | 测试 | 更新后端媒体测试，固定媒体摘要 Markdown contract，并覆盖摘要提要抽取会去掉 Markdown 标记。
- [x] P0 | 验收 | 更新 `frontend/scripts/media_acceptance_round106.mjs`，把真实验收补到“生成后预览已渲染、正式页摘要已渲染、重新编辑后线上预览已渲染”。

## 结束标准
- [x] 媒体摘要已经支持轻量 Markdown 生成与渲染。
- [x] 媒体节目简介继续使用 Markdown，并在后台展示为简单排版结构而不是纯文本块。
- [x] 媒体工作台当前稿与线上稿都能看到渲染后的摘要 / 简介效果。
- [x] 正式 `/audio`、`/video` 页不会再把摘要中的原始 Markdown 标记直接露给管理员或普通用户。
- [x] `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106` 通过。

## 备注
- [x] 本轮只做轻量 Markdown 方案，不扩展复杂富文本编辑器，也不新增独立媒体详情页。
- [x] 真实验收后没有暴露新的明确 P0 / P1 缺口，因此本轮结束后不继续新开下一轮 todo。
