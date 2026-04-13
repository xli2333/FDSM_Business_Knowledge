# 05 — RAG 搜索引擎

本文档详细说明复旦商业知识库平台的搜索功能技术实现，涵盖整体架构、三路混合搜索算法、AI 重排、查询扩展、搜索模式、缓存策略以及 FAISS 向量索引构建流程。

对应代码文件：`backend/services/rag_engine.py`、`backend/services/ai_service.py`、`create_vector_db_faiss.py`

---

## 5.1 搜索架构概览

本系统采用**三路混合搜索 + AI 重排**的架构，融合传统信息检索与现代语义搜索的优势，在中文商业知识库场景下实现高质量的检索结果。

```
用户查询
  │
  ├── 1. 查询扩展（Gemini 生成 2-4 个替代表述）
  │         │
  │         ▼
  │   terms = [原始查询, 分词片段, AI 扩展词]（最多 6 个）
  │
  ├── 2a. 词法搜索 (_relevance_score)
  │         加权字段匹配 + 时效性 + 热度
  │         输出: lexical_score
  │
  ├── 2b. BM25 搜索 (_bm25_scores)
  │         BM25Okapi + CJK bigram/trigram
  │         输出: bm25_score（归一化 0-18）
  │
  ├── 2c. 向量搜索 (_vector_scores)
  │         FAISS + GoogleGenerativeAIEmbeddings
  │         输出: vector_score（归一化 0-14）
  │
  ├── 3. 综合评分
  │         score = lexical + (bm25 × 1.35) + vector
  │
  ├── 4. 排序
  │
  └── 5. AI 重排 (_rerank_rows)
            top 18 → Gemini Pro 评分 → 权重 ×4
            输出: 最终排序结果
```

**核心设计理念**：

- **词法搜索**提供精确匹配能力，确保标题、标签中包含查询词的文章得到高分。
- **BM25 搜索**提供基于词频-逆文档频率的统计相关性，弥补简单词匹配在长文档中的不足。
- **向量搜索**提供语义理解能力，能够找到与查询语义相关但不包含相同关键词的文章。
- **AI 重排**利用大模型的深层理解，对候选结果做最终的质量筛选。

---

## 5.2 查询预处理

### 5.2.1 查询词构建（_build_terms）

用户输入的查询经过以下处理步骤生成搜索词列表：

```python
def _build_terms(query: str) -> list[str]:
    base = query.strip()
    parts = TOKEN_SPLIT_PATTERN.split(base)  # 按空格、逗号、句号等分词
    terms = [base]                            # 第一个 term 始终是完整查询
    for item in parts:
        if item not in terms:
            terms.append(item)
    for expanded in ai_service.expand_query(base):  # AI 查询扩展
        if expanded not in terms:
            terms.append(expanded)
    return terms[:6]                          # 最多保留 6 个 term
```

**分词模式**：`TOKEN_SPLIT_PATTERN = re.compile(r"[\s,，。；;、/|]+")`，涵盖中英文常用分隔符。

**输出示例**：

| 用户输入 | 生成的 terms |
|----------|-------------|
| `"AI 数字化转型"` | `["AI 数字化转型", "AI", "数字化转型", "人工智能驱动的企业数字化", "AI赋能转型升级"]` |
| `"ESG"` | `["ESG", "ESG评级", "可持续发展", "环境社会治理"]` |

### 5.2.2 查询扩展（ai_service.expand_query）

当 Gemini API 可用时，系统会调用大模型生成 2-4 个替代表述：

```python
def expand_query(query: str) -> list[str]:
    prompt = (
        "You rewrite search queries for a Chinese business knowledge base.\n"
        "Return 2 to 4 short alternative queries in the same language...\n"
        "User query:\n{query}\n\nJSON:"
    )
    raw = _invoke_prompt(prompt, {"query": query})
    # 解析 JSON，去重，最多返回 4 个
```

关键特性：
- 使用 Gemini Pro 模型，温度 0.2（低随机性）。
- 要求返回 JSON 格式，便于解析。
- 如果 AI 不可用或调用失败，优雅降级为空列表，不影响搜索。
- 扩展词与原始查询去重后附加到 terms 列表。

### 5.2.3 文本归一化

所有文本比较前经过统一归一化处理：

```python
def _normalize_text(text: str | None) -> str:
    return (text or "").strip().lower()
```

确保大小写不敏感、前后空白不影响匹配。

---

## 5.3 词法搜索（_relevance_score）

