# Round 118：媒体章节改为 Gemini 主生成

## 对齐结论
- [x] 当前媒体摘要与节目简介已经是 `Gemini 先生成 + 脚本收口`，但章节目录仍主要由脚本规则直接生成，这和你现在固定下来的产品规则不一致。
- [x] 本轮目标是把媒体章节目录切到和摘要、节目简介同一模式：`Gemini 主生成目录标题与结构，脚本只负责 JSON contract 校验、时间戳合法性校验与 fallback`。
- [x] 章节目录里的时间戳仍必须来自真实转录 / 脚本文本，不能凭空捏造；AI 负责根据带时间戳的内容块生成“这一部分讲什么”的目录标题。
- [x] 本轮会同时覆盖上传文本即识别、草稿保存重算、点击“生成文案”三条链路，避免章节在不同入口下走不同规则。
- [x] 全部 todo 文档与代码改动保持 UTF-8 中文，不引入中文编码错误或 JSX / Python 语法错误。

## 原子任务
- [x] P0 | 后端 AI | 在 `ai_service.py` 增加媒体章节目录生成能力，让 Gemini 返回结构化 `chapters` JSON。
- [x] P0 | 后端校验 | 增加媒体章节 JSON 归一化逻辑，只接受来源文本中真实存在的时间戳，并对目录标题做轻量清洗。
- [x] P0 | 后端生成 | 更新 `generate_media_text_assets`，让“生成文案”时同一轮 Gemini 输出同时包含摘要、节目简介和章节目录。
- [x] P0 | 后端上传/保存 | 更新媒体上传与草稿保存链路，让转录 / 脚本文本变更后优先走 Gemini 章节生成，只有 AI 不可用或返回无效时才 fallback 到脚本提取。
- [x] P0 | 前端文案 | 校对媒体后台“AI 生成的摘要、节目简介和章节结果”这类文案，使其和实际链路一致。
- [x] P0 | 测试 | 更新后端测试，覆盖“上传文本时优先使用 AI 章节输出”和“生成文案时优先使用 AI 返回的 chapters”。
- [x] P0 | 验收 | 更新 `frontend/scripts/media_acceptance_round106.mjs`，保持真实验收可通过，并确保 fallback 场景不回归。
- [x] P0 | 验证 | 跑通 `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106`。

## 结束标准
- [x] 媒体章节目录不再由脚本规则直接主导，而是改为 Gemini 主生成。
- [x] 上传文本、保存草稿、生成文案三条链路下的章节目录规则一致。
- [x] AI 返回无效章节时，系统仍能 fallback 到脚本提取，不影响可用性。
- [x] `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106` 通过。

## 备注
- [x] 本轮只把章节目录切到 Gemini 主生成，不引入人工编辑目录 UI 或独立章节审核流。
