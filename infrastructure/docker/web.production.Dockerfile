FROM node:22-alpine AS build
WORKDIR /app
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY packages ./packages
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
WORKDIR /app/apps/web
RUN npm ci --include=optional
COPY apps/web ./
ENV VITE_API_BASE_URL="" VITE_FOCUS_ENABLED=true
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 8080