词法搜索是最基础也是最可靠的搜索通道，通过在文章各字段中统计查询词出现次数，并根据字段重要性加权计分。

### 5.3.1 字段权重

| 字段 | 权重 | 说明 |
|------|------|------|
| `title`（标题） | **12** | 标题命中是最强的相关性信号 |
| `main_topic`（主题） | **8** | 主题分类的命中表明高度相关 |
| `tag_text`（标签） | **7** | 标签是编辑精选的关键词 |
| `people_text`（人物） | **6** | 关联人物匹配表示主题相关 |
| `org_text`（机构） | **5** | 机构名称匹配 |
| `excerpt`（摘要） | **4** | 摘要中的命中有中等信号强度 |
| `content`（正文） | **1.2** | 正文命中信号最弱，且限制最多 8 次计数（`min(content_hits, 8)`） |

### 5.3.2 完整评分公式

```python
# 对每个 term 计算得分
for index, term in enumerate(terms):
    weight = 1.0 if index == 0 else 0.65        # 首个 term（完整查询）权重 1.0，其余 0.65
    term_score = (
        title_hits * 12
        + topic_hits * 8
        + tag_hits * 7
        + people_hits * 6
        + org_hits * 5
        + excerpt_hits * 4
        + min(content_hits, 8) * 1.2
    )
    score += term_score * weight

# 如果没有任何 term 命中，直接返回 0
if not matched:
    return 0.0

# 加上时效性和热度加权
score = score + recency_boost + popularity_boost
```

### 5.3.3 时效性加权（Recency Boost）

```python
age_days = max((date.today() - date.fromisoformat(published)).days, 1)
recency_boost = max(0.0, 1.5 - (age_days / 3650))
```

| 文章发布距今 | recency_boost |
|-------------|---------------|
| 当天 | **1.5**（最大值） |
| 1 年 (365 天) | 约 1.4 |
| 5 年 (1825 天) | 约 1.0 |
| 10 年 (3650 天) | 0.0 |
| 10 年以上 | 0.0（下限） |

设计意图：在同等相关性下，新发布的文章略微优先。最大加权 1.5 分，10 年以上的文章不再获得时效性加成。

### 5.3.4 热度加权（Popularity Boost）

```python
popularity_boost = min((row.get("view_count") or 0) / 3000, 2.2)
```

| view_count | popularity_boost |
|------------|-----------------|
| 0 | 0.0 |
| 1500 | 0.5 |
| 3000 | 1.0 |
| 6600+ | **2.2**（最大值，上限封顶） |

设计意图：高阅读量的文章获得额外加分，但封顶 2.2 分，防止热门文章过度压制相关性更高的冷门文章。

### 5.3.5 Term 权重衰减

- 第一个 term（即完整的用户查询）权重为 **1.0**。
- 后续 term（分词片段、AI 扩展词）权重为 **0.65**。

这确保了完整查询的匹配始终优先于部分匹配或扩展匹配。

---

## 5.4 BM25 搜索（_bm25_scores）

### 5.4.1 算法选择

使用 `rank_bm25` 库的 **BM25Okapi** 算法，这是 BM25 家族中最经典的变体，在信息检索领域广泛使用。

### 5.4.2 CJK 分词策略（_tokenize_for_bm25）

由于中文没有天然的词边界，系统采用 **bigram + trigram** 的 n-gram 分词策略：

```python
def _tokenize_for_bm25(text: str | None) -> list[str]:
    tokens: list[str] = []
    for chunk in TEXT_TOKEN_PATTERN.findall(text.lower()):
        tokens.append(chunk)                        # 原始 token
        if all("\u4e00" <= c <= "\u9fff" for c in chunk):  # 如果是纯中文
            for size in (2, 3):                     # bigram 和 trigram
                if len(chunk) >= size:
                    tokens.extend(
                        chunk[i : i + size]
                        for i in range(len(chunk) - size + 1)
                    )
    return tokens
```

**TEXT_TOKEN_PATTERN**：`re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)`

分词示例：

| 输入文本 | 产生的 tokens |
|----------|--------------|
| `"数字化转型"` | `["数字化转型", "数字", "字化", "化转", "转型", "数字化", "字化转", "化转型"]` |
| `"AI strategy"` | `["ai", "strategy"]` |

这种策略的优势：
- 无须依赖中文分词词典，避免 OOV（Out-of-Vocabulary）问题。
- bigram 能捕获大部分双字词组合。
- trigram 能捕获三字词，提高召回率。
- 英文和数字保持原始 token。

