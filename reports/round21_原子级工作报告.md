# Round21 原子级工作报告

## 1. 本轮目标

本轮围绕三件事收口：

1. 为项目补齐中英文适配能力。
2. 为文章页补齐基于 Gemini Flash 的即时英文翻译能力，并且不是全量预翻译，而是按需触发。
3. 按真实用户流程完成集成测试、调试与验收，确保访客路径、英文路径、文章翻译路径与商业化表单路径都可用。

对应 Todo 文件：

- `todo/round21_中英文适配与文章即时英译补齐.md`

---

## 2. 原子级改动清单

### 2.1 后端：Flash-only 即时翻译链路

1. 在 `backend/config.py` 新增 `GEMINI_FLASH_MODEL` 配置项，默认锁定为 `gemini-2.5-flash`。
2. 重写 `backend/services/ai_service.py`，清理原有乱码风险提示词，并把翻译能力独立收口到 `translate_article_to_english()`。
3. 在 `backend/database.py` 新增 `article_translations` 运行时缓存表。
4. 新建 `backend/services/translation_service.py`：
   - 按文章当前可见内容生成 `source_hash`
   - 先查缓存
   - 缓存不存在时才调用 Gemini Flash
   - 访客预览内容与付费全文内容分离缓存，避免互相污染
5. 在 `backend/models/schemas.py` 新增 `ArticleTranslationResponse`。
6. 在 `backend/routers/articles.py` 新增接口：
   - `GET /api/article/{article_id}/translation?lang=en`
7. 后端翻译能力只支持英文目标语种，且只走 Flash 模型，不会落回通用 Pro 模型。

### 2.2 前端：语言状态与核心页面中英适配

1. 新增 `frontend/src/i18n/messages.js`。
2. 新增 `frontend/src/i18n/LanguageContext.js`。
3. 新增 `frontend/src/i18n/LanguageProvider.jsx`：
   - 支持 `zh / en`
   - 读取并持久化 `localStorage`
   - 支持 `?lang=en`
   - 自动写入 `<html lang>`
4. 在 `frontend/src/main.jsx` 接入 `LanguageProvider`。
5. 重写 `frontend/src/App.jsx`，让页面 fallback 进入语言体系。
6. 重写 `frontend/src/components/layout/Navbar.jsx`：
   - 顶栏中英切换
   - 响应式布局调整
   - 英文版导航、搜索占位、登录按钮、会员状态
7. 重写 `frontend/src/components/layout/Footer.jsx`。
8. 重写 `frontend/src/components/shared/ArticleCard.jsx`。
9. 重写 `frontend/src/components/shared/SearchBar.jsx`。
10. 重写 `frontend/src/auth/AuthDialog.jsx` 与 `frontend/src/auth/AuthProvider.jsx`，让登录弹窗与登录反馈进入双语模式。

### 2.3 文章页：即时英译、蒙版与视图切换

1. 在 `frontend/src/api/index.js` 新增 `fetchArticleTranslation()`。
2. 重写 `frontend/src/pages/ArticlePage.jsx`：
   - 英文模式下显示“一键翻译为英文”
   - 翻译完成后支持“查看英文 / 查看原文”双态切换
   - 翻译中对摘要区和正文区显示蒙版与加载提示
   - 展示翻译状态、缓存状态、模型标识
   - 访客仅翻译预览正文，付费会员可翻译全文
3. 文章页的会员墙、互动区、访问标签、会员状态都完成中英文适配。

### 2.4 核心页面英语模式补齐

1. 重写 `frontend/src/pages/HomePage.jsx`。
2. 重写 `frontend/src/pages/SearchPage.jsx`。
3. 重写 `frontend/src/pages/CommercialPage.jsx`。

本轮没有尝试把整个站点所有后台页全部英文化，而是优先覆盖真实访客最核心的三条路径：

- 首页进入
- 搜索进入
- 文章阅读与即时翻译进入
- 商业化表单进入

### 2.5 验收脚本与用户流脚本

1. 重写 `frontend/scripts/visual_acceptance.mjs`：
   - 输出到 `qa/screenshots/round21`
   - 覆盖桌面端中文首页、英文首页、中文文章、英文文章、商业化页、后台页、会员页
   - 覆盖移动端中文与英文视图
2. 新增 `frontend/scripts/user_flow_acceptance.mjs`：
   - 浏览器级真实点击
   - 英文首页搜索
   - 搜索结果进入文章
   - 受限文章翻译
   - 受限文章会员入口可见性
   - 商业化表单提交
   - 移动端英文文章可见性
3. 在 `frontend/package.json` 新增脚本：
   - `npm run userflow:acceptance`

---

## 3. 关键文件清单

### 后端

- `backend/config.py`
- `backend/database.py`
- `backend/models/schemas.py`
- `backend/routers/articles.py`
- `backend/services/ai_service.py`
- `backend/services/translation_service.py`
- `backend/scripts/smoke_test.py`

### 前端

- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/api/index.js`
- `frontend/src/i18n/messages.js`
- `frontend/src/i18n/LanguageContext.js`
- `frontend/src/i18n/LanguageProvider.jsx`
- `frontend/src/components/layout/Navbar.jsx`
- `frontend/src/components/layout/Footer.jsx`
- `frontend/src/components/shared/ArticleCard.jsx`
- `frontend/src/components/shared/SearchBar.jsx`
- `frontend/src/auth/AuthDialog.jsx`
- `frontend/src/auth/AuthProvider.jsx`
- `frontend/src/pages/HomePage.jsx`
- `frontend/src/pages/SearchPage.jsx`
- `frontend/src/pages/ArticlePage.jsx`
- `frontend/src/pages/CommercialPage.jsx`
- `frontend/scripts/visual_acceptance.mjs`
- `frontend/scripts/user_flow_acceptance.mjs`

### 管理与记录

- `todo/round21_中英文适配与文章即时英译补齐.md`

---

## 4. 验收与调试结果

### 4.1 后端编译与烟雾测试

已通过：

- `python -m compileall backend`
- `python backend/scripts/smoke_test.py`

本轮烟雾测试中的关键结论：

1. 英译链路已真实跑通。
2. 访客访问受限文章时，英译返回 `preview` 范围。
3. 升级为付费会员后，英译返回 `full` 范围。
4. 英译模型真实记录为 `gemini-2.5-flash`。
5. 同一访客重复打开文章仍保持浏览去重。

烟雾测试中的关键结果摘录：

- `guest_status = 200`
- `guest_scope = preview`
- `guest_model = gemini-2.5-flash`
- `paid_status = 200`
- `paid_scope = full`
- `db_row = [article_id, "en", "gemini-2.5-flash"]`

### 4.2 前端静态验收

已通过：

- `npm run lint`
- `npm run build`

说明：

- 未出现 JSX / JAX 构建错误
- 未出现新的中文编码错误
- 当前仍存在 Vite 的大包体 warning，但这是性能优化项，不是功能阻塞项

### 4.3 视觉验收

已通过：

- `npm run visual:acceptance`

截图输出目录：

- `qa/screenshots/round21`

主要截图文件：

- `qa/screenshots/round21/desktop-home.png`
- `qa/screenshots/round21/desktop-article_1.png`
- `qa/screenshots/round21/desktop-commercial.png`
- `qa/screenshots/round21/desktop-editorial.png`
- `qa/screenshots/round21/desktop-membership.png`
- `qa/screenshots/round21/desktop-search_q_AI_mode_smart.png`
- `qa/screenshots/round21/desktop-en-lang_en.png`
- `qa/screenshots/round21/desktop-en-article_1_lang_en.png`
- `qa/screenshots/round21/mobile-home.png`
- `qa/screenshots/round21/mobile-membership.png`
- `qa/screenshots/round21/mobile-en-lang_en.png`
- `qa/screenshots/round21/mobile-en-article_1_lang_en.png`

### 4.4 浏览器级真实用户流验收

已通过：

- `npm run userflow:acceptance`

覆盖流程：

1. 英文首页加载
2. 首页搜索 `AI`
3. 搜索结果进入文章
4. 进入受限文章并触发英文即时翻译
5. 校验会员入口存在
6. 打开商业化页面并提交 Demo 表单
7. 移动端英文文章页基础可见性检查

这部分不是接口模拟，而是 Playwright 驱动真实浏览器执行。

---

## 5. 本轮解决的真实问题

本轮并不是一次性写完后全部通过，中间实际解决了这些问题：

1. 修复了 PromptTemplate 将 JSON 示例误识别为模板变量的问题。
2. 修复了浏览器级用户流脚本中搜索结果节点重渲染导致点击失效的问题。
3. 修复了用户流脚本等待错误节点的问题，改为只等待搜索结果卡片里的文章链接。
4. 清理了 AuthProvider 中不必要的 `useMemo` 依赖告警，保证 `npm run lint` 无 warning。
5. 将核心页面与共享组件改为干净 UTF-8 重写，避免在乱码文本上继续打补丁。

---

## 6. 当前完成度判断

到本轮结束，项目在“真实访客阅读 + 英文用户即时翻译 + 响应式浏览 + 商业化表单转化”这条主链路上已经闭环。

当前已经达到的状态：

1. 中文 / 英文界面可切换且可持久化。
2. 英文用户进入文章后可一键触发即时英译。
3. 翻译过程有蒙版与状态提示。
4. 访客预览与付费全文的英译缓存隔离。
5. 首页、搜索页、文章页、商业化页已经进入核心英语模式。
6. 后端、前端、视觉截图、浏览器用户流都已经真实验收通过。

---

## 7. 非阻塞项

目前仅剩一个非阻塞项：

1. 前端主包仍有大于 500 kB 的构建 warning，后续可以继续做 `manualChunks` 拆包优化。

这不会影响明早的功能验收。

---

## 8. 报告落点

本报告存放路径：

- `reports/round21_原子级工作报告.md`
