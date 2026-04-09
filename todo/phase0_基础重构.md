# Phase 0：基础重构（地基工程）

> **目标**：将单文件前后端拆分为模块化架构，引入路由，升级数据库 Schema
>
> **前置条件**：无
>
> **完成标志**：前端多页面路由跑通，后端模块化启动正常，新数据库表创建完成

---

## 0.1 后端模块化拆分

### 0.1.1 创建目录结构

```
[ ] P0 | 后端 | 在 backend/ 下创建以下子目录：
    mkdir -p backend/models
    mkdir -p backend/routers
    mkdir -p backend/services
    mkdir -p backend/scripts
    mkdir -p backend/crawlers
```

### 0.1.2 抽取 config.py

```
[ ] P0 | 后端 | 新建 backend/config.py，从 main.py 中迁移以下内容：
    - GOOGLE_API_KEY 读取逻辑
    - BASE_DIR / RENDER_DISK_PATH / DATA_DIR 路径判断逻辑
    - SQLITE_DB_PATH / FAISS_DB_DIR 路径定义
    - 数据迁移逻辑 (shutil.copy 部分)
    - 导出所有常量供其他模块引用

    具体操作：
    1. 从 main.py 第 26-71 行代码整体剪切
    2. 在 config.py 中整理为：
       - GOOGLE_API_KEY: str
       - BASE_DIR: str
       - DATA_DIR: str
       - SQLITE_DB_PATH: str
       - FAISS_DB_DIR: str
       - run_data_migration() 函数
    3. main.py 改为 from config import *
```

### 0.1.3 抽取 database.py

```
[ ] P0 | 后端 | 新建 backend/database.py，从 main.py 迁移：
    - get_db_connection() 函数 (main.py 第 195-198 行)
    - 新增：get_db() 生成器函数 (用于 FastAPI Depends 注入)

    代码模板：
    ──────────────────────────
    import sqlite3
    from config import SQLITE_DB_PATH

    def get_db_connection():
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def get_db():
        conn = get_db_connection()
        try:
            yield conn
        finally:
            conn.close()
    ──────────────────────────
```

### 0.1.4 抽取 models/schemas.py

```
[ ] P0 | 后端 | 新建 backend/models/schemas.py，从 main.py 迁移所有 Pydantic 模型：
    - SearchRequest (第 116-119 行)
    - SearchResult (第 121-127 行)
    - ArticleDetail (第 129-135 行)
    - ConditionalSearchRequest (第 137-142 行)
    - SummaryResponse (第 395-401 行)
    - TimeMachineResponse (第 457-463 行) → 改名为 KnowledgeCardResponse

    新增模型（为后续阶段预留）：
    - TagSchema (id, name, category, color, article_count)
    - ColumnSchema (id, name, slug, description, icon)
    - TopicSchema (id, title, slug, description, type, status)
    - ChatMessage (role, content)
    - ChatRequest (messages: List[ChatMessage], session_id, mode)
    - ChatResponse (answer, sources, follow_up_questions, confidence)
    - HomeFeedResponse (hero, editors_picks, column_previews, latest, hot_tags)
    - PaginatedResponse (items, total, page, page_size, has_more)
```

### 0.1.5 抽取 services/rag_engine.py

```
[ ] P0 | 后端 | 新建 backend/services/rag_engine.py，迁移 RAG 核心逻辑：
    - embeddings 初始化 (main.py 第 86-89 行)
    - llm 初始化 (main.py 第 92-96 行)
    - vectorstore 加载 (main.py 第 99-113 行)
    - extract_core_query() 函数 (main.py 第 145-169 行)
    - expand_query() 函数 (main.py 第 171-193 行)

    封装为 RAGEngine 类：
    ──────────────────────────
    class RAGEngine:
        def __init__(self):
            self.embeddings = ...
            self.llm = ...
            self.vectorstore = ...

        def extract_core_query(self, user_input: str) -> str: ...
        def expand_query(self, query: str) -> List[str]: ...
        def search(self, query, top_k, source_filter) -> List[dict]: ...
    ──────────────────────────

    - search() 方法整合 main.py 第 207-324 行的融合检索逻辑
    - 所有常量 (MIN_RELEVANCE_THRESHOLD, FREQUENCY_BOOST 等) 定义为类属性
```

### 0.1.6 抽取 services/ai_service.py

