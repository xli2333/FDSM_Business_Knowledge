# 09 — 编辑后台 CMS

本章全面阐述 FDSMArticles 编辑后台的内容管理系统（CMS），涵盖文稿全生命周期管理：从草稿创建、AI 批处理导入、AI 自动排版与标签生成，到工作流状态机驱动的审核发布流程，以及 HTML 渲染、导出与前端 UI 交互。

---

## 9.1 工作流状态机

编辑后台的核心是一个五级工作流状态机，定义在 `editorial_service.py` 的 `WORKFLOW_LABELS` 字典中：

```
draft ──→ in_review ──→ approved ──→ scheduled ──→ published
  ↑___________|______________|            |
  |           |              |            |
  └───────────┴──────────────┘            |
       (可回退到 draft)                    |
                                          v
                                     published（终态，不可逆）
```

### 9.1.1 状态定义

| 状态键值 | 中文标签 | 说明 |
|---|---|---|
| `draft` | 草稿 | 初始状态，可自由编辑 |
| `in_review` | 待审核 | 已提交审核，等待审批 |
| `approved` | 已通过 | 审核通过，可进入排期或直接发布 |
| `scheduled` | 定时发布 | 已设定发布时间，等待定时触发 |
| `published` | 已发布 | 终态，内容已写入公开 articles 表 |

### 9.1.2 状态标准化

```python
def _normalize_workflow_status(value: str | None) -> str:
    workflow_status = (value or "").strip() or "draft"
    if workflow_status not in WORKFLOW_LABELS:
        raise HTTPException(status_code=400, detail="Unsupported workflow status")
    return workflow_status
```

空值默认为 `"draft"`，非法值直接抛出 HTTP 400。

---

## 9.2 草稿创建

系统支持三种草稿创建方式：手动创建、文件上传和 AI 批处理导入。

### 9.2.1 手动创建

**路由：** `POST /api/editorial/articles`

**函数：** `create_editorial_article(payload: dict)`

接受字段：

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 标题，不能为空 |
| `content_markdown` | 是 | Markdown 正文 |
| `source_markdown` | 否 | 原始来源内容（为空时复制 content_markdown） |
| `subtitle` | 否 | 副标题 |
| `author` | 否 | 作者 |
| `organization` | 否 | 机构名称 |
| `publish_date` | 否 | 发布日期（默认当天） |
| `source_url` | 否 | 原文链接 |
| `cover_image_url` | 否 | 封面图 URL |
| `primary_column_slug` | 否 | 主栏目 slug |
| `article_type` | 否 | 文章类型 |
| `main_topic` | 否 | 主题 |
| `access_level` | 否 | 访问级别（默认 `"public"`） |
| `layout_mode` | 否 | 排版模式（默认 `"auto"`） |
| `formatting_notes` | 否 | 排版备注 |
| `slug` | 否 | 自定义 URL slug |

创建流程：

1. 校验 `title` 和 `content_markdown` 非空。
2. `source_markdown` 和 `content_markdown` 互相兜底：任一为空时取另一方的值。
3. 调用 `strip_markdown()` 从 Markdown 生成纯文本。
4. 调用 `_extract_excerpt()` 从纯文本提取前 140 字符摘要。
5. 生成唯一 slug：`_unique_slug()` 基于标题或自定义 slug 生成候选值，若数据库中已存在同名 slug，则追加 SHA1 哈希后缀。
6. 初始 `status = "draft"`，`workflow_status = "draft"`。
7. `tag_payload_json = "[]"`，`html_web = NULL`，`html_wechat = NULL`。

### 9.2.2 文件上传

**路由：** `POST /api/editorial/upload`

**函数：** `create_editorial_from_upload(filename, raw_bytes)`

支持的文件格式：

| 后缀 | 解析方式 |
|---|---|
| `.md` | 直接按文本读取，尝试多种编码 |
| `.txt` | 同上 |
| `.html` / `.htm` | 通过 `_html_to_markdown_like()` 转换为 Markdown 风格文本 |
| `.docx` | 通过 `_docx_to_markdown_like()` 解析 Word XML |

#### 文本编码检测

`_decode_text_bytes()` 按以下顺序尝试解码：

1. `utf-8-sig`（带 BOM 的 UTF-8）
2. `utf-8`
3. `gb18030`（中文 Windows 常用编码）
4. `utf-16`
5. 最后回退到 `utf-8` 的 `errors="replace"` 模式

#### DOCX 解析

`_docx_to_markdown_like()` 处理流程：

