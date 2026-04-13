# Phase 1：标签体系 + 栏目体系 + 首页重构

> **目标**：为 8,431 篇文章建立 AI 标签索引，实现栏目导航，重构首页为内容 Feed 流
>
> **前置条件**：Phase 0 完成（模块化拆分 + DB Schema 就绪）
>
> **完成标志**：所有文章有标签，首页显示栏目预览 + 标签云，栏目页面可浏览

---

## 1.1 AI 批量标签生成引擎

### 1.1.1 编写标签生成脚本

```
[ ] P0 | 后端 | 新建 backend/scripts/generate_tags.py：

    核心逻辑：
    1. 连接 SQLite，查询所有 articles (SELECT id, title, content FROM articles)
    2. 过滤已处理文章 (SELECT DISTINCT article_id FROM article_tags)
    3. 对每篇文章调用 Gemini API 生成标签
    4. 解析 JSON 响应，写入 tags 表 + article_tags 表

    Gemini Prompt 设计：
    ──────────────────────────
    你是一位专业的商业内容分类专家。请为以下文章生成标签。

    标题：{title}
    内容（前3000字）：{content[:3000]}

    请严格按以下 JSON 格式输出：
    {
        "industry": ["行业标签1", "行业标签2"],
        "topic": ["主题标签1", "主题标签2", "主题标签3"],
        "type": "内容类型",
        "entities": {
            "people": ["人名1"],
            "organizations": ["机构名1"],
            "concepts": ["概念1"]
        }
    }

    约束：
    - industry 从以下选项中选择（可多选）：科技互联网、金融投资、消费零售、
      制造业、医疗健康、房地产、教育、能源环保、文化传媒
    - topic 从以下选项中选择（可多选，至少2个）：AI/人工智能、ESG/可持续、
      数字化转型、创业创新、供应链管理、领导力、品牌营销、组织管理、
      平台经济、资本市场、全球化、家族企业、新能源、产学研
    - type 从以下选项中选择（单选）：深度报道、案例分析、人物访谈、
      学术研究、行业报告、观点评论、活动纪要
    - entities 只提取文中明确出现的实体，不要臆造
    ──────────────────────────

    执行参数：
    - 批次大小：50 篇/批
    - 批次间隔：2 秒 (避免 Rate Limit)
    - 使用 gemini-2.5-flash 降低成本（非 pro）
    - 总文章数：约 8,431 篇
    - 预估 API 调用：~169 批 × 50 = 8,450 次
    - 预估耗时：约 2-4 小时

    断点续传机制：
    - 每批完成后，已处理的 article_id 已写入 article_tags 表
    - 重新运行时自动跳过已处理文章
    - 打印进度：[3450/8431] 已处理 40.9%

    错误处理：
    - JSON 解析失败 → 记录到 error_log.txt，跳过该文章
    - API 超时 → 重试 3 次，间隔 5 秒
    - Rate Limit 429 → 等待 60 秒后重试
```

### 1.1.2 标签入库逻辑

```
[ ] P0 | 后端 | 在 generate_tags.py 中实现标签去重入库：

    处理流程：
    1. 对每个标签名，查询 tags 表是否已存在
       - 存在 → 获取 tag_id，UPDATE article_count += 1
       - 不存在 → INSERT INTO tags，获取新 tag_id
    2. INSERT INTO article_tags (article_id, tag_id, confidence)
    3. confidence 默认为 1.0

    标签颜色映射（写入 tags.color 字段）：
    - industry 类标签 → 根据具体行业分配预设颜色
      科技互联网: #7C3AED (紫), 金融投资: #0891B2 (青),
      消费零售: #D97706 (琥珀), 医疗健康: #059669 (翡翠),
      能源环保: #0D9488 (青绿), 教育: #2563EB (蓝),
      制造业: #6366F1 (靛蓝), 房地产: #DC2626 (红),
      文化传媒: #DB2777 (粉)
    - topic 类标签 → 复旦橙 #ea6b00
    - type 类标签 → 复旦蓝 #0d0783
    - entity 类标签 → 灰色 #64748B
```

### 1.1.3 执行标签生成

```
[ ] P0 | 运维 | 运行标签生成脚本：
    1. python backend/scripts/generate_tags.py
    2. 监控进度输出
    3. 完成后验证：
       - SELECT COUNT(*) FROM tags; → 应有 200-500 个标签
       - SELECT COUNT(*) FROM article_tags; → 应有 25,000-40,000 行
       - SELECT COUNT(DISTINCT article_id) FROM article_tags; → 应接近 8,431
    4. 抽检 10 篇文章标签质量：
       SELECT a.title, t.name, t.category, at.confidence
       FROM articles a
       JOIN article_tags at ON a.id = at.article_id
       JOIN tags t ON at.tag_id = t.id
       ORDER BY RANDOM() LIMIT 50;
```

