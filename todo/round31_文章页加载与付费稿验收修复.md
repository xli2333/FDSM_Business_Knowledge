# Round31 文章页加载与付费稿验收修复

## 本轮目标

- [x] 定位 `2144` 在免费会员与付费会员角色下卡在“文章加载中…”的根因
- [x] 修复文章页加载策略，保证正文不再被摘要接口阻塞
- [x] 修复摘要接口的实时回退策略，避免线上请求依赖慢速 AI 生成
- [x] 收紧视觉流验收脚本中付费稿步骤的通过条件，消除假阳性
- [x] 重跑 lint / build / 关键视觉流，并按真实结果更新结论

## 根因结论

- [x] `ArticlePage` 把 `fetchArticle` 和 `fetchArticleSummary` 放在同一个 `Promise.all` 里，导致摘要请求慢时整页一直停在 loading
- [x] `/api/summarize_article/{id}` 在没有现成 AI 摘要时会走实时 AI 总结，不适合作为文章首屏阻塞依赖
- [x] 旧验收脚本对付费稿步骤只看到了“升级”或“没有 paywall”，没有强制要求文章标题真实渲染出来，因此出现假阳性

## 本轮交付

- [x] 修复 [frontend/src/pages/ArticlePage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/ArticlePage.jsx)
- [x] 修复 [backend/routers/articles.py](C:/Users/LXG/fdsmarticles/backend/routers/articles.py)
- [x] 修复 [frontend/scripts/prelaunch_acceptance.mjs](C:/Users/LXG/fdsmarticles/frontend/scripts/prelaunch_acceptance.mjs)
- [x] 回归报告仍沿用 [qa/prelaunch/round30/acceptance_report.md](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/acceptance_report.md)
- [x] 回归截图已更新到 [qa/prelaunch/round30/screenshots](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/screenshots)

## 验收标准

- [x] 免费会员打开 `2144` 不再卡在 loading
- [x] 付费会员打开 `2144` 不再卡在 loading
- [x] 游客打开 `2144` 仍然显示正确门槛
- [x] `2142` 中文页与英文页仍然正常
- [x] `python -m compileall backend` 通过
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] `npm run prelaunch:acceptance` 通过

## 结果摘要

- [x] `2144` 游客页现在能显示标题、权限卡和 preview gate
- [x] `2144` 免费会员页现在能显示标题、权限卡、正文卡与升级边界
- [x] `2144` 付费会员页现在能显示标题、交互卡和正文卡
- [x] AI 摘要区即使仍在等待，也只会显示局部占位，不再阻塞整页正文
- [x] 视觉流报告当前仍是 `27 / 27` 全通过，见 [qa/prelaunch/round30/acceptance_report.md](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/acceptance_report.md)

## 备注

- [x] `vite build` 仍有 chunk size warning，但不是阻塞修复上线的构建错误
