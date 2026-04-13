# Round14 前端拆包与Supabase接入说明补齐

## 本轮目标

- [x] 盘点当前上线前仍存在的工程化缺口
- [x] 对前端主要页面做路由级懒加载，降低主包体积告警
- [x] 增加统一加载占位，保证拆包后体验不突兀
- [x] 补齐 Supabase 接入说明文档，明确所需环境变量与接入步骤
- [x] 运行构建与验收，确认无 JSX、编码和路由问题

## 验收标准

- [x] 前端已切换为路由级懒加载
- [x] 存在明确的 Supabase 配置文档
- [x] `npm run lint` 通过
- [x] `npm run build` 通过
- [x] `npm run visual:acceptance` 通过
