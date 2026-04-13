# Round 103：编辑台 AI 摘要改为正文摘要

## 对齐结论
- [x] 当前编辑台 AI 摘要 prompt 把输出明确引向了 `brief`、分节和项目符号，这与“摘要”目标不一致。
- [x] 本轮要把 AI 摘要收口成 `2-3 段、总长不超过 350 字` 的正文摘要，而不是简报或提纲。
- [x] 本轮不能只改 prompt，必须同时补后处理兜底，防止模型继续输出“以下是…”“本文…”“这篇文章…”之类说明性前缀，以及标题、分节、项目符号残留。
- [x] 本轮完成后要补自动化验证；如果真实验收仍有明确提升空间，再新开下一轮中文 todo 继续推进。

## 原子任务
- [x] P0 | 后端 | 重写编辑台 AI 摘要 prompt，明确要求只输出摘要正文，不要“以下是…”等说明性开头，不要标题，不要分节，不要项目符号。
- [x] P0 | 后端 | 将编辑台 AI 摘要长度收口为 `2-3 段` 且 `不超过 350 字`。
- [x] P0 | 后端 | 为 AI 摘要增加结果规整逻辑，把说明性前缀、标题、项目符号、分节标题压平为正文段落。
- [x] P0 | 后端 | 调整 AI 失败时的 fallback 摘要，避免继续返回过长或简报式结构。
- [x] P0 | 后端测试 | 覆盖摘要 prompt / 输出规整结果，确认不会保留说明性前缀、标题和 bullet 结构。
- [x] P0 | 后端测试 | 覆盖编辑台自动生成摘要并发布后，文章详情读取到的仍是规整后的摘要 HTML。
- [x] P0 | 验收 | `pytest backend/tests/test_ai_service_summary.py -q`
- [x] P0 | 验收 | `python -m py_compile backend/services/ai_service.py backend/services/editorial_service.py`
- [x] P0 | 验收 | `pytest backend/tests/test_admin_editorial_media_features.py -q`
- [x] P0 | 验收 | `pytest backend/tests/test_summary_preview_service.py -q`
- [x] P0 | 验收 | `npm run build`

## 结束标准
- [x] 编辑台 AI 摘要生成结果不再出现“以下是…”“本文…”“这篇文章…”等说明性开头。
- [x] 编辑台 AI 摘要不再以“简报 / 分节 / bullet list”形式呈现，而是 2-3 段正文摘要。
- [x] 生成后的摘要总长不超过 350 字。
- [x] 后端测试与前端构建通过，且未引入中文编码错误或 JSX 错误。

## 结论
- [x] 本轮真实样例规整结果已压成 3 段、175 字，没有再暴露出新的明确摘要 contract 缺口，暂不新开下一轮 todo。
