# syntax=docker/dockerfile:1.7

FROM node:20-bookworm-slim AS builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_BASE_URL=/api
ARG VITE_ENABLE_DEBUG_AUTH=0

RUN VITE_API_BASE_URL="${VITE_API_BASE_URL}" \
    VITE_ENABLE_DEBUG_AUTH="${VITE_ENABLE_DEBUG_AUTH}" \
    npm run build

FROM nginx:1.27-alpine AS runtime

COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
