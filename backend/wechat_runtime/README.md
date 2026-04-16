# 公众号排版运行时

这个目录承载编辑台自动排版与公众号预览的正式运行时代码。

设计约束：

- 运行时只依赖当前主项目内部文件。
- 不再依赖外部 `公众号排版`、`AI_writer` 或其他学习目录。
- 即使外部参考目录被删除，`POST /api/editorial/articles/:id/auto-format` 也应继续可用。

当前内置内容：

- `wechatOfficialPublisherService.mjs`
- `package.json`
- `package-lock.json`

安装方式：

```powershell
npm install --prefix backend/wechat_runtime
```
