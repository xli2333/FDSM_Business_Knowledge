# Round 114：媒体节目简介轻强调与三点要点

## 对齐结论
- [x] 当前媒体节目简介虽然已经支持 Markdown 渲染，但默认生成结果仍偏纯段落，视觉重点不够明确。
- [x] 本轮目标不是把媒体简介做成复杂富文本，而是在保持简洁的前提下，把默认生成结构收口为“一段导语 + 两到三条要点”。
- [x] 要点展示允许使用 Markdown bullet point，但总数不得超过 3 条，避免简介区再次变重。
- [x] 本轮继续沿用现有 `MediaMarkdownBlock.jsx` 渲染链路，重点修改生成规则、fallback 输出和真实验收。
- [x] 顺手清理了 `ai_service.py` 里媒体文案生成函数的重复入口，只保留一个有效的 `generate_media_text_assets`。
- [x] 全部 todo 文档与代码改动保持 UTF-8 中文，不引入中文编码错误或 JSX / Python 语法错误。

## 原子任务
- [x] P0 | 后端 AI | 调整媒体 `body_markdown` 生成约束，让节目简介默认包含一段导语，并可追加 2 到 3 条要点，禁止超过 3 条 bullet point。
- [x] P0 | 后端 fallback | 改造媒体节目简介 fallback，在无 AI 或模型输出过素时也能稳定生成“导语 + 三点内要点”结构。
- [x] P0 | 后端归一化 | 增加媒体节目简介 Markdown 收口逻辑，统一限制 bullet point 数量不超过 3 条，并在缺少要点时自动补足轻量要点区。
- [x] P0 | 前端渲染 | 保持现有 Markdown 组件样式，确认节目简介中的 `###` 与 bullet point 在后台预览和线上预览里都清晰可读。
- [x] P0 | 测试 | 更新后端媒体测试，固定节目简介包含轻强调要点区的 contract，并验证 bullet point 不超过 3 条。
- [x] P0 | 验收 | 更新 `frontend/scripts/media_acceptance_round106.mjs`，把真实验收补到“节目简介预览出现列表项，且列表项数量在 1 到 3 之间”。

## 结束标准
- [x] 媒体节目简介默认不再只是纯段落。
- [x] 媒体节目简介生成结果稳定包含一段导语和不超过 3 条要点。
- [x] 后台当前稿预览、后台线上稿预览都能正确渲染要点列表。
- [x] `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106` 通过。

## 备注
- [x] 本轮只增强节目简介的轻强调结构，不扩展复杂卡片、图文混排或额外视觉容器。
- [x] 真实验收复跑后没有暴露新的明确 P0 / P1 缺口，因此本轮结束后不继续新开下一轮 todo。
