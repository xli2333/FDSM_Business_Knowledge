# 09 · Nginx 配置与静态资产

> **当前状态提示（2026-04-21）**：本文是早期容器内 Nginx/HTTPS 设计稿。当前实际实现为：前端容器使用 `deploy/nginx/default.conf` 监听 HTTP 80，宿主机 Nginx 使用 `deploy/nginx/fdsmarticles-https.conf` 终止 HTTPS 并反代到 `127.0.0.1:${APP_PORT}`。本文中 `deploy/nginx.conf`、`deploy/default.conf`、`_proxy_base.conf`、容器内 443 和证书 volume 方案不再作为当前执行依据。私有云执行请看 [16_私有云发布包_Nginx_HTTPS上线验收.md](./16_私有云发布包_Nginx_HTTPS上线验收.md) 和 [18_部署文档对齐复查.md](./18_部署文档对齐复查.md)。

> **前置依赖**：[08_Docker构建](./08_Docker构建_Dockerfile与compose.md) 完成
> **预计耗时**：2 小时
> **完成标志**：
> - Nginx 作为入口反代 `/api/*` 到 backend-web，并直出前端静态文件
> - 静态资产（`/audio-files/*`、`/editorial-uploads/*`、`/media-uploads/*`）由 Nginx 直接从 volume 读，不穿透到 FastAPI
> - 限流 zone 生效（AI 端点 5r/s、通用 30r/s、登录 10r/s）
> - 本地（无 HTTPS）和生产（有 HTTPS）可以用同一份 default.conf，HTTPS 块条件启用
> - gzip 压缩生效，`Content-Encoding: gzip` 出现在响应头

---

## 背景与目标

Nginx 在本项目里承担三个角色：

1. **前端静态文件服务器**：把 `frontend/dist/` 直出给浏览器
2. **API 反向代理**：`/api/*` 转给 `backend-web:8000`
3. **静态资产加速**：`/audio-files/*` 等走 `/data/audio/` volume，跳过 FastAPI
4. （生产）**HTTPS 终止**：Let's Encrypt 证书 + HTTP → HTTPS 重定向
5. **安全层**：限流、CORS 辅助、超时、请求体大小限制

**为什么静态资产一定要 Nginx 直出**：
- FastAPI 的 `StaticFiles` 每次请求都要过 Python → uvicorn worker 占用
- Nginx sendfile 系统调用级零拷贝，快 10-50 倍
- 高并发下 FastAPI 扛 100 QPS 的音频文件下载会饱和，Nginx 轻松扛 5000+

---

## 改动清单

- [ ] 步骤 1：填 `deploy/nginx.conf`（主配置：events、http、upstream、限流 zone）
- [ ] 步骤 2：填 `deploy/_proxy_base.conf`（proxy_pass 公共配置，避免重复）
- [ ] 步骤 3：填 `deploy/default.conf`（server 块：HTTP/HTTPS、location 路由）
- [ ] 步骤 4：让 HTTPS server 块在证书缺失时不阻塞启动
- [ ] 步骤 5：重新 build frontend 镜像并启动
- [ ] 步骤 6：验证静态资产走 Nginx
- [ ] 步骤 7：验证限流生效
- [ ] 步骤 8：验证 gzip 生效
- [ ] 步骤 9：Commit

**涉及文件**：
- `deploy/nginx.conf`
- `deploy/default.conf`
- `deploy/_proxy_base.conf`

---

## 原子步骤

### 步骤 1 · `deploy/nginx.conf`（主配置）

**打开 `deploy/nginx.conf`**，替换为：