### 5.4.3 文档构建（_build_bm25_document）

每篇文章构建为一个 BM25 文档时，各字段通过重复来实现隐式加权：

| 字段 | 重复次数 | 说明 |
|------|---------|------|
| `title` | 3 | 标题最重要 |
| `main_topic` | 2 | 主题次之 |
| `tag_text` | 2 | 标签同样重要 |
| `people_text` | 1 | 人物名 |
| `org_text` | 1 | 机构名 |
| `excerpt` | 1 | 摘要 |
| `content`（前 4000 字符） | 1 | 正文截断避免过长文档稀释词频 |

### 5.4.4 归一化

BM25 原始分数通过以下方式归一化到 **0-18** 区间：

```python
max_score = max(positive_scores)
normalized = (float(score) / max_score) * 18
```

归一化后四舍五入保留 4 位小数。仅保留分数大于 0 的文章。

### 5.4.5 查询 Token 构建

搜索时取 terms 前 4 个，对每个 term 分别分词，合并去重后作为 BM25 查询向量：

```python
for term in terms[:4]:
    for token in _tokenize_for_bm25(term):
        if token not in query_tokens:
            query_tokens.append(token)
```

---

## 5.5 向量搜索（_vector_scores）

### 5.5.1 技术栈

| 组件 | 选择 | 说明 |
|------|------|------|
| 向量数据库 | **FAISS**（Facebook AI Similarity Search） | 本地部署，无须外部服务 |
| 嵌入模型 | **GoogleGenerativeAIEmbeddings** | 使用 Gemini 的 embedding 模型 |
| 距离策略 | **余弦距离**（COSINE） | 语义相似度的标准度量 |

### 5.5.2 搜索流程

```python
def _vector_scores(terms: list[str]) -> dict[int, float]:
    store = _load_vectorstore()
    scores: dict[int, float] = {}
    for index, term in enumerate(terms[:3]):         # 取前 3 个 term
        results = store.similarity_search_with_score(term, k=10)  # 每个 term 取 top-10
        weight = 1.0 if index == 0 else 0.7          # 首个 term 权重 1.0，其余 0.7
        for document, distance in results:
            article_id = document.metadata.get("article_id")
            similarity = max(0.0, 1 - float(distance))   # 余弦距离转相似度
            current = scores.get(article_id, 0.0)
            scores[article_id] = max(current, similarity * 14 * weight)
    return scores
```

关键参数：

| 参数 | 值 | 说明 |
|------|----|------|
| terms 数量 | 前 3 个 | 避免过多查询降低性能 |
| top-k | **10** | 每个 term 取最相似的 10 个文档块 |
| 首 term 权重 | **1.0** | 完整查询的向量搜索结果最重要 |
| 后续 term 权重 | **0.7** | 扩展词的权重稍低 |
| 归一化系数 | **14** | 最大可能得分为 14 分 |
| 分数合并策略 | **取最大值**（max） | 同一文章被多个 term 命中时取最高分 |

### 5.5.3 余弦距离到相似度的转换

FAISS 返回的是余弦距离（0 表示完全相同，2 表示完全相反），转换为相似度：

```
similarity = max(0.0, 1 - distance)
```

- 距离 0 -> 相似度 1.0（完全匹配）
- 距离 0.5 -> 相似度 0.5
- 距离 1.0 -> 相似度 0.0

最终得分 = `similarity * 14 * weight`，因此理论最大向量得分为 **14 分**。

### 5.5.4 向量存储加载

```python
@lru_cache(maxsize=1)
def _load_vectorstore():
    if not PRIMARY_GEMINI_KEY:
        return None
    index_file = FAISS_DB_DIR / "index.faiss"
    if not index_file.exists():
        return None
    embeddings = GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=PRIMARY_GEMINI_KEY,
        task_type="retrieval_query",
    )
    return FAISS.load_local(
        str(FAISS_DB_DIR), embeddings,
        allow_dangerous_deserialization=True,
        distance_strategy=DistanceStrategy.COSINE,
    )
```

注意 `task_type="retrieval_query"` 表示这是查询端的嵌入，与构建索引时使用的 `task_type="retrieval_document"` 配对，这是 Google embedding 模型的推荐做法。

---

## 5.6 综合评分

三路搜索的分数通过以下公式合并：

```python
score = lexical_score + (bm25_score * 1.35) + vector_score
```

