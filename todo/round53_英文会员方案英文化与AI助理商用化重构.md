# Round 53：英文会员方案英文化与 AI 助理商用化重构

## 待办
- [x] 梳理会员方案英文页仍显示中文的真实链路，确定前后端改动点
- [x] 给 billing plans 与 billing profile 增加英文本地化能力，并接入会员页/商业页
- [x] 修正会员页英文环境下的权益与方案展示，确保前端不再出现中文
- [x] 重构 AI 助理中英文快捷指令与提示文案，做到中文对应中文、英文对应英文
- [x] 给聊天后端补齐中英文命令别名与新简报指令，去掉英文 demo 式交互
- [x] 清理 `/today` 与 `/recommend` 中的 smoke/test/demo/editorial 内容，提升商用品质
- [x] 把 AI 助理返回的后续问题接成可点击操作，补齐真正可用的快捷继续交互
- [x] 完成构建、自检与回填

## 验收重点
- [x] 英文会员页公开方案、订阅信息、方案名称不再出现中文
- [x] 中文 AI 助理默认指令、快捷按钮、占位提示均为中文指令
- [x] 英文 AI 助理默认指令、快捷按钮、占位提示均为英文指令
- [x] `/today` 与 `/recommend` 不再给出 smoke/editorial/test/demo 内容

## 本轮结果
- billing plans 与 billing profile 已支持 `language=en`，会员页和商业页会拿英文方案文案。
- 会员页英文环境下不再直接显示后端中文权益文案，改为英文权益清单。
- AI 助理已改成真正的中英双语命令体系：中文环境用 `/简报 /总结 /比较 /时间线 /今日简报 /推荐`，英文环境用 `/brief /summarize /compare /timeline /today /recommend`。
- 聊天后端新增命令别名归一层与 `/brief` 能力，前端补齐 follow-up 点击继续提问链路。
- `/today` 与 `/recommend` 已过滤 smoke/test/demo/editorial 内容，并在英文环境下返回英文标题与英文摘要。
- 已完成 `python -m py_compile`、`npm.cmd run build`、`npm.cmd run lint`。
- 命令级本地降级验证已通过；真实 AI 模型直连冒烟因调用时长较长未作为最终验收依据。