```
[ ] P0 | 后端 | 新建 backend/services/ai_service.py，迁移 AI 相关逻辑：
    - genai_client 初始化 (main.py 第 466 行)
    - summarize_article 的摘要生成 Prompt + Chain (main.py 第 415-427 行)
    - 知识卡的金句提取 + 图像生成逻辑 (原 time_machine，main.py 第 500-541 行)

    封装为 AIService 类：
    ──────────────────────────
    class AIService:
        def __init__(self):
            self.llm = ...  # 复用 RAGEngine 的 llm 或独立实例
            self.genai_client = ...

        def generate_summary(self, title: str, content: str) -> str: ...
        def extract_quote(self, title: str, content: str) -> str: ...
        def generate_knowledge_card_image(self, title: str) -> Optional[str]: ...
    ──────────────────────────

    **重要变更**：
    - 原 time_machine 图像生成 → 改名为 generate_knowledge_card_image
    - Prompt 修改：保留手绘插画风格，但增加一致性约束：
      * 统一构图：左侧 60% 为插画区域，右侧 40% 为文字留白区
      * 统一色调：暖橙 #ea6b00 + 深蓝 #0d0783 为主色
      * 统一元素：每张卡片右下角保留复旦管院 logo 占位区
      * 统一风格关键词：marker sketch, colored pencil, warm academic, diary illustration
      * 统一尺寸：正方形 1:1
```

### 0.1.7 拆分路由文件

```
[ ] P0 | 后端 | 新建 backend/routers/search.py：
    - 迁移 POST /api/rag_search (main.py 第 206-324 行)
    - 迁移 POST /api/sql_search (main.py 第 326-373 行)
    - 两个路由都改为调用 rag_engine.search() 或直接 SQL
    - 后续 Phase 2 将合并为统一的 POST /api/search

[ ] P0 | 后端 | 新建 backend/routers/articles.py：
    - 迁移 GET /api/article/{article_id} (main.py 第 375-393 行)
    - 迁移 GET /api/summarize_article/{article_id} (main.py 第 403-455 行)
    - 新增 GET /api/articles/latest (分页查询最新文章)
    - 新增 GET /api/articles/trending (按 view_count 排序，Phase 1 才有数据)

[ ] P0 | 后端 | 新建 backend/routers/knowledge_card.py（原 time_machine）：
    - 迁移 GET /api/time_machine → 改为 GET /api/knowledge_card
    - 保留原路径 /api/time_machine 做 301 重定向兼容
    - 返回模型改为 KnowledgeCardResponse
    - 调用 ai_service.extract_quote() + ai_service.generate_knowledge_card_image()

[ ] P0 | 后端 | 新建 backend/routers/home.py（预留空壳）：
    - GET /api/home/feed → 返回 mock 数据
    - Phase 1 再实现真实逻辑
```

### 0.1.8 重写 main.py 为入口文件

```
[ ] P0 | 后端 | 重写 backend/main.py，仅保留：
    1. FastAPI() 实例化
    2. CORS 中间件配置
    3. 路由注册 (app.include_router)
    4. 健康检查端点 GET /
    5. uvicorn 启动

    代码模板：
    ──────────────────────────
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from routers import search, articles, knowledge_card, home

    app = FastAPI(title="Fudan Knowledge Base API")

    app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

    app.include_router(search.router, prefix="/api")
    app.include_router(articles.router, prefix="/api")
    app.include_router(knowledge_card.router, prefix="/api")
    app.include_router(home.router, prefix="/api")

    @app.get("/")
    def health_check():
        return {"status": "ok", "service": "Fudan Knowledge Base API"}
    ──────────────────────────
```

### 0.1.9 验证后端拆分

```
[ ] P0 | 后端 | 本地启动验证：
    1. cd backend && uvicorn main:app --reload
    2. 测试 GET / → 返回 health check
    3. 测试 POST /api/rag_search → 返回搜索结果
    4. 测试 POST /api/sql_search → 返回搜索结果
    5. 测试 GET /api/article/1 → 返回文章详情
    6. 测试 GET /api/summarize_article/1 → 返回 AI 摘要
    7. 测试 GET /api/knowledge_card → 返回知识卡数据
    8. 确认所有原有功能不受影响
```

---

## 0.2 数据库 Schema 升级

### 0.2.1 编写迁移脚本