| 通道 | 理论最大分 | 权重系数 | 加权后最大分 | 占比 |
|------|-----------|---------|-------------|------|
| 词法搜索（lexical） | 无固定上限（取决于命中次数），典型 20-80 | 1.0 | 20-80 | 主导 |
| BM25 搜索 | 18 | **1.35** | 24.3 | 补充 |
| 向量搜索 | 14 | 1.0 | 14 | 语义补充 |

BM25 乘以 1.35 的系数是为了将其贡献提升到与向量搜索相当的水平。词法搜索因为有字段加权机制，在精确匹配场景中天然占据主导地位。

仅当综合分数 > 0 时，文章才进入候选集。

---

## 5.7 AI 重排（_rerank_rows）

### 5.7.1 触发条件

- AI 服务已启用（`ai_service.is_ai_enabled()` 返回 True，即 Gemini API key 已配置）。
- 搜索模式为 `smart`（不在 `exact` 模式下触发）。
- 排序方式为 `relevance`（按日期或热度排序时不触发重排）。
- 候选结果非空。

### 5.7.2 重排流程

```
全部候选结果（按综合分排序）
        │
        ▼
  取 top 18 篇作为候选
        │
        ▼
  构建候选摘要（id, title, publish_date, main_topic, excerpt, tags, columns）
        │
        ▼
  发送给 Gemini Pro 模型
        │
  Prompt: "Score each candidate from 0 to 10 based only on relevance"
        │
        ▼
  返回 JSON: [{"id": 1, "score": 8.6}, {"id": 2, "score": 3.2}, ...]
        │
        ▼
  将 AI 分数乘以 4 加到原始分数上：
  final_score = original_score + (ai_score × 4)
        │
        ▼
  重新排序 top 18，拼接剩余结果
```

### 5.7.3 关键参数

| 参数 | 值 | 说明 |
|------|----|------|
| 候选数量 | **18** | 取综合评分前 18 名进行重排 |
| AI 评分范围 | **0-10** | Gemini 返回的相关性评分 |
| AI 分数权重 | **4** | AI 评分乘以 4 后加到原始分数 |
| AI 最大加分 | **40**（10 × 4） | 极高相关性的文章可获得最多 40 分加成 |
| 排序策略 | 先 AI 分数，再原始分数 | `sorted(key=lambda: (rerank_score, original_score))` |

### 5.7.4 候选摘要结构

发送给 Gemini 的每篇候选文章包含以下字段：

```python
{
    "id": 42,
    "title": "AI 如何重塑企业决策",
    "publish_date": "2024-03-15",
    "main_topic": "人工智能",
    "excerpt": "...",
    "tags": ["AI/人工智能", "数字化转型"],      # 最多 4 个
    "columns": ["深度洞察"],                    # 最多 3 个
}
```

标签限制为前 4 个，栏目限制为前 3 个，以控制 prompt 长度和 token 消耗。

### 5.7.5 容错机制

- 如果 Gemini 调用失败（网络错误、JSON 解析失败等），返回空字典，不影响原始排序。
- AI 分数被强制限制在 `[0.0, 10.0]` 区间内（`max(0.0, min(float(score), 10.0))`）。
- 重排仅影响 top 18 的内部顺序，第 19 名及以后的文章保持原始排序不变。

---

## 5.8 搜索模式

### 5.8.1 smart 模式（默认）

完整的三路混合搜索 + AI 重排流程。需要 Gemini API key 才能发挥全部能力（查询扩展 + 向量搜索 + AI 重排），但在 API key 不可用时会自动降级为词法搜索 + BM25。

评分公式：`lexical + (bm25 × 1.35) + vector`

### 5.8.2 exact 模式

纯精确匹配模式，所有用户均可使用，不依赖 AI 服务。

评分公式：
```python
exact_score = _term_occurrences(title, query) * 10 + _term_occurrences(content, query)
```

只在标题和正文中搜索完整的用户查询字符串（不分词、不扩展）。标题命中权重 10，正文命中权重 1。仅当 `exact_score > 0` 时返回结果。

### 5.8.3 模式对比

| 特性 | smart | exact |
|------|-------|-------|
| 查询扩展 | 有（Gemini） | 无 |
| 词法搜索 | 有 | 无 |
| BM25 搜索 | 有 | 无 |
| 向量搜索 | 有（FAISS） | 无 |
| AI 重排 | 有（Gemini） | 无 |
| 精确匹配 | 通过词法搜索隐含 | 唯一搜索方式 |
| AI 依赖 | 可选（降级运行） | 无 |
| 适用场景 | 探索性搜索、模糊查询 | 已知关键词的精确查找 |