1. 将 bytes 作为 ZIP 文件打开。
2. 读取 `word/document.xml`（不存在则抛出 400）。
3. 遍历所有 `<w:p>` 段落元素。
4. 检查段落样式：`Heading1` → `# `，`Heading2` → `## `，`Heading3` → `### `。
5. 提取所有 `<w:t>` 文本节点，拼接为段落文本。
6. 用双换行连接所有段落。

#### HTML → Markdown 转换

`_html_to_markdown_like()` 使用正则表达式进行标签转换：

- `<br>` → 换行
- `</p>` → 双换行
- `<h1>` → `# `，`<h2>` → `## `，`<h3>` → `### `
- `<li>` → `- `
- `<strong>` / `<b>` → `**...**`
- `<em>` / `<i>` → `*...*`
- 其余标签 → 空格
- 最后 `html.unescape()` 还原 HTML 实体

#### 标题推断

上传完成后，系统尝试从文件内容推断标题：

1. 若第一个非空行以 `#` 开头，去掉标记符号作为标题，剩余内容作为正文。
2. 若第一个非空行不超过 48 个字符，作为标题。
3. 否则使用文件名（去掉扩展名）作为标题。

最终调用 `create_editorial_article()` 创建草稿。

---

## 9.3 AI 批处理导入

**路由：** `POST /api/editorial/source-articles/{article_id}/import-ai`

**函数：** `import_editorial_ai_draft(source_article_id, payload)`

此功能将 `article_ai_outputs` 表中的 AI 格式化结果导入编辑后台，创建或更新编辑稿。

### 9.3.1 前置条件

1. 对应的 `article_ai_outputs` 记录必须存在，且 `format_ready = True`。
2. `formatted_markdown_zh`（中文格式化版本）不能为空。

### 9.3.2 导入流程

```
请求 {source_article_id, editorial_id?}
  |
  v
获取 AI 输出：get_article_ai_output_detail(source_article_id)
  |-- format_ready = False → 400 错误
  |-- formatted_markdown_zh 为空 → 400 错误
  |
  v
从 articles 表读取源文章信息
从 article_tags 获取源文章标签（最多 12 个）
从 article_columns 获取源文章主栏目
  |
  v
editorial_id 是否已指定？
  |
  |-- 是（更新已有编辑稿）
  |     |-- 已发布 → 400 "Published editorial article cannot be overwritten"
  |     |-- 未发布 → UPDATE editorial_articles SET ...
  |
  |-- 否（创建新编辑稿）
  |     → INSERT INTO editorial_articles
  |
  v
返回完整编辑稿详情
```

### 9.3.3 导入时自动设置的字段

| 字段 | 来源 |
|---|---|
| `title` | 源文章标题 |
| `author` | 已有编辑稿保留原值，否则 "Fudan Business Knowledge Editorial Desk" |
| `organization` | 已有编辑稿保留原值，否则源文章的 primary_org_name |
| `source_markdown` | 源文章的原始 content |
| `content_markdown` | AI 的 formatted_markdown_zh |
| `excerpt` | 优先使用 AI 的 summary_zh，否则源文章 excerpt |
| `tag_payload_json` | 源文章的标签（序列化为 JSON） |
| `primary_column_slug` | 源文章的栏目 slug，默认 "insights" |
| `access_level` | 源文章的 access_level |
| `layout_mode` | `"auto"` |
| `formatter_model` | AI 输出的 format_model |
| `ai_synced_at` | 当前时间戳 |
| `html_web` / `html_wechat` | 重置为 NULL（需重新渲染） |

### 9.3.4 相关查询端点

| 路由 | 说明 |
|---|---|
| `GET /api/editorial/source-articles` | 列出可导入的源文章（通过 article_ai_output_service） |
| `GET /api/editorial/source-articles/{id}/ai-output` | 查看某篇源文章的 AI 处理详情 |

---

## 9.4 AI 自动排版

**路由：** `POST /api/editorial/articles/{editorial_id}/auto-format`

**函数：** `auto_format_editorial_article(editorial_id, payload)`

### 9.4.1 排版模型

使用 Google Gemini `gemini-3-flash-preview` 模型（配置项 `GEMINI_EDITORIAL_FORMAT_MODEL`）。

### 9.4.2 四种排版模式

在 `ai_service.py` 的 `LAYOUT_MODE_GUIDANCE` 字典中定义：