```nginx
# fdsm-knowledge · Nginx 主配置
#
# 这个文件被 Dockerfile.frontend 拷到 /etc/nginx/nginx.conf
# http 块内的 include 会加载 /etc/nginx/conf.d/*.conf （default.conf 和 _proxy_base.conf）

user nginx;
worker_processes auto;                              # 和 CPU 核数一致
worker_rlimit_nofile 65535;                         # 文件描述符上限

pid /var/run/nginx.pid;
error_log /var/log/nginx/error.log warn;

events {
    worker_connections 4096;                        # 每个 worker 的并发连接
    use epoll;                                      # Linux 高效事件模型
    multi_accept on;                                # 一次 accept 多个连接
}

http {
    # ==========================================
    # 基础
    # ==========================================
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    charset utf-8;

    sendfile on;                                    # 零拷贝发文件
    tcp_nopush on;                                  # 和 sendfile 搭配，发完整包
    tcp_nodelay on;                                 # 小包不缓冲
    keepalive_timeout 65;
    keepalive_requests 1000;                        # 单连接最多复用 1000 个请求
    server_tokens off;                              # 响应头不泄露版本
    server_names_hash_bucket_size 64;

    # ==========================================
    # 超时
    # ==========================================
    client_header_timeout 30s;
    client_body_timeout 120s;                       # 上传大文件留足时间
    send_timeout 60s;
    proxy_connect_timeout 10s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    # ==========================================
    # 请求体大小
    # ==========================================
    client_max_body_size 100m;                      # 音视频上传
    client_body_buffer_size 128k;                   # 大于这个值写临时文件

    # ==========================================
    # 日志格式
    # ==========================================
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';
    access_log /var/log/nginx/access.log main buffer=32k flush=1s;

    # ==========================================
    # gzip（全局开启，但大文件/已压缩格式不压）
    # ==========================================
    gzip on;
    gzip_vary on;                                   # Vary: Accept-Encoding
    gzip_comp_level 6;                              # 1 最快 9 最狠
    gzip_min_length 1024;                           # < 1KB 不压
    gzip_proxied any;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml
        application/xml+rss
        application/atom+xml
        image/svg+xml;

    # ==========================================
    # 限流 zone
    # 三个 zone 按业务特征分：
    #   general: 绝大多数 API，30 req/sec per IP
    #   ai:      耗时调用，5 req/sec per IP
    #   auth:    登录/注册，10 req/sec per IP（防爆破）
    # ==========================================
    limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=api_ai:10m rate=5r/s;
    limit_req_zone $binary_remote_addr zone=api_auth:10m rate=10r/s;
    limit_conn_zone $binary_remote_addr zone=conn_per_ip:10m;

    # ==========================================
    # upstream 到后端
    # ==========================================
    upstream backend {
        server backend-web:8000 max_fails=3 fail_timeout=10s;
        keepalive 32;                               # 复用 32 个到后端的长连接
        keepalive_requests 1000;
        keepalive_timeout 60s;
    }

    # ==========================================
    # 包含 server 块（default.conf 在 conf.d 里）
    # ==========================================
    include /etc/nginx/conf.d/*.conf;
}
```

**关键点解释**：

| 配置 | 作用 |
|---|---|
| `worker_processes auto` | 按容器可用 CPU 数起 worker（通常 4） |
| `worker_connections 4096` | 单 worker 最大并发。4 worker × 4096 = 16k 并发上限 |
| `sendfile` + `tcp_nopush` | 大文件零拷贝 |
| `keepalive 32` 到 upstream | Nginx 和 backend-web 之间复用 TCP 连接，避免每请求重建 |
| `limit_req_zone ... 10m` | 用 10MB 内存记录 IP 维度限流状态 |
| `$binary_remote_addr` | 比 `$remote_addr` 省内存（IP 二进制 4-16 字节 vs 字符串 7-45 字节） |

---

### 步骤 2 · `deploy/_proxy_base.conf`（公共 proxy 配置）

**打开 `deploy/_proxy_base.conf`**，替换为：

```nginx
# 所有 proxy_pass 到 backend-web 的公共头设置
# 被 default.conf 里 include 到每个 location / api 里
# 不直接放 http 块，因为 proxy_* 指令不能在 http 块外用

proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port $server_port;

# 保留客户端传来的 Authorization、X-Visitor-Id 等
proxy_pass_request_headers on;

# 清空 Connection 头（允许 upstream keepalive）
proxy_set_header Connection "";

# 缓冲（让 Nginx 先读完上游响应再发客户端，保护慢客户端不占 upstream）
proxy_buffering on;
proxy_buffer_size 16k;
proxy_buffers 8 16k;
proxy_busy_buffers_size 32k;

# 忽略上游可能返回的某些头
proxy_ignore_headers X-Accel-Expires Expires Cache-Control;

# 错误重试（后端瞬时挂了换一个 upstream，虽然我们只有一个 upstream）
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 2;
proxy_next_upstream_timeout 10s;
```

⚠️ **注意**：Nginx 的 `include` 指令在 `conf.d/*.conf` 加载顺序下，`_proxy_base.conf` 和 `default.conf` 都会被当成 server 配置加载。但 `_proxy_base.conf` 里的指令**不是 server 级**的，而是 location 级的——所以它不能被当成 server 独立加载。

