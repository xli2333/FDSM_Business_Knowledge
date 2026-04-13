# Round 79：会员权限回归与预览认证修复
## 待办
- [x] P0 | 排查 | 重新核对免费会员、付费会员在当前本地环境中的登录态、会员资料接口与媒体权限返回，确认错误落点
- [x] P0 | 后端 | 修复本地无 Supabase 时预览账号不可用、身份被统一降为访客的问题
- [x] P0 | 后端 | 补齐免费会员与付费会员在 `auth/status`、`membership/me`、`media/audio`、`media/video` 上的回归测试
- [x] P0 | 验收 | 跑通后端测试、前端构建与真实登录验收，确认付费会员与免费会员权限分层恢复正确

## 验收记录
- [x] `pytest backend/tests/test_auth_membership_permissions.py backend/tests/test_media_service.py`
- [x] `npm run build`
- [x] 真实登录验收：免费会员与付费会员分别检查首页身份、音频页、视频页，截图输出到 `qa/screenshots/round79_permissions/`，摘要写入 `acceptance-summary.json`

## 验收重点
- [x] 免费会员登录后不再被后端识别为访客
- [x] 付费会员登录后不再被后端识别为访客
- [x] 免费会员只能试听付费音频，但可进入公开视频与会员视频
- [x] 付费会员可直接播放完整付费音频，并可访问公开/会员/付费视频
- [x] 登录页在当前默认本地环境下可正常提供预览账号密码登录

## 结果判断
- [x] 本轮真实验收未再暴露新的权限错位或首页入口误导问题，暂不新开下一轮 Todo
