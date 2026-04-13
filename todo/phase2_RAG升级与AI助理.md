# Phase 2：RAG 检索升级 + AI 对话助理

> **目标**：检索从"能搜到"升级到"搜得准"；新增 AI 对话式知识顾问
>
> **前置条件**：Phase 0 完成（模块化架构就绪）
>
> **完成标志**：Hybrid Search 上线，AI 助理可多轮对话并引用来源

---

## 2.1 Hybrid Search（向量 + BM25 混合检索）

### 2.1.1 安装 BM25 依赖

```
[ ] P1 | 后端 | 安装 rank_bm25：
    pip install rank-bm25
    更新 requirements.txt
```

### 2.1.2 构建 BM25 索引

```
[ ] P1 | 后端 | 在 backend/services/rag_engine.py 中新增 BM25 索引构建：

    实现步骤：
    1. 启动时从 SQLite 加载所有文章 (id, title, content)
    2. 对每篇文章做分词（中文用 jieba.cut，英文用空格分割）
       pip install jieba → 加入 requirements.txt
    3. 构建 BM25Okapi 索引：
       from rank_bm25 import BM25Okapi
       tokenized_corpus = [list(jieba.cut(doc)) for doc in all_contents]
       bm25 = BM25Okapi(tokenized_corpus)
    4. 维护 article_id 与 bm25 索引位置的映射表

    代码位置：RAGEngine.__init__() 中初始化
    预估内存占用：8000篇 × 平均2000字 ≈ 额外 200-400MB
```

### 2.1.3 实现混合检索逻辑

```
[ ] P1 | 后端 | 在 RAGEngine 中新增 hybrid_search() 方法：

    def hybrid_search(self, query, top_k=10, source_filter=None, alpha=0.7):
        """
        alpha: 向量检索权重 (0-1)，1-alpha 为 BM25 权重
        默认 0.7 = 向量为主，BM25 为辅
        """
        # 1. 向量检索 (现有逻辑)
        vector_results = self.vector_search(query, top_k=50, source_filter=source_filter)
        # → [{article_id, score, doc}, ...]

        # 2. BM25 检索
        tokenized_query = list(jieba.cut(query))
        bm25_scores = self.bm25.get_scores(tokenized_query)
        bm25_top_indices = bm25_scores.argsort()[-50:][::-1]
        bm25_results = [
            {"article_id": self.id_map[idx], "score": bm25_scores[idx]}
            for idx in bm25_top_indices
            if bm25_scores[idx] > 0
        ]

        # 3. 分数归一化 (Min-Max Normalization)
        vector_results = normalize_scores(vector_results)
        bm25_results = normalize_scores(bm25_results)

        # 4. 融合
        combined = {}
        for r in vector_results:
            combined[r["article_id"]] = alpha * r["score"]
        for r in bm25_results:
            aid = r["article_id"]
            combined[aid] = combined.get(aid, 0) + (1 - alpha) * r["score"]

        # 5. 排序并返回 Top-K
        sorted_results = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
```

### 2.1.4 统一搜索入口 API

```
[ ] P1 | 后端 | 新增 POST /api/search（合并 rag_search + sql_search）：

    请求体 UnifiedSearchRequest：
    {
        "query": "string",
        "mode": "smart" | "exact",     // smart=RAG+BM25, exact=SQL LIKE
        "filters": {
            "sources": ["news", "business"],  // 可选
            "tags": ["AI", "ESG"],            // 可选（Phase 1 标签筛选）
            "date_range": ["2023-01-01", "2024-12-31"]  // 可选
        },
        "sort": "relevance" | "date",
        "page": 1,
        "page_size": 20
    }

    处理逻辑：
    - mode="smart" → 调用 hybrid_search()，结果附带标签
    - mode="exact" → 调用 SQL LIKE 查询
    - filters.tags → 对结果做二次过滤（article_tags 表 JOIN）
    - sort="date" → 按 publish_date 重排
    - 分页处理

    保留旧 API /api/rag_search 和 /api/sql_search 做兼容
```

---

## 2.2 Re-Ranker 二阶段精排

### 2.2.1 实现 Re-Ranker

