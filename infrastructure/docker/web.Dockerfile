FROM node:22-alpine
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
WORKDIR /app
COPY packages ./packages
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
WORKDIR /app/apps/web
RUN --mount=type=cache,target=/root/.npm npm ci --include=optional --ignore-scripts --no-audit --no-fund --prefer-offline --fetch-timeout=30000 --fetch-retries=1 \
    && test -x node_modules/@esbuild/linux-x64/bin/esbuild \
    && sha256sum package-lock.json | cut -d ' ' -f 1 > node_modules/.orin-package-lock-hash
COPY apps/web ./
RUN chmod +x ./docker-entrypoint.sh \
    && cp ./docker-entrypoint.sh /usr/local/bin/orin-web-entrypoint
EXPOSE 5173
ENTRYPOINT ["/usr/local/bin/orin-web-entrypoint"]
