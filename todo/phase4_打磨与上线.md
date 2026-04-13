# Phase 4：打磨、优化与上线

> **目标**：文章详情升级、知识卡完善、性能优化、移动端适配、部署上线
>
> **前置条件**：Phase 1-3 全部完成
>
> **完成标志**：全站功能完整、移动端可用、Render+Vercel 部署成功

---

## 4.1 文章详情页升级（Modal → 独立页面）

### 4.1.1 实现独立 ArticlePage

```
[ ] P1 | 前端 | 升级 frontend/src/pages/ArticlePage.jsx：

    从侧边 Modal → 独立全屏页面
    URL: /article/:id

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │              ┌─────────────────────────────────────┐                │
    │              │                                     │                │
    │              │  商业知识  ·  2024-12-01  · 查看原文  │                │
    │              │                                     │                │
    │              │  ══ 文章标题文章标题 ═══════════      │                │
    │              │                                     │                │
    │              │  #AI/人工智能  #数字化转型  #创新     │  ← 标签行       │
    │              │                                     │                │
    │              │  ── AI 智能浓缩 ──────────────       │                │
    │              │                                     │                │
    │              │  正文正文正文正文正文正文正文正文      │                │
    │              │  正文正文正文正文正文正文正文正文      │                │
    │              │                                     │                │
    │              │  ## 小标题                           │  ← Markdown     │
    │              │                                     │                │
    │              │  正文正文正文正文正文正文正文正文      │                │
    │              │  正文正文正文正文正文正文正文正文      │                │
    │              │                                     │                │
    │              └─────────────────────────────────────┘                │
    │                                                                     │
    │              ── 📖 一键生成知识卡 ──────────────                     │
    │              ┌─────────────────────────────────────┐                │
    │              │  [为这篇文章生成手绘知识卡]    [生成]  │                │
    │              └─────────────────────────────────────┘                │
    │                                                                     │
    │              ── 🔗 相关文章推荐 ──────────────────                   │
    │              ┌──────────┐ ┌──────────┐ ┌──────────┐                │
    │              │ Card     │ │ Card     │ │ Card     │                │
    │              └──────────┘ └──────────┘ └──────────┘                │
    │                                                                     │
    │              ── 所属专题 ──────────────────────                      │
    │              [AI 时代的管理革命] [数字化转型专题]                       │
    │                                                                     │
    │              ── Footer ──                                           │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. useParams() 获取 id
    2. useQuery 调用 GET /api/summarize_article/{id}
    3. useQuery 调用 GET /api/articles/{id}/tags
    4. 渲染文章头部（来源、日期、原文链接、标签）
    5. 渲染 AI 摘要（ReactMarkdown）
    6. 底部：知识卡生成入口
    7. 底部：相关文章推荐
    8. 底部：所属专题链接
```

### 4.1.2 相关文章推荐 API

```
[ ] P1 | 后端 | 新增 GET /api/article/{id}/related：

    推荐逻辑：
    1. 获取该文章的标签
    2. 找到标签重叠度最高的其他文章：
       SELECT a.*, COUNT(DISTINCT at2.tag_id) AS overlap
       FROM articles a
       JOIN article_tags at2 ON a.id = at2.article_id
       WHERE at2.tag_id IN (SELECT tag_id FROM article_tags WHERE article_id = ?)
         AND a.id != ?
       GROUP BY a.id
       ORDER BY overlap DESC
       LIMIT 6
    3. 返回 List[ArticleCard]
```

### 4.1.3 所属专题 API

```
[ ] P1 | 后端 | 新增 GET /api/article/{id}/topics：
    SELECT t.* FROM topics t
    JOIN topic_articles ta ON t.id = ta.topic_id
    WHERE ta.article_id = ?
```

### 4.1.4 阅读量统计

```
[ ] P2 | 后端 | 在 GET /api/article/{id} 中增加阅读计数：
    UPDATE articles SET view_count = view_count + 1 WHERE id = ?
    注意：防刷策略 — 同一 IP 10 分钟内不重复计数（用内存 dict 简单实现）

[ ] P2 | 前端 | ArticleCard 和 ArticlePage 显示阅读量：
    👁️ 1.2k views
```

---

## 4.2 知识卡完善

### 4.2.1 文章页内知识卡生成

```
[ ] P1 | 后端 | 新增 POST /api/knowledge_card/generate：

    请求体：
    {
        "article_id": 123,          // 可选，指定文章
        "date": "2024-06-15",       // 可选，按日期找文章
        "keyword": "AI"             // 可选，按关键词找文章
    }

    逻辑：
    - 优先 article_id → 直接取该文章
    - 其次 keyword → RAG 搜索找最相关文章
    - 其次 date → 最近日期文章
    - 都没有 → 随机
    - 生成金句 + 手绘插画图

    一致性约束（与 Phase 0 定义的保持一致）：
    - 同一 Prompt 模板
    - 统一色调/风格/构图
    - 所有知识卡视觉上看起来像"同一个系列"
```

### 4.2.2 知识卡下载为图片

