# round178 CAS 生产身份接入与云端安全闭环

## 本轮目标

在 Docker、Redis Worker、SQLite 写入治理已经跑通后，开始处理真正上云前最关键的生产身份入口。当前生产环境已经禁止 debug auth，但还没有完成 CAS 接入与管理员身份闭环。本轮目标是阅读现有 CAS 文档和认证代码，建立可配置的 CAS 登录/回调/登出流程，并保证生产环境不能依赖调试头或本地假身份。

## 原子 Todo

- [x] 1. 重新阅读 `CAS接入文档.doc`、现有 auth 路由、前端 AuthProvider/LoginPage、会员身份服务。
- [x] 2. 梳理当前认证模式：debug auth、password/mock、Supabase、未来 CAS 的优先级和生产开关。
- [x] 3. 新增 CAS 运行配置：启用开关、server base URL、service base URL、回调路径、登出路径、ticket 校验超时、管理员白名单。
- [x] 4. 后端新增 CAS service，负责生成登录 URL、校验 ticket、解析用户标识、同步本地业务用户和会员记录。
- [x] 5. 后端 auth 路由新增 CAS 登录入口、回调入口、登出入口，并扩展 `/api/auth/status` 返回 `auth_mode=cas`。
- [x] 6. 前端 LoginPage 适配 CAS 模式：生产 CAS 启用时显示统一登录入口，不暴露密码/mock 入口。
- [x] 7. 前端 AuthProvider 适配 CAS 状态：支持 CAS 回调后刷新身份和按角色跳转。
- [x] 8. 生产环境继续拒绝 `X-Debug-User-*`，并补充 QA 覆盖。
- [x] 9. Docker 环境样例补齐 CAS 配置项，默认关闭，避免本地启动被外部 CAS 阻塞。
- [x] 10. 新增 CAS 上云配置文档，明确回调 URL、反向代理、HTTPS、cookie/session 和管理员配置。
- [x] 11. 本地 Python 编译与前端构建通过。
- [x] 12. Docker 重建并启动通过。
- [x] 13. 执行 auth 状态 QA：CAS 关闭时仍能公开访问，生产 debug header 仍返回 400。
- [x] 14. 执行 CAS mock QA：模拟 ticket 校验成功，确认本地用户/会员记录创建或更新。
- [x] 15. 执行前端登录入口 QA：CAS 模式下跳转到后端 CAS 登录入口。
- [x] 16. 回写本轮 Todo 勾选状态、QA 结果和下一轮云端 Nginx/HTTPS/发布包 Todo。

## 验收标准

- 生产环境不再需要 debug auth 或本地密码入口作为管理员入口。
- CAS 配置关闭时，现有 Docker 本地生产闭环不被破坏。
- CAS 配置开启时，后端可以完成 ticket 校验、身份同步、会员/管理员识别。
- 前端能根据 `/api/auth/status` 的 `auth_mode=cas` 展示正确登录入口。
- CAS 相关 URL、HTTPS 和反向代理配置写入部署文档。

## QA 结果

- 已用 Word COM 抽取 `docs/CAS接入文档.doc` 到 `docs/CAS接入文档.extracted.txt`，确认协议为 CAS 2.0：login、serviceValidate、logout。
- `python -m compileall backend` 通过。
- `npm run build` 通过，新增 `CasCallbackPage` 打包成功，无 JSX 错误。
- `docker compose --env-file .env.docker config` 通过，CAS 变量已进入 web/worker/backup 环境，默认关闭。
- 首次 Docker 重启暴露旧库迁移顺序问题：先创建 `cas_employee_number` 索引导致旧库缺列启动失败。已修复为先 ALTER 再建索引，并重新验证启动。
- `docker compose --env-file .env.docker build backend-web backend-worker frontend` 通过。
- `docker compose --env-file .env.docker up -d --force-recreate` 通过，web、worker、frontend、redis、backup 均运行，web/worker 重启次数为 0。
- CAS 关闭场景 QA：`/api/auth/status` 返回 guest，公开 feed 返回 200，生产 `X-Debug-User-*` 返回 400，`/api/auth/cas/login` 在未配置时返回 503。
- CAS mock QA：模拟 `serviceValidate` XML 成功，登录入口返回 302，callback 签发 token，`/api/auth/status` 识别 `cas-10001` 为管理员，logout 后 token 失效。
- 前端入口 QA：`npm run cas:login:acceptance:round178` 通过，CAS 模式下登录页链接指向 `/api/auth/cas/login?redirect=%2Fadmin`，截图 `qa/screenshots/round178_cas_login/cas_login_entry.png`。
- `npm audit --omit=dev` 通过，生产依赖 0 漏洞。
- 容器内 `pip check` 通过，无 Python 依赖冲突。

## 下一轮

进入 `round179_云端Nginx_HTTPS_发布包与上线验收.md`，处理私有云发布包、HTTPS 反向代理、域名变量和最终上云验收清单。
