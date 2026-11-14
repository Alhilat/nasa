FROM node:22-alpine AS build
WORKDIR /workspace/frontend
RUN npm install --global pnpm@11.25.0
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_MAP_STYLE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL VITE_MAP_STYLE_URL=$VITE_MAP_STYLE_URL
RUN pnpm build

FROM nginx:1.28-alpine
RUN apk add --no-cache ca-certificates
COPY infrastructure/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