| layout_mode | 中文标签 | 排版指引 |
|---|---|---|
| `auto` | 自动排版 | 默认使用高端微信公众号长文风格，短导言、清晰 H2/H3 层级、信息密集但可读 |
| `insight` | 深度长文 | 偏重深度分析，显式论证结构，章节过渡，稍长的分析段落 |
| `briefing` | 快报简版 | 快速扫描友好，短章节、列表、关键要点、紧凑摘要 |
| `interview` | 访谈实录 | 保留说话人轮次和问答逻辑，同时加强标题、导言和可读性段落分隔 |

### 9.4.3 排版流程

```
请求 {editorial_id, source_markdown?, layout_mode?, formatting_notes?}
  |
  v
读取当前编辑稿（已发布则拒绝 → 400）
  |
  v
确定 source_markdown：
  请求参数 > current.source_markdown > current.content_markdown
  |-- 全部为空 → 400 "Source content is empty"
  |
  v
构建 Gemini 提示词，包含：
  - 系统角色："top-tier Chinese WeChat official-account editorial CMS"
  - 8 条硬性排版规则
  - 排版模式指引（layout_mode_guidance）
  - 编辑备注（formatting_notes）
  - 文章元数据（title, excerpt, main_topic, article_type, organization, tags）
  - 完整 source_markdown
  |
  v
调用 Gemini API → 获取格式化后的 Markdown
  |-- 返回为空 → 502 "Auto-formatting returned empty content"
  |-- 返回不以 # 开头 → 自动补上 H1 标题
  |
  v
更新 editorial_articles 表：
  - source_markdown（保留原始内容）
  - layout_mode、formatting_notes
  - formatter_model（记录使用的模型名称）
  - last_formatted_at（当前时间戳）
  - content_markdown（更新为排版后内容）
  - plain_text_content（重新生成纯文本）
  - excerpt（重新提取摘要）
  - html_web = NULL, html_wechat = NULL（清空 HTML 缓存）
```

### 9.4.4 Gemini 提示词中的 8 条硬性规则

1. 使用模型判断力创建可读、专业的中文长文排版，类似高端微信发布工具的自动排版模式。
2. 保留每个重要事实、数字、公司名称、引语和结论，不得捏造事实。
3. 第一个标题必须是单个 H1 标题。
4. 在标题后适当添加一段简短导言。
5. 使用清晰的 H2/H3 层级结构，短段落、列表和引用。
6. 保留访谈、对话和演讲的原始结构。
7. 不输出 HTML，不输出代码块围栏，仅输出 Markdown。
8. 不在答案中提及模型、提示词或排版规则。

---

## 9.5 AI 自动标签

**路由：** `POST /api/editorial/articles/{editorial_id}/autotag`

**函数：** `generate_editorial_tags(editorial_id)`

### 9.5.1 双源标签生成策略

系统采用 **启发式 + Gemini 合并去重** 的双源策略：

#### 启发式标签（Heuristic）

调用 `tag_engine._derive_tag_entries()`，基于文章的标题、主题、摘要、正文、文章类型和机构名等字段，通过规则匹配生成标签。输入数据结构：

```python
{
    "title": "...",
    "main_topic": "...",
    "excerpt": "...",
    "content": plain_text_content,
    "search_text": plain_text_content,
    "tag_text": "",
    "article_type": "...",
    "series_or_column": "",
    "people_text": "",
    "org_text": organization,
}
```

同时传入数据库中所有已知标签的 `{name: category}` 映射，用于分类校准。

#### Gemini AI 标签

调用 `ai_service.suggest_editorial_metadata(title, content)`，请求 Gemini 返回 JSON 结构，包含建议的标签列表（每个标签有 name、category、confidence 字段）。

### 9.5.2 合并去重逻辑 — _dedupe_tags()

```python
def _dedupe_tags(entries: list[tuple[str, str, float]]) -> list[dict]
```

1. 将所有标签条目按 `(name, category)` 对进行合并，取最高 confidence。
2. 标签名去前后空白，空名跳过。
3. category 若不在 `TAG_PRIORITY` 中，回退为 `"topic"`。
4. 排序规则：
   - 一级：按 `TAG_PRIORITY` 排序（`industry=0` > `topic=1` > `type=2` > `entity=3` > `series=4`）
   - 二级：按 confidence 倒序
   - 三级：按名称字典序
5. 截取前 12 个标签。
6. 为每个标签生成 slug（`slugify("{category}-{name}")`，截断 80 字符）和颜色（从 `COLOR_BY_CATEGORY` 映射）。

### 9.5.3 标签分类优先级