**解决方案 1（当前这个）**：`_proxy_base.conf` 放到 `conf.d/` 下，但文件名加下划线前缀提醒是内部 include。**不要让 `nginx.conf` 的 `include /etc/nginx/conf.d/*.conf` 直接载入它**——要用 `include /etc/nginx/conf.d/default.conf` 明确指定，或者把 `_proxy_base.conf` 放别处。

**改动 `Dockerfile.frontend`**（§08 里的）：
- 从 `COPY deploy/_proxy_base.conf /etc/nginx/conf.d/_proxy_base.conf`
- **改为** `COPY deploy/_proxy_base.conf /etc/nginx/snippets/_proxy_base.conf`

这样 `_proxy_base.conf` 放 `/etc/nginx/snippets/`（不被 `conf.d/*.conf` glob 匹配到），在 `default.conf` 里显式 `include /etc/nginx/snippets/_proxy_base.conf`。

**回到 §08 的 Dockerfile.frontend**，把对应行改成：
```dockerfile
# 原来是：
COPY deploy/_proxy_base.conf /etc/nginx/conf.d/_proxy_base.conf
# 改成：
COPY deploy/_proxy_base.conf /etc/nginx/snippets/_proxy_base.conf
```

然后 `default.conf` 里的 `include /etc/nginx/conf.d/_proxy_base.conf` 全改成 `include /etc/nginx/snippets/_proxy_base.conf`（下一步会看到）。

---

### 步骤 3 · `deploy/default.conf`（server 块）

**打开 `deploy/default.conf`**，替换为：

```nginx
# fdsm-knowledge · Server 配置
#
# 三个 server 块：
#   1. HTTP :80  —— Let's Encrypt 验证 + HTTPS 重定向（生产）；本地直接服务内容（开发）
#   2. HTTPS :443 —— 主站（生产，有证书时启用）
#   3. 仅 localhost:81 —— 内部监控/调试（可选）

# ==========================================================================
# HTTP :80
# ==========================================================================
server {
    listen 80 default_server;
    server_name _;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Nginx 自己的健康检查
    location = /nginx-health {
        access_log off;
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }

    # 其他请求：
    # 生产环境（有 SSL 证书文件）→ 重定向到 HTTPS
    # 本地环境（无证书）→ 正常服务内容
    #
    # 判断方式：看 /etc/letsencrypt/live/*/fullchain.pem 存不存在
    # Nginx 不能在配置里做文件存在判断，所以用"空 server 块 + 环境变量"组合：
    #
    # 本地 docker-compose.override.yml 里不挂 SSL 证书 volume，
    # 生产 docker-compose.yml 挂了证书。本地就会 skip HTTPS server 块。
    #
    # 这里先不做重定向，让所有请求都走本 server 块提供服务。
    # 生产 HTTPS 上线后再改成重定向（或者通过 include 不同的配置 snippet）

    # ---------------- 前端静态 ----------------
    root /usr/share/nginx/html;
    index index.html;

    # 带 hash 的静态资源永久缓存
    location ~* ^/assets/.+\.(js|css|woff2?|ttf|eot|png|jpg|jpeg|gif|svg|webp|ico|mp4|mp3)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
        try_files $uri =404;
    }

    # 根目录的 favicon 等
    location = /favicon.ico {
        expires 30d;
        access_log off;
        try_files $uri =404;
    }

    # SPA fallback：所有不匹配的路径都返回 index.html 让 React Router 处理
    location / {
        # 但 /api /audio-files /editorial-uploads /media-uploads 不能被 fallback
        try_files $uri $uri/ /index.html;
    }

    # ---------------- API（反代后端） ----------------

    # 鉴权端点：中等限流，防爆破
    location ~ ^/api/auth {
        limit_req zone=api_auth burst=20 nodelay;
        proxy_pass http://backend;
        include /etc/nginx/snippets/_proxy_base.conf;
    }

    # AI 端点：严格限流，超长超时
    location ~ ^/api/(chat|search|editorial/ai|editorial/summarize|editorial/translate|editorial/format) {
        limit_req zone=api_ai burst=10 nodelay;
        proxy_pass http://backend;
        include /etc/nginx/snippets/_proxy_base.conf;
        proxy_read_timeout 180s;
        proxy_send_timeout 180s;
    }

    # 通用 API
    location /api/ {
        limit_req zone=api_general burst=50 nodelay;
        proxy_pass http://backend;
        include /etc/nginx/snippets/_proxy_base.conf;
    }

    # ---------------- 静态资产（Nginx 直出，不穿透到 FastAPI） ----------------

    location /audio-files/ {
        alias /data/audio/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
        autoindex off;
    }

    location /editorial-uploads/ {
        alias /data/uploads/editorial/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /media-uploads/ {
        alias /data/uploads/media/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
    }

    # ---------------- 安全：拒绝所有 .hidden 文件 ----------------
    location ~ /\.(?!well-known) {
        deny all;
        access_log off;
        return 404;
    }
}

# ==========================================================================
# HTTPS :443 —— 仅在证书存在时启用
# ==========================================================================
# 这个 server 块需要证书文件，本地开发时如果没证书会让 Nginx 启动失败。
# 解决办法：用 "include" 条件加载——把 HTTPS server 独立到一个 snippet，
# 然后根据是否存在证书决定是否 include。
#
# 但 Nginx 本身没 "if file exists" 指令，所以实际做法：
#   - 生产：docker-compose.yml 里把 /etc/letsencrypt/live/* 挂成 volume（证书存在）
#   - 本地：docker-compose.override.yml 里不挂这个 volume，并且把 HTTPS 块注释掉
#
# 为了省事：本地 override 直接不挂 443 端口（§08 override 里 `ports: - "8080:80"` 没 443）
# 所以 Nginx 里即使写了 HTTPS 块，listen 443 也不会对外暴露，不影响
#
# 但 Nginx 启动时会验证 ssl_certificate 文件存在——不存在就 fail。
# 所以要么不写 HTTPS 块，要么用下面这招：ssl_certificate_data 用 default 证书，
# 主证书在 default.conf 之外的 ssl.conf 里加载，生产环境独立挂载。

# ---- 方案 A：本地先不开 HTTPS，生产时再加 ----
# 下面的 server 块本地注释掉（本文件里就不存在），生产时单独加一个 ssl.conf snippet。

# server {
#     listen 443 ssl http2;
#     server_name knowledge.fdsm.fudan.edu.cn;
#
#     ssl_certificate /etc/letsencrypt/live/knowledge.fdsm.fudan.edu.cn/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/knowledge.fdsm.fudan.edu.cn/privkey.pem;
#     ssl_session_timeout 1d;
#     ssl_session_cache shared:SSL:50m;
#     ssl_session_tickets off;
#     ssl_protocols TLSv1.2 TLSv1.3;
#     ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
#     ssl_prefer_server_ciphers off;
#     add_header Strict-Transport-Security "max-age=31536000" always;
#     limit_conn conn_per_ip 20;
#
#     # ...所有 location 块和上面 HTTP 的一样，直接 include 一份
# }
```

