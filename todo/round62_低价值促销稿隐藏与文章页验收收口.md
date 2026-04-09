# Round 62：低价值促销稿隐藏与文章页验收收口

## 待办
- [x] P0 | 验收 | 补拍中文文章页样张，确认当前环境中英文成稿是否真实可读
- [x] P0 | 验收 | 识别出真实提升空间：`1697` 等整篇几乎都是赠礼/投票/订阅引导的低价值促销稿仍在可见链路中
- [x] P0 | 规则 | 新增“整篇低价值促销稿”隐藏规则，仅命中正文极短且促销标记密集的条目
- [x] P0 | 接入 | 将低价值促销稿隐藏规则接入 manifest、前台列表、文章详情与后台来源列表
- [x] P0 | 测试 | 增加短促销稿命中与长活动文不误伤的边界测试
- [x] P0 | 数据 | 重建可见集合并核对新的可见文章基数、已隐藏条目与完成状态
- [x] P0 | 验收 | 重新运行前端构建与截图验收，确认首页、编辑台、中英文文章页均正常显示
- [x] P0 | 结论 | 当前已无明确提升空间，已回填 Round 61 结论并结束本轮推进

## 当前发现
- [x] `qa/screenshots/round34_visual/desktop-en-article_2142_lang_en.png` 显示英文文章页正常
- [x] `qa/screenshots/round62_visual/zh-article-2142.png` 显示中文最新公开稿正常
- [x] `qa/screenshots/round61_visual/zh-article-1697.png` 暴露低价值促销稿仍在文章链路中的问题
- [x] `qa/screenshots/round62_visual/zh-article-1697.png` 显示该低价值促销稿已退出可见链路

## 验收记录
- [x] `python -m compileall backend/services/article_visibility_service.py backend/tests/test_article_visibility_service.py`
- [x] `pytest backend/tests/test_article_visibility_service.py backend/tests/test_article_relayout_service.py backend/tests/test_admin_editorial_media_features.py`
- [x] `npm run build`
- [x] `node scripts/visual_acceptance.mjs`

## 候选低价值稿
- [x] 初筛候选中已隐藏：`1638`、`1697`、`1834`
- [x] 保持可见的保守边界样本：`1152`、`1898`、`1903`、`1905`、`2055`

## 本轮结果
- [x] 当前隐藏低价值条目总数：`442`（其中新增短促销稿 `3` 篇）
- [x] 当前可见文章基数：`1700`
- [x] 按当前源码哈希统计的可见集合完成度：`1700 / 1700`
