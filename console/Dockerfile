# 观势台。多阶段构建：先打静态包，再由本容器 nginx 托管。
# /api 与 /auth 原样转到 market-api，路径与原先系统 nginx 一致。
FROM node:22-bookworm-slim AS build

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.4.1 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY packages ./packages
COPY . .

RUN pnpm install --frozen-lockfile --ignore-scripts
RUN pnpm build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