---

### 步骤 4 · HTTPS 的"可选启用"机制

上面 HTTPS 块目前是**注释掉的**，生产时要启用。有两种做法：

**做法 A · 生产部署时 `sed` 一下**

上线时在服务器上：
```bash
sed -i 's|^# server {$|server {|; s|^# }$|}|' deploy/default.conf
# 然后 docker compose restart frontend
```

粗糙但有效。

**做法 B · 用 `deploy/default.ssl.conf` 独立 snippet**

更工程化：
1. 把 HTTPS server 块独立到 `deploy/default.ssl.conf`（不入 `conf.d/*.conf` 的 glob）
2. 生产 `Dockerfile.frontend` 额外 `COPY deploy/default.ssl.conf /etc/nginx/conf.d/default.ssl.conf`
3. 本地 Dockerfile 不拷这个

**推荐做法 B 的简化版**：`default.conf` 里只放 HTTP，HTTPS 配置放 `default.ssl.conf`，**不放到 `conf.d/`** 里，只放到 `/etc/nginx/snippets/`；生产时用一个 `deploy/generate_ssl_conf.sh` 在服务器上把 `snippets/default.ssl.conf` 复制到 `conf.d/` 激活。

**当前选择**：步骤 3 里的注释块已经足够。生产上线按 §11 流程走。

---

### 步骤 5 · 重新 build 并启动

```powershell
cd C:\Users\LXG\fdsmarticles

# rebuild frontend（因为 Dockerfile.frontend 改了 COPY 路径）
docker compose build frontend

# rebuild backend 其实不用，但为了确保所有改动都在镜像里
docker compose build

# 重启
docker compose down
docker compose up -d

# 看日志确认 Nginx 没有启动报错
docker compose logs frontend
# 应该看到 "start worker processes"
```

**如果 frontend 启动失败**：
```
[emerg] open() "/etc/nginx/snippets/_proxy_base.conf" failed
```
说明 Dockerfile 里 COPY 路径没改。回到 §08 修 Dockerfile.frontend，重 build。

