# 复旦管院智识库 — 原子级项目企划书

> **产品定位**：以复旦大学管理学院 8,400+ 篇深度商业文章为知识底座，构建一个集 **RAG 智能检索、AI 对话助理、标签体系、栏目频道、主题专题** 五大核心能力于一体的新一代知识库平台。
>
> **对标产品**：36氪（栏目化 + 标签化 + 主题策划）× 财新网（深度内容 + 知识付费 + 专业检索）× Perplexity（AI 对话式检索）
>
> **品牌基因**：延续复旦蓝 `#0d0783` + 复旦橙 `#ea6b00` 视觉体系，Noto Serif SC 学术衬线字体，保持学术质感与现代交互的平衡。

---

## 一、现状资产盘点

### 1.1 数据资产

| 资产 | 规模 | 格式 |
|------|------|------|
| 商业知识文章 (Business) | 2,110 篇 | content.txt + 配图 |
| 学院新闻 (News) | 4,725 篇 | content.txt + 配图 |
| 微信公众号 (WeChat) | 1,596 篇 | content.txt + 配图 |
| **合计** | **8,431 篇** | 时间跨度 2001–2025 |
| SQLite 数据库 | 50 MB | articles 表 (id, source, title, publish_date, link, content) |
| FAISS 向量索引 | 351 MB | 800字分块, 100字重叠, Gemini Embedding |

### 1.2 技术资产

| 组件 | 技术栈 | 状态 |
|------|--------|------|
| 后端 | FastAPI + Python 3.11 | 已上线 |
| 前端 | React 19 + Vite + Tailwind CSS v4 | 已上线 |
| 向量检索 | FAISS + Gemini Embedding | 已运行 |
| AI 引擎 | Gemini 2.5 Pro (摘要/查询扩展) | 已集成 |
| 图像生成 | Gemini 3 Pro Image Preview | 已集成 |
| 部署 | Render (Backend) + Vercel (Frontend) | 已部署 |
| 爬虫 | 4 个 Python 爬虫脚本 | 可用 |

### 1.3 视觉资产

| 元素 | 说明 |
|------|------|
| 主 Logo | 复旦管院 40 周年院徽 (蓝底金字圆形章 + 复旦大学管理学院文字) |
| 辅助 Logo | 1985-2025 纪念版 (金色渐变 + 彩色斜线装饰) |
| 品牌色 | 复旦蓝 `#0d0783`、复旦橙 `#ea6b00`、深蓝 `#0a0560` |
| 字体 | Noto Serif SC (标题)、Inter / Noto Sans SC (正文) |
| 动效 | Framer Motion 平滑过渡 |

---

## 二、产品愿景与核心理念

### 2.1 一句话定义

**「复旦管院智识库」** — 十年商业智慧，一键触达。

### 2.2 核心价值主张

```
传统新闻稿系统 ────────→ 智识库平台
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
搜索找文章          →    对话问知识
线性时间流          →    标签 × 栏目 × 主题 三维导航
单篇阅读            →    知识网络关联推荐
被动检索            →    AI 主动洞察 + 每日推送
静态内容            →    AI 增强内容 (摘要/观点/图谱)
```

### 2.3 目标用户画像

| 用户群 | 场景 | 核心需求 |
|--------|------|----------|
| 管院师生 | 课程研究、案例教学 | 按主题快速找到相关案例和观点 |
| MBA/EMBA 学员 | 行业研究、论文写作 | 跨领域知识关联、深度内容挖掘 |
| 校友/企业家 | 行业动态追踪 | 栏目订阅、主题专报 |
| 媒体/研究者 | 引用、数据查找 | 精确检索、原文溯源 |

---

## 三、五大核心系统详细设计

---

### 核心一：顶级 RAG 系统 (升级现有)

> **目标**：从"能搜到"升级到"搜得准、搜得全、搜得聪明"

#### 3.1.1 现有 RAG 能力 (保留)

- [x] Gemini Embedding 向量化
- [x] 查询意图提取 (extract_core_query)
- [x] 多查询扩展 + 融合排序
- [x] 来源过滤 + 时间过滤
- [x] 相似度阈值控制

#### 3.1.2 升级项

| 模块 | 升级内容 | 技术方案 |
|------|----------|----------|
| **Hybrid Search** | 向量检索 + BM25 关键词检索混合 | 引入 `rank_bm25` 库，融合得分 = α×向量分 + (1-α)×BM25分 |
| **Re-Ranker** | 粗检索 → 精排序二阶段 | 粗检召回 Top-50 → Gemini 2.5 Pro 对每条做 0-10 相关性打分 → 返回 Top-10 |
| **语义分块优化** | 当前 800 字定长分块 → 语义段落分块 | 按自然段落 + 标题层级分块，保留段落元数据 (所属章节标题) |
| **上下文窗口** | 返回匹配段落 ± 1 段 | 在 chunk metadata 中存储 prev_chunk_id / next_chunk_id |
| **多模态检索** | 支持按图搜文 (远期) | 图片 Embedding 与文本 Embedding 对齐 |
| **搜索建议** | 输入时实时联想 | 前端 debounce + 后端 `/api/suggest` 接口 (SQLite LIKE + 热门查询) |

