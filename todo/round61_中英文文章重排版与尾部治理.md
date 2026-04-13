# Round 61：中英文文章重排版与尾部治理

## 待办
- [x] P0 | 规划 | 核对现网中文页、英文页、摘要页读取链路，锁定需要写回的字段与展示入口
- [x] P0 | 后端 | 新增“只重排、不改正文”的批处理服务，中文正文取原文，英文正文取现有英文稿
- [x] P0 | 后端 | 复用 `公众号排版` 里的 `fudan_business_knowledge` 风格约束，建立当前站点可用的 Markdown 重排规则
- [x] P0 | 后端 | 增加尾部治理规则，只清理广告、报名投票、订阅转发、技术提示和无关尾巴，保留导读、来源、出品等合法元信息
- [x] P0 | 后端 | 摘要、中文正文、英文摘要、英文正文统一改为 `gemini-3-flash-preview` 重排版链路
- [x] P0 | 后端 | 英文返回优先读取重排版后的英文稿，确保现网直接显示最新成稿
- [x] P0 | 测试 | 补充尾部治理与重排兜底逻辑测试，避免误删正文与合法元信息
- [x] P0 | 验收 | 完成多轮小样本试跑，确认正文未被改写、尾部清理准确、空行与层级稳定
- [x] P0 | 运行 | 启动 18 个 worker 全量处理全部文章，主批次结束后补扫收尾，最终完成 `1703` 篇可见成稿并隐藏 `439` 篇图片占位无正文条目
- [x] P0 | 验收 | 运行后端编译、测试、前端构建和截图验收，确认当前环境正常显示

## 验收记录
- [x] `python -m compileall backend/config.py backend/services/article_relayout_service.py backend/scripts/article_relayout_batch.py backend/tests/test_admin_editorial_media_features.py`
- [x] `python -m compileall backend/scripts/recover_visible_relayout_failures.py`
- [x] `pytest backend/tests/test_article_relayout_service.py backend/tests/test_admin_editorial_media_features.py`
- [x] `pytest backend/tests/test_article_visibility_service.py backend/tests/test_article_relayout_service.py backend/tests/test_admin_editorial_media_features.py`
- [x] `npm run build`
- [x] `node frontend/scripts/visual_acceptance.mjs`

## 运行中记录
- [x] 已启动 `18` 个 worker 主批次，模型固定为 `gemini-3-flash-preview`
- [x] 已补齐 JSON 解析兜底、长正文尾部误伤修复、空正文回退兜底
- [x] 已将“图片占位、无正文”的 `439` 篇条目排出可见链路与后续 manifest
- [x] 当前主批次已结束，状态为 `completed_with_failures`，`18` 个 worker 全部正常退出
- [x] 当前有效文章基数：`1703`
- [x] 按当前源码哈希统计的可见集合已完成：`1703 / 1703`
- [x] 已修正 manifest 未读取 `content` 导致低价值占位稿误入补扫范围的问题
- [x] 已执行本地 deterministic recovery，补齐剩余 `6` 篇可见失败稿：`1041`、`1099`、`1687`、`1697`、`1828`、`2069`
- [x] 当前失败待补扫：`0`（可见集合） / `66`（仅剩已隐藏占位条目的历史失败记录）
- [x] 当前仍在运行：`0`
- [x] 当前待补全或待重跑：`0`（可见集合）
- [x] 主批次结束后已按失败集补扫，当前可见文章已全部处理完成

## 小样本结论
- [x] 第一轮 pilot 发现 `gemini-3-flash` 在当前 API 下 404，已改为当前可调用的 `gemini-3-flash-preview`
- [x] 第二轮 pilot 发现尾部治理规则误伤长正文，已改为“短尾块 CTA”识别并补回归测试
- [x] 第三轮 pilot 以 `6 worker / 12 篇` 全量通过
- [x] 抽样文章中文正文相似度稳定在高覆盖区间，且中英文正文均不再重复输出 H1 标题

## 验收重点
- [x] 中文页优先显示重排版后的中文正文，且不重复改写正文事实
- [x] 英文页优先显示重排版后的现有英译，不重新翻译正文
- [x] AI 摘要同步完成重排版，结构清晰且无空列表、无占位说明
- [x] 合法元信息如导读、来源、出品被保留
- [x] 尾部广告、报名投票、订阅转发、技术提示和无关尾巴被清理
- [x] `2142` 篇文章已完成本轮处理决策：`1703` 篇可见文章全部完成，`439` 篇图片占位无正文条目已从前端可见链路与后续 manifest 隐藏

## 本轮结论
- [x] 截图验收后发现低价值促销稿仍在可见链路，已新开 `round62_低价值促销稿隐藏与文章页验收收口.md` 完成最后一轮收口；当前已无明确提升空间，本轮结束