### 1.1.4 标签质量校验脚本

```
[ ] P1 | 后端 | 新建 backend/scripts/validate_tags.py：
    - 检查无标签文章数量
    - 检查标签分布是否合理（某标签关联文章数 > 总数50% → 警告太泛）
    - 检查标签关联文章数 = 0 的僵尸标签
    - 更新 tags.article_count 为准确值：
      UPDATE tags SET article_count = (
        SELECT COUNT(*) FROM article_tags WHERE tag_id = tags.id
      );
```

---

## 1.2 标签 API 开发

### 1.2.1 标签服务层

```
[ ] P0 | 后端 | 新建 backend/services/tag_engine.py：

    class TagEngine:
        def get_all_tags(self, category=None) -> List[TagSchema]:
            """获取所有标签，可按分类过滤，按 article_count 降序"""
            SELECT * FROM tags WHERE category = ? ORDER BY article_count DESC

        def get_tag_cloud(self, limit=50) -> List[dict]:
            """获取热门标签云数据"""
            SELECT name, category, color, article_count FROM tags
            ORDER BY article_count DESC LIMIT ?

        def get_articles_by_tag(self, tag_id, page, page_size) -> PaginatedResponse:
            """获取某标签下的文章，分页"""
            SELECT a.* FROM articles a
            JOIN article_tags at ON a.id = at.article_id
            WHERE at.tag_id = ? ORDER BY a.publish_date DESC
            LIMIT ? OFFSET ?

        def get_article_tags(self, article_id) -> List[TagSchema]:
            """获取某篇文章的所有标签"""
            SELECT t.* FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            WHERE at.article_id = ?

        def search_tags(self, keyword) -> List[TagSchema]:
            """搜索标签（用于搜索联想）"""
            SELECT * FROM tags WHERE name LIKE ? ORDER BY article_count DESC
```

### 1.2.2 标签路由

```
[ ] P0 | 后端 | 新建 backend/routers/tags.py：

    GET /api/tags
    - 查询参数：category (可选, 'industry'|'topic'|'type'|'entity')
    - 返回：List[TagSchema]
    - 调用 tag_engine.get_all_tags(category)

    GET /api/tags/cloud
    - 查询参数：limit (默认 50)
    - 返回：List[{name, category, color, article_count}]
    - 调用 tag_engine.get_tag_cloud(limit)

    GET /api/tags/{tag_id}/articles
    - 查询参数：page (默认 1), page_size (默认 20)
    - 返回：PaginatedResponse
    - 调用 tag_engine.get_articles_by_tag(tag_id, page, page_size)

    GET /api/articles/{article_id}/tags
    - 返回：List[TagSchema]
    - 调用 tag_engine.get_article_tags(article_id)

    在 main.py 注册：app.include_router(tags.router, prefix="/api")
```

---

## 1.3 栏目 API 开发

### 1.3.1 栏目自动归类脚本

```
[ ] P0 | 后端 | 新建 backend/scripts/assign_columns.py：

    归类规则（基于 columns.filter_rules JSON）：

    深度洞察 (slug=insights):
      - source IN ('business')
      - LENGTH(content) >= 3000
      → INSERT INTO article_columns (article_id, column_id=1)

    行业观察 (slug=industry):
      - source IN ('business', 'wechat')
      - 标签中含有 industry 类标签
      → INSERT INTO article_columns (article_id, column_id=2)

    学术前沿 (slug=research):
      - source IN ('news', 'wechat')
      - 标签中含有 '学术研究' type 标签 OR 标题含 '研究|论文|学术|教授'
      → INSERT INTO article_columns (article_id, column_id=3)

    院长说 (slug=dean):
      - source = 'news'
      - 标题或内容含 '院长|陆雄文|管理大视野'
      → INSERT INTO article_columns (article_id, column_id=4)

    注意：一篇文章可以属于多个栏目

    执行后验证：
    SELECT c.name, COUNT(*) FROM article_columns ac
    JOIN columns c ON ac.column_id = c.id
    GROUP BY c.name;
    → 每个栏目应有 数百到数千 篇文章
```

### 1.3.2 栏目服务层