| category | 优先级 | 说明 |
|---|---|---|
| `industry` | 0 | 行业标签，最高优先 |
| `topic` | 1 | 主题标签 |
| `type` | 2 | 类型标签 |
| `entity` | 3 | 实体标签 |
| `series` | 4 | 系列标签 |

### 9.5.4 Gemini 附带的元数据更新

除标签外，Gemini 还可能返回以下建议，系统会在有值时覆盖现有字段：

| AI 返回字段 | 更新目标 | 截断限制 |
|---|---|---|
| `excerpt` | `editorial_articles.excerpt` | 180 字符 |
| `article_type` | `editorial_articles.article_type` | 32 字符 |
| `main_topic` | `editorial_articles.main_topic` | 48 字符 |
| `column_slug` | `editorial_articles.primary_column_slug` | 需在 VALID_COLUMN_SLUGS 内 |

### 9.5.5 栏目 slug 回退推断

当 AI 未返回有效 `column_slug` 且当前编辑稿也没有栏目时，调用 `_infer_column_slug()` 基于关键词匹配推断：

| 匹配关键词 | 推断栏目 |
|---|---|
| 研究、论文、学术、案例教学 | `research` |
| 院长、教授、复旦、管理学院 | `deans-view` |
| 标签中含 `industry` 类别 | `industry` |
| 默认 | `insights` |

---

## 9.6 工作流状态转换规则

**路由：** `POST /api/editorial/articles/{editorial_id}/workflow`

**函数：** `update_editorial_workflow(editorial_id, payload)`

### 9.6.1 可用操作（action）

| action | 转换目标状态 | 说明 |
|---|---|---|
| `save_draft` | `draft` | 回退/保存为草稿，清除定时发布设置 |
| `submit_review` | `in_review` | 提交审核，记录 submitted_at |
| `approve` | `approved` | 审核通过，记录 approved_at |
| `schedule` | `scheduled` | 设定定时发布，必须提供 scheduled_publish_at |

### 9.6.2 前置校验

- 已发布（`status == "published"`）的文章 **不可** 进行任何工作流操作 → 400 "Published article workflow is locked"。
- `schedule` 操作必须提供合法的 `scheduled_publish_at` datetime 字符串 → 400 "Scheduled publish time is required"。

### 9.6.3 状态转换时更新的字段

```python
UPDATE editorial_articles
SET workflow_status = ?,
    review_note = ?,
    scheduled_publish_at = ?,
    submitted_at = ?,
    approved_at = ?,
    updated_at = ?
WHERE id = ?
```

各操作对字段的影响：

| 字段 | save_draft | submit_review | approve | schedule |
|---|---|---|---|---|
| `workflow_status` | `draft` | `in_review` | `approved` | `scheduled` |
| `submitted_at` | 保持不变 | 更新为当前时间 | 保持不变 | 保持不变 |
| `approved_at` | 保持不变 | 保持不变 | 更新为当前时间 | 保持不变 |
| `scheduled_publish_at` | 清空为 NULL | 清空为 NULL | 保持不变 | 更新为指定时间 |
| `review_note` | 若请求中有值则更新 | 同左 | 同左 | 同左 |

### 9.6.4 定时发布时间格式

`_normalize_schedule_datetime()` 函数将输入解析为 ISO 格式并去除微秒。非法格式抛出 400 "Invalid scheduled publish time"。

---

## 9.7 HTML 渲染

**路由：** `POST /api/editorial/articles/{editorial_id}/render-html`

**函数：** `render_editorial_html(editorial_id)`

系统将 Markdown 内容渲染为两种 HTML 版本：标准 Web 版和微信公众号版。渲染引擎位于 `html_renderer.py`。

### 9.7.1 渲染流程

```
请求渲染
  |
  v
获取编辑稿详情
  |
  v
标签是否为空？
  |-- 是 → 自动调用 generate_editorial_tags() 先生成标签
  |
  v
调用 render_editorial_package(article, tags)
  → 返回 {html_web, html_wechat, summary}
  |
  v
更新 editorial_articles 表：
  SET excerpt, html_web, html_wechat, updated_at
  |
  v
返回 {article_id, html_web, html_wechat, summary}
```

### 9.7.2 Markdown → HTML 转换引擎

`markdown_to_html()` 函数是一个纯 Python 实现的 Markdown 解析器，支持：

