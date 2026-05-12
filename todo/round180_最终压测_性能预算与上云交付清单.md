# round180 最终压测、性能预算与上云交付清单

## 本轮目标

在 Docker、Worker、数据库写入治理、CAS、发布包和 HTTPS 文档都完成后，做最后一轮上线前技术验收。目标不是在本机模拟真实公网大流量，而是给出可复现的基础压测、性能预算、服务器配置建议和最终交付清单，判断当前代码是否已经达到“可以上传私有云并开始灰度”的状态。

## 原子 Todo

- [x] 1. 复核当前容器服务状态、镜像构建、端口、健康检查和发布包。
- [x] 2. 新增轻量压测脚本，覆盖 `/healthz`、`/api/health`、`/api/home/feed`、CAS login 关闭/开启路径。
- [x] 3. 执行本地公开读压测，记录并发数、总请求、成功率、耗时。
- [x] 4. 执行数据库写入压测，记录并发写事务、错误、慢写日志和耗时。
- [x] 5. 执行 Worker 队列回归，确认压测后异步任务仍能完成。
- [x] 6. 汇总当前单机私有云推荐配置：CPU、内存、磁盘、带宽、备份、升级触发点。
- [x] 7. 新增最终交付清单文档：上传文件、服务器准备、`.env.production`、数据资产、启动命令、验收命令、回滚命令。
- [x] 8. 本地 `python -m compileall backend` 和 `npm run build` 通过。
- [x] 9. Docker compose config、容器健康、DB 诊断、前端生产依赖 audit、后端 pip check 通过。
- [x] 10. 发布包重新生成并扫描通过。
- [x] 11. 回写本轮 Todo、QA 结果和最终判断：是否还有明确提升空间。

## 本轮实际 QA 结果

- `python -m compileall backend deploy`：通过。
- `npm run build`：通过。
- `npm audit --omit=dev`：0 vulnerabilities。
- 容器内 `pip check`：No broken requirements found。
- Docker compose config：本地 `.env.docker` 与生产 `docker-compose.prod.yml` 均通过。
- 容器健康：backend-web、backend-worker、frontend、redis 为 healthy，backup 为 up。
- 公开读压测：`120` 请求、`24` 并发，`120/120` 成功，耗时 `1796 ms`，p95 `1699 ms`；CAS 关闭态 `503` 按预期处理。
- 数据库写压测：`80` 写事务、`16` 并发、`0` 错误，未出现 `database is locked`。
- Worker 回归：真实 `editorial.auto_summary` 异步任务完成，`progress=100`，返回 `editorial_id=230`。
- DB 诊断：`quick_check=ok`，`journal_mode=wal`，`foreign_keys=1`，writable_probe ok。
- 发布包：`_publish_clean/fdsmarticles-cloud-release.zip` 重新生成，大小约 `4.0 MB`，manifest `500` 行；扫描仅命中 `.env.docker.example` 与 `.env.production.example` 两个示例文件。
- 接受度检查：Windows 宿主机缺少可用 `/bin/bash`，`deploy/acceptance_check.sh` 未在宿主机执行；已用 PowerShell 与容器内 Python 覆盖同等检查，私有云 Linux 主机按脚本执行。

## 最终判断

当前没有明确必须继续修改的代码级提升空间；已达到“可以打包上传私有云并进行灰度部署验收”的状态。下一步提升不是继续改本地代码，而是拿真实私有云域名、CAS 白名单、HTTPS 证书、Gemini key 和服务器数据目录做云端实机验收。

## 验收标准

- 本地基础读压测成功率为 100%。
- 并发写入不出现 `database is locked`。
- 压测后 web/worker 不重启，健康检查仍通过。
- 有明确的私有云服务器配置建议和上线交付清单。
- 若仍有明确提升空间，继续新开下一轮 Todo；否则收口到可上传私有云状态。
