# 16 私有云发布包、Nginx HTTPS 与上线验收

## 发布包必须包含

- `Dockerfile.backend`
- `Dockerfile.backup`
- `frontend/Dockerfile`
- `docker-compose.prod.yml`
- `.env.production.example`
- `backend/`
- `frontend/`
- `deploy/`
- `requirements.txt`
- `docs/deployment_plan/`

发布包不得包含：

- `.env`、`.env.docker`、`.env.production`
- `data/`、`backups/`、`uploads/`、`audio/`
- `*.db`、`*.db-wal`、`*.db-shm`
- `node_modules/`、`frontend/dist/`
- `qa/`、`reports/`、`_publish_clean/`

本地生成命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\create_release_package.ps1
```

输出：

- `_publish_clean/fdsmarticles-cloud-release/`
- `_publish_clean/fdsmarticles-cloud-release.zip`
- `_publish_clean/fdsmarticles-cloud-release.manifest.txt`

## 服务器目录结构

```text
/srv/fdsm/app/
  backend/
  frontend/
  deploy/
  data/
    fudan_knowledge_base.db
    Fudan_Business_Knowledge_Data/
    faiss_index_business/
    uploads/
    audio/
  backups/
  logs/
  .env.production
  docker-compose.prod.yml
```

## 首次部署步骤

```bash
sudo mkdir -p /srv/fdsm/app
sudo chown -R "$USER:$USER" /srv/fdsm/app
cd /srv/fdsm/app

# 上传并解压发布包后：
cp .env.production.example .env.production
vim .env.production

mkdir -p data backups logs secrets
# 上传数据库和资产到 data/

bash deploy/preflight.sh
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
bash deploy/acceptance_check.sh
```

执行 `preflight` 前必须同时核对 `20_上线前严格审核整改记录.md`、`21_上线前严格审核v2整改记录.md` 和 `27_三审上线前必修Bug整改.md` 的硬门槛，尤其是真实 HTTPS 域名、CAS 白名单、Redis 生产密码、metrics token、Sentry DSN、异地加密备份、媒体 stream token 日志保护、blue-green schema guard 和 `.env.production` 权限。

## HTTPS Nginx

宿主机 Nginx 示例在：

```text
deploy/nginx/fdsmarticles-https.conf
```

部署时：

```bash
sudo DOMAIN=<正式域名> EMAIL=<运维邮箱> APP_PORT=8080 bash deploy/bootstrap_https.sh
```

如果不使用 bootstrap 脚本，才手工安装示例配置：

```bash
sudo cp deploy/nginx/fdsmarticles-https.conf /etc/nginx/sites-available/fdsmarticles.conf
sudo ln -s /etc/nginx/sites-available/fdsmarticles.conf /etc/nginx/sites-enabled/fdsmarticles.conf
sudo nginx -t
sudo systemctl reload nginx
```

注意：`deploy/nginx/fdsmarticles-https.conf` 示例默认反代到 `127.0.0.1:8080`。如果 `.env.production` 中 `APP_PORT` 不是 `8080`，必须同步修改 upstream 端口。

证书可用 certbot：

```bash
sudo certbot --nginx -d knowledge.example.edu
```

生产变量必须一致：

```env
SITE_BASE_URL=https://knowledge.example.edu
ALLOWED_ORIGINS=https://knowledge.example.edu
CAS_SERVICE_URL=https://knowledge.example.edu/api/auth/cas/callback
```

## 上线验收

```bash
curl -fsS https://knowledge.example.edu/healthz
curl -fsS https://knowledge.example.edu/api/ready
curl -fsS "https://knowledge.example.edu/api/health?details=1"
curl -fsS "https://knowledge.example.edu/api/home/feed?language=zh"

DEBUG_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -H "X-Debug-User-Id: qa" "https://knowledge.example.edu/api/auth/status")
test "$DEBUG_CODE" = "400"

curl -I "https://knowledge.example.edu/api/auth/cas/login?redirect=/admin"
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml exec backend-web python -m backend.scripts.db_diagnostics
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=80 backend-web backend-worker
```

三审新增验收：

```bash
curl -sS -o /dev/null -w "%{http_code}\n" "https://knowledge.example.edu/metrics"
curl -fsS -H "Authorization: Bearer ${METRICS_TOKEN}" "https://knowledge.example.edu/api/metrics" | grep fdsm_app_info
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 backend-web frontend | grep 'token=' && exit 1 || true
sudo grep 'token=' /var/log/nginx/fdsmarticles.access.log && exit 1 || true
```

## 回滚

代码/镜像回滚：

```bash
cd /srv/fdsm/app
docker compose --env-file .env.production -f docker-compose.prod.yml down
unzip fdsmarticles-cloud-release-previous.zip -d /srv/fdsm/app.rollback
rsync -a --delete --exclude data --exclude backups /srv/fdsm/app.rollback/ /srv/fdsm/app/
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

数据库恢复：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml stop backend-web backend-worker backup
cp backups/<backup-name>/fudan_knowledge_base.db data/fudan_knowledge_base.db
rm -f data/fudan_knowledge_base.db-wal data/fudan_knowledge_base.db-shm
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

CAS 回退：

```env
AUTH_BACKEND=auto
CAS_ENABLED=0
```

改完后：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --force-recreate backend-web frontend
```