```
[ ] P1 | 后端 | 在 RAGEngine 中新增 rerank() 方法：

    def rerank(self, query: str, candidates: List[dict], top_k: int = 10) -> List[dict]:
        """
        粗检索返回 Top-50 → Gemini 打分 → 返回 Top-10
        """
        # 构建批量评分 Prompt
        prompt = f"""
        你是一个搜索相关性评估专家。
        用户查询："{query}"

        请为以下每个文档片段评估与查询的相关性，打分 0-10：
        - 10 = 完全匹配，直接回答查询
        - 7-9 = 高度相关
        - 4-6 = 部分相关
        - 1-3 = 勉强相关
        - 0 = 无关

        文档列表：
        {formatted_candidates}

        输出格式（每行一个）：
        doc_1: 8
        doc_2: 3
        ...
        """

        # 调用 Gemini 2.5 Flash（速度优先）
        response = llm.invoke(prompt)

        # 解析分数，与原始 candidates 合并
        # 按 rerank_score 降序取 Top-K

    调用时机：
    - 在 hybrid_search() 返回 Top-50 后
    - 仅当 top_k <= 20 时启用（避免大批量调用 LLM）
    - 可通过参数 use_reranker=True/False 控制开关
```

### 2.2.2 集成到搜索流程

```
[ ] P1 | 后端 | 修改 POST /api/search 流程：
    1. hybrid_search() → Top-50
    2. rerank(query, top50) → Top-10（如果启用）
    3. 附加标签信息
    4. 返回分页结果
```

---

## 2.3 搜索联想 API

### 2.3.1 实现搜索联想

```
[ ] P1 | 后端 | 新增 GET /api/suggest：

    查询参数：q (用户输入前缀)
    返回：{ suggestions: ["复旦管院", "复旦MBA", ...] }

    实现逻辑：
    1. 标题前缀匹配：
       SELECT DISTINCT title FROM articles
       WHERE title LIKE '{q}%' LIMIT 5
    2. 标签匹配：
       SELECT name FROM tags
       WHERE name LIKE '%{q}%' ORDER BY article_count DESC LIMIT 5
    3. 合并去重，返回最多 10 条
    4. 加缓存：结果缓存 5 分钟
```

### 2.3.2 前端搜索联想组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/search/SearchSuggestions.jsx：

    ASCII 设计稿：
    ┌───────────────────────────────────────────────┐
    │   [输入: 复旦]                         [→]    │
    ├───────────────────────────────────────────────┤
    │   🔍 复旦管院                                 │  ← 标题匹配
    │   🔍 复旦MBA                                  │
    │   🔍 复旦大学管理学院                          │
    │   ────────────────────────────────────         │
    │   🏷️ #复旦管院 (tag, 342篇)                   │  ← 标签匹配
    │   🏷️ #复旦大学 (tag, 128篇)                   │
    └───────────────────────────────────────────────┘

    触发条件：输入 >= 2 个字符
    防抖：300ms debounce
    键盘导航：上下方向键选择，Enter 确认
    点击标签 → 跳转 /tag/{tagName}
    点击标题建议 → 填入搜索框并搜索
```

---

## 2.4 AI 对话助理（后端）

### 2.4.1 对话服务层

```
[ ] P1 | 后端 | 新建 backend/services/chat_service.py：

    class ChatService:
        def __init__(self, rag_engine: RAGEngine, ai_service: AIService):
            self.rag_engine = rag_engine
            self.ai_service = ai_service
            self.sessions = {}  # session_id → [messages]

        def chat(self, messages, session_id, mode="precise"):
            """
            处理一次对话请求
            """
            user_message = messages[-1]["content"]

            # 1. 意图识别
            intent = self._classify_intent(user_message)
            #    → "knowledge_search" | "greeting" | "analysis" | "follow_up"

            # 2. 根据意图分流
            if intent == "greeting":
                return self._handle_greeting()

            elif intent == "knowledge_search":
                # RAG 检索
                search_results = self.rag_engine.hybrid_search(user_message, top_k=5)
                context = self._build_context(search_results)

                # 生成回答
                answer = self._generate_answer(user_message, context, messages)

                return {
                    "answer": answer,
                    "sources": [
                        {"id": r["article_id"], "title": r["title"],
                         "date": r["publish_date"], "relevance": r["score"]}
                        for r in search_results
                    ],
                    "follow_up_questions": self._suggest_follow_ups(user_message, answer),
                    "confidence": self._calculate_confidence(search_results)
                }

            elif intent == "analysis":
                # 多文章综合分析（用更多上下文）
                search_results = self.rag_engine.hybrid_search(user_message, top_k=10)
                ...

        def _classify_intent(self, message: str) -> str:
            prompt = """
            判断用户消息的意图类别：
            - knowledge_search: 需要检索知识库回答的问题
            - greeting: 问候/闲聊
            - analysis: 需要综合多篇文章分析的复杂问题
            - follow_up: 对上一轮回答的追问

            用户消息：{message}
            输出（仅输出类别名）：
            """
            ...

        def _generate_answer(self, question, context, history):
            system_prompt = """
            你是复旦管院智识助理，一个基于复旦大学管理学院知识库的AI顾问。

            行为准则：
            1. 只基于提供的上下文回答，不编造信息
            2. 每个关键论点必须注明来源文章标题
            3. 使用 Markdown 格式，结构清晰
            4. 如果上下文无法回答问题，坦诚告知
            5. 语气：专业、学术、友善

            上下文：
            {context}
            """
            ...