```
[ ] P0 | 后端 | 新建 backend/scripts/migrate_db.py：

    脚本内容（按顺序执行 SQL）：

    ── 1. articles 表新增字段 ──
    ALTER TABLE articles ADD COLUMN view_count INTEGER DEFAULT 0;
    ALTER TABLE articles ADD COLUMN is_featured BOOLEAN DEFAULT FALSE;
    ALTER TABLE articles ADD COLUMN cover_image_path TEXT;

    ── 2. 创建 tags 表 ──
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        category TEXT NOT NULL,       -- 'industry' | 'topic' | 'type' | 'entity'
        description TEXT,
        color TEXT,
        article_count INTEGER DEFAULT 0
    );

    ── 3. 创建 article_tags 关联表 ──
    CREATE TABLE IF NOT EXISTS article_tags (
        article_id INTEGER REFERENCES articles(id),
        tag_id INTEGER REFERENCES tags(id),
        confidence REAL DEFAULT 1.0,
        PRIMARY KEY (article_id, tag_id)
    );

    ── 4. 创建 columns 栏目表 ──
    CREATE TABLE IF NOT EXISTS columns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        icon TEXT,
        sort_order INTEGER DEFAULT 0,
        filter_rules TEXT              -- JSON
    );

    ── 5. 创建 article_columns 关联表 ──
    CREATE TABLE IF NOT EXISTS article_columns (
        article_id INTEGER REFERENCES articles(id),
        column_id INTEGER REFERENCES columns(id),
        is_featured BOOLEAN DEFAULT FALSE,
        sort_order INTEGER DEFAULT 0,
        PRIMARY KEY (article_id, column_id)
    );

    ── 6. 创建 featured_articles 表 ──
    CREATE TABLE IF NOT EXISTS featured_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER REFERENCES articles(id),
        position TEXT NOT NULL,         -- 'hero' | 'sidebar' | 'banner'
        start_date TEXT,
        end_date TEXT,
        is_active BOOLEAN DEFAULT TRUE
    );

    ── 7. 创建 topics 专题表 ──
    CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT,
        cover_image TEXT,
        type TEXT NOT NULL,             -- 'auto' | 'editorial' | 'event' | 'timeline'
        auto_rules TEXT,                -- JSON
        status TEXT DEFAULT 'draft',
        created_at TEXT,
        updated_at TEXT,
        view_count INTEGER DEFAULT 0
    );

    ── 8. 创建 topic_articles 关联表 ──
    CREATE TABLE IF NOT EXISTS topic_articles (
        topic_id INTEGER REFERENCES topics(id),
        article_id INTEGER REFERENCES articles(id),
        sort_order INTEGER DEFAULT 0,
        editor_note TEXT,
        PRIMARY KEY (topic_id, article_id)
    );

    ── 9. 创建 topic_tags 关联表 ──
    CREATE TABLE IF NOT EXISTS topic_tags (
        topic_id INTEGER REFERENCES topics(id),
        tag_id INTEGER REFERENCES tags(id),
        PRIMARY KEY (topic_id, tag_id)
    );

    ── 10. 插入初始栏目数据 ──
    INSERT OR IGNORE INTO columns (name, slug, description, icon, sort_order, filter_rules) VALUES
    ('深度洞察', 'insights',  '长文深度分析、案例研究', 'BookOpen',   1, '{"source": ["business"], "min_length": 3000}'),
    ('行业观察', 'industry',  '按行业标签分类的动态追踪', 'TrendingUp', 2, '{"source": ["business", "wechat"]}'),
    ('学术前沿', 'research',  '教授研究成果、学术论文解读', 'GraduationCap', 3, '{"source": ["news", "wechat"]}'),
    ('院长说',   'dean',      '院长/教授的核心演讲和观点', 'Mic',       4, '{"source": ["news"], "keywords": ["院长", "陆雄文"]}');
```

### 0.2.2 执行迁移并验证

```
[ ] P0 | 后端 | 执行迁移脚本：
    1. 备份当前数据库：cp fudan_knowledge_base.db fudan_knowledge_base.db.bak
    2. 运行：python backend/scripts/migrate_db.py
    3. 验证表创建：sqlite3 fudan_knowledge_base.db ".tables"
       → 应看到：articles, tags, article_tags, columns, article_columns,
                 featured_articles, topics, topic_articles, topic_tags
    4. 验证 articles 新字段：sqlite3 fudan_knowledge_base.db "PRAGMA table_info(articles);"
       → 应包含 view_count, is_featured, cover_image_path
    5. 验证栏目初始数据：sqlite3 fudan_knowledge_base.db "SELECT * FROM columns;"
       → 应返回 4 行栏目数据
```

---

## 0.3 前端路由引入