```
[ ] P0 | 后端 | 新建 backend/services/column_engine.py 或在已有 service 中扩展：

    def get_all_columns() -> List[ColumnSchema]:
        """获取所有栏目，按 sort_order 排序"""

    def get_column_articles(slug, page, page_size) -> PaginatedResponse:
        """获取栏目下文章，分页，最新在前"""
        SELECT a.* FROM articles a
        JOIN article_columns ac ON a.id = ac.article_id
        JOIN columns c ON ac.column_id = c.id
        WHERE c.slug = ?
        ORDER BY a.publish_date DESC
        LIMIT ? OFFSET ?

    def get_column_preview(slug, limit=3) -> List[ArticleSchema]:
        """获取栏目预览（首页用，每栏目取最新3篇）"""
```

### 1.3.3 栏目路由

```
[ ] P0 | 后端 | 新建 backend/routers/columns.py：

    GET /api/columns
    - 返回：List[ColumnSchema]

    GET /api/columns/{slug}/articles
    - 查询参数：page, page_size
    - 返回：PaginatedResponse

    在 main.py 注册路由
```

---

## 1.4 首页 Feed API

### 1.4.1 实现首页聚合接口

```
[ ] P0 | 后端 | 完善 backend/routers/home.py：

    GET /api/home/feed
    - 返回 HomeFeedResponse：
      {
        "hero": {
          "id": 123,
          "title": "...",
          "publish_date": "...",
          "source": "...",
          "snippet": "...",
          "tags": [...]
        },
        "editors_picks": [
          {"id": ..., "title": ..., "tags": [...]} × 5
        ],
        "column_previews": [
          {
            "column": {"name": "深度洞察", "slug": "insights", "icon": "BookOpen"},
            "articles": [...] × 3
          },
          ... × 4 栏目
        ],
        "latest": [...] × 10,
        "hot_tags": [...] × 15
      }

    Hero 文章选取逻辑：
    - 优先取 featured_articles 表中 position='hero' 且 is_active=TRUE 的
    - 若无，取最近 7 天 view_count 最高的文章
    - 若 view_count 全为 0，取最新发布的文章

    editors_picks 选取逻辑：
    - 优先取 featured_articles 表中 position='sidebar' 的
    - 若无，取最近 30 天发布的、content 长度 > 5000 的前 5 篇

    hot_tags 选取逻辑：
    - SELECT * FROM tags ORDER BY article_count DESC LIMIT 15
```

---

## 1.5 前端 — 标签组件

### 1.5.1 TagBadge 组件

```
[ ] P0 | 前端 | 新建 frontend/src/components/tags/TagBadge.jsx：

    Props: { tag: {id, name, category, color}, size: 'sm'|'md', clickable: true }

    渲染效果：
    ┌───────────────┐
    │  #AI/人工智能   │  ← 圆角胶囊, 背景色=tag.color 10%透明度, 文字色=tag.color
    └───────────────┘

    clickable=true 时点击跳转到 /tag/{tag.name}
    size='sm': text-[10px] px-2 py-0.5
    size='md': text-xs px-3 py-1
```

### 1.5.2 TagCloud 组件

```
[ ] P0 | 前端 | 新建 frontend/src/components/tags/TagCloud.jsx：

    Props: { tags: [{name, article_count, color}], maxDisplay: 30 }

    ASCII 设计稿：
    ┌────────────────────────────────────────────────────┐
    │                                                    │
    │   AI/人工智能   数字化转型     ESG     创业创新      │
    │       供应链管理    领导力   品牌营销                │
    │   平台经济    资本市场   新能源    组织管理           │
    │     全球化   家族企业    产学研                     │
    │                                                    │
    └────────────────────────────────────────────────────┘

    - 标签大小根据 article_count 映射 (text-xs ~ text-2xl)
    - 颜色取 tag.color
    - Hover 效果：放大 + 显示文章数
    - 点击跳转到 /tag/{tagName}
```

### 1.5.3 TagFilter 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/tags/TagFilter.jsx：
    - 水平滚动标签条（用于搜索筛选）
    - 支持多选
    - 选中态：实心背景 + 白色文字
    - Props: { selectedTags, onChange, category }
```

---

## 1.6 前端 — 文章卡片升级

### 1.6.1 ArticleCard 升级

```
[ ] P0 | 前端 | 升级 frontend/src/components/article/ArticleCard.jsx：

    在原有基础上新增标签行

    升级后 ASCII 设计稿：
    ┌──────────────────────────────┐
    │   商业知识  │  2024-12-01     │  ← 来源 + 日期（保留）
    │                              │
    │   标题标题标题标题             │  ← font-serif 2xl bold
    │                              │
    │   摘要摘要摘要摘要摘要摘要...  │  ← text-sm slate-500, line-clamp-3
    │                              │
    │   #AI  #数字化转型  #创新     │  ← TagBadge 组件 × 3-5 个
    │                              │
    │   READ ARTICLE →             │  ← 保留现有交互
    └──────────────────────────────┘

    数据来源：
    - 搜索结果 API 返回时附带 tags 数组
    - 或在卡片 mount 时调用 GET /api/articles/{id}/tags
    - 推荐方案：搜索 API 直接返回 tags（减少请求数）
