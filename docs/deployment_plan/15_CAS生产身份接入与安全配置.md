# 15 CAS 生产身份接入与安全配置

## 协议依据

`docs/CAS接入文档.doc` 已抽取到 `docs/CAS接入文档.extracted.txt`。接入流程为 CAS 2.0：

1. 未登录用户跳转到 `CAS_URL/login?service=SERVICE_URL`。
2. CAS 登录成功后回跳 `SERVICE_URL?ticket=TICKET_VALUE`。
3. 后端调用 `CAS_URL/serviceValidate?service=SERVICE_URL&ticket=TICKET_VALUE`。
4. CAS XML 返回 `cas:user`、`cas:username`、`cas:displayName`、`cas:employeeNumber`。
5. 应用注销本地 session 后跳转 `CAS_URL/logout?service=SERVICE_URL`。

## 环境变量

```env
AUTH_BACKEND=auto
CAS_ENABLED=0
CAS_SERVER_URL=https://id.example.edu/cas
CAS_SERVICE_BASE_URL=https://knowledge.example.edu
CAS_SERVICE_URL=https://knowledge.example.edu/api/auth/cas/callback
CAS_VALIDATE_TIMEOUT_SECONDS=8
CAS_SESSION_TTL_SECONDS=28800
CAS_ADMIN_EMPLOYEE_NUMBERS=
CAS_ADMIN_USERNAMES=
```

默认 `CAS_ENABLED=0`，保证本地 Docker 和未接入学校 CAS 白名单的环境不被阻塞。正式切换时建议：

```env
APP_ENV=production
AUTH_BACKEND=cas
CAS_ENABLED=1
SITE_BASE_URL=https://knowledge.example.edu
ALLOWED_ORIGINS=https://knowledge.example.edu
CAS_SERVER_URL=https://id.fudan.edu.cn/cas
CAS_SERVICE_URL=https://knowledge.example.edu/api/auth/cas/callback
```

如果 Supabase 和 CAS 需要过渡共存，可临时使用：

```env
AUTH_BACKEND=dual
CAS_ENABLED=1
```

## 反向代理要求

- 外网必须使用 HTTPS。
- `SITE_BASE_URL`、`ALLOWED_ORIGINS`、`CAS_SERVICE_URL` 必须是同一个正式域名。
- 学校 CAS 白名单登记的 service URL 必须与实际校验时传给 `/serviceValidate` 的 service 完全一致。
- 如果登录入口带 `redirect` 参数，后端会把它纳入 service URL，CAS 白名单侧需要允许该回调 URL 模式。

## 管理员识别

优先级：

1. `CAS_ADMIN_EMPLOYEE_NUMBERS` 匹配 CAS `employeeNumber`。
2. `CAS_ADMIN_USERNAMES` 匹配 CAS `username`。
3. `ADMIN_EMAILS` 匹配 CAS attributes 中的 email/mail，或按工号推导出的邮箱。

未命中的 CAS 用户默认创建为 `free_member`。

## 本地 session

CAS ticket 只用于一次性校验。校验成功后，后端签发随机本地 token，并只保存 SHA-256 token hash 到 SQLite `auth_sessions` 表。前端把 token 存在 `localStorage` 的 `fdsm-cas-token`，后续 API 请求自动带 `Authorization: Bearer <token>`。

## 验收命令

CAS 未开启时：

```bash
curl http://127.0.0.1:18080/api/auth/status
curl -I "http://127.0.0.1:18080/api/auth/cas/login"
```

CAS mock 验收：

```bash
docker compose --env-file .env.docker exec backend-web python - <<'PY'
from backend.services.cas_auth_service import issue_session, get_user_by_session

token = issue_session({
    "username": "cas-admin",
    "employee_number": "10001",
    "display_name": "CAS Admin",
    "attributes": {"email": "cas-admin@example.edu"},
})
print(get_user_by_session(token))
PY
```

生产验证：

```bash
curl -I "https://knowledge.example.edu/api/auth/cas/login?redirect=/admin"
```

应返回 302，Location 指向学校 CAS 登录页。
