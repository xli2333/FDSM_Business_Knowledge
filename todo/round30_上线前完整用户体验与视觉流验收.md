# Round30 上线前完整用户体验与视觉流验收

## 本轮目标

- [x] 盘点现有验收脚本、启动方式与角色测试能力，明确差距
- [x] 建立一套覆盖 guest / 免费会员 / 付费会员 / 管理员 的上线前视觉流验收脚本
- [x] 用真实前后端启动和页面交互去验证关键功能、关键 UI 与角色分流
- [x] 输出截图、结构化结果与中文验收结论，确保与实际用户体验一致
- [x] 排查并修复验收过程中暴露的中文污染、编码问题或 UI 断裂

## 本轮交付

- [x] 新增并收口 [frontend/scripts/prelaunch_acceptance.mjs](C:/Users/LXG/fdsmarticles/frontend/scripts/prelaunch_acceptance.mjs)
- [x] 生成结构化结果 [qa/prelaunch/round30/acceptance_results.json](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/acceptance_results.json)
- [x] 生成中文报告 [qa/prelaunch/round30/acceptance_report.md](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/acceptance_report.md)
- [x] 生成整套截图目录 [qa/prelaunch/round30/screenshots](C:/Users/LXG/fdsmarticles/qa/prelaunch/round30/screenshots)
- [x] 跑通 `npm run lint`
- [x] 跑通 `npm run build`
- [x] 跑通 `npm run prelaunch:acceptance`
- [x] 本轮真实验收已经没有明确提升空间，不再新开下一轮中文 Todo

## 验收标准

- [x] guest / 免费会员 / 付费会员 / 管理员 四条主路径都已实际跑通
- [x] 登录页、搜索、公开文章、英文翻译、付费门槛、会员页、音频、视频、我的关注、后台入口都经过真实交互校验
- [x] 桌面端与移动端都输出了可复核截图
- [x] 验收产物中没有新的中文乱码、编码污染或 JSX 构建错误
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] 视觉流验收脚本通过

## 结果摘要

- [x] 总步骤 `27`
- [x] 通过 `27`
- [x] 失败 `0`
- [x] 桌面端覆盖 `guest-desktop / free-desktop / paid-desktop / admin-desktop`
- [x] 移动端覆盖 `mobile-guest / mobile-free_member / mobile-paid_member / mobile-admin`
- [x] 公开文章样本 `2142`
- [x] 付费文章样本 `2144`
- [x] 当前库内没有真实 `member` 级文章，因此 `memberArticleId` 回退到 `2142`

## 本轮修正点

- [x] 将验收器路由切换改为真实 URL 导航，避免 `pushState + 固定等待` 带来的误判
- [x] 过滤路由切换产生的 `net::ERR_ABORTED` 请求失败噪音
- [x] 将英文翻译验证切到英文界面下执行，确保真正覆盖“翻译按钮出现并返回状态”
- [x] 修复验收器在新文档加载时错误清空 `fdsm-debug-auth` 的问题，保证 free/admin 角色跨页面验证稳定

## 备注

- [x] `vite build` 仍有 chunk size warning，但不是阻塞上线的构建错误