### 0.3.1 安装依赖

```
[ ] P0 | 前端 | 安装新依赖包：
    cd frontend
    npm install react-router-dom@7
    npm install @tanstack/react-query
    npm install react-intersection-observer

    验证：package.json 中出现以上三个依赖
```

### 0.3.2 改造 main.jsx 引入路由

```
[ ] P0 | 前端 | 修改 frontend/src/main.jsx：

    改造前（当前）：
    ──────────────────────────
    import App from './App'
    ReactDOM.createRoot(...).render(<App />)
    ──────────────────────────

    改造后：
    ──────────────────────────
    import { BrowserRouter } from 'react-router-dom'
    import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
    import App from './App'

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 5 * 60 * 1000,  // 5 分钟缓存
          retry: 1,
        },
      },
    })

    ReactDOM.createRoot(document.getElementById('root')).render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    )
    ──────────────────────────
```

### 0.3.3 改造 App.jsx 为路由入口

```
[ ] P0 | 前端 | 重写 frontend/src/App.jsx 为路由骨架：

    ──────────────────────────
    import { Routes, Route } from 'react-router-dom'
    import Navbar from './components/layout/Navbar'
    import HomePage from './pages/HomePage'
    import SearchPage from './pages/SearchPage'
    import ArticlePage from './pages/ArticlePage'
    import ColumnPage from './pages/ColumnPage'
    import TagPage from './pages/TagPage'
    import TopicPage from './pages/TopicPage'
    import TopicsPage from './pages/TopicsPage'

    function App() {
      return (
        <div className="min-h-screen bg-slate-50 text-slate-900">
          <Navbar />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/article/:id" element={<ArticlePage />} />
            <Route path="/column/:slug" element={<ColumnPage />} />
            <Route path="/tag/:tagName" element={<TagPage />} />
            <Route path="/topic/:slug" element={<TopicPage />} />
            <Route path="/topics" element={<TopicsPage />} />
          </Routes>
        </div>
      )
    }
    ──────────────────────────

    注意：第一版各页面组件先放占位内容，后续阶段逐步填充
```

### 0.3.4 创建前端目录结构

```
[ ] P0 | 前端 | 创建以下目录和占位文件：

    frontend/src/
    ├── components/
    │   ├── layout/
    │   │   ├── Navbar.jsx          ← 【本阶段实现】
    │   │   └── Footer.jsx          ← 占位
    │   ├── search/
    │   │   ├── SearchBar.jsx       ← 【本阶段实现】从 App.jsx 提取
    │   │   └── SearchFilters.jsx   ← 【本阶段实现】从 App.jsx 提取
    │   ├── article/
    │   │   ├── ArticleCard.jsx     ← 【本阶段实现】从 ResultCard 提取
    │   │   ├── ArticleDetail.jsx   ← 【本阶段实现】从阅读器 Modal 提取
    │   │   └── ArticleGrid.jsx     ← 占位
    │   ├── tags/                   ← Phase 1
    │   ├── topic/                  ← Phase 3
    │   ├── chat/                   ← Phase 2
    │   └── common/
    │       ├── KnowledgeCard.jsx   ← 【本阶段实现】从时光机提取并改造
    │       ├── HeroSection.jsx     ← 【本阶段实现】从 App.jsx 提取
    │       └── LoadingStates.jsx   ← 占位
    │
    ├── pages/
    │   ├── HomePage.jsx            ← 【本阶段实现】组合 Hero + Search + KnowledgeCard
    │   ├── SearchPage.jsx          ← 【本阶段实现】组合 SearchBar + Results Grid
    │   ├── ArticlePage.jsx         ← 占位（Phase 4 升级为独立页面）
    │   ├── ColumnPage.jsx          ← 占位（Phase 1）
    │   ├── TagPage.jsx             ← 占位（Phase 1）
    │   ├── TopicPage.jsx           ← 占位（Phase 3）
    │   └── TopicsPage.jsx          ← 占位（Phase 3）
    │
    ├── api/
    │   ├── index.js                ← 【本阶段实现】API 基础配置 (baseURL, fetch wrapper)
    │   ├── search.js               ← 【本阶段实现】迁移 searchArticles, searchSql
    │   ├── articles.js             ← 【本阶段实现】迁移 getArticleDetail, summarizeArticle
    │   ├── knowledgeCard.js        ← 【本阶段实现】迁移 travelTimeMachine → generateKnowledgeCard
    │   ├── tags.js                 ← 占位（Phase 1）
    │   ├── columns.js              ← 占位（Phase 1）
    │   ├── topics.js               ← 占位（Phase 3）
    │   └── chat.js                 ← 占位（Phase 2）
    │
    └── utils/
        ├── constants.js            ← 【本阶段实现】来源标签映射、颜色常量
        └── formatters.js           ← 【本阶段实现】日期格式化
```

