# Round10 内容分发导出与SEO触达补齐

## 本轮目标

- [x] 盘点内容后台在交付与分发层面仍缺失的商业化能力
- [x] 补齐后台文章 HTML 导出能力，支持网页版与微信公众号版下载
- [x] 补齐内容后台概览接口，输出草稿数、发布数、最新发布时间等运营指标
- [x] 为站点新增 SEO 触达能力，包括 `sitemap.xml`、`rss.xml` 与 `robots.txt`
- [x] 在前端编辑工作台增加导出按钮和运营概览展示
- [x] 扩展后端烟雾测试，覆盖导出与 SEO 接口
- [x] 扩展前端视觉验收，确保编辑工作台导出区正常渲染
- [x] 运行编译、构建、烟雾测试与视觉验收，确保无编码或 JSX 问题

## 验收标准

- [x] 已生成 HTML 的后台文章可以直接导出下载
- [x] 编辑工作台可看到后台运营概览和导出入口
- [x] 站点存在可访问的 `sitemap.xml`、`rss.xml` 与 `robots.txt`
- [x] `python -m compileall backend` 通过
- [x] `python backend/scripts/smoke_test.py` 通过
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] `npm run visual:acceptance` 通过
