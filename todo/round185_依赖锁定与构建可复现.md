# round185 依赖锁定与构建可复现

## 本轮目标

降低云端 Docker 重建时因上游 Python 依赖变化导致的不可复现风险，补齐依赖锁文件、Docker 构建校验和文档。

## 原子 Todo

- [x] 1. 复核 Python/Node 依赖锁定现状，确认缺口。
- [x] 2. 生成或维护 Python 锁文件，避免把本机无关包混入。
- [x] 3. 调整 Dockerfile/backend CI/preflight，使生产构建优先使用锁文件并校验存在。
- [x] 4. 更新部署文档，说明何时更新锁文件和如何验证。
- [x] 5. 运行 Docker 后端重建、pip check、专项测试、Compose config、发布包重建与 manifest 扫描。
- [x] 6. 回写本轮 Todo 与验收结果；若仍有明确提升空间，继续开启下一轮。

## 本轮验收记录

- `requirements.lock.txt` 已新增，来源为 Python 3.12 后端 Docker 镜像 `pip freeze`。
- `Dockerfile.backend` 已改为安装 `requirements.lock.txt`。
- `deploy/check_requirements_lock.py` 已新增并接入 CI。
- CI 后端依赖安装改为 `pip install -r requirements.lock.txt`。
- `preflight.sh` 已检查 `requirements.lock.txt` 存在。
- 文档 `23_依赖锁定与构建可复现.md` 已新增并更新索引/交付清单。
- `python deploy/check_requirements_lock.py` 通过，16 个直接依赖、77 个锁定包。
- `python -m compileall backend deploy` 通过。
- 本地/生产 Compose config 均通过。
- 后端 Web/Worker/Housekeeping 镜像已用锁文件重建成功，主栈健康。
- 容器内 `pip check` 通过。
- `/api/ready` 与 `/api/metrics` 探针通过。
- 会员/媒体专项测试 7 passed。
- 发布包重建通过，manifest 520 行，zip 约 3.91 MB，敏感文件扫描未命中。

## 后续判断

依赖锁定已闭环。仍有明确提升空间：备份恢复演练脚本化、Supabase 历史路径退场、wechat runtime 独立容器化、真实云端验收记录。因此继续开启下一轮。