### 0.3.5 实现 Navbar 组件

```
[ ] P0 | 前端 | 实现 frontend/src/components/layout/Navbar.jsx：

    功能要求：
    - 左侧：Logo (mainpage_logo.png) + "复旦管院智识库" 文字，点击回首页
    - 中间：栏目导航链接 → 首页 | 深度洞察 | 行业观察 | 学术前沿 | 院长说
    - 右侧：搜索图标 (点击跳转 /search) + AI 助理图标 (Phase 2 实现)
    - 样式：固定顶部，白色背景，底部细线分隔，z-50
    - 当前路由高亮 (useLocation 判断)

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │ [Logo] 复旦管院智识库     首页  深度洞察  行业观察  学术前沿  院长说   🔍  │
    └─────────────────────────────────────────────────────────────────────┘
```

### 0.3.6 提取 HeroSection 组件

```
[ ] P0 | 前端 | 新建 frontend/src/components/common/HeroSection.jsx：
    - 从 App.jsx 第 107-126 行提取 Hero 区域
    - 保留"开智求真 / 拓新领变" 标题动画
    - 保留 Framer Motion 动效
    - 接收 prop: onSearchSubmit (触发搜索后跳转到 /search?q=xxx)
```

### 0.3.7 提取 SearchBar 组件

```
[ ] P0 | 前端 | 新建 frontend/src/components/search/SearchBar.jsx：
    - 从 App.jsx 第 128-246 行提取搜索框区域
    - Props: { onSubmit, initialQuery, initialMode, compact }
    - compact=true 时缩小尺寸（用于搜索结果页顶部）
    - 保留 RAG/精确检索 Tab 切换
    - 保留来源过滤器
    - 保留 SQL 模式下的年份筛选
```

### 0.3.8 提取 KnowledgeCard 组件（原时光机改造）

```
[ ] P0 | 前端 | 新建 frontend/src/components/common/KnowledgeCard.jsx：
    - 从 App.jsx 第 248-343 行提取时光机区域并改造

    **UI 变更**：
    - 按钮文字："启动时光机" → "一键生成知识卡"
    - 输入提示："输入日期 (如 2018-05-20) 或直接穿越..." → "输入日期或关键词，生成专属知识卡..."
    - 加载文字："时光隧道开启中..." → "正在绘制知识卡..."
    - 结果卡片保留宝丽来风格
    - 在卡片底部新增 "保存知识卡" 按钮（下载为 PNG，Phase 4 实现）

    **API 调用**：
    - 从 travelTimeMachine(date) → generateKnowledgeCard(date)
    - 后端 API 路径兼容新旧两个

    **一致性约束（视觉）**：
    - 卡片固定比例：正方形主图 + 下方标题/金句区域
    - 主图边框：2px solid #0d0783 (复旦蓝)
    - 金句字体：Noto Serif SC, italic
    - 卡片阴影：shadow-2xl
    - 刷新按钮保留右上角
```

### 0.3.9 实现 HomePage

```
[ ] P0 | 前端 | 实现 frontend/src/pages/HomePage.jsx：
    - 组合 HeroSection + SearchBar + KnowledgeCard
    - 保留现有首页的整体布局和动效
    - 搜索提交后：navigate(`/search?q=${query}&mode=${mode}&source=${source}`)
    - Phase 1 再添加栏目预览和 Feed 流
```

### 0.3.10 实现 SearchPage

```
[ ] P0 | 前端 | 实现 frontend/src/pages/SearchPage.jsx：
    - 从 URL 参数读取 q, mode, source
    - 顶部：SearchBar (compact 模式)
    - 下方：ArticleCard Grid (三列布局)
    - 保留现有搜索结果的卡片样式和动画
    - 点击卡片：弹出 ArticleDetail 侧边栏（保留现有 Modal 交互，Phase 4 改为独立页面）
```

### 0.3.11 提取 ArticleCard 和 ArticleDetail

