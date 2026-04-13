# 复旦管院智识库 — 原子级开发 TODO 总览

> 基于 PROJECT_BLUEPRINT.md，拆解为 6 个阶段，每阶段独立文件
>
> **变更记录**：原"时光机"功能 → 改为"一键生成知识卡"（手绘插画风格，一致性视觉约束）

---

## 阶段索引

| 阶段 | 文件 | 核心内容 | 依赖 |
|------|------|----------|------|
| Phase 0 | `phase0_基础重构.md` | 前后端拆分、路由引入、DB Schema 升级 | 无 |
| Phase 1 | `phase1_标签与栏目.md` | AI 标签引擎、标签/栏目 API、首页重构、知识卡 | Phase 0 |
| Phase 2 | `phase2_RAG升级与AI助理.md` | Hybrid Search、Re-Ranker、AI 对话系统 | Phase 0 |
| Phase 3 | `phase3_专题系统.md` | 专题 CRUD、AI 自动生成、专题页面 | Phase 1 |
| Phase 4 | `phase4_打磨与上线.md` | 文章详情升级、性能优化、移动端、部署 | Phase 1-3 |
| 附录 | `appendix_前端页面ASCII设计稿.md` | 所有页面的 ASCII 线框图 | 参考用 |

---

## 当前代码现状

```
已有文件:
  backend/main.py          — 单文件，含全部 API (rag_search, sql_search, article, summarize, time_machine)
  frontend/src/App.jsx     — 单文件 SPA，含搜索、结果、阅读器、时光机
  frontend/src/api.js      — 5 个 API 函数
  frontend/src/index.css   — Tailwind 主题 + 自定义字体
  fudan_knowledge_base.db  — SQLite (articles 表)
  faiss_index/             — FAISS 向量索引

技术栈:
  前端: React 19 + Vite + Tailwind CSS v4 + Framer Motion + Lucide React
  后端: FastAPI + LangChain + Gemini + FAISS + SQLite
  部署: Render (后端) + Vercel (前端)
```

## 命名约定

- 每个 TODO 项格式：`[ ] P{优先级} | {模块} | {具体任务描述}`
- 优先级：P0=必须完成，P1=重要，P2=可延后
- 完成后改为 `[x]`