```
[ ] P2 | 前端 | 在 KnowledgeCard 组件中添加"保存"按钮：

    实现方案：
    - 使用 html2canvas 或 dom-to-image 库
    - npm install html2canvas
    - 点击保存 → 将卡片 DOM 截图为 PNG → 触发下载

    下载文件名格式：复旦智识卡_{日期}_{标题前10字}.png
```

### 4.2.3 知识卡分享

```
[ ] P2 | 前端 | 知识卡底部添加分享功能：
    - 复制链接（/article/{id}?card=true）
    - 微信分享（调用 Web Share API，移动端）
```

---

## 4.3 性能优化

### 4.3.1 后端缓存

```
[ ] P1 | 后端 | 引入简单内存缓存（避免引入 Redis 增加复杂度）：

    使用 functools.lru_cache 或 cachetools：
    pip install cachetools

    缓存策略：
    - GET /api/home/feed → TTL 5 分钟
    - GET /api/tags → TTL 1 小时
    - GET /api/tags/cloud → TTL 1 小时
    - GET /api/columns → TTL 1 小时
    - GET /api/suggest → TTL 5 分钟
    - GET /api/topics → TTL 10 分钟
    - AI 摘要 → 已有前端 summaryCache，后端可加 TTL 24 小时
```

### 4.3.2 前端懒加载

```
[ ] P1 | 前端 | 使用 React.lazy + Suspense 实现路由级懒加载：

    const HomePage = React.lazy(() => import('./pages/HomePage'))
    const SearchPage = React.lazy(() => import('./pages/SearchPage'))
    const TopicPage = React.lazy(() => import('./pages/TopicPage'))
    ...

    <Suspense fallback={<LoadingStates.PageSkeleton />}>
      <Routes>...</Routes>
    </Suspense>
```

### 4.3.3 图片懒加载

```
[ ] P1 | 前端 | 知识卡和专题封面图使用 loading="lazy"：
    <img loading="lazy" src={...} alt={...} />

[ ] P1 | 前端 | 首屏以下的 ArticleCard 使用 IntersectionObserver 懒加载
```

### 4.3.4 API 请求优化

```
[ ] P1 | 前端 | React Query 缓存策略：
    - staleTime: 5 分钟（5 分钟内不重新请求）
    - cacheTime: 30 分钟（30 分钟后清除缓存）
    - 搜索结果：每次请求（staleTime: 0）
    - 首页 Feed：5 分钟
    - 标签/栏目数据：30 分钟
```

---

## 4.4 移动端适配

### 4.4.1 响应式断点

```
[ ] P1 | 前端 | 确认 Tailwind 响应式断点使用正确：

    布局策略：
    - 手机 (<768px)：单列布局
    - 平板 (768-1024px)：两列布局
    - 桌面 (>1024px)：三列布局

    关键适配点：
    - Navbar：桌面=水平导航，手机=汉堡菜单
    - 搜索框：桌面=大尺寸，手机=适中
    - ArticleGrid：桌面=3列，平板=2列，手机=1列
    - ChatPanel：桌面=侧边栏420px，手机=全屏
    - 知识卡：桌面=居中 max-w-2xl，手机=全宽
    - 专题时间线：桌面=左侧线+右侧内容，手机=居中线
```

### 4.4.2 Navbar 移动端

```
[ ] P1 | 前端 | 实现 Navbar 汉堡菜单：

    桌面态（>768px）：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Logo] 复旦管院智识库     首页  深度洞察  行业观察  学术前沿  院长说   🔍  │
    └─────────────────────────────────────────────────────────────────────┘

    手机态（<768px）：
    ┌────────────────────────────┐
    │  [Logo]            [☰] [🔍]│
    └────────────────────────────┘
    点击 ☰ 展开：
    ┌────────────────────────────┐
    │  首页                      │
    │  深度洞察                   │
    │  行业观察                   │
    │  学术前沿                   │
    │  院长说                    │
    │  专题                      │
    └────────────────────────────┘
```

### 4.4.3 触摸交互优化

```
[ ] P1 | 前端 | 移动端交互优化：
    - 卡片点击区域：确保 min-height 48px（Google 推荐触摸目标）
    - 搜索联想下拉：触摸友好的选项间距
    - ChatPanel：移动端全屏展开，滑动关闭
    - 知识卡：支持左右滑动刷新
```

---

## 4.5 错误处理与兜底

### 4.5.1 空状态组件

```
[ ] P1 | 前端 | 实现 frontend/src/components/common/EmptyStates.jsx：

    场景 & ASCII 设计稿：

    搜索无结果：
    ┌──────────────────────────────┐
    │                              │
    │        🔍                    │
    │   暂无相关内容                │
    │   请尝试更具体的关键词         │
    │                              │
    │   热门搜索: [AI] [ESG] [MBA] │
    └──────────────────────────────┘

    栏目空：
    ┌──────────────────────────────┐
    │        📂                    │
    │   该栏目暂无文章              │
    │   [返回首页]                 │
    └──────────────────────────────┘

    网络错误：
    ┌──────────────────────────────┐
    │        ⚠️                    │
    │   加载失败，请检查网络         │
    │   [重试]                     │
    └──────────────────────────────┘

    AI 生成失败：
    ┌──────────────────────────────┐
    │        🤖                    │
    │   AI 导读生成失败             │
    │   已显示原文内容              │
    └──────────────────────────────┘
```