```
[ ] P0 | 前端 | 新建 frontend/src/components/article/ArticleCard.jsx：
    - 从 App.jsx 底部的 ResultCard 函数 (第 506-544 行) 提取
    - 保留现有样式：来源标签 + 日期 + 标题 + 摘要 + READ ARTICLE
    - Phase 1 再添加标签行

[ ] P0 | 前端 | 新建 frontend/src/components/article/ArticleDetail.jsx：
    - 从 App.jsx 第 384-498 行提取阅读器 Modal
    - 保留侧滑动画、AI 摘要加载、Markdown 渲染
    - 独立为可复用组件，接收 articleId prop
```

### 0.3.12 拆分 API 层

```
[ ] P0 | 前端 | 拆分 frontend/src/api.js → 多文件：

    api/index.js:
    ──────────────────────────
    export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

    export async function apiFetch(path, options = {}) {
      const response = await fetch(`${API_BASE_URL}${path}`, {
        headers: { "Content-Type": "application/json", ...options.headers },
        ...options,
      });
      if (!response.ok) throw new Error(`API Error: ${response.status}`);
      return response.json();
    }
    ──────────────────────────

    api/search.js:
    - export searchArticles(query, source)     ← 迁移
    - export searchSql(keyword, start, end, source)  ← 迁移

    api/articles.js:
    - export getArticleDetail(id)   ← 迁移
    - export summarizeArticle(id)   ← 迁移
    - export getLatestArticles(page, pageSize)  ← 新增

    api/knowledgeCard.js:
    - export generateKnowledgeCard(date)  ← 从 travelTimeMachine 改名
```

### 0.3.13 添加 utils

```
[ ] P0 | 前端 | 新建 frontend/src/utils/constants.js：
    ──────────────────────────
    export const SOURCE_LABELS = {
      news: '学院新闻',
      wechat: '公众号',
      business: '商业知识',
      all: '全部来源',
    };

    export const SOURCE_COLORS = {
      business: { bg: 'bg-purple-100', text: 'text-purple-700' },
      news:     { bg: 'bg-blue-100',   text: 'text-blue-700' },
      wechat:   { bg: 'bg-green-100',  text: 'text-green-700' },
    };

    export const BRAND_COLORS = {
      fudanBlue:   '#0d0783',
      fudanOrange: '#ea6b00',
      fudanDark:   '#0a0560',
    };
    ──────────────────────────

[ ] P0 | 前端 | 新建 frontend/src/utils/formatters.js：
    ──────────────────────────
    export function formatDate(dateStr) { ... }
    export function truncateText(text, maxLen = 200) { ... }
    ──────────────────────────
```

### 0.3.14 删除旧文件

```
[ ] P0 | 前端 | 删除旧的单文件 API：
    - 删除 frontend/src/api.js（已拆分到 api/ 目录）
    - 确认所有 import 路径已更新
```

### 0.3.15 前端验证

```
[ ] P0 | 前端 | 本地启动验证：
    1. cd frontend && npm run dev
    2. 访问 / → 看到首页 (Hero + 搜索框 + 知识卡入口)
    3. 搜索提交 → 跳转到 /search?q=xxx → 看到结果列表
    4. 点击结果卡片 → 弹出侧边阅读器 → AI 摘要正常加载
    5. 点击知识卡按钮 → 生成知识卡（手绘插画 + 金句）
    6. 点击 Navbar 导航 → 栏目页面（占位内容）
    7. 确认所有路由切换流畅，无 404
```

---

## 0.4 迁移脚本整理

```
[ ] P1 | 后端 | 将根目录下的脚本迁移到 backend/scripts/：
    - create_vector_db_faiss.py → backend/scripts/create_vector_db_faiss.py
    - business_knowledge_crawler.py → backend/crawlers/business_crawler.py
    - 更新脚本中的 import 路径

[ ] P1 | 后端 | 将根目录下的爬虫迁移到 backend/crawlers/：
    - 整理所有 *_crawler.py 文件
```

---

## Phase 0 完成检查清单

```
[ ] 后端 main.py 不超过 30 行（纯入口）
[ ] 后端所有原有 API 端点正常响应
[ ] 数据库新增 6 张表 + articles 新增 3 个字段
[ ] 前端路由切换正常（至少 /, /search 两个页面可用）
[ ] 知识卡功能可用（替代原时光机）
[ ] Navbar 导航显示正确，当前页面高亮
[ ] 新旧 API 兼容（/api/time_machine 重定向到 /api/knowledge_card）
[ ] git commit: "Phase 0: 前后端模块化重构 + 路由引入 + DB Schema 升级"
```
