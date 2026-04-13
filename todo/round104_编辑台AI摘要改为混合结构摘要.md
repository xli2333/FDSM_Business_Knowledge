# Round 104：编辑台 AI 摘要改为混合结构摘要

## 对齐结论
- [x] Round 103 已经去掉了“简报前缀 + 全分节提纲”，但当前 contract 过度压成纯正文段落，不符合新的摘要样式要求。
- [x] 本轮要把编辑台 AI 摘要改成 `不少于 200 字、不超过 500 字` 的混合结构摘要，允许 `3-4` 个合理 bullet，但不能整篇只剩 bullet 列表。
- [x] 本轮摘要结果需要保留突出的强调信息，优先用 Markdown `**强调**` 呈现关键判断或关键词。
- [x] 本轮继续保持：不要“以下是…”“本文…”“这篇文章…”等说明性开头，不要标题，不要分节标题，不要把摘要写回成简报腔。

## 原子任务
- [x] P0 | 后端 | 重写编辑台 AI 摘要 prompt，改成 200-500 字的混合结构摘要 contract，允许 3-4 个 bullet，但要求有简短引导段落且不能整篇列表化。
- [x] P0 | 后端 | 调整摘要规整逻辑，允许合理 bullet 与 `**强调**` 保留，同时继续剥离说明性前缀、标题和分节标题。
- [x] P0 | 后端 | 为纯 bullet 输出增加兜底重组逻辑，保证最终结果至少包含一段正文引导，不会退化成整篇列表。
- [x] P0 | 后端 | 调整 fallback 摘要 contract，使 AI 失败时也尽量满足 200-500 字、混合结构、非简报腔。
- [x] P0 | 后端测试 | 覆盖新摘要 contract：长度区间、强调保留、允许 bullet、禁止说明性前缀与纯列表化。
- [x] P0 | 后端测试 | 覆盖编辑台自动生成摘要并发布后，文章详情读取到的仍是规整后的混合结构摘要 HTML。
- [x] P0 | 验收 | `pytest backend/tests/test_ai_service_summary.py -q`
- [x] P0 | 验收 | `pytest backend/tests/test_admin_editorial_media_features.py -q`
- [x] P0 | 验收 | `pytest backend/tests/test_summary_preview_service.py -q`
- [x] P0 | 验收 | `npm run build`

## 结束标准
- [x] 编辑台 AI 摘要长度稳定落在 `200-500 字`。
- [x] 编辑台 AI 摘要包含突出的强调信息，且能在需要时合理使用 `3-4` 个 bullet。
- [x] 编辑台 AI 摘要不会再出现“以下是…”“本文…”等说明性开头，也不会退化成纯标题 / 纯分节 / 纯 bullet 列表。
- [x] 后端测试与前端构建通过，且未引入中文编码错误或 JSX 错误。

## 备注
- [x] 本轮新增了编辑台链路兜底与已发布文章详情链路兜底，确保混合结构摘要不会在展示层再被压回单段导语。
- [x] 本轮验收结果：`pytest backend/tests/test_ai_service_summary.py -q` 通过，`pytest backend/tests/test_admin_editorial_media_features.py -q` 通过（`22 passed`），`pytest backend/tests/test_summary_preview_service.py -q` 通过，`npm run build` 通过。
- [x] 当前没有再暴露出明确且可复现的下一轮提升空间，因此本轮结束，不新开 round105。