#### 3.1.3 新增 API 端点

```
POST /api/search          # 统一检索入口 (合并 rag_search + sql_search)
  ├── mode: "smart" | "exact"
  ├── query: string
  ├── filters: { sources[], tags[], dateRange, columns[] }
  ├── sort: "relevance" | "date" | "popularity"
  └── page / pageSize

GET  /api/suggest          # 搜索联想
GET  /api/search/history   # 搜索历史 (本地存储)
```

---

### 核心二：AI 助理系统 (全新)

> **目标**：从"搜索引擎"升级到"对话式知识顾问"
>
> **对标**：Perplexity × ChatGPT with RAG

#### 3.2.1 产品形态

**右下角悬浮助手** → 点击展开为沉浸式对话面板 (类 ChatGPT 侧边栏)

```
┌────────────────────────────────────────────┐
│  🤖 复旦智识助理                    [—] [×]  │
├────────────────────────────────────────────┤
│                                            │
│  用户: 近三年复旦管院在ESG领域有什么研究？    │
│                                            │
│  助理: 根据知识库中的文章，复旦管院在ESG     │
│  领域有以下重要研究和观点：                   │
│                                            │
│  1. **《ESG投资的中国实践》** (2024-03-15)   │
│     - 核心观点：...                         │
│     - [查看原文 →]                          │
│                                            │
│  2. **《双碳目标下的企业治理》** (2023-11-02) │
│     - 核心观点：...                         │
│     - [查看原文 →]                          │
│                                            │
│  📎 引用来源: 5篇文章  ⏱️ 检索范围: 2021-2025 │
│                                            │
├────────────────────────────────────────────┤
│  [输入您的问题...]              [发送 ➤]     │
└────────────────────────────────────────────┘
```

#### 3.2.2 技术架构

```
用户提问
  │
  ├── 1. 意图识别 (Gemini 2.5 Pro)
  │     ├── 知识检索类 → RAG Pipeline
  │     ├── 闲聊/问候类 → 直接回复
  │     └── 分析/总结类 → Multi-Article RAG
  │
  ├── 2. RAG 检索 (复用升级后的 Hybrid Search)
  │     └── 返回 Top-5 相关段落 + 元数据
  │
  ├── 3. 答案生成 (Gemini 2.5 Pro)
  │     ├── System Prompt: 你是复旦管院智识助理...
  │     ├── Context: [检索到的段落]
  │     └── 约束: 必须引用来源、不编造信息
  │
  └── 4. 结构化输出
        ├── answer: Markdown 格式回答
        ├── sources: [{id, title, date, relevance}]
        ├── follow_up_questions: [建议追问]
        └── confidence: 0-1 置信度
```

#### 3.2.3 新增 API 端点

```
POST /api/chat                 # AI 对话 (支持流式输出)
  ├── messages: [{role, content}]  # 多轮对话历史
  ├── session_id: string           # 会话 ID
  └── mode: "precise" | "creative"

GET  /api/chat/sessions        # 会话列表
GET  /api/chat/session/{id}    # 会话详情
```

#### 3.2.4 预设快捷指令

| 指令 | 功能 |
|------|------|
| `/summarize [topic]` | 总结某主题下所有相关文章的核心观点 |
| `/compare [A] vs [B]` | 对比两个话题/企业的相关报道 |
| `/timeline [topic]` | 生成某话题的时间线脉络 |
| `/recommend` | 基于浏览历史推荐文章 |
| `/today` | 历史上的今天 (时光机升级版) |

---

### 核心三：标签体系 (全新)

> **目标**：为 8,400+ 篇文章建立多维度标签索引，实现精准筛选和知识发现
>
> **对标**：36氪标签系统 (每篇文章 3-5 个标签, 标签可点击进入专题页)

#### 3.3.1 标签分类体系

