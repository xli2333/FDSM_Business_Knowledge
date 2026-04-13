# Phase 3：主题专题系统

> **目标**：将散落文章编织为结构化知识专题，支持 AI 自动生成 + 编辑策划
>
> **前置条件**：Phase 1 完成（标签体系就绪，article_tags 数据已有）
>
> **完成标志**：15+ 个自动专题上线，专题详情页可浏览时间线和观点

---

## 3.1 AI 自动专题生成引擎

### 3.1.1 编写专题生成脚本

```
[ ] P1 | 后端 | 新建 backend/scripts/generate_topics.py：

    Pipeline 流程：

    ── Step 1: 标签聚类分析 ──
    找出 article_count > 30 的热门标签组合：
    SELECT t1.name AS tag1, t2.name AS tag2, COUNT(*) AS co_count
    FROM article_tags at1
    JOIN article_tags at2 ON at1.article_id = at2.article_id AND at1.tag_id < at2.tag_id
    JOIN tags t1 ON at1.tag_id = t1.id
    JOIN tags t2 ON at2.tag_id = t2.id
    GROUP BY t1.name, t2.name
    HAVING co_count > 30
    ORDER BY co_count DESC
    LIMIT 20;

    结果示例：
    ("AI/人工智能", "数字化转型") → 85 篇
    ("ESG/可持续", "金融投资") → 52 篇
    ("创业创新", "科技互联网") → 67 篇

    ── Step 2: 专题元数据生成（Gemini）──
    对每个候选聚类调用 Gemini：

    Prompt:
    """
    基于以下标签聚类，为复旦管院知识库生成一个专题：

    标签组合：{tag1} + {tag2}
    共涉及 {count} 篇文章

    请生成：
    1. 专题标题（15字以内，有吸引力）
    2. 专题导读（200-300字，概述该领域的发展脉络）
    3. URL slug（英文小写，用短横线连接）
    4. 专题类型："auto"

    输出 JSON：
    {
        "title": "...",
        "description": "...",
        "slug": "...",
        "type": "auto"
    }
    """

    ── Step 3: 文章筛选与排序 ──
    对每个专题：
    1. 查找同时包含该标签组合的文章
    2. 按 publish_date 降序排列
    3. 取 Top-30（上限）
    4. 写入 topic_articles 表

    ── Step 4: 关联标签 ──
    将构成该专题的标签写入 topic_tags 表

    ── Step 5: 执行并验证 ──
    预期产出：15-20 个自动专题
    每个专题关联 15-30 篇文章
```

### 3.1.2 预定义专题模板

```
[ ] P1 | 后端 | 在 generate_topics.py 中预设几个手动专题：

    手动插入的"编辑策划"专题（type='editorial'）：

    1. "复旦管院 40 年：里程碑回顾"
       slug: fdsm-40-years
       type: timeline
       auto_rules: {"keywords": ["40周年", "恢复建院", "里程碑"]}

    2. "院长说：管理的智慧"
       slug: deans-view
       type: editorial
       auto_rules: {"keywords": ["院长", "陆雄文"], "source": ["news"]}

    3. "2024 年度商业知识盘点"
       slug: 2024-business-review
       type: editorial
       auto_rules: {"date_range": ["2024-01-01", "2024-12-31"], "source": ["business"]}

    每个手动专题也需关联文章和标签
```

### 3.1.3 执行专题生成

```
[ ] P1 | 运维 | 运行专题生成脚本：
    1. python backend/scripts/generate_topics.py
    2. 验证：
       SELECT COUNT(*) FROM topics; → 应有 15-25 个
       SELECT t.title, COUNT(ta.article_id) AS article_count
       FROM topics t
       LEFT JOIN topic_articles ta ON t.id = ta.topic_id
       GROUP BY t.title;
       → 每个专题应有 10-30 篇文章
```

---

## 3.2 专题 API 开发

### 3.2.1 专题服务层