---

### 步骤 6 · 验证静态资产走 Nginx

**目标**：`/audio-files/xxx.mp3` 不穿透到 FastAPI。

**操作**：

```powershell
# 看 data/audio/ 里有什么
Get-ChildItem data\audio | Select-Object -First 3

# 选一个真实文件名，假设是 "foo.mp3"
$audio_file = "foo.mp3"     # 替换成实际文件名

# 直接访问
curl -I "http://localhost:8080/audio-files/$audio_file"
```

**预期响应头**：
```
HTTP/1.1 200 OK
Server: nginx/1.27.x                    ← 注意是 nginx，不是 uvicorn
Content-Type: audio/mpeg
Content-Length: xxxxx
Last-Modified: ...
Accept-Ranges: bytes
Cache-Control: public
Expires: ...（30 天后）
```

**关键**：
- `Server: nginx/...` 表示直接从 Nginx 返回（没走 FastAPI）
- `Accept-Ranges: bytes` 支持 HTTP Range（音频播放器需要）
- Cache 头生效

**对比**：直接敲 FastAPI 端口（如果本地暴露了 8000）：
```powershell
curl -I "http://localhost:8000/audio-files/$audio_file"
# Server: uvicorn  ← 这是原来的路径，现在被 Nginx 覆盖
```

**压测对比**：
```powershell
# Nginx 直出
hey -n 200 -c 20 "http://localhost:8080/audio-files/$audio_file"
# 预期 p99 < 50 ms

# FastAPI StaticFiles（如果本地直接启动 FastAPI 测试）
# 原方案会慢一个数量级
```

---

### 步骤 7 · 验证限流

**启动后**：
```powershell
# 打 AI 端点（限流 5 r/s）快速 100 次
hey -n 100 -c 10 http://localhost:8080/api/chat
```

**预期**：
- 大部分返回 503（`limit_req` 超限时 Nginx 返回 503）或 429（取决于配置）
- 少部分成功（在 burst=10 限内）

**确认 burst 机制**：
```powershell
# 慢速打（每秒 5 个），应该不限流
Measure-Command {
    1..10 | ForEach-Object {
        curl -s "http://localhost:8080/api/home/feed" -o $null
        Start-Sleep -Milliseconds 210   # 每秒 4-5 个
    }
}
```

**Nginx 日志**里能看到限流被触发：
```powershell
docker compose logs frontend | Select-String "limit_req"
# 看到 "limiting requests, excess: xxx by zone api_ai"
```

---

### 步骤 8 · 验证 gzip

```powershell
# 请求 API（返回 JSON 应被压缩）
curl -H "Accept-Encoding: gzip" -I "http://localhost:8080/api/home/feed?language=zh"
```

**预期响应头**：
```
HTTP/1.1 200 OK
Content-Encoding: gzip       ← 关键
Vary: Accept-Encoding
...
```

**小于 1KB 的响应不压**：
```powershell
curl -H "Accept-Encoding: gzip" -I "http://localhost:8080/api/health"
# 如果 body 小于 1024 字节，不会有 Content-Encoding: gzip
```

---

### 步骤 9 · Commit

```powershell
git add deploy/nginx.conf deploy/default.conf deploy/_proxy_base.conf
git add Dockerfile.frontend     # 如果改了 COPY 路径

git commit -m "deploy(step-09): production-grade Nginx configuration

- nginx.conf: worker auto, sendfile zero-copy, keepalive to upstream,
  gzip for text/json, limit_req zones (general 30r/s, ai 5r/s, auth 10r/s)
- default.conf: HTTP server with SPA fallback, hash-suffixed assets with
  1-year cache, proxy rules per endpoint category, static volume direct
  serving for /audio-files /editorial-uploads /media-uploads
- _proxy_base.conf: shared proxy_set_header, buffering, next_upstream retry;
  included from each proxy location via /etc/nginx/snippets/ path
- HTTPS server block commented for local; enabled at production deploy
  time per §11

Static assets no longer hit FastAPI; Nginx serves directly from volume."
```

---

## 阶段验收

### 验收 1 · Nginx 配置语法正确

```powershell
docker compose exec frontend nginx -t
# 预期：
# nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
# nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 验收 2 · 静态资产 Nginx 直出

步骤 6 已做。

### 验收 3 · 限流三档生效

```powershell
# AI 端点（5 r/s）
hey -n 50 -c 10 http://localhost:8080/api/chat | Select-String "Status"
# 应该有大量 429 / 503

