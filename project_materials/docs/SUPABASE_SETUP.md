# Supabase 接入说明

本文档说明如何为当前知识库项目启用 Supabase 登录能力。当前实现只把 Supabase 用于用户身份与会话控制，不改变业务文章的数据来源和主数据库结构。

## 1. 需要的环境变量

后端环境变量：

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SITE_BASE_URL`

前端环境变量：

- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_API_BASE_URL`

推荐本地示例：

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SITE_BASE_URL=http://127.0.0.1:4173

VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## 2. Supabase 控制台配置

1. 创建一个 Supabase 项目。
2. 在 `Authentication > Providers` 中启用邮箱登录。
3. 在 `Authentication > URL Configuration` 中加入允许的站点地址。

本地开发建议加入：

- `http://127.0.0.1:4173`
- `http://localhost:4173`

生产环境则加入你的正式域名。

## 3. 当前产品中的身份边界

- 未登录访客：可以浏览文章，并产生去重浏览事件。
- 已登录用户：可以点赞、收藏，并查看“我的资产”页。
- Supabase 的职责：提供邮箱 OTP / Magic Link 登录、会话持久化和后端令牌校验。

## 4. 当前已经接好的功能

- 顶部导航登录入口
- 文章页点赞 / 收藏
- 我的资产页
- 后端 `/api/auth/status`
- 后端基于 Supabase Token 的点赞 / 收藏权限校验

## 5. 启动与验收

后端：

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm run dev
```

快速验收点：

1. 顶部出现“邮箱登录”入口。
2. 未登录点击文章页点赞或收藏，会出现登录弹窗。
3. 配好 Supabase 后，邮箱会收到登录链接。
4. 登录后可完成点赞、收藏，并访问 `/me` 查看个人资产。
