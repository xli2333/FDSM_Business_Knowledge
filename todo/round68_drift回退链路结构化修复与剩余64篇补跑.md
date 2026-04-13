# Round 68：drift 回退链路结构化修复与剩余 64 篇补跑

## P0 问题来源
- [x] Round67 severe 首轮补跑后，severe 名单由 `377` 篇收缩到 `64` 篇
- [x] 剩余问题的共同特征是：`markdown_structure_count = 0`、`leading_lines_match = true`
- [x] 明确根因：Gemini relayout 两次漂移后，当前 fallback 退回到了“原文平铺版 markdown”，没有走结构化归一化

## P0 链路修复
- [x] 在 [article_relayout_batch.py](C:/Users/LXG/fdsmarticles/backend/scripts/article_relayout_batch.py) 中修补中文 fallback
- [x] 中文 fallback 改为优先走结构化正文归一化，而不是直接回退原文平铺 markdown
- [x] 英文 fallback 也同步走结构化正文归一化
- [x] 摘要 fallback 同步走摘要归一化，避免重新出现星号项目符号清单

## P1 剩余 severe 补跑
- [ ] 对剩余 `64` 篇 severe 文章强制重跑
- [ ] 记录第二轮补跑后 severe 名单是否继续收缩
- [ ] 抓典型边界稿复核，例如 `2081 / 2069 / 2051 / 2037 / 2115`

## P1 验收
- [ ] 重扫 severe 名单
- [ ] 对第二轮后的样本做中英文截图复验
- [ ] 若仍有明确提升空间，继续新开中文 Round69 todo