```
[ ] P1 | 后端 | 新建 backend/services/topic_engine.py：

    class TopicEngine:

        def get_all_topics(self, status="published", page=1, page_size=12):
            """获取专题列表，分页"""
            SELECT t.*, COUNT(ta.article_id) AS article_count
            FROM topics t
            LEFT JOIN topic_articles ta ON t.id = ta.topic_id
            WHERE t.status = ?
            GROUP BY t.id
            ORDER BY t.updated_at DESC
            LIMIT ? OFFSET ?

        def get_topic_detail(self, slug):
            """获取专题详情 + 关联文章 + 关联标签"""
            返回：{
                topic: TopicSchema,
                articles: List[ArticleWithTags],
                tags: List[TagSchema],
                related_topics: List[TopicSchema]  ← 标签重叠度 > 50% 的其他专题
            }

        def get_topic_timeline(self, topic_id):
            """获取专题时间线"""
            SELECT a.id, a.title, a.publish_date, a.source
            FROM articles a
            JOIN topic_articles ta ON a.id = ta.article_id
            WHERE ta.topic_id = ?
            ORDER BY a.publish_date ASC
            → 返回按年月分组的时间线节点

        def get_topic_insights(self, topic_id):
            """AI 生成专题洞察（动态生成，可缓存）"""
            1. 取该专题 Top-10 文章内容
            2. Gemini 提取核心观点：
               Prompt: "分析以下 {count} 篇文章，提炼 5-8 个核心观点..."
            3. 返回结构化观点列表
            4. 缓存到 topics.description 或独立缓存表

        def create_topic(self, data):
            """创建专题（管理端）"""

        def update_topic(self, topic_id, data):
            """更新专题"""
```

### 3.2.2 专题路由

```
[ ] P1 | 后端 | 新建 backend/routers/topics.py：

    GET /api/topics
    - 查询参数：status, page, page_size
    - 返回：PaginatedResponse[TopicSchema]

    GET /api/topics/{slug}
    - 返回：TopicDetailResponse (专题信息 + 文章列表 + 标签 + 相关专题)

    GET /api/topics/{slug}/timeline
    - 返回：List[TimelineNode] (按年月分组)

    GET /api/topics/{slug}/insights
    - 返回：List[InsightItem] (AI 生成的核心观点)

    POST /api/topics
    - 管理端创建专题

    POST /api/topics/auto-generate
    - 触发 AI 自动专题生成（异步执行）

    在 main.py 注册路由
```

---

## 3.3 前端 — 专题广场页

### 3.3.1 实现 TopicsPage

```
[ ] P1 | 前端 | 实现 frontend/src/pages/TopicsPage.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  ═══ 专题广场 ════════════════════════════════════════════════       │
    │  探索复旦管院知识库中的深度主题                                        │
    │                                                                     │
    │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
    │  │                  │ │                  │ │                  │    │
    │  │  [AI 生成封面图]  │ │  [AI 生成封面图]  │ │  [AI 生成封面图]  │    │
    │  │                  │ │                  │ │                  │    │
    │  │  AI 时代的管理革命│ │  ESG 投资深度追踪 │ │  创业创新生态    │    │
    │  │  #AI #管理学     │ │  #ESG #金融      │ │  #创业 #科技     │    │
    │  │  42篇文章        │ │  28篇文章        │ │  35篇文章        │    │
    │  └──────────────────┘ └──────────────────┘ └──────────────────┘    │
    │                                                                     │
    │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐    │
    │  │  TopicCard       │ │  TopicCard       │ │  TopicCard       │    │
    │  └──────────────────┘ └──────────────────┘ └──────────────────┘    │
    │                                                                     │
    │  (三栏网格，分页加载)                                                │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. useQuery 调用 GET /api/topics?page=1
    2. 渲染 TopicCard 网格
    3. 点击卡片 → navigate(`/topic/${slug}`)
```

### 3.3.2 TopicCard 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/topic/TopicCard.jsx：

    Props: { topic: {title, slug, description, cover_image, type, tags, article_count} }

    ┌──────────────────────┐
    │                      │
    │   [封面图 / 渐变色]   │  ← 16:9 比例, 无图时用渐变色背景
    │                      │
    │   专题标题            │  ← font-serif xl bold
    │   #标签1 #标签2       │  ← TagBadge size=sm
    │   42 篇文章           │  ← text-xs slate-400
    └──────────────────────┘

    Hover 效果：卡片上移 + 阴影加深
    type 标识：右上角角标
    - auto → "AI 策划"
    - editorial → "编辑精选"
    - timeline → "时间线"