| 语法元素 | HTML 输出 |
|---|---|
| `# / ## / ### / ####` | `<h1>` ~ `<h4>` |
| 段落文本 | `<p>` |
| `` ``` `` 代码块 | `<pre><code>` |
| `- / * / +` 无序列表 | `<ul><li>` |
| `1. 2.` 有序列表 | `<ol><li>` |
| `> ` 引用 | `<blockquote><p>` |
| `---` / `***` 分隔线 | `<hr />` |
| `**加粗**` | `<strong>` |
| `*斜体*` | `<em>` |
| `` `行内代码` `` | `<code>` |
| `[文本](URL)` | `<a href="..." target="_blank">` |

所有文本输出均经过 `html.escape()` 处理以防止 XSS。

### 9.7.3 Web 版 HTML（标准版）

Web 版使用完整的 CSS 类名和 CSS 变量系统，特点包括：

- **配色方案**：采用复旦蓝（`#0d0783`）和复旦橙（`#ea6b00`）为品牌色
- **布局**：`max-width: 940px` 居中容器
- **Hero 区域**：渐变背景卡片，包含标题、副标题、作者、机构、发布日期、摘要
- **标签芯片**：圆角胶囊样式，颜色来自标签的 `color` 字段
- **正文区域**：白色圆角卡片，衬线标题字体 + 无衬线正文字体
- **页脚**：来源链接和生成模板标记

**中英文字体差异**：

| 场景 | 中文 | 英文 |
|---|---|---|
| 正文字体 | Inter, PingFang SC, Microsoft YaHei | Aptos, Segoe UI, Helvetica Neue, Arial |
| 标题字体 | Noto Serif SC, Songti SC, serif | Iowan Old Style, Palatino Linotype, Georgia |
| 正文行高 | 2 | 1.82 |
| 摘要行高 | 1.9 | 1.78 |
| 正文字号 | 16px | 17px |
| 标题字号 | 52px | 48px |

### 9.7.4 微信公众号版 HTML（内联样式版）

微信版专为微信公众号排版设计，所有样式均使用 **内联 CSS**（`style="..."`），因为微信编辑器不支持外部样式表和大部分 CSS 类名。

特点：
- 所有样式直接写在元素的 `style` 属性中
- 使用 `wechat-shell`（`max-width: 760px`）容器
- `wechat-card` 白色圆角卡片背景
- 标签使用 `wechat-tag` span 样式
- 正文内容同样从 Markdown 转换而来

### 9.7.5 渲染包输入数据

`render_editorial_package()` 从 `article` 字典中提取：

| 字段 | 用途 | 英文回退值 |
|---|---|---|
| `content_markdown` | 正文渲染 | - |
| `excerpt` | 摘要区域 | "Summary unavailable" |
| `title` | 标题 | - |
| `subtitle` | 副标题（英文模式下如含 CJK 则清空） | - |
| `author` | 作者 | "Editorial Desk" |
| `organization` | 机构 | "Fudan Business Knowledge" |
| `publish_date` | 发布日期 | - |
| `source_url` | 来源链接 | - |

英文模式下，标签列表会过滤掉含 CJK 字符的标签。

### 9.7.6 纯文本提取 — strip_markdown()

```python
def strip_markdown(content: str) -> str
```

从 Markdown 内容中移除所有格式标记，保留纯文本。处理顺序：

1. 移除代码块（`` ```...``` ``）
2. 移除行内代码标记
3. 移除图片语法 `![]()`
4. 提取链接文本 `[text](url)` → `text`
5. 移除标题标记 `#`
6. 移除引用标记 `>`
7. 移除列表标记 `- * +`
8. 移除有序列表标记 `1.`
9. 移除 Markdown 特殊字符 `* _ ~ # > -`
10. 压缩多余换行和空白

---

## 9.8 发布流程

**路由：** `POST /api/editorial/articles/{editorial_id}/publish`

**函数：** `publish_editorial_article(editorial_id)`

发布是编辑稿生命周期的终态操作，将编辑稿内容正式写入公开的 `articles` 表。

### 9.8.1 发布前自动补全

1. 若 `tags` 为空 → 自动调用 `generate_editorial_tags()` 生成标签。
2. 若 `html_web` 或 `html_wechat` 为空 → 自动调用 `render_editorial_html()` 渲染 HTML。

### 9.8.2 发布详细流程

