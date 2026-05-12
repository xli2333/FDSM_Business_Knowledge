# round186 备份恢复演练自动化

## 本轮目标

把“备份创建成功”升级为“备份可验证、可恢复、可回滚”的脚本化验收，降低上云后数据库恢复不可用的风险。

## 原子 Todo

- [x] 1. 复核现有备份脚本和恢复缺口。
- [x] 2. 新增 SQLite 备份恢复/校验脚本，支持 `.db`、`.db.gz`、`.gpg` 解密入口、verify-only 和真实恢复。
- [x] 3. 将恢复脚本纳入 preflight、发布包和文档。
- [x] 4. 使用临时 SQLite 库跑创建、压缩、校验、恢复演练。
- [x] 5. 运行编译、Compose config、发布包重建与 manifest 扫描。
- [x] 6. 回写本轮 Todo 与验收结果；若仍有明确提升空间，继续开启下一轮。

## 本轮验收记录

- 新增 `deploy/restore_sqlite_backup.py`，默认 verify-only，显式 `--restore` 才替换目标库。
- 支持 `.db`、`.db.gz`、`.gpg`、`.db.gz.gpg` 的校验/恢复链路。
- 真实恢复前执行 SQLite `PRAGMA quick_check`；目标库存在时会生成 `.pre-restore-YYYYMMDD-HHMMSS` 副本。
- `Dockerfile.backup` 已复制恢复脚本到 `/ops`。
- `preflight.sh` 已检查恢复脚本存在。
- 文档 `24_备份恢复演练.md` 已新增并更新索引/交付清单。
- 临时 SQLite 源库创建、压缩备份、verify-only、`--restore`、恢复后数据读取均通过。
- `python -m compileall deploy` 通过。
- 本地/生产 Compose config 通过。
- Backup 镜像重建成功，容器内恢复脚本 help 可用；本地 backup 服务已重建启动。
- 发布包重建通过，manifest 523 行，zip 约 3.91 MB，敏感文件扫描未命中。

## 后续判断

备份恢复演练自动化已闭环。仍有明确提升空间：生产 CAS 模式下前端 Supabase 历史依赖可退场，后端 Supabase 兼容路径可进一步隔离。因此继续开启下一轮。