```

---

## 3.4 前端 — 专题详情页

### 3.4.1 实现 TopicPage

```
[ ] P1 | 前端 | 实现 frontend/src/pages/TopicPage.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │                                                             │    │
    │  │             [专题封面图 / 渐变色大Banner]                    │    │
    │  │                                                             │    │
    │  │        ═══ AI 时代的管理革命 ════════════════                │    │
    │  │        #AI/人工智能  #管理学  #组织变革  #领导力              │    │
    │  │                                                             │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    │                                                                     │
    │  ── 📝 专题导读 ──────────────────────────────────────────────     │
    │  "从2018年至今，复旦管院知识库中有超过200篇文章涉及人工智能对        │
    │   管理实践的影响。本专题梳理了AI技术从概念讨论到企业落地的完整         │
    │   演进路径..."                                                      │
    │                                                                     │
    │  ── ⏳ 时间线 ──────────────────────────────────────────────       │
    │                                                                     │
    │  2025                                                               │
    │    │                                                                │
    │    ├── 03月  《DeepSeek与大模型的未来》                              │
    │    │         商业知识  #AI  [查看→]                                  │
    │    │                                                                │
    │    ├── 01月  《生成式AI的企业落地实践》                               │
    │    │         学院新闻  #AI #数字化  [查看→]                          │
    │    │                                                                │
    │  2024                                                               │
    │    │                                                                │
    │    ├── 11月  《AI如何重构团队协作》                                   │
    │    │         ...                                                    │
    │    ├── 06月  《从ChatGPT看AI治理》                                   │
    │    │         ...                                                    │
    │    │                                                                │
    │  2023                                                               │
    │    ├── ...                                                          │
    │                                                                     │
    │  ── 💡 核心观点 ──────────────────────────────────────────────     │
    │                                                                     │
    │  ┌────────────────────────────────────────┐                         │
    │  │  1. AI 正在从"工具辅助"转向"决策参与"   │                         │
    │  │     来源：《AI时代的管理革命》等 5 篇    │                         │
    │  │                                        │                         │
    │  │  2. 企业 AI 落地的最大障碍是组织文化     │                         │
    │  │     来源：《生成式AI的企业落地》等 3 篇  │                         │
    │  │                                        │                         │
    │  │  3. ...                                │                         │
    │  └────────────────────────────────────────┘                         │
    │                                                                     │
    │  ── 📚 相关文章 ──────────────────────────────────────────────     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │  (文章卡片网格)             │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │                                                                     │
    │  ── 🔗 相关专题 ──────────────────────────────────────────────     │
    │  [数字化转型专题] [领导力专题] [创业创新专题]                          │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘

    实现步骤：
    1. useParams() 获取 slug
    2. useQuery 调用 GET /api/topics/{slug}
    3. 渲染封面 Banner
    4. 渲染导读文字
    5. useQuery 调用 GET /api/topics/{slug}/timeline → 渲染 TopicTimeline
    6. useQuery 调用 GET /api/topics/{slug}/insights → 渲染核心观点
    7. 渲染相关文章 ArticleGrid
    8. 渲染相关专题 TopicCard 横向列表
```

### 3.4.2 TopicTimeline 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/topic/TopicTimeline.jsx：

    Props: { nodes: [{year, month, articles: [{id, title, source, tags}]}] }

    - 左侧：竖线 + 年份节点（大圆点）
    - 右侧：月份 + 文章标题 + 来源标签
    - 年份切换处加粗分隔
    - 文章标题可点击 → 打开 ArticleDetail
    - 动画：滚动进入视口时淡入
```

### 3.4.3 TopicInsights 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/topic/TopicInsights.jsx：

    Props: { insights: [{point, source_count, source_titles}] }

    - 编号列表，每条观点为一个卡片
    - 底部显示来源文章数
    - 可折叠展开看来源文章列表
```

---

## 3.5 前端 API 层

```
[ ] P1 | 前端 | 实现 frontend/src/api/topics.js：
    - export getTopics(page, pageSize)
    - export getTopicDetail(slug)
    - export getTopicTimeline(slug)
    - export getTopicInsights(slug)
```

---

## 3.6 首页集成专题入口

```
[ ] P1 | 前端 | 在 HomePage 中新增"精选专题"模块：

    位置：栏目预览下方、最新文章上方

    ── 📖 精选专题 ──────────────────────────────────────
    ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
    │  TopicCard       │ │  TopicCard       │ │  TopicCard       │
    └──────────────────┘ └──────────────────┘ └──────────────────┘
    [查看更多专题 →]

    数据来源：/api/home/feed 中新增 featured_topics 字段
```

---

## 3.7 Navbar 集成专题入口

```
[ ] P1 | 前端 | 在 Navbar 中添加"专题"导航项：

    首页  深度洞察  行业观察  学术前沿  院长说  专题   🔍 🤖
                                               ^^^^
    点击 → navigate('/topics')
```

---

## Phase 3 完成检查清单

```
[ ] topics 表有 15-25 个专题
[ ] 每个专题关联 10-30 篇文章
[ ] GET /api/topics 返回分页专题列表
[ ] GET /api/topics/{slug} 返回专题详情 + 文章 + 标签
[ ] GET /api/topics/{slug}/timeline 返回时间线
[ ] GET /api/topics/{slug}/insights 返回 AI 观点
[ ] 专题广场页 (/topics) 显示网格
[ ] 专题详情页 (/topic/{slug}) 显示封面 + 导读 + 时间线 + 观点 + 文章
[ ] 首页有专题入口
[ ] Navbar 有专题链接
[ ] git commit: "Phase 3: 主题专题系统 — AI 自动生成 + 时间线 + 观点提取"
```