```

### 2.4.2 对话 API 路由

```
[ ] P1 | 后端 | 新建 backend/routers/chat.py：

    POST /api/chat
    请求体：
    {
        "messages": [
            {"role": "user", "content": "近三年管院在ESG领域有什么研究？"}
        ],
        "session_id": "uuid-xxx",   // 可选，首次可不传
        "mode": "precise"           // "precise" | "creative"
    }

    返回：
    {
        "answer": "根据知识库中的文章...(Markdown)",
        "sources": [
            {"id": 123, "title": "...", "date": "2024-03-15", "relevance": 0.92}
        ],
        "follow_up_questions": [
            "ESG投资在中国面临哪些挑战？",
            "管院有哪些教授研究可持续发展？"
        ],
        "confidence": 0.85,
        "session_id": "uuid-xxx"
    }
```

### 2.4.3 流式输出（SSE）

```
[ ] P1 | 后端 | 在 POST /api/chat 中支持流式输出：

    请求头：Accept: text/event-stream → 触发流式模式

    使用 FastAPI StreamingResponse + SSE：
    from fastapi.responses import StreamingResponse

    async def chat_stream(request):
        async def event_generator():
            # 先发送 sources
            yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"

            # 流式发送 answer
            for chunk in llm.stream(prompt):
                yield f"data: {json.dumps({'type': 'token', 'data': chunk})}\n\n"

            # 最后发送 follow_up
            yield f"data: {json.dumps({'type': 'follow_up', 'data': questions})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 2.5 AI 对话助理（前端）

### 2.5.1 ChatPanel 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/chat/ChatPanel.jsx：

    两种形态：
    A) 悬浮气泡（收起态）— 右下角圆形按钮
    B) 侧边面板（展开态）— 右侧滑出

    ASCII 设计稿（展开态）：
    ┌──────────────────────────────────────────────┐
    │  🤖 复旦智识助理                      [—] [×] │
    ├──────────────────────────────────────────────┤
    │                                              │
    │  ┌──────────────────────────────────────┐    │
    │  │ 👤 近三年管院在ESG领域有什么研究？     │    │  ← 用户消息（右对齐）
    │  └──────────────────────────────────────┘    │
    │                                              │
    │  ┌──────────────────────────────────────┐    │
    │  │ 🤖 根据知识库中的文章，复旦管院在     │    │  ← AI 回答（左对齐）
    │  │ ESG 领域有以下重要研究和观点：        │    │
    │  │                                      │    │
    │  │ 1. **《ESG投资的中国实践》**         │    │
    │  │    (2024-03-15, 商业知识)            │    │
    │  │    核心观点：...                     │    │
    │  │    [查看原文 →]                      │    │
    │  │                                      │    │
    │  │ 2. **《双碳目标下的企业治理》**       │    │
    │  │    (2023-11-02, 学院新闻)            │    │
    │  │    核心观点：...                     │    │
    │  │                                      │    │
    │  │ 📎 引用: 5篇  ⏱️ 2021-2025          │    │
    │  └──────────────────────────────────────┘    │
    │                                              │
    │  ┌ 猜你想问 ────────────────────────────┐    │
    │  │ · ESG投资在中国面临哪些挑战？         │    │  ← 建议追问
    │  │ · 管院有哪些教授研究可持续发展？       │    │
    │  └──────────────────────────────────────┘    │
    │                                              │
    ├──────────────────────────────────────────────┤
    │  [输入您的问题...]                   [发送 ➤] │
    └──────────────────────────────────────────────┘

    悬浮气泡（收起态）：
    ┌────┐
    │ 🤖 │  ← 右下角固定位置，z-50
    └────┘

    实现要点：
    - 使用 useState 控制展开/收起
    - 展开动画：Framer Motion slideIn from right
    - 面板宽度：w-[420px]
    - 面板高度：h-[80vh] 或 h-screen
    - 消息列表自动滚动到底部
```

### 2.5.2 ChatMessage 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/chat/ChatMessage.jsx：

    Props: { message: {role, content, sources?, follow_ups?}, isStreaming }

    - role="user" → 右对齐，复旦蓝背景，白色文字
    - role="assistant" → 左对齐，白色背景，黑色文字
    - content 使用 ReactMarkdown 渲染
    - sources 渲染为可点击来源卡片列表
    - follow_ups 渲染为可点击的建议追问按钮
    - isStreaming=true 时显示打字机光标效果
```

