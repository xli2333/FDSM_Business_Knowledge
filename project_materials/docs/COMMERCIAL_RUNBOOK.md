# 商业化运行与验收手册

本文档面向本项目当前的 business-only 商业化版本，范围仅包含 `Fudan_Business_Knowledge_Data`。

## 1. 基础运行

### 后端启动

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 前端启动

```powershell
cd frontend
npm install
npm run dev
```

## 2. 常用后台脚本

### 重建 business-only 数据库

```powershell
python build_knowledge_base.py
```

### 重建 business-only FAISS 索引

```powershell
python create_vector_db_faiss.py
```

### 批量生成标签

```powershell
python backend/scripts/generate_tags.py 50
```

### 自动生成专题

```powershell
python backend/scripts/generate_topics.py 3
```

### 检查数据库与运行时表

```powershell
python backend/scripts/migrate_db.py
```

## 3. 后端验收

### 核心烟雾测试

```powershell
python backend/scripts/smoke_test.py
```

当前脚本覆盖：

- 健康检查
- 首页聚合接口
- 智能搜索
- AI 助理快捷指令
- 商业化概览接口
- 演示申请写入数据库

## 4. 前端验收

### 代码与构建

```powershell
cd frontend
npm run lint
npm run build
```

### 视觉截图验收

```powershell
cd frontend
npm run visual:acceptance
```

截图默认输出目录：

```text
qa/screenshots/round7
```

## 5. 线索管理

### 演示申请页面

```text
/commercial
```

### 线索查看页面

```text
/commercial/leads
```

### 线索 CSV 导出接口

```text
GET /api/commerce/demo-requests/export
```

## 6. 当前商业化能力说明

- 已有独立商业化方案页，可直接对外演示
- 已有演示申请写库能力，可沉淀商务线索
- 已有线索列表与 CSV 导出能力，可支持本地运营复核
- 已有后端烟雾测试与前端视觉截图验收链路