# 通用（30 r/s）
hey -n 100 -c 10 http://localhost:8080/api/home/feed | Select-String "Status"
# 应该基本都是 200

# 查 Nginx 错误日志
docker compose logs frontend 2>&1 | Select-String "limiting" | Select-Object -Last 10
```

### 验收 4 · SPA fallback 正确

```powershell
# 访问前端路由（不存在的物理文件）
curl -I http://localhost:8080/admin/editorial
# 预期：200 OK，Content-Type: text/html（返回 index.html）

curl -I http://localhost:8080/does-not-exist
# 预期：200 OK（SPA fallback 把所有未知路径都给 index.html）
```

### 验收 5 · API 反代正确

```powershell
# 带上 Origin 测 CORS
curl -I http://localhost:8080/api/home/feed `
    -H "Origin: http://localhost:8080"
# 预期：
# Access-Control-Allow-Origin: http://localhost:8080
# Server: nginx/...
```

---

## 常见错误与排查

| 症状 | 原因 | 修复 |
|---|---|---|
| Nginx 启动报 `open() "/etc/nginx/snippets/..." failed` | COPY 路径错 | Dockerfile.frontend 用正确路径 |
| `403 Forbidden` 访问 /audio-files/ | Nginx 用户没权限读 volume | `chmod -R 755 data/audio` |
| 限流触发后返回 429 还是 503 | Nginx 默认 503，可以自定义 | `limit_req_status 429;` 加在 http 块 |
| `/api/` 返回 502 Bad Gateway | backend-web 还没 healthy | 等 90 秒 start_period |
| API 响应超长 Nginx 提前 504 | `proxy_read_timeout` 太短 | AI 端点块单独加 180s |
| SPA fallback 把 /api/ 也接管了 | location 优先级错 | `/api/` 用 `^~` 或精确路径匹配 |
| 静态文件返回 HTML 首页 | SPA fallback 匹配到了 | 检查静态资源 location 用 `^~` 或正则 |
| 压测 /assets/xxx.js 比预期慢 | `sendfile` 没开 | 确认 `sendfile on;` |

---

## 关于反代的一些细节

**为什么前端静态同样走 Nginx（不是 backend-web）**：
- Nginx 原生擅长静态
- 前端 build 产物放 `/usr/share/nginx/html`，无需穿透应用层
- 单容器做两件事（静态 + 反代）简化编排

**为什么静态资产 `/audio-files/` 走 `alias` 而不是 `root`**：
- `root /data/audio/` → 请求 `/audio-files/foo.mp3` 会拼成 `/data/audio/audio-files/foo.mp3`（错）
- `alias /data/audio/` → 请求 `/audio-files/foo.mp3` 拼成 `/data/audio/foo.mp3`（对）

**为什么 upstream 用 `keepalive 32`**：
- Nginx 默认每次反代都重建到后端的 TCP 连接
- 高 QPS 下 TCP 建立/关闭的开销可观
- 保持 32 个长连接足够应对典型负载

**为什么要 `server_tokens off`**：
- 默认响应头有 `Server: nginx/1.27.1`，版本号暴露给攻击者
- 关掉后只剩 `Server: nginx`

---

## 关于 HTTPS 的"延后启用"

本地开发不需要 HTTPS。§11 上线时按这个顺序：

1. 先只启 HTTP server 块（就是当前配置）
2. 让 Let's Encrypt certbot 在 80 端口的 `/.well-known/acme-challenge/` 做验证
3. 证书签发到 `/etc/letsencrypt/live/knowledge.fdsm.fudan.edu.cn/`
4. 把 HTTPS server 块的注释去掉
5. HTTP server 块里加上 `return 301 https://$host$request_uri` 重定向
6. `docker compose restart frontend`

§11 会给完整脚本。

---

## 下一步

**去 [10_本地17项验收测试.md](./10_本地17项验收测试.md)** 做完整的本地验收。

做完 09 之后本地 Docker 栈**功能层完整**：
- ✅ 后端 gunicorn × 4 worker
- ✅ 独立 worker 消费 AI 任务
- ✅ Redis 做缓存 + 任务队列 + 浏览计数缓冲
- ✅ Nginx 前端直出 + API 反代 + 静态资产 + 限流 + gzip
- ✅ 备份容器（profile disabled 暂不启）

但没做过**系统性的验收测试**——功能能不能全跑通？并发下性能怎样？§10 用 17 项硬指标检验。