```
编辑稿就绪
  |
  v
自动补全标签和 HTML（如缺失）
  |
  v
生成公开 slug：_unique_slug(connection, "articles", ...)
  |
  v
editorial_articles.article_id 是否已关联且目标文章存在？
  |
  |-- 是（更新已有文章）
  |     → UPDATE articles SET doc_id, slug, title, publish_date,
  |       content, excerpt, main_topic, article_type, tag_text,
  |       org_text, search_text, word_count, access_level, ...
  |
  |-- 否（创建新文章）
  |     → INSERT INTO articles (...)
  |     → 获取 article_id = last_insert_rowid()
  |
  v
写入标签关联：
  DELETE FROM article_tags WHERE article_id = ?
  对每个标签：
    _ensure_tag(name, category) → 获取或创建 tag_id
    INSERT OR REPLACE INTO article_tags (article_id, tag_id, confidence)
  |
  v
写入栏目关联：
  DELETE FROM article_columns WHERE article_id = ?
  若 primary_column_slug 合法：
    查找 column_id
    INSERT OR REPLACE INTO article_columns (article_id, column_id, ...)
  |
  v
维护标签计数：
  UPDATE tags SET article_count = (SELECT COUNT(*) FROM article_tags WHERE tag_id = tags.id)
  DELETE FROM tags WHERE article_count <= 0
  |
  v
更新编辑稿自身：
  UPDATE editorial_articles SET
    article_id = ?,
    slug = ?,
    status = 'published',
    workflow_status = 'published',
    approved_at = COALESCE(approved_at, now),
    published_at = COALESCE(published_at, now),
    updated_at = now
  |
  v
刷新搜索缓存：refresh_search_cache()
  |
  v
返回 {
  "editorial_id": ...,
  "article_id": ...,
  "status": "published",
  "article_url": "/article/{article_id}",
  "updated_at": now
}
```

### 9.8.3 写入 articles 表的字段映射

| articles 字段 | 来源 |
|---|---|
| `doc_id` | SHA1 哈希 `"editorial:{id}:{slug}"` 取前 20 位 |
| `slug` | 基于编辑稿 slug 生成的唯一 slug |
| `relative_path` | `"editorial/{slug}.md"` |
| `source` | `"editorial"` |
| `source_mode` | `"cms"` |
| `title` | 编辑稿标题 |
| `publish_date` | 编辑稿发布日期 |
| `link` | 编辑稿的 source_url |
| `content` | 纯文本内容（plain_text_content） |
| `excerpt` | 编辑稿摘要 |
| `main_topic` | 编辑稿主题 |
| `article_type` | 编辑稿类型 |
| `series_or_column` | 固定为 `"内容后台"` |
| `tag_text` | 标签名称以 ` \| ` 连接 |
| `org_text` | 机构名称 |
| `search_text` | `"{title} {excerpt} {content[:4000]}"` 用于全文搜索 |
| `word_count` | 纯文本字数（去除空白后的字符数） |
| `access_level` | 编辑稿的访问级别 |

### 9.8.4 搜索缓存刷新

发布完成后调用 `refresh_search_cache()`（来自 `rag_engine` 模块），确保新发布的文章可被即时搜索。

---

## 9.9 导出功能

**路由：** `GET /api/editorial/articles/{editorial_id}/export?variant=web|wechat`

**函数：** `export_editorial_html(editorial_id, variant)`

### 9.9.1 导出流程

1. 获取编辑稿详情。
2. 若 HTML 未渲染（`html_web` 或 `html_wechat` 为空），自动触发 `render_editorial_html()` 渲染。
3. 校验 `variant` 参数：仅接受 `"web"` 或 `"wechat"`，否则 400。
4. 根据 variant 选择对应的 HTML 内容。
5. 生成下载文件名：`{slug}-{variant}.html`。
6. 返回 `Response`，MIME 类型为 `text/html; charset=utf-8`，设置 `Content-Disposition: attachment` 头触发浏览器下载。

### 9.9.2 导出格式对比

| 属性 | Web 版 | 微信版 |
|---|---|---|
| CSS 方式 | `<style>` 标签内的类名/变量 | 内联 `style` 属性 |
| 目标平台 | 浏览器/网站嵌入 | 微信公众号编辑器粘贴 |
| 容器宽度 | 940px | 760px |
| 设计风格 | 渐变 Hero + 卡片布局 | 简洁白卡 + 紧凑排版 |
| 标签展示 | 圆角芯片（CSS 变量色） | 简单 span 标签 |
| 适配场景 | 桌面端阅读 | 移动端微信阅读 |

---

## 9.10 EditorialWorkbenchPage 前端 UI 交互

编辑后台的前端以 `EditorialWorkbenchPage` 组件为核心，提供完整的 CMS 工作台界面。以下结合后端 API 路由描述前端的主要 UI 交互流程。

