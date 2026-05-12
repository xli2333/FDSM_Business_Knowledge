#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${DOMAIN:-${1:-}}"
EMAIL="${EMAIL:-${2:-}}"
APP_PORT="${APP_PORT:-8080}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-fdsmarticles}"
WEBROOT="${WEBROOT:-/var/www/certbot}"
SITES_AVAILABLE="${SITES_AVAILABLE:-/etc/nginx/sites-available}"
SITES_ENABLED="${SITES_ENABLED:-/etc/nginx/sites-enabled}"
HTTP_CONFIG="$SITES_AVAILABLE/${NGINX_SITE_NAME}.http.conf"
HTTPS_CONFIG="$SITES_AVAILABLE/${NGINX_SITE_NAME}.conf"
HTTPS_TEMPLATE="${HTTPS_TEMPLATE:-deploy/nginx/fdsmarticles-https.conf}"

fail() {
  echo "[bootstrap_https] $*" >&2
  exit 1
}

[ "$(id -u)" -eq 0 ] || fail "run as root or with sudo"
[ -n "$DOMAIN" ] || fail "DOMAIN is required, e.g. DOMAIN=knowledge.example.edu"
[[ "$DOMAIN" != *"knowledge.example.edu"* ]] || fail "DOMAIN must be the real production domain"
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || fail "DOMAIN contains unsupported characters"
[ -f "$HTTPS_TEMPLATE" ] || fail "HTTPS template not found: $HTTPS_TEMPLATE"
command -v nginx >/dev/null || fail "nginx command not found"
command -v certbot >/dev/null || fail "certbot command not found"

mkdir -p "$WEBROOT" "$SITES_AVAILABLE" "$SITES_ENABLED"

cat > "$HTTP_CONFIG" <<EOF
upstream fdsmarticles_frontend {
    server 127.0.0.1:${APP_PORT};
    keepalive 64;
}

server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
        proxy_set_header Connection "";
        proxy_connect_timeout 10s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
        proxy_pass http://fdsmarticles_frontend;
    }
}
EOF

ln -sfn "$HTTP_CONFIG" "$SITES_ENABLED/${NGINX_SITE_NAME}.http.conf"
nginx -t
systemctl reload nginx

CERTBOT_ARGS=(certonly --webroot -w "$WEBROOT" -d "$DOMAIN" --non-interactive --agree-tos)
if [ -n "$EMAIL" ]; then
  CERTBOT_ARGS+=(--email "$EMAIL")
else
  CERTBOT_ARGS+=(--register-unsafely-without-email)
fi
certbot "${CERTBOT_ARGS[@]}"

sed \
  -e "s/knowledge.example.edu/${DOMAIN}/g" \
  -e "s/server 127.0.0.1:8080;/server 127.0.0.1:${APP_PORT};/g" \
  "$HTTPS_TEMPLATE" > "$HTTPS_CONFIG"

ln -sfn "$HTTPS_CONFIG" "$SITES_ENABLED/${NGINX_SITE_NAME}.conf"
rm -f "$SITES_ENABLED/${NGINX_SITE_NAME}.http.conf"

mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/${NGINX_SITE_NAME}-nginx-reload.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
nginx -t
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/${NGINX_SITE_NAME}-nginx-reload.sh

systemctl enable --now certbot.timer >/dev/null 2>&1 || true
nginx -t
systemctl reload nginx

echo "[bootstrap_https] ok: https://${DOMAIN} -> 127.0.0.1:${APP_PORT}"