```

### 1.6.2 搜索 API 返回标签扩展

```
[ ] P0 | 后端 | 修改搜索结果，附带标签信息：

    在 SearchResult Schema 中新增：
    tags: List[str] = []  # 标签名列表（前端显示用）

    在 rag_search / sql_search 路由中：
    - 对每个结果的 article_id，查询其标签
    - 只返回前 5 个标签（按 article_count 降序取热门的）
    - 性能优化：批量查询 WHERE article_id IN (id1, id2, ...)
```

---

## 1.7 前端 — 首页重构

### 1.7.1 重构 HomePage

```
[ ] P0 | 前端 | 重构 frontend/src/pages/HomePage.jsx：

    ASCII 设计稿（完整首页）：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Logo] 复旦管院智识库     首页  深度洞察  行业观察  学术前沿  院长说   🔍  │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │                                                             │    │
    │  │      ┌───────────────────────────────────────────────┐      │    │
    │  │      │   [搜索框: 输入您的疑问，探索知识边界...]  [→]   │      │    │
    │  │      └───────────────────────────────────────────────┘      │    │
    │  │      [RAG模式] [精确模式]    来源: [全部] [商业] [新闻]      │    │
    │  │                                                             │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    │                                                                     │
    │  ┌─────────────────────────────┐  ┌───────────────────────────┐    │
    │  │                             │  │   📌 编辑精选              │    │
    │  │   🔥 头条文章 (大卡片)       │  │                           │    │
    │  │   [标题：AI时代的管理革命]   │  │   1. 文章标题文章标题...    │    │
    │  │   [摘要：.....]             │  │   2. 文章标题文章标题...    │    │
    │  │   #AI  #管理学  #创新       │  │   3. 文章标题文章标题...    │    │
    │  │                             │  │   4. 文章标题文章标题...    │    │
    │  └─────────────────────────────┘  │   5. 文章标题文章标题...    │    │
    │                                   └───────────────────────────┘    │
    │                                                                     │
    │  ── 🏷️ 热门标签 ──────────────────────────────────────────────     │
    │  [AI/人工智能] [ESG] [创业创新] [供应链] [数字化] [领导力] [新能源]    │
    │                                                                     │
    │  ── 📚 栏目预览 ──────────────────────────────────────────────     │
    │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │
    │  │ 深度洞察    │ │ 行业观察    │ │ 学术前沿    │ │ 院长说      │      │
    │  │ ────────── │ │ ────────── │ │ ────────── │ │ ────────── │      │
    │  │ · 标题1    │ │ · 标题1    │ │ · 标题1    │ │ · 标题1    │      │
    │  │ · 标题2    │ │ · 标题2    │ │ · 标题2    │ │ · 标题2    │      │
    │  │ · 标题3    │ │ · 标题3    │ │ · 标题3    │ │ · 标题3    │      │
    │  │ [更多 →]   │ │ [更多 →]   │ │ [更多 →]   │ │ [更多 →]   │      │
    │  └────────────┘ └────────────┘ └────────────┘ └────────────┘      │
    │                                                                     │
    │  ── 💡 一键生成知识卡 ──────────────────────────────────────────    │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │  [📖] [输入日期或关键词...]           [一键生成知识卡]        │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    │                                                                     │
    │  ── 📰 最新文章 ──────────────────────────────────────────────     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │                           │
    │  │ + Tags   │ │ + Tags   │ │ + Tags   │  (三栏布局)               │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │  (无限滚动加载更多)        │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │                                                                     │
    │  ── Footer ──────────────────────────────────────────────────      │
    │  复旦大学管理学院 © 2025  │  关于  │  联系                         │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. useQuery 调用 GET /api/home/feed
    2. 渲染 Hero 区域（搜索框 + 大标题）
    3. 渲染头条 + 编辑精选（左右布局，2:1 比例）
    4. 渲染热门标签条（TagCloud 组件，水平排列）
    5. 渲染栏目预览（四栏等宽，每栏 3 篇标题）
    6. 渲染知识卡入口（KnowledgeCard 组件）
    7. 渲染最新文章流（ArticleGrid，无限滚动）
