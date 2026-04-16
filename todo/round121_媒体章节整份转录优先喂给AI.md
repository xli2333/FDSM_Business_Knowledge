# Round 121：媒体章节整份转录优先喂给 AI

## 对齐结论
- [x] 当前媒体章节虽然已经是 AI 主生成，但输入源仍有多处沿用 `script_markdown` 优先，导致“重写章节 / 生成文案 / 发布前兜底”在同时存在转录和脚本时，不一定把整份转录交给 AI。
- [x] 本轮目标是把媒体章节相关链路统一收口为 `transcript-first`：有转录就优先把整份转录直接喂给 Gemini，并在章节 prompt 中去掉中段截断；只有没有转录时，才回退到脚本。
- [x] 本轮同时补齐章节回退链路、占位值清洗与测试，确保 AI 不可用或识别失败时，基础提取也仍按“转录优先、脚本兜底”执行。
- [x] 全部 todo 与代码改动保持 UTF-8 中文，不引入中文编码错误或 JSX / Python 语法错误。

## 原子任务
- [x] P0 | Todo | 新建本轮中文 todo，并按原子项推进与勾选。
- [x] P0 | 后端章节输入 | 收口 `_media_chapter_source_text`、`_generate_media_chapters_ai_first` 与章节回退链路，统一改为 `transcript_markdown` 优先，并清洗 `"None" / "null"` 这类占位值。
- [x] P0 | AI 服务 | 收口 `generate_media_chapter_outline`，确保 Gemini 章节提示词与归一化都基于整份转录优先的原文，不再截断中段内容。
- [x] P0 | 生成链路 | 收口 `generate_media_text_assets` 与发布前兜底中的章节输入源，避免 `生成文案` 时又退回脚本优先。
- [x] P0 | 测试 | 补回归测试，覆盖“转录与脚本同时存在时，章节重写和生成文案都必须优先使用转录”，并把媒体上传根目录改成唯一临时目录，去掉套件级目录污染。
- [x] P0 | 验收 | 复跑 `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106`。

## 结束标准
- [x] 重写章节时，Gemini 优先看到整份转录，而不是脚本摘要版。
- [x] 点击 `生成文案` 时，章节与文案链路对同一份转录源保持一致。
- [x] AI 不可用时的章节基础提取仍可用，且优先使用转录。
- [x] `pytest backend/tests/test_admin_editorial_media_features.py -q`、`npm run build`、`npm run media:acceptance:round106` 通过。

## 备注
- [x] 本轮只收口媒体章节与文案生成的输入源优先级，不扩展新的编辑器交互。