### 4.5.2 全局错误边界

```
[ ] P1 | 前端 | 在 App.jsx 中添加 ErrorBoundary：
    - 使用 react-error-boundary 或自定义 class component
    - 捕获渲染错误，显示友好的错误页面
    - 提供"重试"按钮
```

### 4.5.3 加载状态

```
[ ] P1 | 前端 | 实现 frontend/src/components/common/LoadingStates.jsx：

    - PageSkeleton：整页骨架屏（灰色块状占位）
    - CardSkeleton：单个卡片骨架屏
    - ArticleSkeleton：文章页骨架屏
    - InlineSpin：行内小 loading spinner

    全部使用 animate-pulse 动画
```

---

## 4.6 Footer 组件

```
[ ] P1 | 前端 | 实现 frontend/src/components/layout/Footer.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │  [Logo]  复旦大学管理学院 · 智识库                                    │
    │                                                                     │
    │  基于 8,400+ 篇深度商业文章                                          │
    │  RAG 智能检索  ·  AI 对话助理  ·  知识专题                            │
    │                                                                     │
    │  ──────────────────────────────────────────────────────────         │
    │  © 2025 复旦大学管理学院  │  技术支持: Gemini + FAISS + React         │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 4.7 部署更新

### 4.7.1 后端部署（Render）

```
[ ] P0 | 运维 | 更新 Render 部署配置：

    1. 确认 requirements.txt 包含所有新依赖：
       rank-bm25
       jieba
       cachetools
       （其他原有依赖保持不变）

    2. 确认启动命令：
       uvicorn backend.main:app --host 0.0.0.0 --port $PORT

    3. 确认环境变量：
       GOOGLE_API_KEY=xxx
       RENDER=true

    4. 确认持久化磁盘挂载：/etc/fdsm_data
       - fudan_knowledge_base.db（含新表和标签数据）
       - faiss_index/

    5. 上传更新后的数据库到持久化磁盘
```

### 4.7.2 前端部署（Vercel）

```
[ ] P0 | 运维 | 更新 Vercel 部署配置：

    1. 确认 vercel.json 中 rewrites 支持 SPA 路由：
       {
         "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
       }

    2. 确认环境变量：
       VITE_API_BASE_URL=https://xxx.onrender.com/api

    3. 构建命令：npm run build
    4. 输出目录：dist

    5. 测试所有路由在 Vercel 上可访问：
       /
       /search?q=AI
       /column/insights
       /tag/AI
       /topics
       /topic/ai-management
       /article/123
```

### 4.7.3 数据同步

```
[ ] P0 | 运维 | 将本地新数据上传到 Render 持久化磁盘：

    需要同步的数据：
    - fudan_knowledge_base.db（含 tags, article_tags, columns,
      article_columns, topics, topic_articles 等新表数据）
    - faiss_index/ （如果有重建）

    方式：
    - 通过 Render SSH 或文件上传
    - 或通过 API 迁移脚本在线执行
```

---

## 4.8 SEO 基础优化（可选）

```
[ ] P2 | 前端 | 添加 react-helmet-async 管理页面 meta：
    - 每个页面设置 title、description
    - 文章页：title = 文章标题
    - 专题页：title = 专题标题

[ ] P2 | 前端 | 添加 sitemap 生成脚本：
    - 遍历所有文章、专题、栏目 URL
    - 输出 sitemap.xml 到 public/
```

---

## Phase 4 完成检查清单

```
[ ] 文章详情页独立 (/article/:id)，显示 AI 摘要 + 标签 + 相关推荐 + 所属专题
[ ] 知识卡可从文章页生成，保存为 PNG
[ ] 阅读量统计正常工作
[ ] 首页加载时间 < 3 秒
[ ] 路由级懒加载正常
[ ] API 缓存命中率 > 80%
[ ] 移动端所有页面适配正常
[ ] Navbar 汉堡菜单正常工作
[ ] 空状态 / 错误状态 / 加载状态全覆盖
[ ] Footer 显示正确
[ ] Render 后端部署成功，所有 API 可访问
[ ] Vercel 前端部署成功，所有路由可访问
[ ] 端到端测试：首页 → 搜索 → 文章 → 知识卡 → 专题 → AI 对话 全流程跑通
[ ] git commit: "Phase 4: 全站打磨 + 移动端适配 + 部署上线"
```

---

## 最终交付清单

```
[ ] 8 个前端页面全部可用
[ ] 15+ 后端 API 端点全部响应正常
[ ] 8,431 篇文章 × 标签覆盖率 > 95%
[ ] 15+ 自动专题 + 3+ 编辑专题
[ ] 4 个栏目有内容
[ ] AI 对话助理可用，回答有引用
[ ] 知识卡（替代时光机）手绘风格一致
[ ] 搜索结果 Top-3 命中率 > 85%
[ ] 移动端完全适配
[ ] Render + Vercel 部署成功
```
