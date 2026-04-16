# round156 RAG后台公开语料口径与历史失败任务收口

- [x] 复核全量回填后的后台指标，确认历史失败 job 和非公开文章仍会污染 RAG 面板口径。
- [x] 将 failed/pending 任务统计改为只看每篇文章的最新 job，避免历史失败残留继续误报。
- [x] 将 RAG 后台 summary、latest assets、latest jobs 统一收口到公开文章语料，和页面文案保持一致。
- [x] 补定点回归测试，覆盖历史失败不误报和非公开资产不进入公开 RAG 面板。
- [x] 最终核对后台面板 ready/failed/pending 口径与数据库一致。