```

### 1.7.2 实现无限滚动

```
[ ] P0 | 前端 | 新建 frontend/src/hooks/useInfiniteScroll.js：

    使用 @tanstack/react-query 的 useInfiniteQuery + react-intersection-observer：

    import { useInfiniteQuery } from '@tanstack/react-query'
    import { useInView } from 'react-intersection-observer'

    export function useInfiniteArticles(fetchFn) {
      const { ref, inView } = useInView()
      const query = useInfiniteQuery({
        queryKey: ['articles-infinite'],
        queryFn: ({ pageParam = 1 }) => fetchFn(pageParam),
        getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.page + 1 : undefined,
      })

      useEffect(() => {
        if (inView && query.hasNextPage) query.fetchNextPage()
      }, [inView])

      return { ...query, loadMoreRef: ref }
    }
```

---

## 1.8 前端 — 栏目页面

### 1.8.1 实现 ColumnPage

```
[ ] P0 | 前端 | 实现 frontend/src/pages/ColumnPage.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  ═══ 深度洞察 ════════════════════════════════════════════════       │
    │  长文深度分析、案例研究                                               │
    │                                                                     │
    │  ── 筛选 ──────────────────────────────────────────────────         │
    │  [全部] [#AI] [#ESG] [#创业] [#供应链]  ...标签横向滚动              │
    │                                                                     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │                           │
    │  │ + Tags   │ │ + Tags   │ │ + Tags   │                           │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │  (无限滚动)                │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. 从 URL 获取 slug (useParams)
    2. useQuery 调用 GET /api/columns/{slug}/articles
    3. 页面顶部：栏目名 + 描述
    4. 标签筛选条（可选，该栏目下高频标签）
    5. ArticleGrid 三栏布局 + 无限滚动
```

---

## 1.9 前端 — 标签页面

### 1.9.1 实现 TagPage

```
[ ] P0 | 前端 | 实现 frontend/src/pages/TagPage.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  🏷️ #AI/人工智能                                                    │
    │  共 342 篇相关文章                                                   │
    │                                                                     │
    │  ── 相关标签 ──────────────────────────────────────────────         │
    │  [#数字化转型] [#创业创新] [#平台经济]  （共现频率最高的标签）         │
    │                                                                     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │                           │
    │  │ + Tags   │ │ + Tags   │ │ + Tags   │                           │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. 从 URL 获取 tagName (useParams)
    2. 先查 tag_id：GET /api/tags?name={tagName}
    3. 再查文章：GET /api/tags/{tag_id}/articles
    4. 渲染标签名 + 文章数 + 文章列表
```

---

## 1.10 前端 API 层补充

```
[ ] P0 | 前端 | 实现 frontend/src/api/tags.js：
    - export getTags(category?)
    - export getTagCloud(limit?)
    - export getTagArticles(tagId, page, pageSize)
    - export getArticleTags(articleId)

[ ] P0 | 前端 | 实现 frontend/src/api/columns.js：
    - export getColumns()
    - export getColumnArticles(slug, page, pageSize)

[ ] P0 | 前端 | 实现 frontend/src/api/home.js（或直接写在 articles.js 中）：
    - export getHomeFeed()
    - export getLatestArticles(page, pageSize)
```

---

## 1.11 样式扩展

```
[ ] P0 | 前端 | 在 frontend/src/index.css 的 @theme 中新增标签色板：

    --color-tag-tech:      #7C3AED;
    --color-tag-finance:   #0891B2;
    --color-tag-consumer:  #D97706;
    --color-tag-health:    #059669;
    --color-tag-energy:    #0D9488;
    --color-tag-education: #2563EB;
    --color-col-insights:  #0d0783;
    --color-col-industry:  #ea6b00;
    --color-col-research:  #7C3AED;
    --color-col-dean:      #B45309;
```

---

## Phase 1 完成检查清单

```
[ ] tags 表有 200-500 个标签
[ ] 95%+ 文章有标签关联
[ ] GET /api/tags 返回标签列表
[ ] GET /api/tags/{id}/articles 分页返回文章
[ ] GET /api/tags/cloud 返回热门标签
[ ] GET /api/columns 返回 4 个栏目
[ ] GET /api/columns/{slug}/articles 分页返回文章
[ ] GET /api/home/feed 返回聚合首页数据
[ ] 首页显示：搜索框 + 头条 + 编辑精选 + 热门标签 + 栏目预览 + 最新文章流
[ ] 栏目页面可浏览（/column/insights 等）
[ ] 标签页面可浏览（/tag/AI 等）
[ ] 知识卡功能正常（替代时光机）
[ ] ArticleCard 显示标签
[ ] 无限滚动正常工作
[ ] git commit: "Phase 1: 标签体系 + 栏目体系 + 首页内容 Feed 重构"
```