### 9.10.1 权限控制

所有编辑后台路由（`/api/editorial/*`）均通过 `_require_editorial_admin()` 函数进行权限校验：

```python
def _require_editorial_admin(authorization, debug_user_id, debug_user_email):
    user = get_authenticated_user(authorization, ...)
    require_admin_profile(user)
```

前端需确保当前用户已以 admin 身份登录，否则所有 API 调用将返回 401 或 403。

### 9.10.2 仪表盘视图

**API：** `GET /api/editorial/dashboard?limit=6`

前端展示的仪表盘数据结构：

| 指标 | 字段 | 说明 |
|---|---|---|
| 草稿数 | `draft_count` | workflow_status = "draft" 的文章数 |
| 已发布数 | `published_count` | workflow_status = "published" 的文章数 |
| 待审核数 | `pending_review_count` | workflow_status = "in_review" 的文章数 |
| 已通过数 | `approved_count` | workflow_status = "approved" 的文章数 |
| 定时发布数 | `scheduled_count` | workflow_status = "scheduled" 的文章数 |
| 最近发布时间 | `latest_published_at` | 最后一篇已发布文章的时间 |
| 导出就绪数 | `export_ready_count` | html_web 和 html_wechat 均非空的文章数 |
| 工作流分布 | `workflow_counts` | 各状态的数量列表 |
| 最近编辑 | `recent_items` | 最近更新的文章列表 |

### 9.10.3 文章列表与筛选

**API：** `GET /api/editorial/articles?limit=40&status=...&workflow_status=...`

前端可按以下维度筛选：

- `status` -- 文章发布状态（如 `"draft"`, `"published"`）
- `workflow_status` -- 工作流状态

列表按 `updated_at DESC` 排序，最大返回 100 条。

### 9.10.4 文章详情与编辑

**查看详情：** `GET /api/editorial/articles/{editorial_id}`

返回完整的 `EditorialArticleDetail`，包含所有元数据、Markdown 正文、标签、HTML 渲染结果和工作流状态。若文章有关联的源文章（`source_article_id`），还会附带 `source_article_ai` 字段。

**更新文章：** `PUT /api/editorial/articles/{editorial_id}`

可更新的字段列表：

```python
allowed_fields = {
    "title", "subtitle", "author", "organization", "publish_date",
    "source_url", "cover_image_url", "primary_column_slug",
    "article_type", "main_topic", "access_level", "source_markdown",
    "layout_mode", "formatting_notes", "content_markdown",
}
```

更新时自动重新生成：
- `plain_text_content`（从 content_markdown 提取纯文本）
- `excerpt`（从纯文本提取摘要）
- `html_web` 和 `html_wechat` 被清空为 NULL（需重新渲染）

### 9.10.5 前端操作流程汇总

以下是编辑人员典型的工作流程：

```
1. 创建文稿
   |-- 手动创建：填写标题和正文 → POST /api/editorial/articles
   |-- 上传文件：拖拽 .md/.docx/.txt → POST /api/editorial/upload
   |-- AI 导入：选择源文章 → POST /api/editorial/source-articles/{id}/import-ai
   |
   v
2. 编辑与完善
   |-- 修改元数据/正文 → PUT /api/editorial/articles/{id}
   |-- AI 自动排版 → POST /api/editorial/articles/{id}/auto-format
   |-- AI 自动标签 → POST /api/editorial/articles/{id}/autotag
   |
   v
3. 预览渲染
   |-- 渲染 HTML → POST /api/editorial/articles/{id}/render-html
   |-- 导出 HTML → GET /api/editorial/articles/{id}/export?variant=web|wechat
   |
   v
4. 审核流程
   |-- 提交审核 → POST .../workflow {action: "submit_review"}
   |-- 审核通过 → POST .../workflow {action: "approve"}
   |-- 定时发布 → POST .../workflow {action: "schedule", scheduled_publish_at: "..."}
   |-- 回退草稿 → POST .../workflow {action: "save_draft"}
   |
   v
5. 正式发布
   |-- 发布 → POST /api/editorial/articles/{id}/publish
   |     → 写入 articles 表
   |     → 关联标签和栏目
   |     → 刷新搜索缓存
   |     → 返回文章公开 URL
```

### 9.10.6 编辑稿序列化字段全表

