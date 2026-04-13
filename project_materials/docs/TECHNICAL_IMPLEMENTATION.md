# 项目技术实现说明文档

## 1. 切片技术 (Slicing Technology) 

本项目采用 **LangChain** 提供的 `RecursiveCharacterTextSplitter` 进行文档切片，这是一种基于字符层级递归分割的智能切片策略，能够最大限度保留语义的连贯性。

*   **切片策略**：
    *   **Chunk Size (块大小)**：800 字符。选择此大小是为了平衡上下文信息的完整性与向量检索的粒度。
    *   **Chunk Overlap (重叠)**：100 字符。在切片之间保留重叠区域，防止关键信息在切割点丢失，确保语义连贯。
*   **上下文增强**：
    *   在向量化之前，我们会对每个切片进行**元数据增强**。具体做法是将文章的 `Title` (标题) 和 `Source` (来源) 拼接到切片内容的头部 (`Title: ...\nSource: ...\n\nContent...`)。
    *   **目的**：这样做可以显著提高检索的准确性，即使查询词只命中标题，也能通过向量相似度召回对应的正文片段。

## 2. RAG (检索增强生成) 路线

本项目的 RAG 系统基于 **LangChain** 框架构建，采用了先进的 "Query Expansion" (查询扩展) 和 "Fusion Retrieval" (融合检索) 策略。

*   **Embedding 模型**：使用 Google 的 `gemini-embedding-exp-03-07` 模型。
    *   Indexing 阶段任务类型设置为 `retrieval_document`。
    *   Query 阶段任务类型设置为 `retrieval_query`。
*   **向量数据库**：使用 **FAISS** (Facebook AI Similarity Search) 进行本地化的高效向量存储与检索。
*   **检索流程 (Retrieval Pipeline)**：
    1.  **核心意图提取 (Core Query Extraction)**：利用 `gemini-3-flash` 从用户复杂的自然语言输入中提取核心搜索词，去除冗余的对话词汇；当前运行时映射到 `gemini-3-flash-preview`。
    2.  **查询扩展 (Query Expansion)**：利用 LLM 生成 3-4 个与核心词高度相关的同义词或专业术语，解决“词汇不匹配”问题。
    3.  **多路召回与融合 (Multi-query Fusion)**：
        *   系统并行执行多次向量检索（针对核心词和扩展词）。
        *   **加权算法**：对召回结果进行去重和加权。核心词召回的文档权重最高 (1.0)，扩展词召回的权重较低 (0.6)。同时引入“频率加成” (Frequency Boost)，如果一个文档被多个查询词同时召回，其排名会显著提升。
    4.  **最终排序**：基于加权后的综合分数返回 Top-K 结果。
*   **生成与摘要**：检索到的上下文被送入 `gemini-3-flash` 模型，用于生成高保真的文章摘要或回答用户提问；当前运行时映射到 `gemini-3-flash-preview`。

## 3. 网站搭建路线

本项目采用经典的前后端分离架构，确保系统的可扩展性与维护性。

*   **前端 (Frontend)**：
    *   **核心框架**：**React 19**。利用其最新的并发渲染特性提供流畅的用户体验。
    *   **构建工具**：**Vite**。提供极速的开发服务器启动和模块热更新 (HMR)。
    *   **UI 设计**：**Tailwind CSS v4**。使用 Utility-First 的 CSS 框架快速构建现代化的响应式界面。
    *   **组件库与动画**：集成 `lucide-react` 图标库和 `framer-motion` 动画库，提升交互质感。
*   **后端 (Backend)**：
    *   **核心框架**：**FastAPI (Python)**。高性能的异步 Web 框架，完美支持 Python 的 AI 生态。
    *   **数据库**：
        *   **SQLite**：存储结构化的文章元数据（如标题、日期、来源）。
        *   **FAISS**：存储非结构化文本的向量索引。
    *   **API 设计**：遵循 RESTful 标准，提供 `/api/rag_search`, `/api/time_machine` 等接口供前端调用。

## 4. 生图路线 (Image Generation)

项目中集成了“时光机”功能，通过 AI 生成具有艺术感的插画，增强内容的感染力。

*   **模型选择**：**Google Gemini (gemini-3-pro-image-preview)**。利用其强大的多模态生成能力。
*   **实现流程**：
    1.  **内容定位**：根据用户选择的日期（或随机），从数据库中定位一篇历史文章。
    2.  **金句提取**：使用 LLM 从文章中提取一句富有哲理的“金句”或基于标题进行创作，作为画面的灵感来源。
    3.  **Prompt 工程**：构建结构化的提示词 (Prompt)。
        *   *风格定义*：手绘插画风格 (Cute hand-drawn illustration style)，记号笔或彩铅质感。
        *   *氛围设定*：温暖的学院风，复旦大学商学院背景，暖橙色与深蓝色调。
        *   *构图约束*：严格的 1:1 方形构图。
    4.  **图像生成**：通过 Google GenAI SDK 调用模型，直接生成图像数据。
    5.  **前端展示**：后端将生成的图像转换为 Base64 编码流回传给前端，前端即时渲染，无需存储静态文件。
