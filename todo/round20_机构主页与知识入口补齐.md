# Round20 机构主页与知识入口补齐

## 本轮目标

- [x] 新增机构聚合能力，基于文章中的机构字段生成机构索引与机构主页
- [x] 新增后端 Organization API，支持机构列表与机构详情页文章聚合
- [x] 在前端新增机构列表页与机构详情页
- [x] 将机构入口接入文章页与导航，增强从文章深入机构的知识探索路径
- [x] 扩展烟雾测试与视觉验收，覆盖机构索引与机构详情页
- [x] 运行编译、构建、烟雾测试与视觉验收，确保无编码和 JSX 问题

## 验收标准

- [x] 后端存在机构列表与机构详情接口
- [x] 前端存在机构列表页与机构详情页
- [x] 文章页中有机构入口时可直接跳转到机构主页
- [x] `python -m compileall backend` 通过
- [x] `python backend/scripts/smoke_test.py` 通过
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] `npm run visual:acceptance` 通过