```
标签层级:
  ├── L1: 行业标签 (Industry)
  │     ├── 科技互联网    ├── 金融投资    ├── 消费零售
  │     ├── 制造业        ├── 医疗健康    ├── 房地产
  │     ├── 教育          ├── 能源环保    └── 文化传媒
  │
  ├── L2: 主题标签 (Topic)
  │     ├── AI/人工智能   ├── ESG/可持续   ├── 数字化转型
  │     ├── 创业创新      ├── 供应链管理   ├── 领导力
  │     ├── 品牌营销      ├── 组织管理     ├── 平台经济
  │     ├── 资本市场      ├── 全球化       └── 家族企业
  │
  ├── L3: 内容类型标签 (Type)
  │     ├── 深度报道      ├── 案例分析     ├── 人物访谈
  │     ├── 学术研究      ├── 行业报告     ├── 观点评论
  │     └── 活动纪要
  │
  └── L4: 实体标签 (Entity) — AI 自动提取
        ├── 人物: 陆雄文, 马斯克, 任正非...
        ├── 机构: 复旦管院, 华为, 特斯拉...
        └── 概念: LLM, DeepSeek, 新质生产力...
```

#### 3.3.2 AI 自动标签引擎

```python
# 批量标签生成 Pipeline
for article in articles:
    tags = gemini.generate(
        prompt=f"""
        为以下文章生成标签:
        标题: {article.title}
        内容: {article.content[:3000]}

        输出JSON:
        {{
            "industry": ["行业标签1", "行业标签2"],
            "topic": ["主题标签1", "主题标签2", "主题标签3"],
            "type": "内容类型",
            "entities": {{
                "people": ["人名1"],
                "organizations": ["机构1"],
                "concepts": ["概念1"]
            }}
        }}
        """
    )
    save_tags(article.id, tags)
```

#### 3.3.3 数据库扩展

```sql
-- 新增表
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,          -- 标签名
    category TEXT NOT NULL,             -- industry/topic/type/entity
    description TEXT,                   -- 标签描述
    color TEXT,                         -- 前端显示颜色
    article_count INTEGER DEFAULT 0     -- 关联文章数 (缓存)
);

CREATE TABLE article_tags (
    article_id INTEGER REFERENCES articles(id),
    tag_id INTEGER REFERENCES tags(id),
    confidence REAL DEFAULT 1.0,        -- AI 标注置信度
    PRIMARY KEY (article_id, tag_id)
);

-- 为 articles 表新增字段
ALTER TABLE articles ADD COLUMN view_count INTEGER DEFAULT 0;
ALTER TABLE articles ADD COLUMN is_featured BOOLEAN DEFAULT FALSE;
ALTER TABLE articles ADD COLUMN cover_image_path TEXT;
```

#### 3.3.4 新增 API 端点

```
GET  /api/tags                        # 获取所有标签 (分类)
GET  /api/tags/{tag_id}/articles      # 获取某标签下的文章
GET  /api/articles/{id}/tags          # 获取某文章的标签
POST /api/articles/{id}/tags          # 手动添加/修改标签
POST /api/tags/batch-generate         # 批量 AI 生成标签
GET  /api/tags/cloud                  # 标签云数据 (热度排序)
```

---

### 核心四：栏目体系 (全新)

> **目标**：将零散文章组织为结构化的内容频道，类似36氪的"快讯/深氪/创投"频道
>
> **对标**：36氪频道导航 + 财新网栏目体系

#### 3.4.1 栏目规划

```
顶部导航栏:
┌──────────────────────────────────────────────────────────────────┐
│  [Logo]   首页  │ 深度洞察 │ 行业观察 │ 学术前沿 │ 院长说 │ 时光机  │
└──────────────────────────────────────────────────────────────────┘

栏目定义:
```

| 栏目 | 英文 | 内容来源 | 更新频率 | 说明 |
|------|------|----------|----------|------|
| **首页** | Home | 全部 | 实时 | 编辑精选 + AI 推荐 + 最新文章瀑布流 |
| **深度洞察** | Insights | business | 按深度 | 长文深度分析、案例研究 (>3000字的文章) |
| **行业观察** | Industry | business + wechat | 按行业 | 按行业标签分类的动态追踪 |
| **学术前沿** | Research | news + wechat | 按领域 | 教授研究成果、学术论文解读 |
| **院长说** | Dean's View | news | 精选 | 院长/教授的核心演讲和观点 (AI筛选) |
| **时光机** | Time Machine | 全部 | 随机 | 保留现有时光机功能，升级为独立频道 |

#### 3.4.2 首页布局设计 (对标36氪)

