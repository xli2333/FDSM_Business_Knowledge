# Round23 登录中心与角色化资产分发重构
## 本轮目标

- [x] 把登录能力从弹窗附属功能升级为正式登录页与角色分发入口
- [x] 把 `Supabase` 身份认证和本地业务用户库职责拆清，并通过同一套后端聚合输出给前端
- [x] 建立游客 / 免费会员 / 付费会员 / 管理员四类角色的模拟用户库、种子账号和默认角色主页
- [x] 让首页、我的资产页、管理员页、媒体与后台入口按照角色展示不同资产与入口
- [x] 用后端烟雾测试、前端视觉验收和浏览器级真实用户流把这一轮真正验收完

## 已完成事项

### 一、业务用户库与角色底座

- [x] 新增本地业务用户表 `business_users`
- [x] 新增管理员调权审计表 `admin_role_audit_logs`
- [x] 打通 `user_memberships -> business_users` 同步逻辑，保证登录后自动落本地业务档案
- [x] 建立 `mock-free-member`、`mock-paid-member`、`mock-admin` 三个种子账号
- [x] 为种子账号预置收藏、点赞、阅读历史、关注与媒体访问样例数据
- [x] 让业务用户档案返回默认角色主页：游客 `/`、免费会员 `/me`、付费会员 `/membership`、管理员 `/admin`

### 二、认证聚合与接口改造

- [x] 扩展 `/api/auth/status`，返回 `business_profile`、`role_home_path`、`dev_auth_enabled`、`mock_accounts`
- [x] 新增 `/api/me/dashboard`，聚合角色档案、资产摘要和角色快捷入口
- [x] 新增 `/api/admin/overview`，返回角色分布、审计日志、种子账号和后台指标
- [x] 收紧 `/api/editorial/*` 为管理员接口
- [x] 收紧 `/api/media/admin/*` 为管理员接口
- [x] 收紧 `/api/commerce/demo-requests*` 为管理员接口

### 三、登录中心与前端角色分发

- [x] 新建正式登录页 [LoginPage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/LoginPage.jsx)
- [x] 保留弹窗登录，但将其降级为页内快捷入口，并提供跳转到完整登录中心
- [x] 建立本地 mock 登录存储与调试头透传 [debugAuth.js](C:/Users/LXG/fdsmarticles/frontend/src/auth/debugAuth.js)
- [x] 升级认证上下文 [AuthProvider.jsx](C:/Users/LXG/fdsmarticles/frontend/src/auth/AuthProvider.jsx)，支持真实会话与 mock 会话共存
- [x] 建立前端页面级守卫 [ProtectedRoute.jsx](C:/Users/LXG/fdsmarticles/frontend/src/auth/ProtectedRoute.jsx)
- [x] 管理员页面改为受保护路由：`/admin`、`/admin/memberships`、`/editorial`、`/media-studio`、`/commercial/leads`

### 四、角色化页面与资产差异

- [x] 首页按角色展示不同引导与 CTA [HomePage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/HomePage.jsx)
- [x] 导航栏按角色展示不同角色主页入口和后台入口 [Navbar.jsx](C:/Users/LXG/fdsmarticles/frontend/src/components/layout/Navbar.jsx)
- [x] 我的资产页接入角色化摘要、资产指标和快捷入口 [MyLibraryPage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/MyLibraryPage.jsx)
- [x] 新建管理员默认首页 [AdminConsolePage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/AdminConsolePage.jsx)
- [x] 管理员会员页继续承接调权与列表配置 [AdminMembershipsPage.jsx](C:/Users/LXG/fdsmarticles/frontend/src/pages/AdminMembershipsPage.jsx)
- [x] 文章页已有游客 / 会员 / 付费可见性，本轮继续复用到角色化分发中
- [x] 音视频板块继续沿用公开 / 会员 / 付费可见性，管理员可进入媒体后台

### 五、测试与验收

- [x] 更新后端烟雾测试 [smoke_test.py](C:/Users/LXG/fdsmarticles/backend/scripts/smoke_test.py)，覆盖角色档案、mock 账号、管理员总览和新权限边界
- [x] 更新视觉验收脚本 [visual_acceptance.mjs](C:/Users/LXG/fdsmarticles/frontend/scripts/visual_acceptance.mjs)，输出 `round23` 截图
- [x] 更新真实用户流脚本 [user_flow_acceptance.mjs](C:/Users/LXG/fdsmarticles/frontend/scripts/user_flow_acceptance.mjs)，覆盖游客、免费会员、管理员和移动端流程
- [x] 运行 `python -m compileall backend`
- [x] 运行 `python backend/scripts/smoke_test.py`
- [x] 运行 `npm run lint`
- [x] 运行 `npm run build`
- [x] 运行 `npm run visual:acceptance`
- [x] 运行 `npm run userflow:acceptance`

## 本轮验收结论

- [x] 登录页已经从弹窗附属能力升级为正式产品入口
- [x] `Supabase` 身份认证与本地业务用户库职责清晰联动
- [x] 游客、免费会员、付费会员、管理员的默认页面、资产和后台入口已明确区分
- [x] 管理员可以查看总览、进入会员管理并留下调权审计记录
- [x] 模拟用户库和种子账号可重复初始化，便于持续验收
- [x] 中英文与响应式在本轮新增页面上已通过视觉与浏览器流验收
- [x] 无中文编码问题，无 `JSX` / `JAX` 构建问题
