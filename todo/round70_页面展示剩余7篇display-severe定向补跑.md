# Round70 页面展示剩余7篇display-severe定向补跑

- [x] 基于最新 `markdown_structure_failures.json` 重新计算“展示态 severe”
- [x] 展示态 severe 从 `14` 进一步压缩到 `7`
- [x] 锁定 `7` 篇页面仍有明显结构问题的文章：
- [x] `355 / 318 / 219 / 215 / 200 / 190 / 120`
- [x] 结束 Round69 的 broad pass，避免继续消耗在页面已基本正常的稿子上
- [x] 按 `7` 篇 display-severe 拆 shard 启动 Round70 定向 Gemini 补跑
- [x] Round70 worker 分配：
- [x] `round70-display-00 -> 355 / 318 / 219`
- [x] `round70-display-01 -> 215 / 200`
- [x] `round70-display-02 -> 190 / 120`
- [x] 定向补跑后再次计算“展示态 severe”
- [x] 展示态 severe 已降到 `0`
- [x] 对样本 `1790 / 1237 / 1457 / 1420 / 1405 / 219 / 215 / 200 / 1128 / 318` 完成中英文 `20` 图截图
- [x] 截图目录：`qa/screenshots/round70_acceptance`
- [x] 如有英文页同步问题，已补齐 `en-318.png`
- [x] 最终复核：`pytest` 通过、`npm run build` 通过、展示态 severe=`0`、截图=`20`
- [x] 当前没有明确提升空间，不新开 Round71