---

## 5.9 排序与过滤

### 5.9.1 排序方式

搜索结果支持三种排序方式（`sort` 参数）：

| sort | 排序逻辑 | AI 重排 |
|------|---------|---------|
| `relevance`（默认） | 按综合分降序，分数相同按日期降序 | 触发 |
| `date` | 按发布日期降序，日期相同按分数降序 | 不触发 |
| `popularity` | 按阅读量降序，阅读量相同按分数降序 | 不触发 |

### 5.9.2 过滤器

`_matches_filters()` 支持以下过滤条件：

| 过滤字段 | 类型 | 匹配逻辑 |
|----------|------|---------|
| `tags` | 字符串数组 | 文章的 `tag_text` 中至少包含一个匹配的标签（交集非空） |
| `columns` | 字符串数组 | 文章所属栏目中至少包含一个匹配的栏目 |
| `start_date` | 字符串 | 文章发布日期 >= start_date |
| `end_date` | 字符串 | 文章发布日期 <= end_date |

过滤在评分之前执行，不符合过滤条件的文章直接跳过，不参与后续计算。

### 5.9.3 分页

```python
safe_page = max(page, 1)
safe_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
start = (safe_page - 1) * safe_page_size
page_rows = matched_rows[start : start + safe_page_size]
```

页码从 1 开始，页大小受 `MAX_PAGE_SIZE` 上限控制。

---

## 5.10 缓存策略

系统使用 Python 标准库的 `functools.lru_cache` 实现内存级缓存，避免重复加载大量数据。

### 5.10.1 三层缓存

| 缓存函数 | maxsize | 缓存内容 | 说明 |
|----------|---------|---------|------|
| `_load_search_rows()` | **1** | 全部文章的搜索字段（dict 列表） | 从数据库加载所有文章，按 `publish_date DESC` 排序 |
| `_load_bm25_index()` | **1** | BM25Okapi 索引 + article_ids 映射 | 基于搜索行数据构建 BM25 语料库 |
| `_load_vectorstore()` | **1** | FAISS 向量存储对象 | 从磁盘加载 FAISS 索引 + embedding 模型 |

`maxsize=1` 意味着每个缓存只保存最新一次计算的结果。由于搜索数据在应用运行期间很少变化，单条缓存足够。

### 5.10.2 缓存刷新

```python
def refresh_search_cache() -> None:
    _load_search_rows.cache_clear()
    _load_bm25_index.cache_clear()
    _load_vectorstore.cache_clear()
```

在以下场景调用：
- 数据库全量重建后（`rebuild_database()`）。
- 手动触发缓存刷新时。

刷新后，下一次搜索请求会自动触发重新加载。

### 5.10.3 搜索行数据结构

`_load_search_rows()` 返回的每个 dict 包含以下字段：

```python
{
    "id", "title", "slug", "publish_date", "source", "excerpt",
    "article_type", "main_topic", "view_count", "cover_image_path",
    "link", "content", "tag_text", "people_text", "org_text",
    "column_text"  # 通过 JOIN 聚合的栏目标识
}
```

`column_text` 通过子查询实时聚合：`GROUP_CONCAT(c.slug, ' | ')`，将文章所属的所有栏目用 ` | ` 分隔。

---

## 5.11 FAISS 索引构建

索引构建由独立脚本 `create_vector_db_faiss.py` 完成，可单独运行。

### 5.11.1 构建流程

```
1. 从 SQLite 加载文章 (load_documents)
       │
       ▼
2. 构建 Document 对象（含元数据）
       │
       ▼
3. 文本分块 (split_documents)
       │  chunk_size=800, chunk_overlap=120
       │
       ▼
4. 批量嵌入 + 构建索引 (create_index)
       │  batch_size=50, embedding model = Gemini
       │
       ▼
5. 保存到 faiss_index_business/ 目录
```

### 5.11.2 文档加载（load_documents）

从 `articles` 表加载所有文章，每篇文章构建为一个 LangChain `Document` 对象：

**page_content 格式**：
```
Title: {title}
Date: {publish_date}
Type: {article_type}
Main Topic: {main_topic}
Tags: {tag_text}

{content}
```

**metadata 结构**：
```python
{
    "article_id": int,       # 文章 ID，用于搜索结果回溯
    "title": str,
    "publish_date": str,
    "link": str,
    "source": "business",
}
```