```
┌─────────────────────────────────────────────────────────────────────┐
│  [Logo] 复旦管院智识库        首页 深度 行业 学术 院长说     🔍 🤖  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────┐  ┌──────────────┐                  │
│  │                             │  │  📌 编辑精选   │                  │
│  │    🔥 头条文章 (大图)        │  │              │                  │
│  │    标题: AI时代的管理革命     │  │  · 文章标题1  │                  │
│  │    标签: #AI #管理学 #创新   │  │  · 文章标题2  │                  │
│  │                             │  │  · 文章标题3  │                  │
│  └─────────────────────────────┘  └──────────────┘                  │
│                                                                     │
│  ── 🏷️ 热门标签: AI  ESG  创业  供应链  数字化  领导力  新能源 ──    │
│                                                                     │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐           │
│  │ 深度洞察   │ │ 行业观察   │ │ 学术前沿   │ │ 院长说    │           │
│  │ ──────── │ │ ──────── │ │ ──────── │ │ ──────── │           │
│  │ 文章卡片1  │ │ 文章卡片1  │ │ 文章卡片1  │ │ 文章卡片1  │           │
│  │ 文章卡片2  │ │ 文章卡片2  │ │ 文章卡片2  │ │ 文章卡片2  │           │
│  │ 文章卡片3  │ │ 文章卡片3  │ │ 文章卡片3  │ │ 文章卡片3  │           │
│  │ [更多 →]  │ │ [更多 →]  │ │ [更多 →]  │ │ [更多 →]  │           │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘           │
│                                                                     │
│  ── 📰 最新文章 ──────────────────────────────────────────────────  │
│                                                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                               │
│  │ Card    │ │ Card    │ │ Card    │    (三栏瀑布流, 无限滚动)       │
│  │ + Tags  │ │ + Tags  │ │ + Tags  │                               │
│  └─────────┘ └─────────┘ └─────────┘                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 3.4.3 数据库扩展

```sql
CREATE TABLE columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 栏目名
    slug TEXT UNIQUE NOT NULL,       -- URL 路径标识
    description TEXT,                -- 栏目描述
    icon TEXT,                       -- Lucide icon 名
    sort_order INTEGER DEFAULT 0,    -- 导航排序
    filter_rules TEXT                -- JSON: 自动归类规则
);

CREATE TABLE article_columns (
    article_id INTEGER REFERENCES articles(id),
    column_id INTEGER REFERENCES columns(id),
    is_featured BOOLEAN DEFAULT FALSE,   -- 栏目置顶
    sort_order INTEGER DEFAULT 0,
    PRIMARY KEY (article_id, column_id)
);

CREATE TABLE featured_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER REFERENCES articles(id),
    position TEXT NOT NULL,          -- 'hero' | 'sidebar' | 'banner'
    start_date TEXT,
    end_date TEXT,
    is_active BOOLEAN DEFAULT TRUE
);
```

#### 3.4.4 新增 API 端点

```
GET  /api/columns                          # 获取所有栏目
GET  /api/columns/{slug}/articles          # 获取栏目下文章 (分页)
GET  /api/home/feed                        # 首页 Feed 聚合数据
  └── 返回: { hero, editors_picks, column_previews[], latest[], hot_tags[] }
GET  /api/articles/latest                  # 最新文章 (无限滚动)
GET  /api/articles/trending                # 热门文章 (按 view_count)
```

---

### 核心五：主题专题系统 (全新)

> **目标**：围绕特定议题，将多篇散落文章编织成结构化的知识专题
>
> **对标**：财新网"专题报道" + 36氪"特写" + Wikipedia 主题页

#### 3.5.1 主题类型

| 类型 | 示例 | 生成方式 |
|------|------|----------|
| **AI 自动专题** | "AI 革命: 从 ChatGPT 到 DeepSeek 的演进" | AI 分析标签聚类，自动策划 |
| **编辑策划专题** | "2024 年度商业知识盘点" | 管理员手动创建并挑选文章 |
| **事件追踪专题** | "新能源汽车产业链深度追踪" | 基于标签持续自动更新 |
| **时间线专题** | "复旦管院 40 年: 里程碑回顾" | 按时间排列的叙事链 |

#### 3.5.2 专题页面结构

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  专题封面 (AI 生成 Banner / 编辑上传)                 │
│                                                     │
│  ═══ AI 时代的管理革命 ════════════════════════════   │
│  #AI  #管理学  #组织变革  #领导力                     │
│                                                     │
│  📝 专题导读 (AI 自动生成 / 编辑撰写)                 │
│  "从2018年至今，复旦管院知识库中有超过200篇文章        │
│   涉及人工智能对管理实践的影响..."                     │
│                                                     │
│  ── 时间线视图 ──────────────────────────            │
│  2024.12 ●─ 《DeepSeek 与大模型的未来》              │
│  2024.09 ●─ 《AI 如何重构团队协作》                  │
│  2024.06 ●─ 《生成式AI的企业落地》                   │
│  2024.03 ●─ 《从ChatGPT看AI治理》                   │
│  ...                                                │
│                                                     │
│  ── 核心观点图谱 ────────────────────────            │
│  [AI 生成的关键概念关系图 / 词云]                     │
│                                                     │
│  ── 相关文章 (按相关度排列) ─────────────            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐              │
│  │ Card    │ │ Card    │ │ Card    │              │
│  └─────────┘ └─────────┘ └─────────┘              │
│                                                     │
│  ── 相关专题推荐 ────────────────────────            │
│  [数字化转型专题] [领导力专题] [创业创新专题]           │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### 3.5.3 数据库扩展

```sql
CREATE TABLE topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,                 -- 专题标题
    slug TEXT UNIQUE NOT NULL,           -- URL 路径
    description TEXT,                    -- 专题导读
    cover_image TEXT,                    -- 封面图 (base64 / URL)
    type TEXT NOT NULL,                  -- 'auto' | 'editorial' | 'event' | 'timeline'
    auto_rules TEXT,                     -- JSON: 自动收录规则 (标签匹配等)
    status TEXT DEFAULT 'draft',         -- 'draft' | 'published'
    created_at TEXT,
    updated_at TEXT,
    view_count INTEGER DEFAULT 0
);