### 2.5.3 ChatSources 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/chat/ChatSources.jsx：

    Props: { sources: [{id, title, date, relevance}] }

    ASCII 设计稿：
    ┌──────────────────────────────────────┐
    │  📎 引用来源 (5篇)                    │
    │  ──────────────────────────────────  │
    │  1. ESG投资的中国实践    2024-03-15  │  ← 点击跳转文章
    │     相关度: ████████░░ 92%           │
    │  2. 双碳目标下的企业治理  2023-11-02  │
    │     相关度: ███████░░░ 85%           │
    │  ...                                 │
    └──────────────────────────────────────┘
```

### 2.5.4 ChatInput 组件

```
[ ] P1 | 前端 | 新建 frontend/src/components/chat/ChatInput.jsx：

    - 自适应高度 textarea（最多 4 行）
    - Enter 发送，Shift+Enter 换行
    - 发送按钮（复旦橙）
    - 空输入时禁用发送
    - 发送中显示 loading 状态，禁止重复发送
```

### 2.5.5 useChat Hook

```
[ ] P1 | 前端 | 新建 frontend/src/hooks/useChat.js：

    export function useChat() {
      const [messages, setMessages] = useState([])
      const [isLoading, setIsLoading] = useState(false)
      const [sessionId, setSessionId] = useState(null)

      const sendMessage = async (content) => {
        // 1. 添加用户消息到列表
        const userMsg = { role: 'user', content }
        setMessages(prev => [...prev, userMsg])
        setIsLoading(true)

        // 2. 调用 API（支持 SSE 流式）
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
          body: JSON.stringify({
            messages: [...messages, userMsg],
            session_id: sessionId,
          }),
        })

        // 3. 处理 SSE 流
        const reader = response.body.getReader()
        let assistantMsg = { role: 'assistant', content: '', sources: [], follow_ups: [] }
        setMessages(prev => [...prev, assistantMsg])

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const text = new TextDecoder().decode(value)
          // 解析 SSE data 行，更新 assistantMsg
          ...
        }

        setIsLoading(false)
      }

      return { messages, sendMessage, isLoading, clearMessages }
    }
```

### 2.5.6 前端 API 层

```
[ ] P1 | 前端 | 实现 frontend/src/api/chat.js：
    - export sendChatMessage(messages, sessionId, mode)
    - export getChatSessions()  // 预留
    - 支持 SSE 流式读取

[ ] P1 | 前端 | 实现 frontend/src/api/search.js 新增：
    - export getSuggestions(q)  // 搜索联想
```

### 2.5.7 集成到全局布局

```
[ ] P1 | 前端 | 在 App.jsx 中添加 ChatPanel：

    <Routes>...</Routes>
    <ChatPanel />   ← 悬浮在所有页面之上

    Navbar 右侧 AI 助理图标点击 → 展开 ChatPanel
```

---

## 2.6 搜索结果页升级

### 2.6.1 统一搜索页面

```
[ ] P1 | 前端 | 升级 frontend/src/pages/SearchPage.jsx：

    ASCII 设计稿：
    ┌─────────────────────────────────────────────────────────────────────┐
    │  [Navbar]                                                           │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │  ┌───────────────────────────────────────────────────────────────┐  │
    │  │  [搜索框 compact]                                    [→]     │  │
    │  │  [智能] [精确]   来源: [全部] [商业] [新闻] [公众号]           │  │
    │  │  标签: [#AI] [#ESG] [#创业] [+更多]                           │  │  ← 新增标签筛选
    │  └───────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  搜索 "ESG" · 找到 42 篇相关文章 · 排序: [相关度▼] [时间]          │  ← 结果统计
    │                                                                     │
    │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
    │  │ Card     │ │ Card     │ │ Card     │                           │
    │  │ + Tags   │ │ + Tags   │ │ + Tags   │                           │
    │  └──────────┘ └──────────┘ └──────────┘                           │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 2 完成检查清单

```
[ ] BM25 索引构建成功，启动时无报错
[ ] Hybrid Search 测试：对比纯向量检索，命中率提升
[ ] Re-Ranker 可开关，开启后结果更精准
[ ] GET /api/suggest?q=复旦 返回联想结果
[ ] POST /api/search 统一入口可用，支持 mode/filters/sort/page
[ ] POST /api/chat 返回 AI 回答 + 来源引用
[ ] SSE 流式输出正常工作（逐字显示）
[ ] ChatPanel 悬浮气泡展开/收起正常
[ ] 多轮对话上下文保持
[ ] 搜索页显示标签筛选和结果统计
[ ] git commit: "Phase 2: Hybrid Search + Re-Ranker + AI 对话助理"
```