`_serialize_editorial_row()` 返回的完整字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `int` | 编辑稿 ID |
| `article_id` | `int \| None` | 关联的已发布文章 ID |
| `source_article_id` | `int \| None` | 关联的源文章 ID |
| `slug` | `str` | URL slug |
| `title` | `str` | 标题 |
| `subtitle` | `str \| None` | 副标题 |
| `author` | `str \| None` | 作者 |
| `organization` | `str \| None` | 机构 |
| `publish_date` | `str` | 发布日期 |
| `source_url` | `str \| None` | 原文链接 |
| `cover_image_url` | `str \| None` | 封面图 URL |
| `primary_column_slug` | `str \| None` | 主栏目 slug |
| `article_type` | `str \| None` | 文章类型 |
| `main_topic` | `str \| None` | 主题 |
| `access_level` | `str` | 访问级别（public/member/paid） |
| `access_label` | `str` | 访问级别中文标签 |
| `workflow_status` | `str` | 工作流状态 |
| `workflow_label` | `str` | 工作流状态中文标签 |
| `review_note` | `str \| None` | 审核备注 |
| `scheduled_publish_at` | `str \| None` | 定时发布时间 |
| `submitted_at` | `str \| None` | 提交审核时间 |
| `approved_at` | `str \| None` | 审核通过时间 |
| `ai_synced_at` | `str \| None` | AI 同步时间 |
| `layout_mode` | `str` | 排版模式 |
| `formatting_notes` | `str \| None` | 排版备注 |
| `formatter_model` | `str \| None` | 使用的 AI 排版模型 |
| `last_formatted_at` | `str \| None` | 最后排版时间 |
| `source_markdown` | `str` | 原始 Markdown 内容 |
| `content_markdown` | `str` | 当前 Markdown 正文 |
| `plain_text_content` | `str` | 纯文本内容 |
| `excerpt` | `str` | 摘要 |
| `tags` | `list[dict]` | 标签列表 |
| `html_web` | `str \| None` | Web 版 HTML |
| `html_wechat` | `str \| None` | 微信版 HTML |
| `status` | `str` | 文章状态 |
| `created_at` | `str` | 创建时间 |
| `updated_at` | `str` | 更新时间 |
| `published_at` | `str \| None` | 发布时间 |

---

## 9.11 API 路由汇总

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/api/editorial/dashboard` | 仪表盘概览 | admin |
| `GET` | `/api/editorial/articles` | 编辑稿列表 | admin |
| `POST` | `/api/editorial/articles` | 创建编辑稿 | admin |
| `POST` | `/api/editorial/upload` | 上传文件创建编辑稿 | admin |
| `GET` | `/api/editorial/articles/{id}` | 编辑稿详情 | admin |
| `PUT` | `/api/editorial/articles/{id}` | 更新编辑稿 | admin |
| `POST` | `/api/editorial/articles/{id}/auto-format` | AI 自动排版 | admin |
| `POST` | `/api/editorial/articles/{id}/autotag` | AI 自动标签 | admin |
| `POST` | `/api/editorial/articles/{id}/workflow` | 工作流状态转换 | admin |
| `POST` | `/api/editorial/articles/{id}/render-html` | 渲染 HTML | admin |
| `GET` | `/api/editorial/articles/{id}/export` | 导出 HTML 文件 | admin |
| `POST` | `/api/editorial/articles/{id}/publish` | 正式发布 | admin |
| `GET` | `/api/editorial/source-articles` | 可导入的源文章列表 | admin |
| `GET` | `/api/editorial/source-articles/{id}/ai-output` | 源文章 AI 输出详情 | admin |
| `POST` | `/api/editorial/source-articles/{id}/import-ai` | AI 批处理导入 | admin |

---

## 9.12 关键源文件索引

| 文件路径 | 职责 |
|---|---|
| `backend/services/editorial_service.py` | 编辑后台核心业务逻辑（草稿、导入、排版、标签、发布） |
| `backend/services/html_renderer.py` | Markdown → HTML 渲染引擎（Web 版 + 微信版） |
| `backend/services/ai_service.py` | Gemini API 调用（排版和标签建议） |
| `backend/services/article_ai_output_service.py` | AI 批处理输出管理 |
| `backend/services/tag_engine.py` | 启发式标签推导引擎 |
| `backend/services/rag_engine.py` | 搜索缓存刷新 |
| `backend/services/membership_service.py` | 访问级别标准化与管理员权限校验 |
| `backend/routers/editorial.py` | 编辑后台 API 路由定义 |
| `backend/models/schemas.py` | Pydantic 请求/响应模型定义 |
| `backend/scripts/build_business_db.py` | slugify 工具函数和颜色映射 |