CREATE TABLE topic_articles (
    topic_id INTEGER REFERENCES topics(id),
    article_id INTEGER REFERENCES articles(id),
    sort_order INTEGER DEFAULT 0,        -- 在专题中的排序
    editor_note TEXT,                    -- 编辑按语
    PRIMARY KEY (topic_id, article_id)
);

CREATE TABLE topic_tags (
    topic_id INTEGER REFERENCES topics(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (topic_id, tag_id)
);
```

#### 3.5.4 AI 自动专题生成 Pipeline

```
1. 标签聚类分析
   └── 找到 article_count > 15 的标签组合 → 候选专题

2. 专题元数据生成 (Gemini)
   ├── 专题标题
   ├── 专题导读 (200-300字)
   └── 封面图 Prompt

3. 文章筛选与排序
   ├── 匹配标签的文章按相关度排序
   └── 去重、限制上限 (30篇)

4. 时间线生成
   └── 按 publish_date 排列关键事件节点

5. 观点提取
   └── 从 Top-10 文章中提取核心论点，生成观点图谱
```

#### 3.5.5 新增 API 端点

```
GET  /api/topics                          # 获取所有专题 (分页)
GET  /api/topics/{slug}                   # 专题详情 + 文章列表
POST /api/topics                          # 创建专题 (管理端)
PUT  /api/topics/{id}                     # 编辑专题
POST /api/topics/auto-generate            # AI 自动生成专题
GET  /api/topics/{id}/timeline            # 获取专题时间线
GET  /api/topics/{id}/insights            # 获取专题 AI 洞察
```

---

## 四、前端路由与页面规划

### 4.1 路由结构

```
/                           → 首页 (Feed 流 + 栏目预览 + 编辑精选)
/search?q=xxx               → 搜索结果页 (统一检索)
/column/:slug               → 栏目页 (如 /column/insights)
/article/:id                → 文章详情页 (全屏阅读 + AI 摘要)
/tag/:tagName               → 标签页 (聚合该标签下所有文章)
/topic/:slug                → 专题页 (沉浸式主题阅读)
/topics                     → 专题广场 (所有专题的网格展示)
/time-machine               → 时光机 (独立页面，升级版)
/chat                       → AI 助理 (全屏对话模式，可选)
```

### 4.2 组件拆分 (从单文件 App.jsx → 模块化)

```
frontend/src/
├── main.jsx
├── App.jsx                          # 路由入口
├── index.css                        # 全局样式 (保留)
│
├── components/
│   ├── layout/
│   │   ├── Navbar.jsx               # 顶部导航栏 (Logo + 栏目 + 搜索 + AI助理入口)
│   │   ├── Footer.jsx               # 页脚
│   │   └── Sidebar.jsx              # 侧边栏 (标签云/推荐)
│   │
│   ├── search/
│   │   ├── SearchBar.jsx            # 搜索组件 (保留现有设计语言)
│   │   ├── SearchFilters.jsx        # 筛选器 (来源/时间/标签)
│   │   └── SearchSuggestions.jsx    # 搜索联想下拉
│   │
│   ├── article/
│   │   ├── ArticleCard.jsx          # 文章卡片 (升级自 ResultCard，加标签)
│   │   ├── ArticleDetail.jsx        # 文章详情 (升级自阅读 Modal → 独立页面)
│   │   ├── ArticleGrid.jsx          # 文章网格/瀑布流
│   │   └── ArticleMeta.jsx          # 文章元数据 (来源/日期/标签/阅读量)
│   │
│   ├── tags/
│   │   ├── TagBadge.jsx             # 标签徽章
│   │   ├── TagCloud.jsx             # 标签云
│   │   └── TagFilter.jsx            # 标签筛选组件
│   │
│   ├── topic/
│   │   ├── TopicCard.jsx            # 专题卡片 (封面 + 标题)
│   │   ├── TopicTimeline.jsx        # 专题时间线视图
│   │   └── TopicInsights.jsx        # 专题 AI 洞察面板
│   │
│   ├── chat/
│   │   ├── ChatPanel.jsx            # AI 对话面板 (悬浮 + 展开)
│   │   ├── ChatMessage.jsx          # 消息气泡
│   │   ├── ChatSources.jsx          # 引用来源列表
│   │   └── ChatInput.jsx            # 输入框 + 快捷指令
│   │
│   └── common/
│       ├── TimeMachine.jsx          # 时光机组件 (提取自 App.jsx)
│       ├── HeroSection.jsx          # 首页 Hero (提取自 App.jsx)
│       ├── LoadingStates.jsx        # 各种加载动画
│       └── EmptyStates.jsx          # 空状态
│
├── pages/
│   ├── HomePage.jsx                 # 首页
│   ├── SearchPage.jsx               # 搜索结果页
│   ├── ColumnPage.jsx               # 栏目页
│   ├── ArticlePage.jsx              # 文章详情页
│   ├── TagPage.jsx                  # 标签页
│   ├── TopicPage.jsx                # 专题详情页
│   ├── TopicsPage.jsx               # 专题广场
│   └── TimeMachinePage.jsx          # 时光机页
│
├── hooks/
│   ├── useSearch.js                 # 搜索逻辑 Hook
│   ├── useChat.js                   # AI 对话 Hook
│   ├── useArticle.js                # 文章数据 Hook
│   └── useInfiniteScroll.js         # 无限滚动 Hook
│
├── api/
│   ├── index.js                     # API 配置
│   ├── search.js                    # 搜索 API
│   ├── articles.js                  # 文章 API
│   ├── tags.js                      # 标签 API
│   ├── columns.js                   # 栏目 API
│   ├── topics.js                    # 专题 API
│   └── chat.js                      # AI 对话 API
│
└── utils/
    ├── constants.js                 # 常量 (颜色映射、来源标签等)
    └── formatters.js                # 日期/文本格式化工具
```

---

## 五、后端架构升级

### 5.1 项目结构 (从单文件 → 模块化)

```
backend/
├── main.py                          # FastAPI 应用入口 + CORS + 启动
├── config.py                        # 配置管理 (环境变量、路径、常量)
├── database.py                      # 数据库连接池 + 迁移
│
├── models/
│   ├── schemas.py                   # Pydantic 模型
│   └── database_models.py          # SQLAlchemy 模型 (可选升级)
│
├── routers/
│   ├── search.py                    # /api/search, /api/suggest
│   ├── articles.py                  # /api/articles/*, /api/article/*
│   ├── tags.py                      # /api/tags/*
│   ├── columns.py                   # /api/columns/*
│   ├── topics.py                    # /api/topics/*
│   ├── chat.py                      # /api/chat/*
│   ├── home.py                      # /api/home/feed
│   └── time_machine.py             # /api/time_machine
│
├── services/
│   ├── rag_engine.py               # RAG 检索引擎 (Hybrid Search + Re-Rank)
│   ├── ai_service.py               # Gemini API 封装 (摘要/标签/对话)
│   ├── tag_engine.py               # 标签生成与管理
│   ├── topic_engine.py             # 专题生成引擎
│   └── recommendation.py           # 推荐算法
│
├── scripts/
│   ├── build_knowledge_base.py     # ETL (迁移自根目录)
│   ├── create_vector_db_faiss.py   # FAISS 索引 (迁移自根目录)
│   ├── generate_tags.py            # 批量标签生成脚本
│   ├── generate_topics.py          # 批量专题生成脚本
│   └── migrate_db.py              # 数据库迁移脚本
│
└── crawlers/                        # 爬虫模块 (迁移自根目录)
    ├── business_crawler.py
    ├── news_crawler.py
    ├── wechat_crawler.py
    └── media_crawler.py
```

### 5.2 完整 API 一览

| 方法 | 路径 | 功能 | 优先级 |
|------|------|------|--------|
| GET | `/api/home/feed` | 首页聚合数据 | P0 |
| POST | `/api/search` | 统一智能检索 | P0 |
| GET | `/api/suggest` | 搜索联想 | P1 |
| GET | `/api/articles/latest` | 最新文章 (分页) | P0 |
| GET | `/api/articles/trending` | 热门文章 | P1 |
| GET | `/api/article/{id}` | 文章详情 | P0 |
| GET | `/api/summarize_article/{id}` | AI 摘要 | P0 |
| GET | `/api/tags` | 所有标签 | P0 |
| GET | `/api/tags/{id}/articles` | 标签下文章 | P0 |
| GET | `/api/tags/cloud` | 标签云 | P1 |
| GET | `/api/columns` | 所有栏目 | P0 |
| GET | `/api/columns/{slug}/articles` | 栏目文章 | P0 |
| GET | `/api/topics` | 专题列表 | P1 |
| GET | `/api/topics/{slug}` | 专题详情 | P1 |
| POST | `/api/chat` | AI 对话 | P1 |
| GET | `/api/time_machine` | 时光机 | P0 (保留) |
| POST | `/api/tags/batch-generate` | 批量生成标签 | P1 |
| POST | `/api/topics/auto-generate` | 自动生成专题 | P2 |

---

## 六、数据处理 Pipeline

### 6.1 一次性迁移任务

```
Step 1: 数据库 Schema 升级
  └── 运行 migrate_db.py → 创建 tags, article_tags, columns,
      article_columns, topics, topic_articles 等新表

Step 2: AI 批量标签生成
  └── 运行 generate_tags.py → 8,431 篇文章 × Gemini API
      ├── 批次: 每批 50 篇，间隔 2 秒
      ├── 断点续传: 记录已处理 article_id
      └── 预计耗时: ~4 小时 (Rate Limit: 1500 RPM)

Step 3: 栏目自动归类
  └── 基于 source + content_length + keyword 规则自动分配栏目

Step 4: AI 自动专题生成
  └── 运行 generate_topics.py → 分析标签聚类 → 生成 10-20 个初始专题

Step 5: 重建 FAISS 索引 (可选)
  └── 将标签信息嵌入 chunk metadata，提升标签相关检索
```

### 6.2 增量更新流程

```
新文章入库:
  1. 爬虫抓取 → content.txt
  2. ETL → 写入 SQLite articles 表
  3. AI 自动标签 → 写入 article_tags
  4. 规则匹配 → 自动归入栏目
  5. 标签匹配 → 自动关联相关专题
  6. FAISS 增量索引 → 追加新向量
```

---

## 七、UI/UX 设计规范

### 7.1 设计原则

| 原则 | 说明 |
|------|------|
| **学术质感** | 衬线字体标题、充足留白、克制的颜色使用 |
| **信息密度** | 对标36氪，每屏传递足够信息量，避免空洞 |
| **渐进披露** | 首页概览 → 栏目深入 → 文章全文 → AI 增强 |
| **一致性** | 卡片高度统一、标签样式统一、间距系统化 |

### 7.2 色彩系统 (继承并扩展)

```css
/* 品牌色 - 保留 */
--fudan-blue:    #0d0783;    /* 主色调 */
--fudan-orange:  #ea6b00;    /* 强调色 */
--fudan-dark:    #0a0560;    /* 深色背景 */

/* 新增 - 标签色板 */
--tag-tech:      #7C3AED;    /* 科技/AI - 紫色 */
--tag-finance:   #0891B2;    /* 金融 - 青色 */
--tag-consumer:  #D97706;    /* 消费 - 琥珀色 */
--tag-health:    #059669;    /* 医疗 - 翡翠色 */
--tag-energy:    #0D9488;    /* 能源 - 青绿 */
--tag-education: #2563EB;    /* 教育 - 蓝色 */

/* 新增 - 栏目色 */
--col-insights:  #0d0783;    /* 深度洞察 - 复旦蓝 */
--col-industry:  #ea6b00;    /* 行业观察 - 复旦橙 */
--col-research:  #7C3AED;    /* 学术前沿 - 紫色 */
--col-dean:      #B45309;    /* 院长说 - 深金色 */
```

### 7.3 卡片设计升级

```
现有 ResultCard:
┌──────────────────────────┐
│  [来源] [日期]            │
│  标题                     │
│  摘要...                  │
│  READ ARTICLE →           │
└──────────────────────────┘

升级后 ArticleCard:
┌──────────────────────────┐
│  [封面图 / AI生成缩略图]   │
│                           │
│  #AI  #管理学  #创新       │  ← 标签行 (可点击)
│                           │
│  标题标题标题              │
│  摘要摘要摘要摘要...       │
│                           │
│  📅 2024-12-01  │ 深度洞察 │  ← 日期 + 所属栏目
│  👁️ 1.2k views           │  ← 阅读量 (新增)
└──────────────────────────┘
```

---

## 八、实施路线图

### Phase 0: 基础重构 (第1-2周)

| 任务 | 优先级 | 预估工作量 |
|------|--------|-----------|
| 前端 App.jsx 拆分为组件/页面结构 | P0 | 前端 |
| 引入 React Router | P0 | 前端 |
| 后端 main.py 拆分为 routers + services | P0 | 后端 |
| 数据库 Schema 升级 (新增表) | P0 | 后端 |
| 编写 migrate_db.py 迁移脚本 | P0 | 后端 |

### Phase 1: 标签 + 栏目 (第3-4周)

| 任务 | 优先级 | 预估工作量 |
|------|--------|-----------|
| AI 批量标签生成脚本 | P0 | 后端 |
| 运行标签生成 (8,431 篇) | P0 | 运维 |
| 标签 API 开发 | P0 | 后端 |
| 栏目 API 开发 | P0 | 后端 |
| 首页 Feed API | P0 | 后端 |
| 首页 UI 重构 (栏目导航 + Feed) | P0 | 前端 |
| TagBadge / TagCloud 组件 | P0 | 前端 |
| 栏目页面 | P0 | 前端 |
| 标签筛选与标签页 | P0 | 前端 |

### Phase 2: RAG 升级 + AI 助理 (第5-7周)

| 任务 | 优先级 | 预估工作量 |
|------|--------|-----------|
| Hybrid Search (BM25 + 向量) | P1 | 后端 |
| Re-Ranker 二阶段排序 | P1 | 后端 |
| 搜索联想 API | P1 | 后端 |
| 统一搜索页面 | P1 | 前端 |
| AI 对话后端 (RAG + 多轮对话) | P1 | 后端 |
| ChatPanel 前端组件 | P1 | 前端 |
| 流式输出 (SSE) | P1 | 全栈 |
| 快捷指令系统 | P2 | 全栈 |

### Phase 3: 专题系统 (第8-9周)

| 任务 | 优先级 | 预估工作量 |
|------|--------|-----------|
| 专题 API 开发 | P1 | 后端 |
| AI 自动专题生成引擎 | P2 | 后端 |
| 专题详情页 (时间线 + 观点) | P1 | 前端 |
| 专题广场页 | P1 | 前端 |
| 相关推荐算法 | P2 | 后端 |

### Phase 4: 打磨与上线 (第10-12周)

| 任务 | 优先级 | 预估工作量 |
|------|--------|-----------|
| 文章详情页升级 (独立页面 + 相关推荐) | P1 | 前端 |
| 阅读量统计 | P2 | 全栈 |
| SEO 优化 (SSR / 预渲染) | P2 | 前端 |
| 性能优化 (懒加载、缓存) | P1 | 全栈 |
| 移动端适配优化 | P1 | 前端 |
| 错误处理与兜底 | P1 | 全栈 |
| 部署更新 (Render + Vercel) | P0 | 运维 |

---

## 九、技术选型确认

### 保留不变
- **前端框架**: React 19 + Vite
- **UI 框架**: Tailwind CSS v4
- **动画**: Framer Motion
- **图标**: Lucide React
- **后端框架**: FastAPI
- **向量数据库**: FAISS
- **AI 引擎**: Google Gemini (Embedding + 2.5 Pro)
- **关系数据库**: SQLite
- **部署**: Render + Vercel

### 新增引入
| 库/工具 | 用途 | 理由 |
|---------|------|------|
| `react-router-dom` v7 | 前端路由 | 多页面导航必须 |
| `rank_bm25` (Python) | BM25 关键词检索 | Hybrid Search |
| `@tanstack/react-query` | 前端数据请求管理 | 缓存、分页、无限滚动 |
| `react-intersection-observer` | 无限滚动检测 | 首页 Feed 瀑布流 |

---

## 十、成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 搜索结果相关度 (Top-3 命中率) | ~60% | >85% |
| 平均检索耗时 | ~3s | <1.5s (首次) |
| 页面数量 | 1 (SPA) | 8+ (多路由) |
| 文章有标签覆盖率 | 0% | >95% |
| 自动生成专题数 | 0 | 15+ |
| AI 助理单轮回答有引用率 | N/A | >90% |
| 移动端可用性 | 基本可用 | 完全适配 |

---

## 十一、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Gemini API 配额不足 | 批量标签生成受阻 | 分批执行 + 断点续传 + 降级使用 Flash 模型 |
| 标签质量不稳定 | 分类不准确 | 人工抽检 10% + 置信度阈值过滤 |
| SQLite 并发性能瓶颈 | 多用户访问卡顿 | Phase 4 考虑迁移 PostgreSQL |
| 前端重构范围大 | 开发周期延长 | Phase 0 严格控制，先跑通路由再逐步迁移 |
| FAISS 索引更新需重建 | 新文章入库延迟 | 实现增量索引 (FAISS add_documents) |

---

> **文档版本**: v1.0
> **创建日期**: 2026-03-24
> **产品经理**: AI 产品顾问
> **技术基础**: 基于 fdsmarticles 现有代码库资产