### 5.11.3 文本分块（split_documents）

使用 LangChain 的 `RecursiveCharacterTextSplitter`：

| 参数 | 值 | 说明 |
|------|----|------|
| `chunk_size` | **800** | 每个文本块最大 800 字符 |
| `chunk_overlap` | **120** | 相邻块之间重叠 120 字符，确保跨块语义连贯 |
| `length_function` | `len` | 按字符数计算长度（对中文友好） |

**设计考量**：
- 800 字符对中文来说约 400-500 个汉字，接近一个完整段落的长度。
- 120 字符的重叠确保段落边界处的语义不会丢失。
- 每个 chunk 继承原始 Document 的 metadata（包括 `article_id`），搜索时可回溯到源文章。

### 5.11.4 嵌入与索引构建（create_index）

| 参数 | 值 | 说明 |
|------|----|------|
| 嵌入模型 | `GEMINI_EMBEDDING_MODEL`（来自 config） | Google Generative AI Embeddings |
| task_type | `"retrieval_document"` | 文档端嵌入（与查询端的 `retrieval_query` 配对） |
| 批量大小 | **50** | 每次向 API 发送 50 个文本块进行嵌入 |
| 距离策略 | `DistanceStrategy.COSINE` | 余弦距离 |
| 重试策略 | 最多 **3 次**，每次失败后等待 2 秒 | 应对 API 限流和瞬时错误 |

**批量处理流程**：

```python
for index in range(0, len(chunks), BATCH_SIZE):
    batch = chunks[index : index + BATCH_SIZE]
    for attempt in range(3):          # 最多重试 3 次
        try:
            if vectorstore is None:
                vectorstore = FAISS.from_documents(batch, embeddings, ...)
            else:
                vectorstore.add_documents(batch)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)             # 失败后等待 2 秒
```

第一个批次使用 `FAISS.from_documents()` 创建新索引，后续批次使用 `add_documents()` 追加。

### 5.11.5 索引存储

构建完成后保存到 `faiss_index_business/` 目录：

```python
os.makedirs(FAISS_DB_DIR, exist_ok=True)
vectorstore.save_local(FAISS_DB_DIR)
```

该目录包含两个文件：
- `index.faiss` — FAISS 二进制索引文件
- `index.pkl` — 文档元数据的 pickle 文件

### 5.11.6 API Key 获取

脚本按以下顺序获取 Google API Key：

1. 环境变量 `GOOGLE_API_KEY`
2. 环境变量 `GEMINI_API_KEYS`（逗号分隔，取第一个）
3. 均不存在时抛出 `ValueError`

---

## 5.12 搜索建议（suggest）

除了主搜索功能外，系统还提供搜索建议接口 `suggest()`，用于搜索框的自动补全。

### 5.12.1 空查询建议

当用户未输入任何内容时，返回热门标签：

- **中文模式**：从 `tags` 表中按 `article_count DESC` 取前 8 个 `topic` 或 `industry` 类标签的名称。
- **英文模式**：同样取热门标签，但通过 `localize_tag_name()` 本地化为英文，过滤掉仍含中文的结果，最多返回 8 个。

### 5.12.2 有查询建议

当用户已输入部分文本时，使用 `LIKE %query%` 在以下来源中搜索：

- **中文模式**：标题（前 8 条）+ 标签名（前 6 条），合并去重后返回前 10 条。
- **英文模式**：英文翻译标题（`article_translations.title`，前 8 条）+ 标签名英文本地化（前 160 个标签中匹配的），合并去重后返回前 10 条。

---

## 5.13 搜索结果响应结构

`search_articles()` 返回的字典结构：

```python
{
    "query": "AI 数字化转型",            # 原始查询
    "mode": "smart",                     # 搜索模式
    "total": 42,                         # 匹配总数
    "page": 1,                           # 当前页码
    "page_size": 12,                     # 每页数量
    "query_terms": ["AI 数字化转型", "AI", "数字化转型", ...],  # 展开后的搜索词
    "items": [                           # 当前页的文章列表
        {
            "id": 1,
            "title": "...",
            "slug": "...",
            "score": 45.6789,            # 综合得分（含 AI 重排加分）
            ...                          # 其他 ArticleCard 字段
        }
    ]
}
```

每个 item 是经过 `_serialize_articles()` 处理的文章卡片数据，额外附带 `score` 字段用于调试和排序透明化。
